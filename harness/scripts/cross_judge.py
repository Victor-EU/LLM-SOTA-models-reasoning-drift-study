"""
Cross-vendor judge ablation (v3 follow-up).

Re-judge Tier-3 records from the v3 *-temporal arms with non-Anthropic judges
(GPT-5.5 max, Gemini 3.1 Pro HIGH). Detects within-family judge bias: if Opus
scores its own outputs (or sibling Anthropic Sonnet) systematically higher
than the out-of-family judges do, that's evidence of self-favoritism in the
primary instrument.

Instrument equivalence: uses the EXACT SAME `JUDGE_ABSOLUTE_SYSTEM_PROMPT`
bytes (imported from src.prompts) plus the same target-materials block
construction. Only the vendor changes. The user-message format is also
byte-identical to what `judge_absolute` sends to Anthropic.

Output: per-arm sidecar JSONL at `data/cross_judged/<filter>.jsonl`.
Each record keys back to (run_id, q_id) so analysis can join against the
existing graded JSONL and compute pairwise ICC across (Opus, GPT-5.5, Gemini).

Usage:
    python -m scripts.cross_judge \\
        --arms gpt-5-5-temporal,opus-4-7-temporal,sonnet-4-6-temporal,gemini-3-1-pro-temporal,deepseek-v4-pro-temporal \\
        --judges gpt-5.5,gemini-3.1-pro \\
        # (deepseek-v4-pro available as judge but excluded by default —
        #  analyst-side Tier-1 reliability was 75% vs 100% for other vendors,
        #  and as analyst it produced the most severe drift; calibration as
        #  judge on rubric scoring is unvalidated.)
        --filter 95pct_tier3      # or 'all_tier3'

Cost estimate at default scope (5 arms × 21 reps × 3 Tier-3 q_ids × 2 judges
= 630 calls): ~$220-440 depending on output verbosity.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))

from src.config import load_arm_config  # noqa: E402
from src.materials import load_materials, TargetBundle  # noqa: E402
from src.prompts import JUDGE_ABSOLUTE_SYSTEM_PROMPT  # noqa: E402

log = logging.getLogger("cross_judge")


# ---- prompt assembly (byte-identical to judge_absolute) -----------------

def build_target_materials_text(bundle: TargetBundle) -> str:
    """Same target-materials text block judge_absolute injects as a cacheable
    Anthropic system block. Replicated verbatim so out-of-family judges see
    the same context bytes."""
    return (
        f"<<< TARGET MATERIALS: {bundle.company_name} >>>\n\n"
        f"<<< 10-K FY{bundle.report.fiscal_year} >>>\n"
        f"{bundle.report.text}\n"
        f"<<< END 10-K >>>\n\n"
        f"<<< EARNINGS CALL: {bundle.earnings_call.quarter} FY{bundle.earnings_call.fiscal_year} "
        f"— {bundle.earnings_call.call_date} >>>\n"
        f"{bundle.earnings_call.text}\n"
        f"<<< END EARNINGS CALL >>>\n\n"
        f"<<< END TARGET MATERIALS >>>"
    )


def format_anchors(anchors_raw: list[dict[str, Any]] | None) -> str:
    """Mirror src.judge._format_anchors output bytes."""
    if not anchors_raw:
        return "(no anchors provided)"
    lines: list[str] = []
    for a in anchors_raw:
        lines.append(f"- [{a['anchor_id']}] ({a['source']}, {a['citation_span']})")
        lines.append(f"    Summary: {a['summary']}")
        sigs = a.get("engagement_signals") or []
        if sigs:
            lines.append("    Engagement signals (>=1 must surface to count as engaged):")
            for sig in sigs:
                lines.append(f"      * {sig}")
        ne = a.get("not_engagement")
        if ne:
            lines.append(f"    NOT engagement: {ne}")
    return "\n".join(lines)


def build_user_text(
    *, q_id: str, question_prompt: str, anchors_text: str, candidate_response: str,
) -> str:
    """Byte-identical to the user message sent in judge_absolute."""
    return (
        f"Q_ID: {q_id}\n\n"
        f"QUESTION:\n{question_prompt}\n\n"
        f"EVIDENTIARY_ANCHORS (disclosures that exist in the target materials; "
        f"NOT conclusions the analyst must reach):\n"
        f"{anchors_text}\n\n"
        f"CANDIDATE_RESPONSE:\n{candidate_response}\n\n"
        f"Think carefully, verify every substantive claim against the cached "
        f"target materials above, then return the JSON object. JSON only."
    )


# ---- vendor-specific judge clients --------------------------------------

async def call_openai_judge(
    *, system_text: str, user_text: str, model: str = "gpt-5.5-2026-04-23",
    reasoning_effort: str = "xhigh", max_tokens: int = 16384, timeout_s: int = 900,
) -> tuple[str, dict[str, Any]]:
    """Call OpenAI Responses API as a judge. Returns (text, usage_meta)."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    t0 = time.monotonic()
    try:
        stream = await client.responses.create(
            model=model,
            instructions=system_text,
            input=user_text,
            reasoning={"effort": reasoning_effort, "summary": "auto"},
            max_output_tokens=max_tokens,
            include=["reasoning.encrypted_content"],
            stream=True,
        )
        final = None
        async for event in stream:
            if getattr(event, "type", None) == "response.completed":
                final = getattr(event, "response", None)
        if final is None:
            raise RuntimeError("OpenAI Responses stream completed without a response.completed event")
        # Extract text from output
        text_parts: list[str] = []
        for item in (getattr(final, "output", None) or []):
            if getattr(item, "type", None) == "message":
                for c in (getattr(item, "content", None) or []):
                    if getattr(c, "type", None) == "output_text":
                        text_parts.append(getattr(c, "text", "") or "")
        text = "".join(text_parts)
        usage = getattr(final, "usage", None)
        meta = {
            "vendor": "openai",
            "model": getattr(final, "model", model),
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0) if usage else 0,
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0) if usage else 0,
            "reasoning_tokens": int(
                getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
            ) if usage else 0,
            "latency_seconds": time.monotonic() - t0,
            "system_fingerprint": getattr(final, "system_fingerprint", None),
        }
        return text, meta
    finally:
        try:
            await client.close()
        except Exception:
            pass


# Module-level Gemini state. We create a single explicit cached_content for
# the system_text (~95K tokens of judge prompt + target materials) and reuse
# the handle across all calls in a run. Without this, every call pays full
# input rate (~$4/M for the >200K tier) on the same 95K bytes — for 1.4K
# calls that's ~$520. With caching, cache reads are ~$0.30/M ≈ $39 total.
#
# Lifecycle: lock-guarded create + on-403 invalidate-and-recreate. The naïve
# implementation (single check `if _gemini_cache_name is None`) had two bugs
# observed at 22:05 launch: (1) without a Lock, concurrent tasks all entered
# the create branch and we paid for 6 caches; (2) without 403 handling, the
# cache TTL silently expired mid-run and every subsequent Gemini call
# returned PERMISSION_DENIED. TTL bumped to 7200s for safety; on 403 the
# call is retried once with a freshly-created cache.
_gemini_client: Any = None
_gemini_cache_name: str | None = None
_gemini_cache_lock: asyncio.Lock | None = None


def _gemini_lock() -> asyncio.Lock:
    global _gemini_cache_lock
    if _gemini_cache_lock is None:
        _gemini_cache_lock = asyncio.Lock()
    return _gemini_cache_lock


async def _ensure_gemini_cache(model: str, system_text: str) -> tuple[Any, str]:
    """Return (client, cache_name). Creates the cache on first call (lock-guarded)."""
    global _gemini_client, _gemini_cache_name
    async with _gemini_lock():
        if _gemini_client is None:
            from google import genai
            _gemini_client = genai.Client()
        if _gemini_cache_name is None:
            from google.genai import types as gtypes
            full_model = model if model.startswith("models/") else f"models/{model}"
            cache = await _gemini_client.aio.caches.create(
                model=full_model,
                config=gtypes.CreateCachedContentConfig(
                    system_instruction=system_text,
                    ttl="7200s",
                ),
            )
            _gemini_cache_name = cache.name
            log.info("created gemini cache: %s (system_text %d chars)",
                     _gemini_cache_name, len(system_text))
        return _gemini_client, _gemini_cache_name


async def _invalidate_gemini_cache(stale_name: str) -> None:
    """Reset the module-level cache name if it matches `stale_name`. Lock-guarded
    so concurrent 403-handlers cooperate (only one recreates)."""
    global _gemini_cache_name
    async with _gemini_lock():
        if _gemini_cache_name == stale_name:
            log.warning("invalidating expired/missing gemini cache: %s", stale_name)
            _gemini_cache_name = None


async def _cleanup_gemini_cache() -> None:
    global _gemini_client, _gemini_cache_name
    if _gemini_client is not None and _gemini_cache_name is not None:
        try:
            await _gemini_client.aio.caches.delete(name=_gemini_cache_name)
            log.info("deleted gemini cache: %s", _gemini_cache_name)
        except Exception as e:  # noqa: BLE001
            log.warning("could not delete gemini cache: %s", e)


async def call_deepseek_judge(
    *, system_text: str, user_text: str, model: str = "deepseek-v4-pro",
    reasoning_effort: str = "max", max_tokens: int = 32768, timeout_s: int = 900,
) -> tuple[str, dict[str, Any]]:
    """Call DeepSeek V4 Pro as a judge via openai SDK against api.deepseek.com.
    Returns (text, usage_meta). DeepSeek auto-caches the prompt prefix so no
    explicit cache lifecycle needed. Adds a 5th judge to the cross-vendor
    ablation; deviation from the April-26 sober-state precedent (which used
    Opus, Sonnet, GPT, Gemini only — DeepSeek was a candidate, not a judge).
    Per user request 2026-05-05 to test DeepSeek self-favoritism on its own
    analyst outputs."""
    from openai import AsyncOpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    t0 = time.monotonic()
    try:
        # DeepSeek-extended chat completion with reasoning_effort in extra_body.
        text_segments: list[str] = []
        reasoning_segments: list[str] = []
        final_usage = None
        final_model = None
        final_fp = None
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            max_tokens=max_tokens,
            temperature=1.0,
            stream=True,
            extra_body={
                "reasoning_effort": reasoning_effort,
                "stream_options": {"include_usage": True},
            },
        )
        async for chunk in stream:
            sf = getattr(chunk, "system_fingerprint", None)
            if sf: final_fp = sf
            mv = getattr(chunk, "model", None)
            if mv: final_model = mv
            usage = getattr(chunk, "usage", None)
            if usage is not None: final_usage = usage
            for choice in (getattr(chunk, "choices", None) or []):
                delta = getattr(choice, "delta", None)
                if delta is None: continue
                txt = getattr(delta, "content", None)
                if txt: text_segments.append(txt)
                rc = getattr(delta, "reasoning_content", None)
                if rc: reasoning_segments.append(rc)
                elif hasattr(delta, "model_extra"):
                    me = delta.model_extra or {}
                    rc2 = me.get("reasoning_content")
                    if rc2: reasoning_segments.append(rc2)
        text = "".join(text_segments)
        meta = {
            "vendor": "deepseek",
            "model": final_model or model,
            "input_tokens": int(getattr(final_usage, "prompt_tokens", 0) or 0) if final_usage else 0,
            "output_tokens": int(getattr(final_usage, "completion_tokens", 0) or 0) if final_usage else 0,
            "cache_read_tokens": int(getattr(final_usage, "prompt_cache_hit_tokens", 0) or 0) if final_usage else 0,
            "reasoning_chars": sum(len(s) for s in reasoning_segments),
            "latency_seconds": time.monotonic() - t0,
            "system_fingerprint": final_fp,
        }
        return text, meta
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def call_gemini_judge(
    *, system_text: str, user_text: str, model: str = "gemini-3-pro-preview",
    thinking_level: str = "HIGH", max_tokens: int = 32768, timeout_s: int = 900,
) -> tuple[str, dict[str, Any]]:
    """Call Gemini API as a judge using explicit cached_content for the system
    text (one-time cache create, reused across all calls). On cache-miss/expiry
    (403 PERMISSION_DENIED), invalidate the cached handle and retry once with a
    fresh cache. Returns (text, usage)."""
    from google.genai import types as gtypes
    for attempt in range(2):
        client, cache_name = await _ensure_gemini_cache(model, system_text)
        try:
            return await _call_gemini_judge_once(
                client=client, cache_name=cache_name, user_text=user_text,
                model=model, thinking_level=thinking_level, max_tokens=max_tokens,
            )
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            is_cache_gone = ("CachedContent not found" in msg
                             or "PERMISSION_DENIED" in msg and "Cached" in msg
                             or "403" in msg and "cache" in msg.lower())
            if is_cache_gone and attempt == 0:
                await _invalidate_gemini_cache(cache_name)
                continue
            raise
    raise RuntimeError("call_gemini_judge: unreachable retry loop")


async def _call_gemini_judge_once(
    *, client: Any, cache_name: str, user_text: str, model: str,
    thinking_level: str, max_tokens: int,
) -> tuple[str, dict[str, Any]]:
    from google.genai import types as gtypes
    t0 = time.monotonic()
    config = gtypes.GenerateContentConfig(
        cached_content=cache_name,
        temperature=1.0,
        max_output_tokens=max_tokens,
        thinking_config=gtypes.ThinkingConfig(
            thinking_level=getattr(gtypes.ThinkingLevel, thinking_level),
            include_thoughts=True,
        ),
    )
    text_segments: list[str] = []
    thought_sig_total = 0
    final_usage = None
    final_model_version = None
    stream = await client.aio.models.generate_content_stream(
        model=model, contents=user_text, config=config,
    )
    async for chunk in stream:
        um = getattr(chunk, "usage_metadata", None)
        if um is not None:
            final_usage = um
        mv = getattr(chunk, "model_version", None)
        if mv:
            final_model_version = mv
        for cand in (getattr(chunk, "candidates", None) or []):
            content = getattr(cand, "content", None)
            if content is None:
                continue
            for part in (getattr(content, "parts", None) or []):
                ptext = getattr(part, "text", "") or ""
                is_thought = bool(getattr(part, "thought", False))
                if is_thought:
                    sig = getattr(part, "thought_signature", None)
                    if sig:
                        try: thought_sig_total += len(sig)
                        except TypeError: pass
                else:
                    if ptext: text_segments.append(ptext)
    text = "".join(text_segments)
    meta = {
        "vendor": "google",
        "model": final_model_version or model,
        "input_tokens": int(getattr(final_usage, "prompt_token_count", 0) or 0) if final_usage else 0,
        "output_tokens": int(getattr(final_usage, "candidates_token_count", 0) or 0) if final_usage else 0,
        "thinking_tokens": int(getattr(final_usage, "thoughts_token_count", 0) or 0) if final_usage else 0,
        "thought_signature_chars": thought_sig_total,
        "latency_seconds": time.monotonic() - t0,
    }
    return text, meta


# ---- judge JSON parsing (mirror src.judge) ------------------------------

def _parse_judgement_obj(text: str) -> dict[str, Any]:
    """Extract the JSON object the judge should have returned. Tolerant to
    fenced markdown and surrounding prose, mirrors src.judge._parse_judgement_obj."""
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    try:
        v = json.loads(s)
        if isinstance(v, dict): return v
    except json.JSONDecodeError:
        pass
    # find first balanced {...}
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        try:
            v = json.loads(m.group(0))
            return v if isinstance(v, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _int(v: Any, *, default: int | None, lo: int | None = None, hi: int | None = None) -> int | None:
    if v is None: return default
    try:
        i = int(v)
    except (ValueError, TypeError):
        return default
    if lo is not None and i < lo: i = lo
    if hi is not None and i > hi: i = hi
    return i


def parse_to_absolute_dict(text: str, q_id: str) -> dict[str, Any]:
    """Mirror src.judge.judge_absolute's parsing — returns a dict shaped like
    AbsoluteJudgement.asdict()."""
    parsed = _parse_judgement_obj(text)
    is_q8 = q_id == "MSFT-S-03"
    return {
        "groundedness": _int(parsed.get("groundedness"), default=3, lo=1, hi=5),
        "evidentiary_breadth": _int(parsed.get("evidentiary_breadth"), default=3, lo=1, hi=5),
        "scope_adherence": _int(parsed.get("scope_adherence"), default=3, lo=1, hi=5),
        "clarity": _int(parsed.get("clarity"), default=3, lo=1, hi=5),
        "citation_accuracy": _int(parsed.get("citation_accuracy"), default=3, lo=1, hi=5),
        "unsupported_claims": _int(parsed.get("unsupported_claims"), default=0, lo=0, hi=999),
        "cross_contamination": _int(parsed.get("cross_contamination"), default=0, lo=0, hi=999),
        "reasoning_quality": _int(parsed.get("reasoning_quality"), default=5, lo=0, hi=10),
        "units_decomposed": (_int(parsed.get("units_decomposed"), default=None, lo=0, hi=20) if is_q8 else None),
        "frameworks_applied": (_int(parsed.get("frameworks_applied"), default=None, lo=0, hi=4) if is_q8 else None),
        "synthesis_consistent": (bool(parsed.get("synthesis_consistent")) if is_q8 and "synthesis_consistent" in parsed else None),
        "brief_justification": str(parsed.get("brief_justification", "")),
        "temporal_contamination": _int(parsed.get("temporal_contamination"), default=0, lo=0, hi=999),
        "raw_response_chars": len(text),
    }


# ---- main orchestration -------------------------------------------------

@dataclass
class JudgeJob:
    arm: str
    run_id: str
    q_id: str
    cell_id: str
    rep_idx: int
    fill_pct: float
    position: str | None
    candidate_response: str


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", required=True,
                    help="Comma-separated arm names (e.g. gpt-5-5-temporal,opus-4-7-temporal,...)")
    ap.add_argument("--judges", default="gpt-5.5,gemini-3.1-pro",
                    help="Comma-separated judges (gpt-5.5, gemini-3.1-pro; deepseek-v4-pro available but not default — analyst-side reliability concerns)")
    ap.add_argument("--filter", default="95pct_tier3",
                    choices=["95pct_tier3", "all_tier3"],
                    help="Which records to re-judge")
    ap.add_argument("--max-concurrent", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_dotenv()
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-5s %(message)s")

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    judges = [j.strip() for j in args.judges.split(",") if j.strip()]
    log.info("arms: %s", arms)
    log.info("judges: %s", judges)
    log.info("filter: %s", args.filter)

    # Load materials once (target bundle text only depends on materials_lock).
    cfg0 = load_arm_config(arms[0])
    materials = load_materials(cfg0.paths.materials_dir, cfg0.paths.materials_lock)
    bundle = materials.target_bundles["MSFT"]
    target_text = build_target_materials_text(bundle)

    # Load questions + ground truth from materials_dir (not via Materials class).
    materials_dir = Path(cfg0.paths.materials_dir)
    questions = {q["q_id"]: q for q in json.loads((materials_dir / "questions" / "MSFT.json").read_text())}
    gt_raw = {g["q_id"]: g for g in json.loads((materials_dir / "ground_truth" / "MSFT.json").read_text())}

    # System text shared across all judge calls (instrument equivalence).
    system_text = JUDGE_ABSOLUTE_SYSTEM_PROMPT + "\n\n" + target_text
    log.info("judge prompt + materials bytes: %d chars  sha256=%s",
             len(system_text), hashlib.sha256(system_text.encode()).hexdigest()[:16])

    # Build job list across all arms.
    jobs: list[JudgeJob] = []
    for arm in arms:
        cfg = load_arm_config(arm)
        graded_dir = Path(cfg.paths.data_dir) / "graded"
        ext_dir = Path(cfg.paths.data_dir) / "extracted"
        # Index extracted records by (run_id, q_id) for candidate_response lookup.
        ext_idx: dict[tuple[str, str], dict[str, Any]] = {}
        for f in ext_dir.glob("*.jsonl"):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip(): continue
                r = json.loads(line)
                ext_idx[(r["run_id"], r["q_id"])] = r
        for f in sorted(graded_dir.glob("*.jsonl")):
            if f.name.endswith(".bak") or "prescanfix" in f.name: continue
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip(): continue
                rec = json.loads(line)
                if rec.get("tier") != 3: continue
                if args.filter == "95pct_tier3" and rec["fill_pct"] != 0.95: continue
                er = ext_idx.get((rec["run_id"], rec["q_id"]))
                if er is None or not er.get("answer_raw"):
                    continue
                jobs.append(JudgeJob(
                    arm=arm,
                    run_id=rec["run_id"],
                    q_id=rec["q_id"],
                    cell_id=rec["cell_id"],
                    rep_idx=rec["rep_idx"],
                    fill_pct=rec["fill_pct"],
                    position=rec.get("position"),
                    candidate_response=er["answer_raw"],
                ))
    log.info("jobs to run: %d records × %d judges = %d total calls",
             len(jobs), len(judges), len(jobs)*len(judges))

    if args.dry_run:
        for j in jobs[:5]:
            log.info("sample job: arm=%s run=%s q=%s cand_len=%d",
                     j.arm, j.run_id[-12:], j.q_id, len(j.candidate_response))
        log.info("DRY RUN — exiting before any API calls.")
        return 0

    # Output sidecar dirs per arm.
    out_paths: dict[str, Path] = {}
    for arm in arms:
        cfg = load_arm_config(arm)
        out_dir = Path(cfg.paths.data_dir) / "cross_judged"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_paths[arm] = out_dir / f"{args.filter}.jsonl"

    # Concurrency control.
    sem = asyncio.Semaphore(args.max_concurrent)
    results: dict[str, list[dict[str, Any]]] = {arm: [] for arm in arms}
    n_done = 0
    n_total = len(jobs) * len(judges)
    start = time.monotonic()

    async def one_call(job: JudgeJob, judge_name: str) -> None:
        nonlocal n_done
        async with sem:
            q = questions[job.q_id]
            gt = gt_raw[job.q_id]
            anchors = format_anchors(gt.get("evidentiary_anchors"))
            user_text = build_user_text(
                q_id=job.q_id, question_prompt=q["prompt"],
                anchors_text=anchors, candidate_response=job.candidate_response,
            )
            try:
                if judge_name == "gpt-5.5":
                    text, meta = await call_openai_judge(
                        system_text=system_text, user_text=user_text)
                elif judge_name == "gemini-3.1-pro":
                    text, meta = await call_gemini_judge(
                        system_text=system_text, user_text=user_text)
                elif judge_name == "deepseek-v4-pro":
                    text, meta = await call_deepseek_judge(
                        system_text=system_text, user_text=user_text)
                else:
                    raise ValueError(f"unknown judge {judge_name}")
                parsed = parse_to_absolute_dict(text, job.q_id)
            except Exception as e:  # noqa: BLE001
                log.warning("call failed arm=%s run=%s q=%s judge=%s: %s",
                            job.arm, job.run_id[-12:], job.q_id, judge_name, e)
                parsed = {"_error": repr(e)}
                meta = {"vendor": judge_name, "_error": True}
            n_done += 1
            if n_done % 25 == 0 or n_done == n_total:
                rate = n_done / (time.monotonic() - start)
                eta = (n_total - n_done) / rate if rate > 0 else 0
                log.info("progress %d/%d (%.0f%%) | rate %.2f/s | eta %.0fs",
                         n_done, n_total, 100*n_done/n_total, rate, eta)
            results[job.arm].append({
                "_ts": time.time(),
                "judge": judge_name,
                "run_id": job.run_id,
                "q_id": job.q_id,
                "cell_id": job.cell_id,
                "rep_idx": job.rep_idx,
                "fill_pct": job.fill_pct,
                "position": job.position,
                "absolute": parsed,
                "meta": meta,
            })

    try:
        await asyncio.gather(*(one_call(j, jn) for j in jobs for jn in judges))
    finally:
        if "gemini-3.1-pro" in judges:
            await _cleanup_gemini_cache()

    # Persist per-arm sidecar JSONL.
    for arm, out_path in out_paths.items():
        rows = sorted(results[arm], key=lambda r: (r["judge"], r["run_id"], r["q_id"]))
        with out_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        log.info("wrote %d records → %s", len(rows), out_path)

    log.info("total wall: %.1fs", time.monotonic() - start)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
