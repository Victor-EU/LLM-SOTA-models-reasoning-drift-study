"""
Cross-arm comparison.

Reads arms/<arm>/arm.lock.json from every locked arm and REFUSES to compare
unless every arm shares the same:
  - pre_registration_hash (methodology DESIGN+PROMPTS+RUBRIC unchanged)
  - materials_lock_hash   (corpus unchanged)
  - design_grid           (cells, fill levels, positions, reps unchanged)
  - extractor + judge configuration (instruments held constant)

This gating is what makes the comparison apples-to-apples — observed
differences come from the analyst, not the methodology, the corpus, or the
measuring instruments.

If gating passes, joins graded records across arms and produces a drift-
profile-by-arm comparison: per-cell judge dimension means, accuracy, etc.

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


def gate_consistency(arms: list[tuple[str, Path, dict]]) -> tuple[bool, list[str]]:
    """Verify all arms agree on the things that must not vary. Returns (ok, errors)."""
    errors: list[str] = []
    if len(arms) < 2:
        return True, []  # nothing to gate against

    ref_name, _, ref_lock = arms[0]

    def get(d: dict, *path):
        cur = d
        for p in path:
            cur = cur.get(p, {}) if isinstance(cur, dict) else {}
        return cur

    ref_method = get(ref_lock, "pre_registration", "hash")
    ref_mat = get(ref_lock, "materials", "lock_hash")
    ref_design = get(ref_lock, "design_used")
    ref_extractor = get(ref_lock, "instruments_used", "extractor")
    ref_judge_p = get(ref_lock, "instruments_used", "judge_primary")
    ref_judge_s = get(ref_lock, "instruments_used", "judge_secondary")

    for name, _, lock in arms[1:]:
        if get(lock, "pre_registration", "hash") != ref_method:
            errors.append(f"arm {name}: pre_registration.hash differs from {ref_name}")
        if get(lock, "materials", "lock_hash") != ref_mat:
            errors.append(f"arm {name}: materials.lock_hash differs from {ref_name}")
        if get(lock, "design_used") != ref_design:
            errors.append(f"arm {name}: design_used differs from {ref_name}")
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
    """Return a nested dict: arm -> { 'tier12_acc_by_fill': ..., 'tier3_rq_by_fill': ..., 'cost_usd': float }."""
    comp: dict = {}
    for name, arm_dir, arm_lock in arms:
        records = load_graded_records(arm_dir)
        # Group by fill_pct
        tier12_by_fill: dict[float, list[bool]] = defaultdict(list)
        tier3_rq_by_fill: dict[float, list[float]] = defaultdict(list)
        tier3_unsupported_by_fill: dict[float, list[float]] = defaultdict(list)
        for r in records:
            fill = r.get("fill_pct")
            if r.get("tier") in (1, 2):
                ag = r.get("autograde", {}) or {}
                tier12_by_fill[fill].append(bool(ag.get("correct")))
            elif r.get("tier") == 3:
                judgement = r.get("judgement", {}) or {}
                rq = judgement.get("reasoning_quality")
                if rq is not None:
                    tier3_rq_by_fill[fill].append(float(rq))
                un = judgement.get("unsupported_claims")
                if un is not None:
                    tier3_unsupported_by_fill[fill].append(float(un))
        comp[name] = {
            "n_records": len(records),
            "cost_usd": float(arm_lock.get("execution_results", {}).get("cumulative_cost_usd", 0.0)),
            "analyst_snapshot": arm_lock.get("analyst", {}).get("snapshot", "?"),
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

    lines.append("## Cost per arm")
    lines.append("")
    lines.append("| arm | analyst | cost (USD) | n graded records |")
    lines.append("|-----|---------|------------|------------------|")
    for arm in arms:
        c = comp[arm]
        lines.append(f"| {arm} | {c['analyst_snapshot']} | ${c['cost_usd']:.2f} | {c['n_records']} |")
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
