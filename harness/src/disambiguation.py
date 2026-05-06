"""
§4.2 disambiguation suffixes.

Frozen text appended to each Tier-1, Tier-2, and Tier-3 question when the
prompt is assembled under noise_type = temporal_msft. Source of truth:
TEMPORAL_NOISE_ADDENDUM.md §4.2. Edits here change disambiguation_suffix_hash
recorded in arm.lock.json and would invalidate any locked v3 arm.

Each sentence is written self-conditionally so it is valid both at the
temporal-arm baseline (fill = 0, no other Microsoft filings in prompt) and
at fill > 0 (other filings present): the "if … appear" clause is vacuously
satisfied at baseline, binding at fill > 0.

Apply rule: under noise_type = peer_materials these suffixes are NOT
appended. v2 arms therefore see byte-identical prompts pre/post v3.
"""
from __future__ import annotations

import hashlib

# --- frozen suffix text (verbatim from TEMPORAL_NOISE_ADDENDUM.md §4.2) ---

TIER1_SUFFIX: str = (
    "Use the figure as disclosed in Microsoft's FY2025 10-K specifically "
    "(the document inside `<<< TARGET MATERIALS >>>`); if any other "
    "Microsoft filings or earnings-call transcripts appear elsewhere in "
    "this prompt, treat them as scenario realism only."
)

TIER2_SUFFIX: str = (
    "Compute the figure from values disclosed in Microsoft's FY2025 10-K "
    "specifically (the document inside `<<< TARGET MATERIALS >>>`); if any "
    "other Microsoft filings or earnings-call transcripts appear elsewhere "
    "in this prompt, do not mix in figures from them."
)

TIER3_SUFFIX: str = (
    "Ground all claims in Microsoft's FY2025 10-K and Q2 FY2026 earnings "
    "call (the documents inside `<<< TARGET MATERIALS >>>`). If "
    "prior-period Microsoft filings or earnings-call transcripts appear "
    "elsewhere in this prompt, you may reference them only for explicit "
    "longitudinal context (e.g., \"revenue grew from $X in FY2024 to $Y in "
    "FY2025\") and only when the period of each cited figure is stated "
    "explicitly."
)

SUFFIX_BY_TIER: dict[int, str] = {
    1: TIER1_SUFFIX,
    2: TIER2_SUFFIX,
    3: TIER3_SUFFIX,
}


def disambiguation_suffix_sha256() -> str:
    """SHA-256 of the three §4.2 sentences concatenated as raw UTF-8 bytes,
    in tier order (1, 2, 3) with no separator. Pinned into arm.lock.json
    under prompt_assembly.disambiguation_suffix_hash.
    """
    payload = (TIER1_SUFFIX + TIER2_SUFFIX + TIER3_SUFFIX).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def suffix_for_tier(tier: int) -> str:
    if tier not in SUFFIX_BY_TIER:
        raise ValueError(f"unknown tier {tier!r}; expected 1, 2, or 3")
    return SUFFIX_BY_TIER[tier]


if __name__ == "__main__":
    print(disambiguation_suffix_sha256())
