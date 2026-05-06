"""
Grading subpackage.

Holds modules whose SHA-256 is part of the methodology surface: their bytes
are pinned in the per-arm `arm.lock.json` (under `grading_modules`) and
in `pre_registration.v3.lock`. Edits change those hashes and would
invalidate any locked v3 arm.

Currently:
  - scope_cap — applies the RUBRIC §scope_adherence cap rule extended for
    temporal_contamination per TEMPORAL_NOISE_ADDENDUM.md §5.2.
  - temporal_scan — programmatic detector for temporal_contamination per
    TEMPORAL_NOISE_ADDENDUM.md §5.1. Pure regex/numeric match against the
    answer + citation; counts distinct distractors hit (each unique
    period+source pair counts at most once per record).
"""
from __future__ import annotations

from .scope_cap import apply_scope_cap, scope_cap_module_sha256  # noqa: F401
from .temporal_scan import (  # noqa: F401
    Distractor,
    ScanResult,
    TemporalHit,
    load_distractors,
    scan_record,
    scan_text,
    temporal_scan_module_sha256,
)
