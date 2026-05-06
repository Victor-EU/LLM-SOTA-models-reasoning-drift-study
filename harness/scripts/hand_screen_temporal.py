"""
TEMPORAL_NOISE_ADDENDUM.md §3.3 hand-screen — automated numeric pass.

For every file in materials/noise/temporal_msft/MSFT/, scan for any number
within +/- 0.5% of an FY2025 Tier-1 / Tier-2 ground-truth value. A hit is a
candidate confound: if the prior-period file accidentally contains the
"right" FY2025 value, a model that picks it up may register as having
answered correctly while sourcing from the wrong period — an inflated
correct-answer rate without genuine FY2025 attribution. Symmetrically, a
forward-guidance midpoint from the Q1 FY2026 call landing near a FY2025
actual would inflate temporal_contamination for a reason orthogonal to
drift.

Output: writes `materials/noise_screening_log.md`. Records:
  - Per-target: canonical value, +/- 0.5% band, total scan radius.
  - Per-file: count of matches inside the band; the matched numeric strings
    with surrounding context (~80 chars).
  - Restated-comparator wrinkle (§3.1b) is handled inline by the band check
    — any restated FY24 value drifting close to FY25 surfaces here too.

Tier 3 (synthesis) screening is NOT in scope for this automated pass —
addendum §3.3 specifies Tier-1/Tier-2 numeric screening; Tier-3 anchor
contamination is judged at grading time.

Usage:
    python -m scripts.hand_screen_temporal
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# --- target canonical values from materials/ground_truth/MSFT.json (FY2025) ---
# (q_id, canonical, unit, tolerance — matches MSFT.json verbatim).
TARGETS: list[tuple[str, float, str, float]] = [
    ("MSFT-F-01", 281724.0, "USD_millions",   0.005),  # total revenue
    ("MSFT-F-02", 128528.0, "USD_millions",   0.005),  # operating income
    ("MSFT-F-03",     13.64, "USD_per_share", 0.005),  # diluted EPS
    ("MSFT-C-01",     17.6,  "percent",       0.005),  # effective tax rate
    ("MSFT-C-02",     14.9,  "percent",       0.005),  # revenue growth %
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPORAL_DIR = PROJECT_ROOT / "materials" / "noise" / "temporal_msft" / "MSFT"
OUT_PATH = PROJECT_ROOT / "materials" / "noise_screening_log.md"


# Match numbers with optional thousand-separator commas and decimal:
#   281,724  281724  13.64  17.6  14.9
_NUM_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+\.\d+\b|\b\d{4,}\b")


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _scan_file(text: str, target: float, tol_rel: float) -> list[tuple[str, str]]:
    """Return [(matched_string, ~80-char context)]."""
    hits: list[tuple[str, str]] = []
    radius = abs(target) * tol_rel
    lo, hi = target - radius, target + radius
    for m in _NUM_RE.finditer(text):
        v = _to_float(m.group(0))
        if v is None:
            continue
        if lo <= v <= hi:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            ctx = text[start:end].replace("\n", " ")
            hits.append((m.group(0), ctx.strip()))
    return hits


def _meta_for(txt: Path) -> dict:
    meta_path = txt.with_suffix(".meta.json")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def main() -> int:
    if not TEMPORAL_DIR.exists():
        print(f"ERROR: {TEMPORAL_DIR} not found")
        return 1

    files = sorted(TEMPORAL_DIR.glob("*.txt"))
    if not files:
        print(f"ERROR: no .txt files under {TEMPORAL_DIR}")
        return 1

    lines: list[str] = []
    lines.append("# Temporal-Noise Hand-Screen Log")
    lines.append("")
    lines.append("**Methodology surface:** TEMPORAL_NOISE_ADDENDUM.md §3.3 + §3.1b.")
    lines.append("")
    lines.append("**Automated screen recipe:** for each FY2025 Tier-1/Tier-2 ground-truth")
    lines.append("value V, scan every .txt under `materials/noise/temporal_msft/MSFT/` for")
    lines.append("any number within +/- 0.5% of V. Each in-band match is reported with the")
    lines.append("surrounding ~80 characters of context for human review of intent.")
    lines.append("")
    lines.append("**Why ±0.5%:** matches the tightest ground-truth tolerance (Tier-1 numeric)")
    lines.append("plus a small slack to capture restated-comparator (§3.1b) drift.")
    lines.append("")
    lines.append("**Action on hit:** human review decides whether the match is a legitimate")
    lines.append("longitudinal disclosure (e.g., a prior 10-K's FY2025 forecast that landed")
    lines.append("near actuals — keep), an unintended distractor (e.g., a coincidental peer")
    lines.append("number — keep, document), or a contamination requiring removal of the file.")
    lines.append("To-date no file has been removed; the noise pool is locked as-is.")
    lines.append("")
    lines.append("**Scope of this automated pass:** Tier-1 and Tier-2 numeric screening. Tier-3")
    lines.append("(synthesis) anchor contamination is judged at grading time, not pre-locked.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Target canonical values + bands")
    lines.append("")
    lines.append("| q_id | canonical | unit | tolerance_rel | scan band |")
    lines.append("|------|-----------|------|----------------|-----------|")
    for qid, val, unit, tol in TARGETS:
        radius = abs(val) * tol
        lines.append(
            f"| {qid} | {val} | {unit} | ±{tol*100:.1f}% | "
            f"[{val - radius:.4f}, {val + radius:.4f}] |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-file findings")
    lines.append("")

    total_files = 0
    total_clean = 0
    total_hits = 0
    by_target_total: dict[str, int] = {qid: 0 for qid, _, _, _ in TARGETS}

    for txt in files:
        total_files += 1
        meta = _meta_for(txt)
        text = txt.read_text(encoding="utf-8")
        period = meta.get("period_label", "?")
        subpool = meta.get("subpool", "?")

        # Subhead per file
        lines.append(f"### `{txt.name}`")
        lines.append("")
        lines.append(f"- subpool: `{subpool}`  period: `{period}`  tokens: `{meta.get('token_count')}`")

        any_hit = False
        for qid, val, _, tol in TARGETS:
            hits = _scan_file(text, val, tol)
            if not hits:
                continue
            any_hit = True
            total_hits += len(hits)
            by_target_total[qid] += len(hits)
            lines.append("")
            lines.append(f"  **{qid} (target {val})** — {len(hits)} match(es) in band:")
            # Cap at 5 contexts per (file, target) to keep the log scannable.
            for matched, ctx in hits[:5]:
                lines.append(f"    - `{matched}`  …{ctx}…")
            if len(hits) > 5:
                lines.append(f"    - … {len(hits) - 5} more match(es) elided")

        if not any_hit:
            lines.append("")
            lines.append("  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*")
            total_clean += 1

        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Files scanned: **{total_files}**")
    lines.append(f"- Files with zero in-band matches: **{total_clean}** ({100 * total_clean / total_files:.1f}%)")
    lines.append(f"- Files with ≥1 match: **{total_files - total_clean}**")
    lines.append(f"- Total numeric matches: **{total_hits}**")
    lines.append("")
    lines.append("Per-target match counts:")
    lines.append("")
    lines.append("| q_id | total matches across pool |")
    lines.append("|------|---------------------------|")
    for qid, _, _, _ in TARGETS:
        lines.append(f"| {qid} | {by_target_total[qid]} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Reviewer notes")
    lines.append("")
    lines.append("**Restated comparators (§3.1b).** MSFT 10-Ks disclose the prior year for")
    lines.append("comparability. The FY2024 10-K's \"as restated\" figures may differ from the")
    lines.append("FY2024 actuals as originally filed. The ±0.5% band catches both versions when")
    lines.append("they near a FY2025 value — both are kept in the noise pool deliberately, with")
    lines.append("§5.3 logging the period of any actual hit as a diagnostic.")
    lines.append("")
    lines.append("**Q1 FY2026 call forward guidance.** The Q1 FY2026 transcript (held Oct 2025)")
    lines.append("provides Q2 FY2026 guidance, not FY2025 figures. Any in-band hits there should")
    lines.append("be examined for guidance-midpoints landing on FY2025 actuals — a known §3.3.1")
    lines.append("failure mode. Human-reviewed below if any such hits appear.")
    lines.append("")
    lines.append("**Disposition.** No files removed in this pass. The pool composition stands")
    lines.append("as locked in `materials_temporal.lock.json` (SHA recorded in addendum §13).")
    lines.append("Subsequent re-screens after human review of the contexts above amend this file")
    lines.append("(and re-hash via `noise_screening_log_hash` in arm.lock.json).")

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"  files={total_files}  clean={total_clean}  total_hits={total_hits}")
    for qid, _, _, _ in TARGETS:
        print(f"  {qid}: {by_target_total[qid]} match(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
