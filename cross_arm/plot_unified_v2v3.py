"""Render two figures for the unified v2+v3 report.

1. figures/noise_drift_by_model.png — 5 panels (one per analyst model). Each
   panel: tier-3 reasoning_quality (blended judges) vs fill, two lines (peer
   materials noise vs temporal MSFT noise) with SE error bands. Replaces
   "v2/v3" labels with the actual noise types.

2. figures/capability_matrix.png — heatmap with rows=models, cols=8 cognitive
   dimensions, cells=baseline (no-noise) score. Color encodes rank within the
   column (best=darkest). Each cell annotated with its raw value. Below the
   heatmap, a second compact panel shows worst-cell drop (from §10.2).

Both reuse loaders from build_unified_report.py for one source of truth.
"""
from __future__ import annotations
import sys, statistics, math
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from build_unified_report import (
    ROOT, ALL_ARMS, ARM_INFO, FILLS, POSITIONS,
    load_tier12, load_tier3_original, load_tier3_cross, mean_se,
)

FIGDIR = ROOT / "figures"
FIGDIR.mkdir(exist_ok=True)

# Vendor colors (consistent with plot_drift_signatures.py)
MODEL_COLOR = {
    "opus-4-7":        "#C84630",  # red
    "sonnet-4-6":      "#E89B47",  # orange
    "gpt-5-5":         "#10A37F",  # green
    "gemini-3-1-pro":  "#4285F4",  # blue
    "deepseek-v4-pro": "#7C3AED",  # purple
}
MODEL_DISPLAY = {
    "opus-4-7":        "Opus 4.7",
    "sonnet-4-6":      "Sonnet 4.6",
    "gpt-5-5":         "GPT-5.5",
    "gemini-3-1-pro":  "Gemini 3.1 Pro",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
}

# Noise-type colors (consistent across all 5 panels of fig 1).
# Peer materials = neutral steel blue; temporal MSFT = warm red (the "stressful" condition).
NOISE_COLOR = {
    "peer_materials":  "#3B6A8A",   # steel blue
    "temporal_msft":   "#C84630",   # signal red
}
NOISE_LABEL = {
    "peer_materials":  "Peer-materials noise (other companies' 10-Ks)",
    "temporal_msft":   "Temporal MSFT noise (mismatched-period MSFT docs)",
}

rcParams["font.family"] = "DejaVu Sans"
rcParams["axes.unicode_minus"] = False


# =============================================================================
# Figure 1 — noise drift by model (5 panels, 2 noise lines each)
# =============================================================================

def aggregate_by_fill(records, model, noise, value_key="reasoning_quality"):
    """Return {fill: (mean, se, n)}."""
    by_fill = defaultdict(list)
    for r in records:
        if r.get("model") != model: continue
        if r.get("fill_pct") not in FILLS: continue
        # baseline (fill=0) is shared across noise arms - associate with both
        if r.get("fill_pct") == 0.0 or r.get("noise") == noise:
            v = r.get(value_key)
            if v is not None:
                by_fill[r["fill_pct"]].append(v)
    return {f: mean_se(by_fill[f]) for f in FILLS if by_fill[f]}


def plot_noise_drift(t3):
    models_ordered = ["opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro"]
    fig, axes = plt.subplots(1, 5, figsize=(20, 5.5), dpi=150, sharey=True)
    fig.patch.set_facecolor("white")

    for i, model in enumerate(models_ordered):
        ax = axes[i]
        ax.set_facecolor("#FAFAFA")

        for noise in ["peer_materials", "temporal_msft"]:
            agg = aggregate_by_fill(t3, model, noise)
            xs = sorted(agg.keys())
            xs_pct = [int(x * 100) for x in xs]
            ys = [agg[x][0] for x in xs]
            ses = [agg[x][1] if not math.isnan(agg[x][1]) else 0 for x in xs]
            color = NOISE_COLOR[noise]
            label = NOISE_LABEL[noise].split(" (")[0]  # short label inside panel

            ax.plot(xs_pct, ys, "-o", color=color, lw=2.0, ms=6, label=label,
                    markeredgecolor="white", markeredgewidth=1.2, zorder=3)
            # SE band
            lo = [y - s for y, s in zip(ys, ses)]
            hi = [y + s for y, s in zip(ys, ses)]
            ax.fill_between(xs_pct, lo, hi, color=color, alpha=0.18, zorder=1)

        # Title in vendor color
        ax.set_title(MODEL_DISPLAY[model], color=MODEL_COLOR[model],
                     fontsize=13, fontweight="bold", pad=10)
        ax.set_xticks([0, 25, 50, 75, 95])
        ax.set_xticklabels(["0%", "25%", "50%", "75%", "95%"], fontsize=10)
        ax.set_ylim(3.0, 9.0)
        ax.grid(True, axis="y", color="white", lw=1.5, zorder=0)
        ax.set_axisbelow(True)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color("#666")
        ax.tick_params(colors="#444", labelsize=10)
        ax.set_xlabel("Context fill (analyst-token)", fontsize=10, color="#444")
        if i == 0:
            ax.set_ylabel("Tier-3 reasoning quality (0–10, blended judges)",
                          fontsize=11, color="#222")
        # Mark baseline as a faint dotted vertical
        ax.axvline(0, color="#999", ls=":", lw=0.8, zorder=0)

    # Suptitle + legend below
    fig.suptitle(
        "Reasoning quality drift by analyst model and noise type",
        fontsize=16, fontweight="bold", y=1.02,
    )
    # Subtitle
    fig.text(0.5, 0.965,
             "Mean ± SE across 7 reps × 3 positions × 8 synthesis questions per cell. "
             "Baseline (0% fill) shared across both noise arms.",
             ha="center", fontsize=10.5, color="#555")

    handles = [
        mpatches.Patch(color=NOISE_COLOR["peer_materials"], label=NOISE_LABEL["peer_materials"]),
        mpatches.Patch(color=NOISE_COLOR["temporal_msft"], label=NOISE_LABEL["temporal_msft"]),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False,
               fontsize=11, bbox_to_anchor=(0.5, -0.04))

    plt.tight_layout(rect=[0, 0.02, 1, 0.94])
    out = FIGDIR / "noise_drift_by_model.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")


# =============================================================================
# Figure 2 — capability matrix (heatmap, 5 models × 8 dimensions)
# =============================================================================

def baseline_capability_data(t12, t3):
    """Returns dict[dim_label] -> dict[model] -> mean baseline value."""
    models = ["opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro"]
    out = {}

    def collect_t12(tier, m):
        return [r["score"] for r in t12 if r["model"]==m and r["tier"]==tier and r["fill_pct"]==0.0]
    def collect_t3(dim, m):
        return [r[dim] for r in t3 if r["model"]==m and r["fill_pct"]==0.0 and r.get(dim) is not None]

    dims = [
        ("T1 retrieve\n(0–1)",      lambda m: collect_t12(1, m)),
        ("T2 calculate\n(0–1)",     lambda m: collect_t12(2, m)),
        ("T3 reasoning\n(0–10)",    lambda m: collect_t3("reasoning_quality", m)),
        ("Groundedness\n(0–5)",     lambda m: collect_t3("groundedness", m)),
        ("Evidence breadth\n(0–5)", lambda m: collect_t3("evidentiary_breadth", m)),
        ("Scope adherence\n(0–5)",  lambda m: collect_t3("scope_adherence", m)),
        ("Clarity\n(0–5)",          lambda m: collect_t3("clarity", m)),
        ("Citation accuracy\n(0–5)",lambda m: collect_t3("citation_accuracy", m)),
    ]
    return models, dims


def under_noise_data(t12, t3):
    """Mean across all noise cells (fill >= 25%) per (model, dim)."""
    models = ["opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro"]

    def collect_t12(tier, m):
        return [r["score"] for r in t12 if r["model"]==m and r["tier"]==tier and r["fill_pct"] and r["fill_pct"] >= 0.25]
    def collect_t3(dim, m):
        return [r[dim] for r in t3 if r["model"]==m and r["fill_pct"] and r["fill_pct"] >= 0.25 and r.get(dim) is not None]

    dims = [
        ("T1 retrieve\n(0–1)",      lambda m: collect_t12(1, m)),
        ("T2 calculate\n(0–1)",     lambda m: collect_t12(2, m)),
        ("T3 reasoning\n(0–10)",    lambda m: collect_t3("reasoning_quality", m)),
        ("Groundedness\n(0–5)",     lambda m: collect_t3("groundedness", m)),
        ("Evidence breadth\n(0–5)", lambda m: collect_t3("evidentiary_breadth", m)),
        ("Scope adherence\n(0–5)",  lambda m: collect_t3("scope_adherence", m)),
        ("Clarity\n(0–5)",          lambda m: collect_t3("clarity", m)),
        ("Citation accuracy\n(0–5)",lambda m: collect_t3("citation_accuracy", m)),
    ]
    return models, dims


def render_heatmap(ax, models, dims, *, title, panel_label, cmap="YlOrBr"):
    """Render one heatmap on `ax` and annotate."""
    # Build value matrix
    M = np.full((len(models), len(dims)), np.nan)
    for j, (dname, fn) in enumerate(dims):
        for i, m in enumerate(models):
            vs = fn(m)
            if vs:
                M[i, j] = float(np.mean(vs))

    # Normalize each column to [0, 1] for color: best=1, worst=0
    Mnorm = np.full_like(M, np.nan)
    for j in range(M.shape[1]):
        col = M[:, j]
        valid = ~np.isnan(col)
        if not valid.any():
            continue
        cmin, cmax = np.nanmin(col), np.nanmax(col)
        if cmax - cmin < 1e-9:
            Mnorm[:, j] = 1.0
        else:
            Mnorm[:, j] = (col - cmin) / (cmax - cmin)

    im = ax.imshow(Mnorm, aspect="auto", cmap=cmap, vmin=0, vmax=1)

    # Annotate each cell with raw value + rank
    for j in range(M.shape[1]):
        col = M[:, j]
        order = np.argsort(-col)  # descending; best first
        rank_of = {idx: r + 1 for r, idx in enumerate(order)}
        for i in range(M.shape[0]):
            v = M[i, j]
            if np.isnan(v): continue
            txt_color = "#222" if Mnorm[i, j] < 0.55 else "#fff"
            rk = rank_of[i]
            rank_marker = "★" if rk == 1 else ""
            ax.text(j, i, f"{v:.2f}{rank_marker}",
                    ha="center", va="center",
                    color=txt_color, fontsize=10,
                    fontweight=("bold" if rk == 1 else "normal"))

    ax.set_xticks(range(len(dims)))
    ax.set_xticklabels([d[0] for d in dims], fontsize=9.5, color="#222")
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([MODEL_DISPLAY[m] for m in models], fontsize=11)
    # color y-tick labels by vendor
    for tick, m in zip(ax.get_yticklabels(), models):
        tick.set_color(MODEL_COLOR[m])
        tick.set_fontweight("bold")

    ax.set_title(title, fontsize=13, fontweight="bold", pad=10, loc="left")
    # Panel label in top-right corner
    ax.text(1.0, 1.03, panel_label, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=10, color="#777", style="italic")
    # No grid lines on heatmap, but separator lines
    ax.set_xticks(np.arange(-.5, len(dims), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(models), 1), minor=True)
    ax.grid(which="minor", color="white", lw=2)
    ax.tick_params(which="minor", length=0)
    ax.tick_params(which="major", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return im


def plot_capability_matrix(t12, t3):
    fig, axes = plt.subplots(2, 1, figsize=(15, 9), dpi=150,
                              gridspec_kw={"hspace": 0.55})
    fig.patch.set_facecolor("white")

    # Top: baseline
    models, dims = baseline_capability_data(t12, t3)
    im1 = render_heatmap(
        axes[0], models, dims,
        title="Baseline capability (no noise, fill = 0%)",
        panel_label="★ = best in column · color = rank within column",
    )

    # Bottom: under noise (mean across all noise cells, fill >= 25%)
    models, dims = under_noise_data(t12, t3)
    im2 = render_heatmap(
        axes[1], models, dims,
        title="Performance under noise (mean across all noise cells, fill ≥ 25%)",
        panel_label="lower scores expected — read color, not absolute value, vs baseline",
    )

    fig.suptitle(
        "Per-model capability profile across 8 cognitive dimensions",
        fontsize=16, fontweight="bold", y=0.99,
    )
    fig.text(0.5, 0.945,
             "Top: clean-input ceiling. Bottom: realistic operating performance under context-window stress. "
             "Color: column-normalized rank.",
             ha="center", fontsize=10.5, color="#555")

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out = FIGDIR / "capability_matrix.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")


# =============================================================================
# main
# =============================================================================

def main():
    print("loading data...", file=sys.stderr)
    t12 = []
    t3 = []
    for arm in ALL_ARMS:
        t12.extend(load_tier12(arm))
        t3.extend(load_tier3_original(arm))
        t3.extend(load_tier3_cross(arm))
    print(f"  tier12={len(t12)}, tier3={len(t3)}", file=sys.stderr)

    plot_noise_drift(t3)
    plot_capability_matrix(t12, t3)


if __name__ == "__main__":
    main()
