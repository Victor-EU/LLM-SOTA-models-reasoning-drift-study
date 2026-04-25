"""
Pre-registered exclusion checks (DESIGN §7.5).

A run is excluded if and only if:
  - HTTP error not recovered by retry (→ handled upstream in api.py).
  - Output fully truncated (<50% of questions addressed).
  - Realized context fill deviated from target by > tolerance.

Response-quality issues (hallucinations, wrong answers, scope drift) are
dependent variables, NOT exclusion criteria.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .api import CallResult
from .config import ExperimentConfig


@dataclass(frozen=True)
class ValidationResult:
    exclude: bool
    reason: str | None
    # Informational flags (not exclusion triggers).
    flags: dict[str, bool]


def validate_run(
    result: CallResult,
    *,
    realized_input_tokens: int,
    target_input_tokens: int,
    expected_question_ids: list[str],
    cfg: ExperimentConfig,
    pool_exhausted: bool = False,
    is_baseline: bool = False,
) -> ValidationResult:
    flags: dict[str, bool] = {
        "truncated": result.stop_reason == "max_tokens",
        "malformed_json": False,
        "partial_answers": False,
        "pool_exhausted": pool_exhausted,
        "baseline": is_baseline,
    }

    # ---- fill-tolerance check -------------------------------------------
    # Fill deviation is an exclusion EXCEPT when the harness has already
    # signalled that the discrete noise pool prevented tighter convergence
    # (pool_exhausted) or that this is a baseline with no noise to adjust.
    # In both exempted cases the realized fill is the closest achievable and
    # realized_fill_pct is logged for downstream re-binning.
    fill_delta = realized_input_tokens - target_input_tokens   # signed
    tol = cfg.tokens.fill_tolerance_tokens
    if fill_delta > tol and not pool_exhausted and not is_baseline:
        return ValidationResult(
            exclude=True,
            reason=f"over-target fill: +{fill_delta} tokens (tolerance {tol})",
            flags=flags,
        )
    if fill_delta < -tol and not pool_exhausted and not is_baseline:
        return ValidationResult(
            exclude=True,
            reason=f"under-target fill with pool available: {fill_delta} tokens (tolerance {tol})",
            flags=flags,
        )

    # ---- answer-completeness check ---------------------------------------
    parsed = _try_parse_json_array(result.text)
    if parsed is None:
        flags["malformed_json"] = True
        return ValidationResult(
            exclude=False,  # do NOT exclude on parse failure — it's a DV.
            reason=None,
            flags=flags,
        )

    addressed = {
        obj.get("q_id")
        for obj in parsed
        if isinstance(obj, dict) and obj.get("q_id")
    }
    coverage = len(addressed & set(expected_question_ids)) / max(1, len(expected_question_ids))
    flags["partial_answers"] = coverage < 1.0

    if coverage < 0.5:
        return ValidationResult(
            exclude=True,
            reason=f"output addressed only {coverage:.0%} of questions (< 50%)",
            flags=flags,
        )

    return ValidationResult(exclude=False, reason=None, flags=flags)


def _try_parse_json_array(text: str) -> list[dict] | None:
    """
    Best-effort JSON array extraction. Tolerates markdown fences and
    surrounding prose; returns None if nothing parseable.
    """
    # Strip common markdown fences.
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()

    # Try direct parse first.
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass

    # Fallback: extract first balanced [...] block.
    match = re.search(r"\[.*\]", stripped, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None
