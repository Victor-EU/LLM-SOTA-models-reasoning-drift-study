"""
Sober-state head-to-head ranking judge.

Question this answers
---------------------
Setting drift aside: at fill=0.00 (no noise), which model produces the
best Tier-3 synthesis answers? The existing per-arm absolute judge already
scores baseline answers, but at the rubric ceiling its discrimination
collapses (most arms pile near 5/5 on dimensions, 7-9 on RQ). A
head-to-head ranking call — the judge sees all five anonymized answers
side-by-side for the same (question, rep) — forces the discrimination
that absolute scoring compresses away.

Methodology
-----------
- Scope: baseline cell only (`c_MSFT_00_X_X_*`), Tier-3 questions
  {MSFT-S-01, MSFT-S-02, MSFT-S-03}, all 7 reps per arm.
- 21 ranking items total. Each item bundles 5 anonymized answers (one per
  arm), random-permuted into labels A-E. The {label -> arm} mapping is
  logged to `permutations.jsonl` for reproducibility and de-anonymization.
- Same RUBRIC.md dimensions as the existing absolute judge, but the prompt
  asks for a per-candidate dimension scorecard PLUS a total ordering 1..5.
  Borda + win-matrix derive from the ordering; per-dimension means derive
  from the scorecards.
- Two judges (instruments held constant from `pre_registration.lock`):
    * Primary:   Opus 4.7 max-effort.
    * Secondary: Sonnet 4.6 high-effort, run on 100% of items (cheap, gives
      us cross-judge agreement specifically for the sober-state finding).
- Self-preference disclosure: Opus is one of the candidates AND the primary
  judge. The Sonnet cross-check + dual reporting bounds the effect size; if
  Opus and Sonnet rank-agree, self-preference is small.

Outputs
-------
- `cross_arm/sober_state/judge_opus.jsonl`      (one row per item)
- `cross_arm/sober_state/judge_sonnet.jsonl`
- `cross_arm/sober_state/permutations.jsonl`    (the {label -> arm} map per item)
- `cross_arm/sober_state/cost.json`             (cumulative cost log)

Idempotency: re-runs skip items whose (q_id, rep_idx, judge) row already
exists. Permutations are also cached — once an item gets permuted, the same
permutation is reused on retry so the two judges score identical bundles.

Usage:
    python -m scripts.judge_sober_ranking --judges both
    python -m scripts.judge_sober_ranking --judges primary --concurrency 3
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

HARNESS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = HARNESS_ROOT.parent
sys.path.insert(0, str(HARNESS_ROOT))

from src.api import call_messages  # noqa: E402
from src.config import (  # noqa: E402
    AuxModelConfig,
    ExperimentConfig,
    ModelPricing,
    RetryConfig,
    load_arm_config,
)
from src.judge import build_target_materials_system_blocks  # noqa: E402
from src.materials import GroundTruth, Materials, TargetBundle, load_materials  # noqa: E402

log = logging.getLogger("sober")

# ---- methodological constants --------------------------------------------

ARMS = ("opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro")
TIER3_QIDS = ("MSFT-S-01", "MSFT-S-02", "MSFT-S-03")
REPS = 7
BASELINE_CELL_PREFIX = "c_MSFT_00_X_X_"

# Stable seed for the permutation order — keyed only on (q_id, rep_idx) so
# both judges see the SAME shuffled bundle for the same item.
PERMUTATION_SALT = "sober-state-ranking-v1"

# Output area lives under cross_arm/, not arms/<arm>/, because this analysis
# is cross-arm by construction (no arm "owns" it).
OUT_DIR = PROJECT_ROOT / "cross_arm" / "sober_state"


# ---- ranking judge prompt ------------------------------------------------

SOBER_RANKING_SYSTEM_PROMPT = """\
You are an expert financial analyst comparing FIVE analysts' answers to the \
same Tier-3 synthesis question about Microsoft.

You have access, via the cached TARGET MATERIALS block earlier in this \
conversation, to the FULL Microsoft 10-K (FY2025) and earnings-call \
transcript (Q2 FY2026). That block is your SOURCE OF TRUTH for every \
factual check.

You also receive, per call:
- QUESTION: the prompt all five analysts were asked.
- EVIDENTIARY_ANCHORS: specific material disclosures a sound analysis should \
  engage with. Each anchor has an `engagement_signals` list — concrete cues \
  that indicate engagement. Anchors guide BREADTH; the full TARGET MATERIALS \
  block is the ground truth for GROUNDEDNESS.
- RESPONSES A through E: five anonymized analyst outputs. Label assignment is \
  RANDOMIZED — do not assume any A/B/C/D/E corresponds to any particular \
  analyst, model, vendor, or stylistic identity.

GRADING PHILOSOPHY — read carefully:
- You grade PROCESS, not VERDICT. Two analysts reaching opposite conclusions \
  from the same disclosures can both be maximally grounded.
- Penalize: fabricated evidence (not in the target materials), factually wrong \
  claims, missed material disclosures (anchors the response ignored), \
  misattribution of peer data to Microsoft, internal contradictions.
- Mentioning peer companies as competitive context is NOT a scope failure. \
  Citing peer data AS Microsoft data IS a scope failure.
- Do NOT prefer length. A tight response that engages every anchor with \
  precise citations is stronger than a sprawling one that pads with \
  generalities.
- Do NOT prefer a particular writing style or formatting. Markdown headers, \
  bullet points, prose paragraphs — equally acceptable. Score the substance.

You have extended thinking enabled. USE IT. Before emitting the JSON, work \
through each candidate against the materials: for every substantive numeric \
claim, locate it in the target materials; for each anchor, check whether any \
engagement signal is present. Then compare candidates on each dimension and \
produce a total ordering.

SCORING SURFACE — score EACH candidate on EACH dimension

Per RUBRIC.md v2.1 (1-5 anchors):
1. groundedness         — every substantive claim traces to the target materials
2. evidentiary_breadth  — engages anchors via the stated engagement signals
3. scope_adherence      — no misattribution of peer data to MSFT
4. clarity              — internally coherent, well-structured
5. citation_accuracy    — citations resolve to real sections of the target materials

Counts (int >= 0):
- unsupported_claims  — substantive claims without trace in the target materials
- cross_contamination — claims attributing peer data to Microsoft

reasoning_quality (0-10, integer): gestalt rigor score per RUBRIC.md anchors. \
Use the full 0-10 range; do not cluster.

Q8 STRUCTURAL DIAGNOSTICS (ONLY for q_id == "MSFT-S-03"; OMIT the three \
fields for other questions): units_decomposed (int >=0), frameworks_applied \
(0-4), synthesis_consistent (bool). Same definitions as RUBRIC.md.

TOTAL ORDERING — `ranking`

After scoring, produce a STRICT TOTAL ORDER over {A, B, C, D, E} from \
strongest to weakest. Ties are NOT allowed in this field — if two candidates \
are genuinely indistinguishable, break the tie on reasoning_quality, then on \
groundedness, then on evidentiary_breadth, then arbitrarily. Record any \
near-ties in `tie_notes`.

OUTPUT — JSON only, no prose, no markdown fences:

{
  "scores": {
    "A": {
      "groundedness":         <1-5>,
      "evidentiary_breadth":  <1-5>,
      "scope_adherence":      <1-5>,
      "clarity":              <1-5>,
      "citation_accuracy":    <1-5>,
      "unsupported_claims":   <int>,
      "cross_contamination":  <int>,
      "reasoning_quality":    <0-10>,
      "units_decomposed":     <int>    // MSFT-S-03 only
      "frameworks_applied":   <0-4>    // MSFT-S-03 only
      "synthesis_consistent": <bool>   // MSFT-S-03 only
    },
    "B": { ... },
    "C": { ... },
    "D": { ... },
    "E": { ... }
  },
  "ranking": ["X","X","X","X","X"],   // strict total order, best -> worst
  "tie_notes": "<empty string if none; else 'C and D essentially indistinguishable on RQ' style>",
  "rationale": "<3-6 sentences justifying the top pick and the ordering at the margins>"
}
"""


# ---- vendor-pricing snapshot (matches what arm.lock.json captured) ------

# We need pricing only for the two judge models — both Anthropic. Pull from the
# v1 base config so the cost line in the report matches the pricing the arms
# were originally locked under.
def _load_judge_pricing(cfg: ExperimentConfig) -> dict[str, ModelPricing]:
    return {
        "opus_4_7": cfg.cost.pricing["opus_4_7"],
        "sonnet_4_6": cfg.cost.pricing["sonnet_4_6"],
    }


# ---- bundle assembly -----------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    arm: str
    answer_text: str   # the analyst's `reasoning` field for this q_id (the synthesis prose)


@dataclass(frozen=True)
class Bundle:
    q_id: str
    rep_idx: int
    permutation: tuple[str, ...]      # arm names in shuffled order; index i is label A,B,C,...
    candidates: tuple[Candidate, ...] # parallel to permutation


def _label_for(idx: int) -> str:
    return chr(ord("A") + idx)


def _load_extracted(arm: str) -> list[dict[str, Any]]:
    """Load the single baseline extracted JSONL for an arm and return all 56 rows."""
    base_dir = PROJECT_ROOT / "arms" / arm / "data" / "extracted"
    files = sorted(base_dir.glob(f"{BASELINE_CELL_PREFIX}*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no baseline extracted file for arm {arm!r}")
    if len(files) > 1:
        raise RuntimeError(f"multiple baseline files for {arm!r}: {files}")
    rows: list[dict[str, Any]] = []
    with files[0].open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _load_raw(arm: str) -> list[dict[str, Any]]:
    """Load raw rows so we can recover the full per-question prose (extractor stores
    only the normalized scalar for Tier 1/2; for Tier 3 it copies answer_raw)."""
    base_dir = PROJECT_ROOT / "arms" / arm / "data" / "raw"
    files = sorted(base_dir.glob(f"{BASELINE_CELL_PREFIX}*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no baseline raw file for arm {arm!r}")
    rows: list[dict[str, Any]] = []
    with files[0].open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _strip_markdown_fences(text: str) -> str:
    s = text.strip()
    if not s.startswith("```"):
        return s
    # Drop opening fence (and optional language tag), and closing fence.
    s = s.lstrip("`").lstrip()
    if s.lower().startswith("json"):
        s = s[4:].lstrip()
    if s.endswith("```"):
        s = s[: -3].rstrip()
    return s


def _extract_tier3_prose(raw_rows: list[dict[str, Any]], q_id: str, rep_idx: int) -> str:
    """Pull the full Tier-3 synthesis answer for one (q_id, rep_idx). Returns "" if absent.
    Handles plain JSON and ```json ... ``` markdown-fenced output. Some arms (notably
    Sonnet rep=3) have a failed-then-retried-and-succeeded pair of rows for the same
    rep_idx; we want the row with non-empty response_text."""
    matches = [r for r in raw_rows if r.get("rep_idx") == rep_idx]
    text = ""
    for row in matches:
        candidate = row.get("response_text", "") or ""
        if candidate:
            text = candidate
            break
    if not text:
        return ""
    cleaned = _strip_markdown_fences(text)
    try:
        # strict=False tolerates raw control chars in strings — Sonnet sometimes
        # emits embedded newlines inside JSON string values that the strict
        # parser rejects. The content is still well-formed enough to recover.
        obj = json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        return _salvage_qid_block(text, q_id)
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and item.get("q_id") == q_id:
                return _format_tier3_block(item)
    return ""


def _format_tier3_block(item: dict[str, Any]) -> str:
    """Render a Tier-3 answer as the same shape the original analyst emitted, so
    the judge sees exactly what an analyst-side reader would have seen."""
    parts: list[str] = []
    if "answer" in item:
        parts.append(f"ANSWER:\n{item['answer']}")
    if "reasoning" in item:
        parts.append(f"REASONING:\n{item['reasoning']}")
    if "citation" in item:
        parts.append(f"CITATION:\n{item['citation']}")
    if "structured" in item:
        parts.append(f"STRUCTURED:\n{json.dumps(item['structured'], indent=2)}")
    return "\n\n".join(parts) if parts else json.dumps(item, indent=2)


def _salvage_qid_block(text: str, q_id: str) -> str:
    """Last-ditch: locate the `\"q_id\": \"<q_id>\"` substring and return ~3000 chars
    around it. Better than empty for the judge."""
    needle = f'"q_id": "{q_id}"'
    idx = text.find(needle)
    if idx < 0:
        return ""
    start = max(0, idx - 200)
    end = min(len(text), idx + 3000)
    return f"[salvaged from malformed JSON]\n{text[start:end]}"


def _build_permutation(q_id: str, rep_idx: int, arms: tuple[str, ...]) -> tuple[str, ...]:
    """Stable random permutation keyed on (q_id, rep_idx) so both judges
    score the same shuffle for the same item."""
    seed = int.from_bytes(
        hashlib.sha256(f"{PERMUTATION_SALT}|{q_id}|{rep_idx}".encode()).digest()[:8],
        "big",
    )
    rng = random.Random(seed)
    arms_list = list(arms)
    rng.shuffle(arms_list)
    return tuple(arms_list)


def build_all_bundles(
    arms: tuple[str, ...] = ARMS,
    qids: tuple[str, ...] = TIER3_QIDS,
    reps: int = REPS,
) -> list[Bundle]:
    raw_by_arm = {arm: _load_raw(arm) for arm in arms}
    bundles: list[Bundle] = []
    for q_id in qids:
        for rep in range(reps):
            permutation = _build_permutation(q_id, rep, arms)
            cands: list[Candidate] = []
            for arm in permutation:
                prose = _extract_tier3_prose(raw_by_arm[arm], q_id, rep)
                cands.append(Candidate(arm=arm, answer_text=prose or "[empty / unrecoverable]"))
            bundles.append(Bundle(q_id=q_id, rep_idx=rep, permutation=permutation, candidates=tuple(cands)))
    return bundles


# ---- judge call ----------------------------------------------------------

def _format_anchors(gt: GroundTruth) -> str:
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


def _build_user_text(bundle: Bundle, question_prompt: str, gt: GroundTruth) -> str:
    sections = [
        f"Q_ID: {bundle.q_id}",
        f"REP_INDEX: {bundle.rep_idx}",
        "",
        f"QUESTION:\n{question_prompt}",
        "",
        f"EVIDENTIARY_ANCHORS:\n{_format_anchors(gt)}",
        "",
        "FIVE CANDIDATE RESPONSES (label assignment is RANDOM — do not infer identity):",
    ]
    for i, cand in enumerate(bundle.candidates):
        label = _label_for(i)
        sections.append(f"\n=== RESPONSE {label} ===\n{cand.answer_text}")
    sections.append(
        "\nThink carefully, verify every substantive claim against the cached "
        "target materials above, then return the JSON object. JSON only."
    )
    return "\n".join(sections)


# Build a system block with our ranking prompt instead of the absolute one.
def _build_system_blocks_for_ranking(bundle_dummy: Bundle | None, target: TargetBundle) -> list[dict[str, Any]]:
    blocks = build_target_materials_system_blocks(target)
    blocks[0]["text"] = SOBER_RANKING_SYSTEM_PROMPT
    return blocks


# ---- IO + idempotency ----------------------------------------------------

def _judge_path(judge_label: str) -> Path:
    return OUT_DIR / f"judge_{judge_label}.jsonl"


def _permutations_path() -> Path:
    return OUT_DIR / "permutations.jsonl"


def _existing_keys(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    keys: set[tuple[str, int]] = set()
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add((row["q_id"], int(row["rep_idx"])))
    return keys


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parse_judge_obj(text: str) -> dict[str, Any]:
    """Tolerant JSON parse — strip markdown fences if any."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:].strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        log.warning("ranking judge output unparseable; first 200 chars: %s", s[:200])
        return {}


# ---- core run ------------------------------------------------------------

@dataclass
class JudgeSpec:
    label: str            # "opus" | "sonnet"
    model: AuxModelConfig
    pricing_key: str      # "opus_4_7" | "sonnet_4_6"


# The instrument's default max_output_tokens (16K Opus / 8K Sonnet) is sized for
# single-candidate absolute judging. A 5-way ranking with thinking_effort=max/high
# can spend 10-15K tokens on thinking ALONE before emitting any answer JSON
# (5 candidates × 8 dimensions + ordering + rationale ~ 2K). Empirical evidence:
# the first run had Opus 1/21 and Sonnet 4/4 hit the cap with zero text emitted.
# We override here, locally, only for the ranking task — the held-constant judge
# config in base.yaml is untouched and still governs the regular grading pipeline.
SOBER_OPUS_MAX_OUTPUT = 32_000
# Sonnet 4.6 high-effort can run extremely long thinking loops on the hardest
# question (S-03 structural diagnostic). Empirical: 32K cap saw 2/7 reps for
# S-03 burn the entire output on thinking with zero visible text. 64K gives
# enough headroom; Sonnet 4.6 supports 64K output.
SOBER_SONNET_MAX_OUTPUT = 64_000


def _override_max_tokens(model: AuxModelConfig, new_max: int) -> AuxModelConfig:
    return AuxModelConfig(
        snapshot=model.snapshot,
        max_output_tokens=new_max,
        temperature=model.temperature,
        thinking_effort=model.thinking_effort,
    )


async def _run_one(
    *,
    bundle: Bundle,
    judge: JudgeSpec,
    target: TargetBundle,
    question_prompt: str,
    gt: GroundTruth,
    client: AsyncAnthropic,
    cfg: ExperimentConfig,
    pricing: dict[str, ModelPricing],
    cost_log_path: Path,
) -> dict[str, Any]:
    system_blocks = _build_system_blocks_for_ranking(None, target)
    user_text = _build_user_text(bundle, question_prompt, gt)

    t0 = time.monotonic()
    result = await call_messages(
        client=client,
        model=judge.model.snapshot,
        system=system_blocks,
        messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
        max_tokens=judge.model.max_output_tokens,
        temperature=judge.model.temperature,
        thinking_effort=judge.model.thinking_effort,
        extra_headers=None,
        retry=cfg.execution.retry,
        per_call_timeout_seconds=1500,
    )
    elapsed = time.monotonic() - t0

    parsed = _parse_judge_obj(result.text)
    # De-anonymize: produce {arm: scores} and {arm: rank}.
    label_to_arm = {_label_for(i): bundle.permutation[i] for i in range(len(bundle.permutation))}
    arm_to_label = {v: k for k, v in label_to_arm.items()}
    scores_by_arm = {
        arm: parsed.get("scores", {}).get(arm_to_label[arm])
        for arm in bundle.permutation
    }
    ranking_labels = parsed.get("ranking") or []
    ranking_arms = [label_to_arm[lbl] for lbl in ranking_labels if lbl in label_to_arm]

    # Cost accounting.
    pricing_obj = pricing[judge.pricing_key]
    cost_usd = (
        result.usage.uncached_input_tokens * pricing_obj.input / 1_000_000
        + result.usage.cache_read_input_tokens * pricing_obj.cache_read / 1_000_000
        + result.usage.cache_creation_input_tokens * pricing_obj.cache_write / 1_000_000
        + result.usage.output_tokens * pricing_obj.output / 1_000_000
    )
    _log_cost(cost_log_path, judge=judge.label, q_id=bundle.q_id, rep_idx=bundle.rep_idx,
              cost_usd=cost_usd, latency_seconds=elapsed,
              input_tokens=result.usage.input_tokens,
              output_tokens=result.usage.output_tokens,
              cache_read=result.usage.cache_read_input_tokens,
              cache_write=result.usage.cache_creation_input_tokens)

    return {
        "_ts": time.time(),
        "judge": judge.label,
        "judge_model": judge.model.snapshot,
        "judge_thinking_effort": judge.model.thinking_effort,
        "q_id": bundle.q_id,
        "rep_idx": bundle.rep_idx,
        "permutation": list(bundle.permutation),     # arms in label order [A,B,C,D,E]
        "label_to_arm": label_to_arm,
        "ranking_labels": ranking_labels,
        "ranking_arms": ranking_arms,
        "scores_by_arm": scores_by_arm,
        "scores_raw": parsed.get("scores", {}),
        "tie_notes": parsed.get("tie_notes", ""),
        "rationale": parsed.get("rationale", ""),
        "raw_text": result.text,
        "latency_seconds": elapsed,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "thinking_tokens": result.usage.thinking_tokens,
            "cache_read_input_tokens": result.usage.cache_read_input_tokens,
            "cache_creation_input_tokens": result.usage.cache_creation_input_tokens,
        },
        "cost_usd": round(cost_usd, 4),
    }


def _log_cost(path: Path, **kwargs: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"_ts": time.time(), **kwargs}
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _record_permutation(bundle: Bundle) -> None:
    path = _permutations_path()
    existing = _existing_keys(path)
    if (bundle.q_id, bundle.rep_idx) in existing:
        return
    row = {
        "q_id": bundle.q_id,
        "rep_idx": bundle.rep_idx,
        "permutation": list(bundle.permutation),
        "label_to_arm": {_label_for(i): bundle.permutation[i] for i in range(len(bundle.permutation))},
    }
    _append_jsonl(path, row)


# ---- driver --------------------------------------------------------------

async def _drive(judges: list[JudgeSpec], concurrency: int, cfg: ExperimentConfig) -> None:
    materials = load_materials(
        materials_dir=PROJECT_ROOT / "materials",
        lock_path=PROJECT_ROOT / "materials" / "materials.lock.json",
    )
    target_bundle = materials.target_bundles["MSFT"]
    questions_by_qid = {q.q_id: q for q in materials.questions["MSFT"]}
    gt_by_qid = {q_id: materials.ground_truth[q_id] for q_id in TIER3_QIDS}

    bundles = build_all_bundles()
    log.info("built %d ranking bundles (Tier-3, baseline only)", len(bundles))

    # Persist permutations once.
    for b in bundles:
        _record_permutation(b)

    pricing = _load_judge_pricing(cfg)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
    client = AsyncAnthropic(api_key=api_key)

    cost_log_path = OUT_DIR / "cost.jsonl"

    async def _do(bundle: Bundle, judge: JudgeSpec, sem: asyncio.Semaphore) -> None:
        path = _judge_path(judge.label)
        if (bundle.q_id, bundle.rep_idx) in _existing_keys(path):
            log.info("[skip] %s rep=%d (%s already done)", bundle.q_id, bundle.rep_idx, judge.label)
            return
        async with sem:
            try:
                row = await _run_one(
                    bundle=bundle,
                    judge=judge,
                    target=target_bundle,
                    question_prompt=questions_by_qid[bundle.q_id].prompt,
                    gt=gt_by_qid[bundle.q_id],
                    client=client,
                    cfg=cfg,
                    pricing=pricing,
                    cost_log_path=cost_log_path,
                )
                _append_jsonl(path, row)
                rk = ",".join(row.get("ranking_labels", [])) or "?"
                log.info("[done] %s rep=%d (%s) ranking=%s cost=$%.3f lat=%.1fs",
                         bundle.q_id, bundle.rep_idx, judge.label, rk,
                         row["cost_usd"], row["latency_seconds"])
            except Exception as e:  # noqa: BLE001
                log.exception("[fail] %s rep=%d (%s): %s", bundle.q_id, bundle.rep_idx, judge.label, e)

    sem = asyncio.Semaphore(concurrency)
    tasks = []
    for judge in judges:
        for bundle in bundles:
            tasks.append(_do(bundle, judge, sem))
    await asyncio.gather(*tasks)

    await client.close()


# ---- CLI -----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Sober-state head-to-head ranking judge.")
    parser.add_argument("--judges", choices=["primary", "secondary", "both"], default="both",
                        help="primary=Opus 4.7 max; secondary=Sonnet 4.6 high")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="concurrent judge calls (keep small to amortize 5-min cache)")
    parser.add_argument("--anchor-arm", default="opus-4-7",
                        help="arm whose base.yaml is loaded for instrument config (any v1 arm works)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would run, no API calls")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    load_dotenv(PROJECT_ROOT / "harness" / ".env")

    cfg = load_arm_config(args.anchor_arm)

    judges: list[JudgeSpec] = []
    if args.judges in ("primary", "both"):
        judges.append(JudgeSpec(
            label="opus",
            model=_override_max_tokens(cfg.models.judge_primary, SOBER_OPUS_MAX_OUTPUT),
            pricing_key="opus_4_7",
        ))
    if args.judges in ("secondary", "both"):
        judges.append(JudgeSpec(
            label="sonnet",
            model=_override_max_tokens(cfg.models.judge_secondary, SOBER_SONNET_MAX_OUTPUT),
            pricing_key="sonnet_4_6",
        ))

    if args.dry_run:
        bundles = build_all_bundles()
        print(f"would run {len(bundles)} bundles × {len(judges)} judge(s) = {len(bundles)*len(judges)} calls")
        for j in judges:
            print(f"  judge={j.label} model={j.model.snapshot} effort={j.model.thinking_effort}")
        out = _judge_path(judges[0].label) if judges else None
        if out:
            existing = _existing_keys(out)
            print(f"  existing rows in {out.name}: {len(existing)}")
        print(f"output dir: {OUT_DIR}")
        return 0

    asyncio.run(_drive(judges, args.concurrency, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
