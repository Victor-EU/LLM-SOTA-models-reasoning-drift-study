"""
Prompt assembly — the correctness-critical module.

Builds the message payload for a single analyst run. Enforces the invariants
documented in DESIGN §6:

  1. Ordering: [system][noise_a][target][noise_b][questions]
  2. Position controls the noise split:
       start:  noise_a = 0, noise_b = full
       middle: noise_a = noise_b = full / 2
       end:    noise_a = full, noise_b = 0
  3. Noise content is seeded by cell_id (NOT run_id) so the cacheable prefix
     is byte-identical across the reps_per_cell reps in a cell.
  4. Question order is shuffled by run_id.
  5. Cache breakpoints are placed at (end of system, end of noise_a,
     end of target, end of noise_b) — up to 4 breakpoints per the
     Anthropic prompt-caching contract. The question block is the only
     uncached segment.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Iterable

from .cells import CellSpec, RunSpec
from .materials import Materials, NoiseDoc, Question, TargetBundle
from .prompts import ANALYST_SYSTEM_PROMPT


# ---- seeds ----------------------------------------------------------------

def _seed(*parts: Any) -> int:
    """Deterministic 64-bit seed from arbitrary identifier parts."""
    payload = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


# ---- noise split ---------------------------------------------------------

def compute_noise_split(position: str | None, total_noise_tokens: int) -> tuple[int, int]:
    """
    Given a total noise budget and a position, return (noise_a_tokens, noise_b_tokens).
    Baseline (position=None) returns (0, 0).
    """
    if position is None:
        return (0, 0)
    if total_noise_tokens <= 0:
        return (0, 0)
    if position == "start":
        return (0, total_noise_tokens)
    if position == "end":
        return (total_noise_tokens, 0)
    if position == "middle":
        half = total_noise_tokens // 2
        return (half, total_noise_tokens - half)
    raise ValueError(f"unknown position {position!r}")


# ---- noise sampling ------------------------------------------------------

def _select_noise_pool(materials: Materials, cell: CellSpec) -> list[NoiseDoc]:
    """
    Select the pool of noise docs usable for this cell.

    Peer-material docs are paired to a specific target (on-disk layout:
    noise/peer_materials/{pair_target}/*.txt); use only those matching this
    cell's report (falling back to pair_target=None if unpaired entries exist).
    Other noise types are assumed unpaired — use the whole pool.

    Must agree with tokens._pool_max_tokens so pool-exhaustion detection and
    noise sampling see the same universe of docs.
    """
    if cell.noise_type is None:
        return []
    pool = materials.noise.get(cell.noise_type, [])
    if cell.noise_type == "peer_materials":
        paired = [d for d in pool if d.pair_target in (cell.report_id, None)]
        return paired
    return list(pool)


def sample_noise(
    pool: list[NoiseDoc],
    target_tokens: int,
    seed: int,
    greedy_pack: bool = True,
) -> list[NoiseDoc]:
    """
    Greedy first-fit-decreasing pack of noise docs until cumulative tokens
    approach `target_tokens`. Deterministic given `seed`.

    The returned list is in presentation order (shuffled from pack order so the
    noise block doesn't always start with the largest doc).
    """
    if target_tokens <= 0 or not pool:
        return []

    rng = random.Random(seed)
    shuffled = pool.copy()
    rng.shuffle(shuffled)

    packed: list[NoiseDoc] = []
    remaining = target_tokens
    if greedy_pack:
        # Sort descending by token count for tighter packing.
        for doc in sorted(shuffled, key=lambda d: -d.token_count):
            if doc.token_count <= remaining:
                packed.append(doc)
                remaining -= doc.token_count
            if remaining < 500:   # good-enough fit
                break
    else:
        for doc in shuffled:
            if doc.token_count <= remaining:
                packed.append(doc)
                remaining -= doc.token_count

    # Re-shuffle presentation order (independent of pack order) for realism.
    presentation_order_seed = _seed(seed, "presentation")
    presentation_rng = random.Random(presentation_order_seed)
    presentation_rng.shuffle(packed)
    return packed


# ---- question ordering ---------------------------------------------------

def shuffle_questions(questions: list[Question], seed: int) -> list[Question]:
    rng = random.Random(seed)
    ordered = questions.copy()
    rng.shuffle(ordered)
    return ordered


# ---- block formatters ----------------------------------------------------

def format_noise_block(label: str, docs: Iterable[NoiseDoc]) -> str:
    parts = [f"[CONTEXT BLOCK {label} — reference documents, NOT the target]"]
    for doc in docs:
        parts.append(f"<<< {doc.title} >>>")
        parts.append(doc.text)
        parts.append(f"<<< END {doc.title} >>>")
    return "\n\n".join(parts)


def format_target_block(bundle: TargetBundle) -> str:
    """Render the target materials bundle (10-K + earnings call) as one block."""
    report = bundle.report
    call = bundle.earnings_call
    return (
        f"<<< TARGET MATERIALS: {bundle.company_name} >>>\n\n"
        f"<<< 10-K FY{report.fiscal_year} >>>\n{report.text}\n<<< END 10-K >>>\n\n"
        f"<<< EARNINGS CALL: {call.quarter} FY{call.fiscal_year} — {call.call_date} >>>\n"
        f"{call.text}\n"
        f"<<< END EARNINGS CALL >>>\n\n"
        f"<<< END TARGET MATERIALS >>>"
    )


def format_question_block(bundle: TargetBundle, questions: list[Question]) -> str:
    header = (
        f"=== QUESTIONS ===\n"
        f"You are answering {len(questions)} questions about {bundle.company_name} "
        f"based on the target materials above (10-K + earnings call).\n\n"
    )
    tier1 = [q for q in questions if q.tier == 1]
    tier2 = [q for q in questions if q.tier == 2]
    tier3 = [q for q in questions if q.tier == 3]

    sections: list[str] = [header]
    if tier1:
        sections.append("— TIER 1: FACTUAL —\n" + _render_q_list(tier1))
    if tier2:
        sections.append("— TIER 2: CALCULATION —\n" + _render_q_list(tier2))
    if tier3:
        sections.append("— TIER 3: SYNTHESIS —\n" + _render_q_list(tier3))

    sections.append("=== END QUESTIONS ===\n\nRespond now with the JSON array. No prose outside the JSON.")
    return "\n\n".join(sections)


def _render_q_list(qs: list[Question]) -> str:
    return "\n".join(f"[id: {q.q_id}] {q.prompt}" for q in qs)


# ---- assembled prompt ----------------------------------------------------

@dataclass(frozen=True)
class AssembledPrompt:
    system: list[dict[str, Any]]        # Anthropic system content blocks
    messages: list[dict[str, Any]]      # Anthropic messages list
    # Breakdown (approximate; authoritative count comes from tokens.count())
    estimated_tokens: dict[str, int] = field(default_factory=dict)
    # Diagnostics
    cell_id: str = ""
    run_id: str = ""
    noise_doc_ids: tuple[str, ...] = ()


def _block(text: str, cacheable: bool) -> dict[str, Any]:
    b: dict[str, Any] = {"type": "text", "text": text}
    if cacheable:
        b["cache_control"] = {"type": "ephemeral"}
    return b


def assemble(
    run: RunSpec,
    materials: Materials,
    noise_a_token_budget: int,
    noise_b_token_budget: int,
) -> AssembledPrompt:
    """
    Build the Anthropic messages payload for a single run.

    Noise budgets are provided by the caller (tokens.py computes them given
    the cell's fill target and the realized report / system / question sizes).
    """
    cell = run.cell
    bundle = materials.target_bundles[cell.report_id]
    questions = materials.questions[cell.report_id]
    noise_pool = _select_noise_pool(materials, cell)

    noise_a_docs = sample_noise(
        pool=noise_pool,
        target_tokens=noise_a_token_budget,
        seed=_seed(cell.cell_id, "noise_a"),
    )
    noise_b_docs = sample_noise(
        pool=noise_pool,
        target_tokens=noise_b_token_budget,
        seed=_seed(cell.cell_id, "noise_b"),
    )

    ordered_questions = shuffle_questions(
        questions,
        seed=_seed(run.run_id, "questions"),
    )

    # ----- system -----
    system = [_block(ANALYST_SYSTEM_PROMPT, cacheable=True)]

    # ----- user content blocks -----
    # Up to 4 cache breakpoints total across the whole request; we use:
    #   (1) end of system prompt
    #   (2) end of noise_a      (skipped if noise_a empty)
    #   (3) end of target
    #   (4) end of noise_b      (skipped if noise_b empty)
    user_blocks: list[dict[str, Any]] = []
    if noise_a_docs:
        user_blocks.append(_block(format_noise_block("A", noise_a_docs), cacheable=True))
    user_blocks.append(_block(format_target_block(bundle), cacheable=True))
    if noise_b_docs:
        user_blocks.append(_block(format_noise_block("B", noise_b_docs), cacheable=True))
    # The question block is NOT cached.
    user_blocks.append(_block(format_question_block(bundle, ordered_questions), cacheable=False))

    messages = [{"role": "user", "content": user_blocks}]

    estimated = {
        "system": _rough_tokens(ANALYST_SYSTEM_PROMPT),
        "noise_a_target": noise_a_token_budget,
        "noise_a_actual": sum(d.token_count for d in noise_a_docs),
        "target": bundle.combined_token_count,
        "noise_b_target": noise_b_token_budget,
        "noise_b_actual": sum(d.token_count for d in noise_b_docs),
        "questions": _rough_tokens(user_blocks[-1]["text"]),
    }

    return AssembledPrompt(
        system=system,
        messages=messages,
        estimated_tokens=estimated,
        cell_id=cell.cell_id,
        run_id=run.run_id,
        noise_doc_ids=tuple(d.doc_id for d in (noise_a_docs + noise_b_docs)),
    )


def _rough_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 characters. Used only for diagnostics."""
    return max(1, len(text) // 4)
