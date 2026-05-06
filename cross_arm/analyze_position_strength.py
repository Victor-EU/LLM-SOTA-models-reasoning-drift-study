"""Analyze (1) noise-position effects and (2) per-model strength profile.

Reuses loaders from build_unified_report.py to keep one source of truth.

Q1 — Position effects:
    For each (model, noise) cell, aggregate scores by position (start/middle/end)
    pooling across fill levels >= 0.25, and per fill level. Report mean ± SE,
    delta vs row mean, and a model-level "position spread" (max − min position
    means) to surface whether any model has a systematic position bias.
    Compare position-spread vs fill-spread to put it in scale.

Q2 — Per-model strength:
    Build a baseline-only matrix: rows = model, cols = each cognitive dimension.
    Then a noise-resilience matrix: how much each model loses from baseline to
    worst-cell per dimension. Identifies what each model is best at and what
    decays fastest under load.
"""
from __future__ import annotations
import sys, statistics, math
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_unified_report import (
    ROOT, ARMS_V2, ARMS_V3, ALL_ARMS, ARM_INFO, JUDGES,
    FILLS, POSITIONS, T3_DIMS,
    load_tier12, load_tier3_original, load_tier3_cross, mean_se, fmt,
)


# =======================
# Q1 — POSITION EFFECTS
# =======================

def position_aggregate(records, value_key, *, model_filter=None, noise_filter=None,
                       fill_filter=None, judge_filter=None):
    """Group by position, return {position: (mean, se, n)}."""
    buckets = defaultdict(list)
    for r in records:
        if model_filter and r.get("model") != model_filter: continue
        if noise_filter and r.get("noise") != noise_filter: continue
        if fill_filter is not None and r.get("fill_pct") != fill_filter: continue
        if judge_filter and r.get("judge") != judge_filter: continue
        if r.get("position") not in POSITIONS: continue
        v = r.get(value_key)
        if v is not None:
            buckets[r["position"]].append(v)
    return {p: mean_se(vs) for p, vs in buckets.items()}


def position_table(records, value_key, *, judge_filter=None, scale="0-10"):
    """Table: rows = (model, noise), cols = start / middle / end / row mean / spread.

    Pools across all noise fills (>= 25%), excludes baseline.
    """
    out = [
        f"| model | noise | start | middle | end | mean | spread (max−min) |",
        f"|-------|-------|-------|--------|-----|-----:|-----------------:|",
    ]
    # Filter records to noise fills only
    noise_records = [r for r in records if r.get("fill_pct") and r["fill_pct"] >= 0.25]
    pos_spreads = []
    for arm in ALL_ARMS:
        model, noise = ARM_INFO[arm]
        agg = position_aggregate(noise_records, value_key,
                                  model_filter=model, noise_filter=noise,
                                  judge_filter=judge_filter)
        # row-pooled mean
        all_vals = []
        for r in noise_records:
            if r.get("model") == model and r.get("noise") == noise:
                if judge_filter and r.get("judge") != judge_filter: continue
                v = r.get(value_key)
                if v is not None and r.get("position") in POSITIONS:
                    all_vals.append(v)
        rm, rs, rn = mean_se(all_vals)
        cells = []
        means_only = []
        for pos in POSITIONS:
            ms = agg.get(pos)
            if ms and not math.isnan(ms[0]):
                cells.append(f"{ms[0]:.2f} ± {ms[1]:.2f}")
                means_only.append(ms[0])
            else:
                cells.append("—")
        spread = max(means_only) - min(means_only) if len(means_only) >= 2 else float("nan")
        pos_spreads.append((arm, spread))
        spread_str = f"{spread:.2f}" if not math.isnan(spread) else "—"
        # mark significant spreads (loose heuristic: >2× max SE)
        max_se = max((agg[p][1] for p in agg if not math.isnan(agg[p][1])), default=float("nan"))
        marker = ""
        if not math.isnan(spread) and not math.isnan(max_se) and spread > 2 * max_se:
            marker = " ⚠"
        out.append(f"| {model} | {noise.replace('_',' ')} | {cells[0]} | {cells[1]} | {cells[2]} | {fmt(rm,rs)} | **{spread_str}**{marker} |")
    return "\n".join(out), pos_spreads


def position_by_fill_table(records, value_key, model, noise, *, judge_filter=None):
    """For one (model, noise): rows = fill, cols = start/middle/end."""
    out = [
        f"### {model} / {noise} — {value_key} by (fill × position)",
        f"",
        f"| fill | start | middle | end | row spread |",
        f"|-----:|-------|--------|-----|-----------:|",
    ]
    for f in FILLS[1:]:
        agg = position_aggregate(records, value_key,
                                  model_filter=model, noise_filter=noise,
                                  fill_filter=f, judge_filter=judge_filter)
        means_only = []
        cells = []
        for pos in POSITIONS:
            ms = agg.get(pos)
            if ms and not math.isnan(ms[0]):
                cells.append(f"{ms[0]:.2f} ± {ms[1]:.2f}")
                means_only.append(ms[0])
            else:
                cells.append("—")
        spread = max(means_only) - min(means_only) if len(means_only) >= 2 else float("nan")
        spread_str = f"{spread:.2f}" if not math.isnan(spread) else "—"
        out.append(f"| {int(f*100)}% | {cells[0]} | {cells[1]} | {cells[2]} | {spread_str} |")
    return "\n".join(out)


def position_vs_fill_variance(records, value_key, *, judge_filter=None):
    """For each (model, noise): compute fill-spread (mean@95% − mean@25%) vs
    position-spread (max position mean − min position mean, pooled across fills).
    """
    out = [
        f"| model | noise | fill spread (25%→95%) | position spread (pooled) | ratio (fill/position) |",
        f"|-------|-------|----------------------:|-------------------------:|----------------------:|",
    ]
    for arm in ALL_ARMS:
        model, noise = ARM_INFO[arm]
        rs = [r for r in records if r.get("model") == model and r.get("noise") == noise]
        if judge_filter:
            rs = [r for r in rs if r.get("judge") == judge_filter]
        # fill spread: 25% mean vs 95% mean
        v25 = [r[value_key] for r in rs if r.get("fill_pct") == 0.25 and r.get(value_key) is not None]
        v95 = [r[value_key] for r in rs if r.get("fill_pct") == 0.95 and r.get(value_key) is not None]
        fill_spread = (statistics.mean(v95) - statistics.mean(v25)) if (v25 and v95) else float("nan")
        # position spread (pooled, fills >= 25%)
        agg = position_aggregate(rs, value_key)
        means_only = [agg[p][0] for p in agg if not math.isnan(agg[p][0])]
        pos_spread = max(means_only) - min(means_only) if len(means_only) >= 2 else float("nan")
        ratio = abs(fill_spread / pos_spread) if (pos_spread and not math.isnan(pos_spread) and pos_spread > 0.01) else float("nan")
        fs = f"{fill_spread:+.2f}" if not math.isnan(fill_spread) else "—"
        ps = f"{pos_spread:.2f}" if not math.isnan(pos_spread) else "—"
        rs_ = f"{ratio:.1f}×" if not math.isnan(ratio) else "—"
        out.append(f"| {model} | {noise.replace('_',' ')} | {fs} | {ps} | {rs_} |")
    return "\n".join(out)


# =================================
# Q2 — PER-MODEL STRENGTH PROFILE
# =================================

def baseline_strength_matrix(t12, t3):
    """Rows = model, cols = (T1 retrieve, T2 calc, T3 reasoning, T3 grounded,
    T3 evidence, T3 clarity, T3 citation). Tier-3 cols use blended judges.
    Baseline only (fill=0)."""
    models = ["opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro"]
    # tier-1
    t1 = {m: [r["score"] for r in t12 if r["model"]==m and r["tier"]==1 and r["fill_pct"]==0.0] for m in models}
    t2 = {m: [r["score"] for r in t12 if r["model"]==m and r["tier"]==2 and r["fill_pct"]==0.0] for m in models}
    # tier-3 baseline blended (fill=0, only "peer arm" baseline records — they're identical to temporal arm baselines for autograde, but tier-3 baseline records are duplicated across both arms; we use one)
    def t3_dim(m, dim):
        # use ALL judge records for baseline, both noise arms (baselines are independent reps but generated separately under each arm — pool both for higher n at baseline)
        return [r[dim] for r in t3 if r["model"]==m and r["fill_pct"]==0.0 and r.get(dim) is not None]

    cols = [
        ("T1 retrieve (0-1)", lambda m: t1[m]),
        ("T2 calc (0-1)", lambda m: t2[m]),
        ("T3 reasoning (0-10)", lambda m: t3_dim(m, "reasoning_quality")),
        ("T3 grounded (0-5)", lambda m: t3_dim(m, "groundedness")),
        ("T3 evidence (0-5)", lambda m: t3_dim(m, "evidentiary_breadth")),
        ("T3 scope (0-5)", lambda m: t3_dim(m, "scope_adherence")),
        ("T3 clarity (0-5)", lambda m: t3_dim(m, "clarity")),
        ("T3 citation (0-5)", lambda m: t3_dim(m, "citation_accuracy")),
    ]

    header = "| model | " + " | ".join(c[0] for c in cols) + " |"
    sep = "|---" * (len(cols) + 1) + "|"
    out = [header, sep]
    # also collect for ranking
    cell_means = defaultdict(dict)
    for m in models:
        row = [m]
        for cname, fn in cols:
            vs = fn(m)
            mn, se, n = mean_se(vs)
            row.append(fmt(mn, se))
            cell_means[cname][m] = mn
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out), cell_means


def rank_summary(cell_means):
    """Per dimension: sort models by mean. Print rank order + gap."""
    out = ["", "**Per-dimension ranking (baseline; best → worst):**", ""]
    for dim, by_model in cell_means.items():
        ranked = sorted(by_model.items(), key=lambda x: -x[1] if not math.isnan(x[1]) else 99)
        line = f"- **{dim}**: " + " > ".join(f"{m} ({v:.2f})" for m, v in ranked if not math.isnan(v))
        out.append(line)
    return "\n".join(out)


def resilience_matrix(t12, t3):
    """How much each model loses from baseline to worst noise cell, per dimension.

    "Worst cell" = (fill, position, noise) cell with lowest mean. Reported as
    raw drop and as % of baseline (where applicable).
    """
    models = ["opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro"]
    def worst_drop(records, m, value_key, judge_filter=None):
        # baseline
        base = [r[value_key] for r in records if r.get("model")==m and r.get("fill_pct")==0.0
                and r.get(value_key) is not None and (not judge_filter or r.get("judge")==judge_filter)]
        b = statistics.mean(base) if base else float("nan")
        # cells
        cells = defaultdict(list)
        for r in records:
            if r.get("model")!=m or r.get("fill_pct")==0.0: continue
            if judge_filter and r.get("judge")!=judge_filter: continue
            if r.get(value_key) is None: continue
            cells[(r["noise"], r["fill_pct"], r["position"])].append(r[value_key])
        if not cells:
            return (b, float("nan"), float("nan"), None)
        cell_means = {k: statistics.mean(v) for k, v in cells.items()}
        worst_k = min(cell_means, key=lambda k: cell_means[k])
        w = cell_means[worst_k]
        drop = w - b
        drop_pct = 100 * drop / b if b > 0.01 else float("nan")
        return (b, w, drop_pct, worst_k)

    cols = [
        ("T1 retrieve", t12, "score", None, lambda r: r["tier"]==1),
        ("T2 calc", t12, "score", None, lambda r: r["tier"]==2),
        ("T3 reasoning (blended)", t3, "reasoning_quality", None, lambda r: True),
        ("T3 grounded (blended)", t3, "groundedness", None, lambda r: True),
        ("T3 evidence (blended)", t3, "evidentiary_breadth", None, lambda r: True),
        ("T3 clarity (blended)", t3, "clarity", None, lambda r: True),
    ]
    out = [
        "| model | dimension | baseline | worst-cell | drop % | worst (noise/fill/pos) |",
        "|-------|-----------|---------:|-----------:|-------:|------------------------|",
    ]
    for m in models:
        for cname, src, key, jf, fn in cols:
            sub = [r for r in src if fn(r)]
            b, w, pct, wk = worst_drop(sub, m, key, judge_filter=jf)
            if math.isnan(b):
                out.append(f"| {m} | {cname} | — | — | — | — |")
                continue
            wkstr = f"{wk[0]} / {int(wk[1]*100)}% / {wk[2]}" if wk else "—"
            pct_str = f"{pct:+.1f}%" if not math.isnan(pct) else "—"
            out.append(f"| {m} | {cname} | {b:.2f} | {w:.2f} | {pct_str} | {wkstr} |")
    return "\n".join(out)


def best_at_what(t12, t3):
    """Distill: under noise (mean across all noise cells), who is best at what?"""
    models = ["opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro"]
    def noise_mean(records, m, value_key, judge_filter=None, tier_fn=None):
        vs = [r[value_key] for r in records if r.get("model")==m
              and r.get("fill_pct") and r["fill_pct"] >= 0.25
              and r.get(value_key) is not None
              and (not judge_filter or r.get("judge")==judge_filter)
              and (not tier_fn or tier_fn(r))]
        return statistics.mean(vs) if vs else float("nan")

    cols = [
        ("T1 retrieve under noise", t12, "score", None, lambda r: r["tier"]==1),
        ("T2 calc under noise", t12, "score", None, lambda r: r["tier"]==2),
        ("T3 reasoning under noise", t3, "reasoning_quality", None, None),
        ("T3 grounded under noise", t3, "groundedness", None, None),
        ("T3 evidence under noise", t3, "evidentiary_breadth", None, None),
        ("T3 clarity under noise", t3, "clarity", None, None),
        ("T3 citation under noise", t3, "citation_accuracy", None, None),
    ]
    out = ["", "**Best-under-noise ranking (mean across all noise cells, fill ≥ 25%):**", ""]
    for cname, src, key, jf, tf in cols:
        scores = []
        for m in models:
            v = noise_mean(src, m, key, judge_filter=jf, tier_fn=tf)
            scores.append((m, v))
        scores.sort(key=lambda x: -x[1] if not math.isnan(x[1]) else 99)
        line = f"- **{cname}**: " + " > ".join(f"{m} ({v:.2f})" for m, v in scores if not math.isnan(v))
        out.append(line)
    return "\n".join(out)


def main():
    print("# loading data...", file=sys.stderr)
    t12 = []
    t3 = []
    for arm in ALL_ARMS:
        t12.extend(load_tier12(arm))
        t3.extend(load_tier3_original(arm))
        t3.extend(load_tier3_cross(arm))
    print(f"# tier12={len(t12)}, tier3={len(t3)}", file=sys.stderr)

    print("\n# ============================")
    print("# Q1 — POSITION EFFECTS")
    print("# ============================\n")

    print("## 1.1 Tier-3 reasoning_quality, blended judges (pooled across noise fills)\n")
    tbl, _ = position_table(t3, "reasoning_quality")
    print(tbl)
    print()
    print("## 1.2 Tier-3 reasoning_quality per individual judge\n")
    for j in JUDGES:
        print(f"### Judge: {j}\n")
        tbl, _ = position_table(t3, "reasoning_quality", judge_filter=j)
        print(tbl)
        print()

    print("## 1.3 Tier-1 retrieval (autograded)\n")
    tbl, _ = position_table([r for r in t12 if r["tier"]==1], "score")
    print(tbl)
    print()

    print("## 1.4 Tier-2 calculation (autograded)\n")
    tbl, _ = position_table([r for r in t12 if r["tier"]==2], "score")
    print(tbl)
    print()

    print("## 1.5 Position spread vs fill spread (Tier-3 reasoning, blended)\n")
    print(position_vs_fill_variance(t3, "reasoning_quality"))
    print()

    print("## 1.6 Position spread vs fill spread (Tier-1 retrieval)\n")
    print(position_vs_fill_variance([r for r in t12 if r["tier"]==1], "score"))
    print()

    print("## 1.7 Drill-in: any (fill × position) interaction for outlier arms?\n")
    for model, noise in [("sonnet-4-6", "temporal_msft"),
                         ("deepseek-v4-pro", "peer_materials"),
                         ("opus-4-7", "temporal_msft")]:
        print(position_by_fill_table(t3, "reasoning_quality", model, noise))
        print()
        print(position_by_fill_table([r for r in t12 if r["tier"]==1], "score", model, noise))
        print()

    print("\n# ============================")
    print("# Q2 — PER-MODEL STRENGTH PROFILE")
    print("# ============================\n")

    print("## 2.1 Baseline (fill=0) strength matrix\n")
    tbl, cell_means = baseline_strength_matrix(t12, t3)
    print(tbl)
    print()
    print(rank_summary(cell_means))
    print()

    print("## 2.2 Worst-cell drop matrix (resilience)\n")
    print(resilience_matrix(t12, t3))
    print()

    print("## 2.3 Best-under-noise ranking (collapses fill+position+judge)\n")
    print(best_at_what(t12, t3))
    print()


if __name__ == "__main__":
    main()
