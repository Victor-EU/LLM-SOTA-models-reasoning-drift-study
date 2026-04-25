"""
Judge stage — Tier 3 (synthesis) scoring.

Rubric v2.1 design (DESIGN §8.3, RUBRIC.md §Aggregation):

- Primary judge: Opus 4.7 with adaptive thinking at effort="max". Single pass
  per response. With max-effort thinking, run-to-run variance collapses enough
  that single-pass replaces the earlier triple-pass median (RUBRIC.md v2.1).
- Secondary judge: Sonnet 4.6 on a 20% subsample for cross-model inter-rater
  reliability (ICC). Not a correctness check — a rubric-application check.
- Pairwise vs baseline: 25% subsample, Opus 4.7 effort=max, same-model,
  different task form. Catches cases where absolute Likerts flatten but
  preference can still rank.

Judge context design:
- TARGET MATERIALS (10-K + earnings call, ~94K tokens) are passed as a
  cache-breakpointed system block. The orchestrator schedules judge calls in
  per-cell sessions to amortize the cache write across many reads.
- Anchors (with engagement_signals) are inlined per call as the breadth guide;
  the full target materials remain the ground truth for groundedness.

Selection of the dual-judge and pairwise subsamples is deterministic from
run_id + q_id so runs are reproducible.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from .api import CallResult, call_messages
from .autograder import grade_record
from .config import ExperimentConfig, AuxModelConfig
from .cost import CostTracker
from .manifest import Manifest, Stage
from .materials import GroundTruth, Materials, TargetBundle
from .persistence import WriterCache
from .prompts import JUDGE_ABSOLUTE_SYSTEM_PROMPT, JUDGE_PAIRWISE_SYSTEM_PROMPT

log = logging.getLogger(__name__)


# ---- sampling flags (deterministic) --------------------------------------

def should_dual_judge(run_id: str, q_id: str, rate: float = 0.20) -> bool:
    """20% of (run, question) pairs get a cross-model secondary judge (Sonnet 4.6)."""
    return _hash_unit(f"{run_id}|{q_id}|dual") < rate


def should_pairwise(run_id: str, q_id: str, rate: float = 0.25) -> bool:
    """25% subsample uses pairwise-vs-baseline instead of absolute."""
    return _hash_unit(f"{run_id}|{q_id}|pair") < rate


def _hash_unit(s: str) -> float:
    digest = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


# ---- target-materials block (cacheable) ----------------------------------

def build_target_materials_system_blocks(
    bundle: TargetBundle,
) -> list[dict[str, Any]]:
    """
    Build the judge's system content: [instructions, target materials].

    Both blocks carry cache_control so a per-cell session writes once and
    reads on every subsequent judge call (5-min TTL; orchestrator schedules
    calls within that window).
    """
    target_block = (
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
    return [
        {
            "type": "text",
            "text": JUDGE_ABSOLUTE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": target_block,
            "cache_control": {"type": "ephemeral"},
        },
    ]


def build_pairwise_system_blocks(bundle: TargetBundle) -> list[dict[str, Any]]:
    """Same layout, but with the pairwise system prompt as the first block."""
    blocks = build_target_materials_system_blocks(bundle)
    blocks[0]["text"] = JUDGE_PAIRWISE_SYSTEM_PROMPT
    return blocks


def _format_anchors(gt: GroundTruth) -> str:
    """Render anchors with engagement_signals for judge-prompt consumption."""
    anchors = gt.evidentiary_anchors or ()
    if not anchors:
        return "(no anchors provided)"
    lines: list[str] = []
    for a in anchors:
        lines.append(f"- [{a.anchor_id}] ({a.source}, {a.citation_span})")
        lines.append(f"    Summary: {a.summary}")
        if a.engagement_signals:
            lines.append("    Engagement signals (>=1 must surface to count as engaged):")
            for sig in a.engagement_signals:
                lines.append(f"      * {sig}")
        if a.not_engagement:
            lines.append(f"    NOT engagement: {a.not_engagement}")
    return "\n".join(lines)


# ---- absolute judging ----------------------------------------------------

@dataclass(frozen=True)
class AbsoluteJudgement:
    groundedness: int
    evidentiary_breadth: int
    scope_adherence: int
    clarity: int
    citation_accuracy: int
    unsupported_claims: int
    cross_contamination: int
    reasoning_quality: int               # 0-10 holistic (v2.1)
    # Q8-only structural diagnostics. None for Q6/Q7.
    units_decomposed: int | None
    frameworks_applied: int | None
    synthesis_consistent: bool | None
    brief_justification: str


async def judge_absolute(
    *,
    client: AsyncAnthropic,
    model_cfg: AuxModelConfig,
    question_prompt: str,
    q_id: str,
    rubric: GroundTruth,
    candidate_response: str,
    target_bundle: TargetBundle,
    cfg: ExperimentConfig,
) -> tuple[AbsoluteJudgement, CallResult]:
    """
    Score a single candidate response against the rubric.

    `target_bundle` is injected into the system context as a cacheable block;
    repeated calls within a 5-min window read from cache. Returns the parsed
    judgement plus the raw CallResult for cost accounting.
    """
    system_blocks = build_target_materials_system_blocks(target_bundle)
    user_text = (
        f"Q_ID: {q_id}\n\n"
        f"QUESTION:\n{question_prompt}\n\n"
        f"EVIDENTIARY_ANCHORS (disclosures that exist in the target materials; "
        f"NOT conclusions the analyst must reach):\n"
        f"{_format_anchors(rubric)}\n\n"
        f"CANDIDATE_RESPONSE:\n{candidate_response}\n\n"
        f"Think carefully, verify every substantive claim against the cached "
        f"target materials above, then return the JSON object. JSON only."
    )
    result = await call_messages(
        client=client,
        model=model_cfg.snapshot,
        system=system_blocks,
        messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
        max_tokens=model_cfg.max_output_tokens,
        temperature=model_cfg.temperature,
        thinking_effort=model_cfg.thinking_effort,
        extra_headers=None,
        retry=cfg.execution.retry,
        per_call_timeout_seconds=900,
    )
    parsed = _parse_judgement_obj(result.text)
    is_q8 = q_id == "MSFT-S-03"
    judgement = AbsoluteJudgement(
        groundedness=_int(parsed.get("groundedness"), default=3, lo=1, hi=5),
        evidentiary_breadth=_int(parsed.get("evidentiary_breadth"), default=3, lo=1, hi=5),
        scope_adherence=_int(parsed.get("scope_adherence"), default=3, lo=1, hi=5),
        clarity=_int(parsed.get("clarity"), default=3, lo=1, hi=5),
        citation_accuracy=_int(parsed.get("citation_accuracy"), default=3, lo=1, hi=5),
        unsupported_claims=_int(parsed.get("unsupported_claims"), default=0, lo=0, hi=999),
        cross_contamination=_int(parsed.get("cross_contamination"), default=0, lo=0, hi=999),
        reasoning_quality=_int(parsed.get("reasoning_quality"), default=5, lo=0, hi=10),
        units_decomposed=_int(parsed.get("units_decomposed"), default=None, lo=0, hi=20) if is_q8 else None,
        frameworks_applied=_int(parsed.get("frameworks_applied"), default=None, lo=0, hi=4) if is_q8 else None,
        synthesis_consistent=_bool(parsed.get("synthesis_consistent")) if is_q8 else None,
        brief_justification=str(parsed.get("brief_justification", "")),
    )
    return judgement, result


# ---- pairwise judging ----------------------------------------------------

@dataclass(frozen=True)
class PairwiseJudgement:
    verdict: str                                  # "A" | "B" | "tie"
    dimension_preference: dict[str, str]
    reasoning_quality_delta: int                  # -10..10 (v2.1)
    brief_justification: str
    a_is_baseline: bool                           # track which side was baseline


async def judge_pairwise(
    *,
    client: AsyncAnthropic,
    model_cfg: AuxModelConfig,
    question_prompt: str,
    q_id: str,
    rubric: GroundTruth,
    baseline_response: str,
    candidate_response: str,
    a_is_baseline: bool,
    target_bundle: TargetBundle,
    cfg: ExperimentConfig,
) -> tuple[PairwiseJudgement, CallResult]:
    response_a = baseline_response if a_is_baseline else candidate_response
    response_b = candidate_response if a_is_baseline else baseline_response
    system_blocks = build_pairwise_system_blocks(target_bundle)
    user_text = (
        f"Q_ID: {q_id}\n\n"
        f"QUESTION:\n{question_prompt}\n\n"
        f"EVIDENTIARY_ANCHORS:\n{_format_anchors(rubric)}\n\n"
        f"RESPONSE_A:\n{response_a}\n\n"
        f"RESPONSE_B:\n{response_b}\n\n"
        f"Think carefully, verify substantive claims in each response against "
        f"the cached target materials above, then return the JSON object."
    )
    result = await call_messages(
        client=client,
        model=model_cfg.snapshot,
        system=system_blocks,
        messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
        max_tokens=model_cfg.max_output_tokens,
        temperature=model_cfg.temperature,
        thinking_effort=model_cfg.thinking_effort,
        extra_headers=None,
        retry=cfg.execution.retry,
        per_call_timeout_seconds=900,
    )
    parsed = _parse_judgement_obj(result.text)
    judgement = PairwiseJudgement(
        verdict=str(parsed.get("verdict", "tie")),
        dimension_preference=dict(parsed.get("dimension_preference", {})),
        reasoning_quality_delta=_int(parsed.get("reasoning_quality_delta"), default=0, lo=-10, hi=10),
        brief_justification=str(parsed.get("brief_justification", "")),
        a_is_baseline=a_is_baseline,
    )
    return judgement, result


# ---- helpers -------------------------------------------------------------

def _parse_judgement_obj(text: str) -> dict[str, Any]:
    """Best-effort parse of judge JSON output; tolerates stray markdown fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        log.warning("judge output unparseable; returning defaults")
        return {}


def _int(
    v: Any, *, default: int | None, lo: int = -10**9, hi: int = 10**9
) -> int | None:
    if v is None:
        return default
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1")
    return bool(v)


# ---- orchestrator stub ---------------------------------------------------

async def run_grade_stage(
    *,
    client: AsyncAnthropic,
    materials: Materials,
    cfg: ExperimentConfig,
    manifest: Manifest,
    cost_tracker: CostTracker,
    writers: WriterCache,
) -> None:
    """
    Grade every extracted (run, q_id) record:
      - Tier 1/2 → local autograder (numeric tolerance + distractor check).
      - Tier 3 → Opus 4.7 absolute judge (cached target materials).
      - 25% subsample (non-baseline reps only) → Opus pairwise vs baseline.
      - 20% subsample → Sonnet 4.6 secondary absolute judge for ICC.

    Per-cell writes data/graded/{cell_id}.jsonl. Per-run grade-stage row in
    the manifest is marked completed once all 8 questions for that run are
    persisted, so resumption is run-granular.
    """
    # 1. Load extracted records, grouped by run_id.
    extracted_dir = Path(cfg.paths.extracted_dir)
    extracted_by_run: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for f in sorted(extracted_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            qid = rec.get("q_id")
            rid = rec.get("run_id")
            if qid and rid:
                extracted_by_run[rid][qid] = rec

    if not extracted_by_run:
        log.warning("no extracted records found — extract stage must run first")
        return

    # 2. Index baseline responses (rep_idx -> q_id -> answer text) for pairwise.
    baseline_responses: dict[int, dict[str, str]] = defaultdict(dict)
    for rid, q_recs in extracted_by_run.items():
        first = next(iter(q_recs.values()))
        if first.get("fill_pct") == 0.0:
            for qid, rec in q_recs.items():
                baseline_responses[first["rep_idx"]][qid] = (
                    rec.get("answer_raw") or rec.get("answer_normalized") or ""
                )

    # 3. Index analyst questions by q_id for prompts.
    questions_by_id: dict[str, str] = {}
    for qs in materials.questions.values():
        for q in qs:
            questions_by_id[q.q_id] = q.prompt

    # 4. Pre-register grade rows in the manifest.
    for rid, q_recs in extracted_by_run.items():
        first = next(iter(q_recs.values()))
        manifest.ensure_pending(
            run_id=rid,
            cell_id=first["cell_id"],
            rep_idx=first["rep_idx"],
            stage=Stage.GRADE,
        )

    sem = asyncio.Semaphore(cfg.execution.max_concurrent_judge)

    async def grade_one_run(run_id: str, q_recs: dict[str, dict[str, Any]]) -> None:
        if manifest.is_done(run_id, Stage.GRADE):
            return

        first = next(iter(q_recs.values()))
        cell_id: str = first["cell_id"]
        rep_idx: int = first["rep_idx"]
        report_id: str = first["report_id"]
        fill_pct: float = first["fill_pct"]
        position = first.get("position")
        bundle = materials.target_bundles[report_id]
        is_baseline_run = fill_pct == 0.0

        manifest.mark_in_progress(run_id, Stage.GRADE, started_at=time.time())

        per_question_grades: list[dict[str, Any]] = []

        async def grade_q(q_id: str, rec: dict[str, Any]) -> dict[str, Any]:
            gt = materials.ground_truth.get(q_id)
            common = {
                "run_id": run_id,
                "cell_id": cell_id,
                "rep_idx": rep_idx,
                "fill_pct": fill_pct,
                "position": position,
                "q_id": q_id,
                "tier": gt.tier if gt else None,
            }
            if gt is None:
                return {**common, "skipped": "no ground truth"}

            # Tier 1/2: local autograder. No API call.
            if gt.tier in (1, 2):
                ag = grade_record(rec, materials)
                return {**common, "autograde": asdict(ag) if ag else None}

            # Tier 3: judge_absolute. Optionally pairwise + secondary.
            cand_text = rec.get("answer_raw") or rec.get("answer_normalized") or ""
            qprompt = questions_by_id.get(q_id, "")

            out: dict[str, Any] = dict(common)

            async with sem:
                cost_tracker.check_budget()
                try:
                    j_abs, call_abs = await judge_absolute(
                        client=client,
                        model_cfg=cfg.models.judge_primary,
                        question_prompt=qprompt,
                        q_id=q_id,
                        rubric=gt,
                        candidate_response=cand_text,
                        target_bundle=bundle,
                        cfg=cfg,
                    )
                    cost_tracker.record(
                        usage=call_abs.usage,
                        component="judge_primary_abs",
                        model=call_abs.model or cfg.models.judge_primary.snapshot,
                        run_id=run_id,
                        stage=Stage.GRADE,
                    )
                    out["absolute"] = asdict(j_abs)
                    out["absolute_meta"] = {
                        "latency_seconds": call_abs.latency_seconds,
                        "thinking_tokens": call_abs.usage.thinking_tokens,
                    }
                except Exception as e:  # noqa: BLE001
                    log.exception("absolute judge failed for %s/%s: %s", run_id, q_id, e)
                    out["absolute_error"] = repr(e)

            # 25% pairwise subsample (non-baseline only; baseline can't be paired with itself).
            if not is_baseline_run and should_pairwise(run_id, q_id, 0.25):
                base_text = baseline_responses.get(rep_idx, {}).get(q_id)
                if base_text:
                    a_is_baseline = (_hash_unit(f"{run_id}|{q_id}|side") < 0.5)
                    async with sem:
                        cost_tracker.check_budget()
                        try:
                            j_pw, call_pw = await judge_pairwise(
                                client=client,
                                model_cfg=cfg.models.judge_primary,
                                question_prompt=qprompt,
                                q_id=q_id,
                                rubric=gt,
                                baseline_response=base_text,
                                candidate_response=cand_text,
                                a_is_baseline=a_is_baseline,
                                target_bundle=bundle,
                                cfg=cfg,
                            )
                            cost_tracker.record(
                                usage=call_pw.usage,
                                component="judge_primary_pw",
                                model=call_pw.model or cfg.models.judge_primary.snapshot,
                                run_id=run_id,
                                stage=Stage.GRADE,
                            )
                            out["pairwise"] = asdict(j_pw)
                        except Exception as e:  # noqa: BLE001
                            log.exception("pairwise judge failed for %s/%s: %s", run_id, q_id, e)
                            out["pairwise_error"] = repr(e)

            # 20% Sonnet secondary subsample for cross-model ICC.
            if should_dual_judge(run_id, q_id, 0.20):
                async with sem:
                    cost_tracker.check_budget()
                    try:
                        j_sec, call_sec = await judge_absolute(
                            client=client,
                            model_cfg=cfg.models.judge_secondary,
                            question_prompt=qprompt,
                            q_id=q_id,
                            rubric=gt,
                            candidate_response=cand_text,
                            target_bundle=bundle,
                            cfg=cfg,
                        )
                        cost_tracker.record(
                            usage=call_sec.usage,
                            component="judge_secondary",
                            model=call_sec.model or cfg.models.judge_secondary.snapshot,
                            run_id=run_id,
                            stage=Stage.GRADE,
                        )
                        out["secondary"] = asdict(j_sec)
                    except Exception as e:  # noqa: BLE001
                        log.exception("secondary judge failed for %s/%s: %s", run_id, q_id, e)
                        out["secondary_error"] = repr(e)

            return out

        # Schedule all q_id grading concurrently for this run.
        results = await asyncio.gather(
            *(grade_q(qid, rec) for qid, rec in q_recs.items()),
            return_exceptions=False,
        )
        per_question_grades.extend(results)

        graded_writer = writers.for_cell(cfg.paths.graded_dir, cell_id)
        for g in per_question_grades:
            graded_writer.append(g)

        manifest.mark_completed(
            run_id=run_id,
            stage=Stage.GRADE,
            completed_at=time.time(),
            meta={"n_graded": len(per_question_grades)},
        )

    # 5. Run all runs concurrently — the inner `sem` limits in-flight API calls;
    #    the outer asyncio.gather controls run-level fan-out.
    await asyncio.gather(*(grade_one_run(rid, qs) for rid, qs in extracted_by_run.items()))
