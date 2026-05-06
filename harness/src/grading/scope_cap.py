"""
scope_adherence cap rule.

RUBRIC.md §scope_adherence v2.1 caps the dimension at 3 when the response
attributes peer data to Microsoft (cross_contamination >= 1). The judge is
instructed to apply this cap in its head; this module re-applies it in code
as a safety net so the cap is enforceable independently of judge compliance.

TEMPORAL_NOISE_ADDENDUM.md §5.2 extends the cap symmetrically: under
temporal noise the cap fires when (cross_contamination + temporal_contamination)
>= 1. RUBRIC.md is NOT edited; the extended rule lives here and is pinned
into the v3 methodology hash via `grading_module_hash` (the SHA-256 of this
file's bytes), recorded in each v3 arm.lock.json.

Behavior on peer arms (noise_type = peer_materials):
  temporal_contamination is absent (or 0 by convention). The function
  reduces to the v1/v2 rule. Re-grading a v1/v2 record through this module
  is a no-op when the judge already capped — i.e., backwards compatible.

Pure function. No I/O. No state. Deterministic.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# Cap floor — the value scope_adherence is clamped down to when the rule fires.
# Locked at 3 by RUBRIC.md v2.1 §scope_adherence and reaffirmed by
# TEMPORAL_NOISE_ADDENDUM.md §5.2.
SCOPE_CAP_FLOOR: int = 3


def apply_scope_cap(
    *,
    scope_adherence: int,
    cross_contamination: int,
    temporal_contamination: int = 0,
) -> int:
    """
    Apply the §scope_adherence cap.

    If the response had any misattribution (peer-to-target OR
    prior-period-to-target), force scope_adherence down to SCOPE_CAP_FLOOR.

    Args:
      scope_adherence: judge-reported 1..5.
      cross_contamination: judge-reported count of peer-to-MSFT misattributions.
      temporal_contamination: count of prior-MSFT-period-to-current-MSFT
        misattributions. 0 for peer arms (TEMPORAL_NOISE_ADDENDUM.md §5.1).

    Returns:
      The (possibly reduced) scope_adherence value, clamped to [1, 5].
    """
    if scope_adherence < 1 or scope_adherence > 5:
        raise ValueError(
            f"scope_adherence must be in 1..5, got {scope_adherence}"
        )
    if cross_contamination < 0 or temporal_contamination < 0:
        raise ValueError(
            f"contamination counts must be non-negative, got "
            f"cross={cross_contamination}, temporal={temporal_contamination}"
        )
    if (cross_contamination + temporal_contamination) >= 1:
        return min(scope_adherence, SCOPE_CAP_FLOOR)
    return scope_adherence


def scope_cap_module_sha256() -> str:
    """SHA-256 of this module's source bytes — pinned into arm.lock.json."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


if __name__ == "__main__":
    print(scope_cap_module_sha256())
