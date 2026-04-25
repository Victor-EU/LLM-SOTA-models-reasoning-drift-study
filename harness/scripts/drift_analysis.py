"""Drift analysis on graded data.

Aggregates judge scores + autograde results per cell and per fill level
for ONE arm. For cross-arm comparison see scripts/compare_arms.py.

Surfaces:
  - Tier 1/2 numeric accuracy + distractor (cross-contamination) rate by fill.
  - Tier 3 dimension means + variance by fill, by question.
  - reasoning_quality (0-10) drift across fill levels.
  - Q8 structural diagnostics (units_decomposed, frameworks_applied, synthesis_consistent).
  - Pairwise verdict distribution and reasoning_quality_delta vs baseline.
  - Cross-model ICC from Sonnet secondary subsample (within-arm).

Usage:
  python -m scripts.drift_analysis --arm opus-4-7
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def fmt_mean_sd(vals, prec=2):
    if not vals:
        return "n/a"
    if len(vals) == 1:
        return f"{vals[0]:.{prec}f}"
    return f"{statistics.mean(vals):.{prec}f}±{statistics.pstdev(vals):.{prec}f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, help="analyst arm name (matches arms/<arm>/)")
    args = parser.parse_args()

    graded_dir = PROJECT_ROOT / "arms" / args.arm / "data" / "graded"
    if not graded_dir.exists():
        print(f"no graded directory at {graded_dir} — has this arm been graded yet?")
        return 2
    files = sorted(graded_dir.glob("*.jsonl"))
    if not files:
        print(f"no graded files in {graded_dir} — run scripts.run_grading --arm {args.arm} first")
        return 2

    print(f"Drift analysis for arm: {args.arm}")
    print(f"Reading from: {graded_dir.relative_to(PROJECT_ROOT)}")
    print()

    # Group by cell_id, then by q_id.
    by_cell: dict[str, dict] = defaultdict(lambda: {
        "fill_pct": None, "position": None,
        "tier12": defaultdict(list),    # q_id -> [autograde dicts]
        "tier3":  defaultdict(list),    # q_id -> [absolute judge dicts]
        "pairwise": defaultdict(list),  # q_id -> [(verdict, delta, candidate_won_bool)]
        "secondary": defaultdict(list), # q_id -> [absolute judge dicts] (Sonnet)
    })

    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            cid = r["cell_id"]
            c = by_cell[cid]
            c["fill_pct"] = r["fill_pct"]
            c["position"] = r.get("position")
            qid = r["q_id"]

            ag = r.get("autograde")
            if ag:
                c["tier12"][qid].append(ag)

            ab = r.get("absolute")
            if ab:
                c["tier3"][qid].append(ab)

            pw = r.get("pairwise")
            if pw:
                # Determine if candidate (non-baseline) won.
                a_is_baseline = pw.get("a_is_baseline", False)
                v = pw.get("verdict", "tie")
                cand_won = (v == "B" and a_is_baseline) or (v == "A" and not a_is_baseline)
                base_won = (v == "A" and a_is_baseline) or (v == "B" and not a_is_baseline)
                # delta sign: +ve = A stronger; flip to candidate-relative.
                delta_signed_to_cand = pw.get("reasoning_quality_delta", 0)
                if a_is_baseline:
                    delta_signed_to_cand = -delta_signed_to_cand
                c["pairwise"][qid].append((v, delta_signed_to_cand, cand_won, base_won))

            sec = r.get("secondary")
            if sec:
                c["secondary"][qid].append(sec)

    # ----- Tier 1/2 accuracy table -----
    print()
    print("=" * 100)
    print("TIER 1/2 — numeric accuracy + distractor hits (per cell, across 7 reps)")
    print("=" * 100)
    print(f"{'cell':<55} {'fill':>5} {'pos':>7} "
          f"{'F01':>6} {'F02':>6} {'F03':>6} {'C01':>6} {'C02':>6}  {'distract':>9}")
    print("-" * 100)
    for cid in sorted(by_cell, key=lambda k: (by_cell[k]["fill_pct"], by_cell[k]["position"] or "")):
        c = by_cell[cid]
        def acc(qid):
            entries = c["tier12"].get(qid, [])
            if not entries: return "n/a"
            n = len(entries); ok = sum(1 for e in entries if e.get("correct"))
            return f"{ok}/{n}"
        distract = sum(
            1 for qs in c["tier12"].values() for e in qs
            if e.get("distractor_hit")
        )
        print(f"{cid[:55]:<55} {c['fill_pct']:>5.2f} {(c['position'] or '-'):>7} "
              f"{acc('MSFT-F-01'):>6} {acc('MSFT-F-02'):>6} {acc('MSFT-F-03'):>6} "
              f"{acc('MSFT-C-01'):>6} {acc('MSFT-C-02'):>6}  {distract:>9}")

    # ----- Tier 3 dimension means by fill -----
    print()
    print("=" * 130)
    print("TIER 3 — judge dimensions, mean ± stdev across reps × position (3 positions × 7 reps = 21 per cell at non-baseline)")
    print("=" * 130)
    print(f"{'fill':>5} {'q_id':>10}  {'gnd':>10} {'breadth':>10} {'scope':>10} {'clarity':>10} {'cite':>10} {'reasoning':>11}  {'unsup':>5} {'xcontam':>7}")
    print("-" * 130)

    by_fill_q3: dict[tuple, list[dict]] = defaultdict(list)
    for cid, c in by_cell.items():
        for qid, judgements in c["tier3"].items():
            by_fill_q3[(c["fill_pct"], qid)].extend(judgements)

    for (fill, qid) in sorted(by_fill_q3):
        js = by_fill_q3[(fill, qid)]
        gnd = [j["groundedness"] for j in js]
        brd = [j["evidentiary_breadth"] for j in js]
        scp = [j["scope_adherence"] for j in js]
        cla = [j["clarity"] for j in js]
        cit = [j["citation_accuracy"] for j in js]
        rq  = [j["reasoning_quality"] for j in js]
        unsup = [j["unsupported_claims"] for j in js]
        xc    = [j["cross_contamination"] for j in js]
        print(f"{fill:>5.2f} {qid:>10}  {fmt_mean_sd(gnd):>10} {fmt_mean_sd(brd):>10} "
              f"{fmt_mean_sd(scp):>10} {fmt_mean_sd(cla):>10} {fmt_mean_sd(cit):>10} "
              f"{fmt_mean_sd(rq, prec=1):>11}  {fmt_mean_sd(unsup, prec=1):>5} {fmt_mean_sd(xc, prec=1):>7}")

    # ----- Q8 structural diagnostics -----
    print()
    print("=" * 95)
    print("Q8 STRUCTURAL DIAGNOSTICS by fill (units_decomposed, frameworks_applied, synthesis_consistent%)")
    print("=" * 95)
    print(f"{'fill':>5}  {'units':>10} {'frameworks':>12} {'synth_consistent':>17}  n")
    print("-" * 95)
    for fill in sorted({c["fill_pct"] for c in by_cell.values()}):
        js = by_fill_q3.get((fill, "MSFT-S-03"), [])
        if not js: continue
        ud = [j["units_decomposed"] for j in js if j.get("units_decomposed") is not None]
        fa = [j["frameworks_applied"] for j in js if j.get("frameworks_applied") is not None]
        sc = [1 if j.get("synthesis_consistent") else 0 for j in js if j.get("synthesis_consistent") is not None]
        sc_pct = (100 * sum(sc) / len(sc)) if sc else 0
        print(f"{fill:>5.2f}  {fmt_mean_sd(ud, prec=1):>10} {fmt_mean_sd(fa, prec=1):>12} {sc_pct:>13.0f}%   {len(js)}")

    # ----- Pairwise verdict distribution -----
    print()
    print("=" * 90)
    print("PAIRWISE vs BASELINE (Opus 4.7 max thinking, 25% subsample of non-baseline reps)")
    print("=" * 90)
    print(f"{'fill':>5}  {'wins':>5} {'losses':>7} {'ties':>5}  {'mean Δ (cand−base, +ve=cand wins)':>40}  n")
    print("-" * 90)
    pairs_by_fill: dict[float, list[tuple]] = defaultdict(list)
    for cid, c in by_cell.items():
        if c["fill_pct"] == 0.0: continue
        for qid, pws in c["pairwise"].items():
            pairs_by_fill[c["fill_pct"]].extend(pws)
    for fill in sorted(pairs_by_fill):
        pws = pairs_by_fill[fill]
        wins = sum(1 for _, _, cw, _ in pws if cw)
        losses = sum(1 for _, _, _, bw in pws if bw)
        ties = len(pws) - wins - losses
        deltas = [d for _, d, _, _ in pws]
        print(f"{fill:>5.2f}  {wins:>5} {losses:>7} {ties:>5}  {fmt_mean_sd(deltas, prec=1):>40}  {len(pws)}")

    # ----- Sonnet vs Opus per-dimension agreement (RUBRIC §Judge-model agreement) -----
    # Pair by (run_id, q_id) — the deterministic 20% subsample puts Sonnet on the
    # same response Opus rated, so this is a true paired-rater design.
    print()
    print("=" * 95)
    print("CROSS-MODEL JUDGE AGREEMENT (Opus 4.7 primary vs Sonnet 4.6 secondary, 20% subsample)")
    print("RUBRIC.md §Judge-model agreement: ICC(2,1) and Lin's CCC per dimension; flag if < 0.70.")
    print("=" * 95)

    # Re-load graded files keyed by (run_id, q_id) so we can match Opus and Sonnet
    # ratings on the same response (rather than the previous element-wise hack).
    paired: dict[tuple[str, str], dict[str, dict]] = {}
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            key = (r["run_id"], r["q_id"])
            slot = paired.setdefault(key, {})
            if r.get("absolute"): slot["primary"] = r["absolute"]
            if r.get("secondary"): slot["secondary"] = r["secondary"]

    paired_full = [(p["primary"], p["secondary"]) for p in paired.values()
                   if "primary" in p and "secondary" in p]

    if not paired_full:
        print("  no Sonnet secondary records found")
        return 0

    DIMENSIONS = [
        ("groundedness",        1, 5),
        ("evidentiary_breadth", 1, 5),
        ("scope_adherence",     1, 5),
        ("clarity",             1, 5),
        ("citation_accuracy",   1, 5),
        ("reasoning_quality",   0, 10),
    ]

    print(f"{'dimension':<22} {'n':>4}  {'Opus μ':>7} {'Son μ':>7} {'Δ μ':>7}  "
          f"{'Pearson r':>10} {'ICC(2,1)':>10} {'Lin CCC':>10}  flag")
    print("-" * 95)

    for name, _lo, _hi in DIMENSIONS:
        xs = [p[0].get(name) for p in paired_full]
        ys = [p[1].get(name) for p in paired_full]
        # Drop pairs where either side is None.
        pairs_d = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
        if not pairs_d:
            continue
        n = len(pairs_d)
        xs_d = [float(x) for x, _ in pairs_d]
        ys_d = [float(y) for _, y in pairs_d]

        mx, my = statistics.mean(xs_d), statistics.mean(ys_d)
        ccc, r = lins_ccc(xs_d, ys_d)
        icc = icc21(xs_d, ys_d)

        flag = ""
        if ccc < 0.70 or icc < 0.70:
            flag = "⚠ < 0.70 — fall back to pairwise per RUBRIC §Judge-model agreement"

        print(f"{name:<22} {n:>4}  {mx:>7.2f} {my:>7.2f} {mx - my:>+7.2f}  "
              f"{r:>10.3f} {icc:>10.3f} {ccc:>10.3f}  {flag}")

    return 0


# ---- agreement statistics -------------------------------------------------

def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation. Returns 0.0 if either side has zero variance."""
    n = len(xs)
    if n < 2: return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom = (sxx * syy) ** 0.5
    return sxy / denom if denom > 0 else 0.0


def lins_ccc(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """
    Lin's Concordance Correlation Coefficient.

    Decomposes agreement into precision (Pearson r) and accuracy (bias correction
    factor C_b that penalises mean / variance shifts between raters):

        ρ_c = (2 ρ σ_x σ_y) / (σ_x² + σ_y² + (μ_x − μ_y)²)
            = ρ · C_b

    Returns (ccc, pearson_r). Range: [-1, 1]. ≥ 0.70 is the RUBRIC.md threshold
    for "use absolute scores"; < 0.70 ⇒ fall back to pairwise.
    """
    n = len(xs)
    if n < 2:
        return 0.0, 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    # Population variance (divisor n) — Lin's original formulation.
    vx = sum((x - mx) ** 2 for x in xs) / n
    vy = sum((y - my) ** 2 for y in ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    denom = vx + vy + (mx - my) ** 2
    if denom == 0:
        return (1.0 if mx == my else 0.0), 1.0
    ccc = (2 * cov) / denom
    r = _pearson(xs, ys)
    return ccc, r


def icc21(xs: list[float], ys: list[float]) -> float:
    """
    Intraclass correlation, two-way random, single rater, absolute agreement
    — ICC(2,1) per Shrout & Fleiss (1979). Treats each (Opus, Sonnet) rating
    as a measurement of the same underlying response by two random raters.

        ICC(2,1) = (MS_R − MS_E) / (MS_R + (k−1)·MS_E + k·(MS_C − MS_E)/n)

    where R = rows (responses), C = columns (raters), k = 2 raters,
    n = number of responses. Returns 0.0 on degenerate input.
    """
    n = len(xs)
    k = 2
    if n < 2:
        return 0.0

    # Row means (per-response mean across the two raters).
    row_means = [(x + y) / 2 for x, y in zip(xs, ys)]
    # Column means.
    col_means = [sum(xs) / n, sum(ys) / n]
    grand = sum(row_means) / n

    # Mean-square decomposition.
    ms_rows = (k * sum((rm - grand) ** 2 for rm in row_means)) / max(1, n - 1)
    ms_cols = (n * sum((cm - grand) ** 2 for cm in col_means)) / max(1, k - 1)

    ss_total = sum((x - grand) ** 2 for x in xs) + sum((y - grand) ** 2 for y in ys)
    ss_within_row = k * sum((rm - grand) ** 2 for rm in row_means)
    ss_between_col = n * sum((cm - grand) ** 2 for cm in col_means)
    ss_error = ss_total - ss_within_row - ss_between_col
    df_error = max(1, (n - 1) * (k - 1))
    ms_error = ss_error / df_error

    denom = ms_rows + (k - 1) * ms_error + (k * (ms_cols - ms_error) / n)
    if denom == 0:
        return 0.0
    return (ms_rows - ms_error) / denom


if __name__ == "__main__":
    raise SystemExit(main())
