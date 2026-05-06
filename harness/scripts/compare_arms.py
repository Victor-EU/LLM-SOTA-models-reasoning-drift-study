"""
Cross-arm comparison.

Reads arms/<arm>/arm.lock.json from every locked arm and REFUSES to compare
unless every arm shares the same:
  - pre_registration_hash (methodology unchanged — v1 OR v2 hash accepted)
  - materials_lock_hash   (corpus unchanged)
  - design fingerprint    (positions, noise types, reports, reps, total
                           context target — fill levels handled separately)
  - extractor + judge configuration (instruments held constant)

v1 arms (Opus 4.7, Sonnet 4.6) carry the v1 methodology hash from
`pre_registration.lock`. v2 arms (multi-vendor: GPT-5.5, Gemini 3.1 Pro,
DeepSeek V4 Pro) carry the v2 hash from `pre_registration.v2.lock`. v1
arms remain valid evidence under v2 by inheritance — the addendum only
adds scope; see MULTI_VENDOR_ADDENDUM.md §1.

Fill-level handling: the cross-arm tables are built over the INTERSECTION
of `fill_levels_supported` (v2) or `fill_levels` (v1) across arms. Cells
missing from any arm appear as `n/a` and are footnoted.

If gating passes, joins graded records across arms and produces a drift-
profile-by-arm comparison: per-cell judge dimension means, accuracy, plus
per-arm parser-failure rate (model-side JSON adherence is a real model
property — reported per arm, not filtered out).

Usage:
  python -m scripts.compare_arms                                 # stdout summary
  python -m scripts.compare_arms --write-report                  # writes cross_arm/COMPARATIVE_REPORT.md
  python -m scripts.compare_arms --arms opus-4-7,sonnet-4-6      # restrict to subset
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def discover_arms(restrict: list[str] | None = None) -> list[tuple[str, Path, dict]]:
    """Return list of (arm_name, arm_dir, arm_lock_dict) for arms that have a lock file."""
    arms_root = PROJECT_ROOT / "arms"
    if not arms_root.exists():
        return []
    out = []
    for arm_dir in sorted(arms_root.iterdir()):
        if not arm_dir.is_dir():
            continue
        if restrict and arm_dir.name not in restrict:
            continue
        lock_path = arm_dir / "arm.lock.json"
        if not lock_path.exists():
            continue
        try:
            arm_lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"WARN: cannot parse {lock_path}: {e}", file=sys.stderr)
            continue
        out.append((arm_dir.name, arm_dir, arm_lock))
    return out


def valid_methodology_hashes() -> dict[str, str]:
    """Return {hash → version_label} for every accepted methodology hash.

    Per TEMPORAL_NOISE_ADDENDUM.md §10 + MULTI_VENDOR_ADDENDUM.md §1: an arm
    passes the gate if its pre_registration.hash matches v1 OR v2 OR v3.
    Adding a future v4 lock = adding one (filename, label) pair here.
    """
    out: dict[str, str] = {}
    for fname, label in [("pre_registration.lock", "v1"),
                         ("pre_registration.v2.lock", "v2"),
                         ("pre_registration.v3.lock", "v3")]:
        p = PROJECT_ROOT / fname
        if p.exists():
            h = json.loads(p.read_text(encoding="utf-8")).get("methodology_hash")
            if h:
                out[h] = label
    return out


def design_fingerprint(design_used: dict) -> dict:
    """Extract the 'must match across arms' subset of design_used.

    Excludes fill levels (handled by intersection logic), tokenizer_note
    (record-only), and version-specific fields. Works for both v1 schema
    (fill_levels) and v2 schema (fill_levels_target / fill_levels_supported).
    """
    return {
        "positions": design_used.get("positions"),
        "noise_types": design_used.get("noise_types"),
        "reports": design_used.get("reports"),
        "reps_per_cell": design_used.get("reps_per_cell"),
        "tokens_total_context_target": design_used.get("tokens_total_context_target"),
        "tokens_report_token_cap": design_used.get("tokens_report_token_cap"),
    }


def arm_fill_levels(design_used: dict) -> list[float]:
    """Return the fill levels this arm actually ran. v2 arms expose
    fill_levels_supported; v1 arms expose fill_levels."""
    if "fill_levels_supported" in design_used:
        return [float(f) for f in design_used["fill_levels_supported"]]
    return [float(f) for f in design_used.get("fill_levels", [])]


def gate_consistency(arms: list[tuple[str, Path, dict]]) -> tuple[bool, list[str]]:
    """Verify all arms agree on the things that must not vary. Returns (ok, errors)."""
    errors: list[str] = []
    if len(arms) < 2:
        return True, []  # nothing to gate against

    accepted_hashes = valid_methodology_hashes()
    if not accepted_hashes:
        errors.append("no pre_registration lock files found at project root")
        return False, errors

    ref_name, _, ref_lock = arms[0]

    def get(d: dict, *path):
        cur = d
        for p in path:
            cur = cur.get(p, {}) if isinstance(cur, dict) else {}
        return cur

    # Every arm's methodology hash must be in the accepted set (v1 or v2),
    # not necessarily the SAME entry — v1 arms are valid evidence under v2.
    for name, _, lock in arms:
        h = get(lock, "pre_registration", "hash")
        if h not in accepted_hashes:
            errors.append(
                f"arm {name}: pre_registration.hash {h!r} matches no known "
                f"lock file (accepted: {sorted(accepted_hashes.keys())})"
            )

    ref_mat = get(ref_lock, "materials", "lock_hash")
    ref_design_fp = design_fingerprint(get(ref_lock, "design_used"))
    ref_extractor = get(ref_lock, "instruments_used", "extractor")
    ref_judge_p = get(ref_lock, "instruments_used", "judge_primary")
    ref_judge_s = get(ref_lock, "instruments_used", "judge_secondary")

    for name, _, lock in arms[1:]:
        if get(lock, "materials", "lock_hash") != ref_mat:
            errors.append(f"arm {name}: materials.lock_hash differs from {ref_name}")
        if design_fingerprint(get(lock, "design_used")) != ref_design_fp:
            errors.append(f"arm {name}: design fingerprint differs from {ref_name}")
        if get(lock, "instruments_used", "extractor") != ref_extractor:
            errors.append(f"arm {name}: extractor configuration differs from {ref_name}")
        if get(lock, "instruments_used", "judge_primary") != ref_judge_p:
            errors.append(f"arm {name}: judge_primary configuration differs from {ref_name}")
        if get(lock, "instruments_used", "judge_secondary") != ref_judge_s:
            errors.append(f"arm {name}: judge_secondary configuration differs from {ref_name}")

    return (not errors), errors


def load_graded_records(arm_dir: Path) -> list[dict]:
    graded_dir = arm_dir / "data" / "graded"
    if not graded_dir.exists():
        return []
    out = []
    for f in sorted(graded_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def fmt_mean(vals, prec=2):
    if not vals:
        return "n/a"
    if len(vals) == 1:
        return f"{vals[0]:.{prec}f}"
    return f"{statistics.mean(vals):.{prec}f}"


def fmt_pct(num, den):
    if den == 0:
        return "n/a"
    return f"{100 * num / den:.1f}%"


def build_comparison(arms: list[tuple[str, Path, dict]]) -> dict:
    """Return a nested dict: arm -> { 'tier12_acc_by_fill': ..., 'tier3_rq_by_fill': ..., 'cost_usd': float, ... }.

    Schema notes (matches what judge.py / autograder.py write to graded jsonl):
      tier 1/2 records: top-level `autograde` dict with `correct: bool`.
      tier 3 records:   top-level `absolute` dict with judge dimensions
                        (reasoning_quality, unsupported_claims, etc.).
                        Optional `secondary` dict (Sonnet 20% subsample) and
                        `pairwise` dict (vs baseline) — not used here.
    """
    accepted = valid_methodology_hashes()
    comp: dict = {}
    for name, arm_dir, arm_lock in arms:
        records = load_graded_records(arm_dir)
        tier12_by_fill: dict[float, list[bool]] = defaultdict(list)
        tier3_rq_by_fill: dict[float, list[float]] = defaultdict(list)
        tier3_unsupported_by_fill: dict[float, list[float]] = defaultdict(list)
        for r in records:
            fill = r.get("fill_pct")
            if r.get("tier") in (1, 2):
                ag = r.get("autograde", {}) or {}
                tier12_by_fill[fill].append(bool(ag.get("correct")))
            elif r.get("tier") == 3:
                absolute = r.get("absolute", {}) or {}
                rq = absolute.get("reasoning_quality")
                if rq is not None:
                    tier3_rq_by_fill[fill].append(float(rq))
                un = absolute.get("unsupported_claims")
                if un is not None:
                    tier3_unsupported_by_fill[fill].append(float(un))
        analyst = arm_lock.get("analyst", {}) or {}
        design_used = arm_lock.get("design_used", {}) or {}
        execution = arm_lock.get("execution_results", {}) or {}
        method_hash = arm_lock.get("pre_registration", {}).get("hash", "?")
        comp[name] = {
            "n_records": len(records),
            "cost_usd": float(execution.get("cumulative_cost_usd", 0.0)),
            "analyst_snapshot": analyst.get("snapshot", "?"),
            "vendor": analyst.get("vendor", "anthropic"),
            "snapshot_note": analyst.get("snapshot_note", ""),
            "tokenizer_note": design_used.get("tokenizer_note", ""),
            "fill_levels_supported": arm_fill_levels(design_used),
            "methodology_version": accepted.get(method_hash, "unknown"),
            "parser_unparseable_pct": float(execution.get("grade_unparseable_pct", 0.0)),
            "tier12_acc_by_fill": {
                fill: (sum(v), len(v)) for fill, v in sorted(tier12_by_fill.items())
            },
            "tier3_rq_by_fill": {
                fill: vals for fill, vals in sorted(tier3_rq_by_fill.items())
            },
            "tier3_unsupported_by_fill": {
                fill: vals for fill, vals in sorted(tier3_unsupported_by_fill.items())
            },
        }
    return comp


def render_comparison(comp: dict) -> list[str]:
    lines = []
    arms = list(comp.keys())
    lines.append("# Cross-arm drift comparison")
    lines.append("")
    lines.append(f"Arms compared: {', '.join(arms)}")
    lines.append("")

    lines.append("## Tier 1/2 accuracy (correct / total) by fill level")
    lines.append("")
    fills = sorted({f for arm in comp.values() for f in arm["tier12_acc_by_fill"]})
    header = "| fill | " + " | ".join(arms) + " |"
    sep = "|------|" + "|".join("------" for _ in arms) + "|"
    lines.append(header)
    lines.append(sep)
    for fill in fills:
        cells = []
        for arm in arms:
            entry = comp[arm]["tier12_acc_by_fill"].get(fill)
            if entry is None:
                cells.append("n/a")
            else:
                num, den = entry
                cells.append(f"{num}/{den} ({fmt_pct(num, den)})")
        lines.append(f"| {fill:.2f} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Tier 3 reasoning_quality (mean) by fill level")
    lines.append("")
    fills = sorted({f for arm in comp.values() for f in arm["tier3_rq_by_fill"]})
    lines.append(header)
    lines.append(sep)
    for fill in fills:
        cells = []
        for arm in arms:
            vals = comp[arm]["tier3_rq_by_fill"].get(fill, [])
            cells.append(fmt_mean(vals))
        lines.append(f"| {fill:.2f} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Tier 3 unsupported_claims (mean) by fill level")
    lines.append("")
    fills = sorted({f for arm in comp.values() for f in arm["tier3_unsupported_by_fill"]})
    lines.append(header)
    lines.append(sep)
    for fill in fills:
        cells = []
        for arm in arms:
            vals = comp[arm]["tier3_unsupported_by_fill"].get(fill, [])
            cells.append(fmt_mean(vals))
        lines.append(f"| {fill:.2f} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Cost + parser-failure rate per arm")
    lines.append("")
    lines.append("| arm | vendor | analyst | methodology | cost (USD) | n graded records | parser unparseable % |")
    lines.append("|-----|--------|---------|-------------|------------|------------------|----------------------|")
    for arm in arms:
        c = comp[arm]
        lines.append(
            f"| {arm} | {c['vendor']} | {c['analyst_snapshot']} | "
            f"{c['methodology_version']} | ${c['cost_usd']:.2f} | {c['n_records']} | "
            f"{c['parser_unparseable_pct']:.1f}% |"
        )
    lines.append("")

    # ---- footnotes -------------------------------------------------------
    # Per-arm rendering of fill-level support, snapshot mutability,
    # tokenizer disclosure. Empty fields (v1 arms) skip silently.
    notes_lines: list[str] = []
    union_fills = sorted({f for arm in comp.values() for f in arm["fill_levels_supported"]})
    for arm in arms:
        c = comp[arm]
        supported = set(c["fill_levels_supported"])
        missing = sorted(set(union_fills) - supported)
        bits = []
        if missing:
            bits.append(f"missing fills: {missing}")
        if c["snapshot_note"]:
            bits.append(f"snapshot: {c['snapshot_note']}")
        if c["tokenizer_note"]:
            bits.append(f"tokenizer: {c['tokenizer_note']}")
        if bits:
            notes_lines.append(f"- **{arm}** — " + "; ".join(bits))
    if notes_lines:
        lines.append("## Per-arm notes")
        lines.append("")
        lines.extend(notes_lines)
        lines.append("")
        lines.append("Cross-arm cells where an arm did not run a fill level appear as `n/a` in the tables above.")
        lines.append("")

    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-arm drift-profile comparison.")
    parser.add_argument("--arms", help="comma-separated arm names to restrict to")
    parser.add_argument("--write-report", action="store_true",
                        help="write cross_arm/COMPARATIVE_REPORT.md instead of stdout")
    args = parser.parse_args()

    restrict = args.arms.split(",") if args.arms else None
    arms = discover_arms(restrict)
    if not arms:
        print("No arms found (need arms/<arm>/arm.lock.json files).")
        return 2

    print(f"Discovered {len(arms)} locked arm(s): {', '.join(a[0] for a in arms)}")
    ok, errors = gate_consistency(arms)
    if not ok:
        print()
        print("INTEGRITY GATE FAILED — arms are not directly comparable:")
        for e in errors:
            print(f"  - {e}")
        print()
        print("Refusing to produce a comparison. Investigate the differences,")
        print("re-lock the affected arm(s), and re-run.")
        return 1
    print("Integrity gate: PASS — methodology, materials, design, and instruments match across arms.")
    print()

    if len(arms) < 2:
        print("(Only one arm locked — cross-arm comparison not yet meaningful.)")
        print(f"Run more arms to enable comparison.")
        return 0

    comp = build_comparison(arms)
    lines = render_comparison(comp)
    text = "\n".join(lines) + "\n"

    if args.write_report:
        out_dir = PROJECT_ROOT / "cross_arm"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / "COMPARATIVE_REPORT.md"
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote {out_path.relative_to(PROJECT_ROOT)}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
