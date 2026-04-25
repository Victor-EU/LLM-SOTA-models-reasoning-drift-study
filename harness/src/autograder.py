"""
Auto-grader for Tier 1 (factual) and Tier 2 (calculation) questions.

Grades extracted records against ground-truth keys:
  - Numeric: within configured tolerance (absolute or relative).
  - String: case-insensitive exact match.
  - Citation: partial credit if answer correct but citation missing/wrong.
  - Hallucination: flag if answer matches any common_distractor.

Pure function over extracted records — no API calls. Runs locally as part of
the grading stage before the tier-3 judge pass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .materials import GroundTruth, Materials


@dataclass(frozen=True)
class AutoGrade:
    q_id: str
    tier: int
    correct: bool
    citation_match: bool
    score: float                 # 1.0 if answer + citation; 0.5 if answer only; 0.0 otherwise
    distractor_hit: bool
    distractor_source: str | None
    reason: str | None


def grade_record(extracted: dict[str, Any], materials: Materials) -> AutoGrade | None:
    """Grade a single extracted record; returns None if q_id is tier 3 (skip)."""
    q_id = extracted.get("q_id")
    if not q_id or q_id not in materials.ground_truth:
        return None
    gt = materials.ground_truth[q_id]
    if gt.tier == 3:
        return None  # tier 3 goes to the judge, not the autograder

    if not extracted.get("parsed_ok", True):
        return AutoGrade(
            q_id=q_id,
            tier=gt.tier,
            correct=False,
            citation_match=False,
            score=0.0,
            distractor_hit=False,
            distractor_source=None,
            reason="extractor could not parse a value",
        )

    answer = extracted.get("answer_normalized")
    correct, reason = _compare(answer, gt)

    distractor_hit, distractor_source = _check_distractor(answer, gt)

    citation_match = _citation_matches(extracted.get("citation"), gt)

    score = 0.0
    if correct and citation_match:
        score = 1.0
    elif correct:
        score = 0.5

    return AutoGrade(
        q_id=q_id,
        tier=gt.tier,
        correct=correct,
        citation_match=citation_match,
        score=score,
        distractor_hit=distractor_hit,
        distractor_source=distractor_source,
        reason=reason,
    )


# ---- comparators ---------------------------------------------------------

def _compare(answer: Any, gt: GroundTruth) -> tuple[bool, str | None]:
    if answer is None:
        return False, "answer is null"
    if isinstance(gt.canonical_answer, (int, float)):
        return _compare_numeric(answer, gt)
    # String comparison
    if str(answer).strip().casefold() == str(gt.canonical_answer).strip().casefold():
        return True, None
    return False, "string mismatch"


def _compare_numeric(answer: Any, gt: GroundTruth) -> tuple[bool, str | None]:
    val = _coerce_number(answer)
    if val is None:
        return False, "could not coerce answer to number"
    target = float(gt.canonical_answer)
    if gt.tolerance_abs is not None:
        if abs(val - target) <= gt.tolerance_abs:
            return True, None
        return False, f"|{val}-{target}| > abs_tol {gt.tolerance_abs}"
    if gt.tolerance_rel is not None:
        if target == 0:
            return (val == 0), None if val == 0 else "rel_tol undefined at target=0"
        if abs(val - target) / abs(target) <= gt.tolerance_rel:
            return True, None
        return False, f"|{val}-{target}|/|{target}| > rel_tol {gt.tolerance_rel}"
    # No tolerance specified — require exact numeric equality.
    return (val == target), None if val == target else "numeric mismatch"


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _coerce_number(x: Any) -> float | None:
    if isinstance(x, (int, float)):
        return float(x)
    if not isinstance(x, str):
        return None
    # Strip commas first so "281,724" becomes "281724". The previous attempt
    # at a comma-aware regex (-?\d{1,3}(?:,\d{3})*) matched "281" before
    # "281724" via leftmost-match semantics — silently turning every uncommatted
    # large integer into its first 3 digits and breaking F01/F02 grading.
    cleaned = x.replace("$", "").replace("%", "").replace(",", "").strip()
    match = _NUMBER_RE.search(cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _check_distractor(answer: Any, gt: GroundTruth) -> tuple[bool, str | None]:
    val = _coerce_number(answer)
    if val is None or not gt.common_distractors:
        return False, None
    for d in gt.common_distractors:
        d_val = _coerce_number(d) if not isinstance(d, (int, float)) else float(d)
        if d_val is None:
            continue
        if d_val == 0:
            if val == 0:
                return True, str(d)
            continue
        if abs(val - d_val) / abs(d_val) <= 0.01:  # within 1%
            return True, str(d)
    return False, None


def _citation_matches(citation: Any, gt: GroundTruth) -> bool:
    if not citation or not isinstance(citation, str):
        return False
    needle = citation.casefold()
    return any(span.casefold() in needle or needle in span.casefold() for span in gt.citation_spans)
