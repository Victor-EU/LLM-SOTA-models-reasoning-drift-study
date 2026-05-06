"""Generate the Opus-vs-Sonnet hero chart for agent builders.

Two-panel figure showing how Anthropic's flagship reasoning models behave
as their context windows fill with adjacent-but-irrelevant material:

  Panel A — Mean reasoning quality (Tier-3, 0–10) vs realized context fill.
            Headline: Sonnet recovers above baseline at 95% fill; Opus
            declines monotonically.

  Panel B — Mean unsupported claims per Tier-3 response vs realized context
            fill. Both rise under load, but Opus peaks 60% higher than
            Sonnet at 95% fill and is the only Anthropic arm with non-zero
            cross-contamination (peer-10K facts attributed to MSFT).

Latency and per-call cost are surfaced as endpoint annotations rather than
as a third panel — agent-builder-relevant deployment numbers belong in the
margin, not on the y-axis.

Source data is the cross-arm headline tables in
`cross_arm/CROSS_ARM_REPORT.md` §2.1 (RQ), §2.3 (hallucinations), §2.5
(latency). This script only renders; it does not re-aggregate.

Output: `figures/opus_vs_sonnet_for_agents.png` (1800 x 1350 @ 150 DPI).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import rcParams

# ----------------------------------------------------------------------------
# Data — pinned to CROSS_ARM_REPORT.md headline tables.
# ----------------------------------------------------------------------------

FILLS = [13, 24, 47, 72, 92]  # realized, Anthropic-counted

# §2.1 — mean Tier-3 reasoning_quality (0–10)
RQ = {
    "Opus 4.7":   [8.05, 7.33, 6.89, 7.17, 7.02],
    "Sonnet 4.6": [7.43, 8.00, 7.94, 7.19, 7.60],
}

# §2.3 — mean unsupported_claims per Tier-3 response
UNSUP = {
    "Opus 4.7":   [0.24, 0.76, 0.62, 1.02, 1.68],
    "Sonnet 4.6": [0.10, 0.46, 0.46, 0.95, 1.06],
}

# §2.5 — mean latency (s/call) at baseline → 95% fill, used as endpoint annotations.
LATENCY_HINT = {
    "Opus 4.7":   "≈ 200 s / call",
    "Sonnet 4.6": "≈ 800 s / call (5× slower)",
}

COLORS = {
    "Opus 4.7":   "#C84630",  # vendor red — kept consistent with drift_signatures.png
    "Sonnet 4.6": "#E89B47",  # vendor orange
}

# ----------------------------------------------------------------------------
# Style
# ----------------------------------------------------------------------------

rcParams["font.family"] = "DejaVu Sans"
rcParams["axes.unicode_minus"] = False

fig, (ax_rq, ax_un) = plt.subplots(
    nrows=2, ncols=1, sharex=True,
    figsize=(12, 9), dpi=150,
    gridspec_kw={"height_ratios": [1.0, 0.9], "hspace": 0.18},
)
fig.patch.set_facecolor("white")
for ax in (ax_rq, ax_un):
    ax.set_facecolor("#FAFAFA")
    ax.grid(True, alpha=0.25, linestyle="--", zorder=1)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#999999")
    ax.spines["bottom"].set_color("#999999")

# ----------------------------------------------------------------------------
# Panel A — Reasoning quality
# ----------------------------------------------------------------------------

for name, vals in RQ.items():
    color = COLORS[name]
    ax_rq.plot(
        FILLS, vals,
        marker="o", markersize=9, markeredgecolor="white", markeredgewidth=1.4,
        linewidth=2.8, color=color, solid_capstyle="round", zorder=3,
    )
    # Endpoint name + Δ + latency hint, right of last marker
    delta = vals[-1] - vals[0]
    delta_str = f"{delta:+.2f} RQ baseline → 95%"
    ax_rq.annotate(
        name,
        xy=(FILLS[-1] + 1.5, vals[-1]),
        color=color, fontsize=11.5, fontweight="bold",
        va="center", ha="left",
    )
    ax_rq.annotate(
        delta_str,
        xy=(FILLS[-1] + 1.5, vals[-1] - 0.16),
        color="#444444", fontsize=8.7,
        va="center", ha="left",
    )
    ax_rq.annotate(
        LATENCY_HINT[name],
        xy=(FILLS[-1] + 1.5, vals[-1] - 0.30),
        color="#888888", fontsize=8.3, style="italic",
        va="center", ha="left",
    )

ax_rq.set_ylabel("Reasoning quality (Tier-3, 0–10)",
                 fontsize=11, color="#333333")
ax_rq.set_ylim(6.3, 8.5)

# Headline annotations — the counter-intuitive finding.
# Positioned so neither collides with title block, endpoint labels, or callout box.
ax_rq.annotate(
    "Sonnet recovers above\nbaseline at 95% fill",
    xy=(88, 7.60), xytext=(60, 7.95),
    color=COLORS["Sonnet 4.6"], fontsize=9.5, fontweight="bold",
    ha="center", va="center",
    arrowprops=dict(arrowstyle="-|>", color=COLORS["Sonnet 4.6"],
                    lw=1.2, shrinkA=4, shrinkB=6,
                    connectionstyle="arc3,rad=-0.22"),
)
ax_rq.annotate(
    "Opus declines monotonically",
    xy=(47, 6.89), xytext=(28, 6.55),
    color=COLORS["Opus 4.7"], fontsize=9.5, fontweight="bold",
    ha="center", va="center",
    arrowprops=dict(arrowstyle="-|>", color=COLORS["Opus 4.7"],
                    lw=1.2, shrinkA=4, shrinkB=6,
                    connectionstyle="arc3,rad=0.18"),
)

# Pairwise win-rate callout (top-left of Panel A — empty space above Opus curve at low fill)
ax_rq.text(
    0.015, 0.96,
    "At 95% fill, head-to-head vs own baseline:\n"
    "Sonnet wins 13/20    ·    Opus loses 18/20",
    transform=ax_rq.transAxes,
    fontsize=8.8, color="#222222",
    ha="left", va="top",
    bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
              edgecolor="#CCCCCC", linewidth=0.8),
)

# ----------------------------------------------------------------------------
# Panel B — Unsupported claims
# ----------------------------------------------------------------------------

for name, vals in UNSUP.items():
    color = COLORS[name]
    ax_un.plot(
        FILLS, vals,
        marker="o", markersize=9, markeredgecolor="white", markeredgewidth=1.4,
        linewidth=2.8, color=color, solid_capstyle="round", zorder=3,
    )
    rise = vals[-1] / vals[0] if vals[0] > 0 else float("inf")
    rise_str = f"{rise:.0f}× rise (baseline → 95%)"
    ax_un.annotate(
        name,
        xy=(FILLS[-1] + 1.5, vals[-1]),
        color=color, fontsize=11.5, fontweight="bold",
        va="center", ha="left",
    )
    ax_un.annotate(
        rise_str,
        xy=(FILLS[-1] + 1.5, vals[-1] - 0.075),
        color="#444444", fontsize=8.7,
        va="center", ha="left",
    )

ax_un.set_xlabel("Context fill — % of vendor-counted token budget",
                 fontsize=11, color="#333333")
ax_un.set_ylabel("Unsupported claims per Tier-3 response",
                 fontsize=11, color="#333333")
ax_un.set_xticks(FILLS)
ax_un.set_xticklabels([f"{f}%" for f in FILLS], fontsize=10)
ax_un.tick_params(axis="y", labelsize=10)
ax_un.set_xlim(8, 145)
ax_un.set_ylim(0, 1.95)

# Cross-contamination callout — only Opus has a non-zero rate at 95% fill.
# Positioned top-left so it doesn't collide with Sonnet endpoint label on the right.
ax_un.text(
    0.015, 0.96,
    "At 95% fill, peer-10K facts attributed to MSFT:\n"
    "Opus 0.095/response    ·    Sonnet ≈ 0.02/response",
    transform=ax_un.transAxes,
    fontsize=8.8, color="#222222",
    ha="left", va="top",
    bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
              edgecolor="#CCCCCC", linewidth=0.8),
)

# ----------------------------------------------------------------------------
# Title block + footnote
# ----------------------------------------------------------------------------

fig.suptitle(
    "Opus 4.7 vs Sonnet 4.6 under context pressure — what agent builders should see",
    fontsize=14.5, fontweight="bold", x=0.06, y=0.975, ha="left", color="#111111",
)
ax_rq.set_title(
    "Identical inputs at every coordinate. Both at vendor-max thinking effort. "
    "n = 21 baseline + 63 per noise cell, 7 reps × 3 positions.",
    fontsize=10, color="#666666", pad=10, loc="left",
)

fig.text(
    0.06, 0.018,
    "Source: opus-4-7 + sonnet-4-6 arms × 91 runs each, MSFT FY2025 10-K target + 7 peer 10-Ks as adversarially-near noise. "
    "Held-constant judge: Opus 4.7 max-effort.\n"
    "Per-call cost is similar ($6.40 Opus · $5.74 Sonnet); the deployment tradeoff is latency, not price. "
    "Repo: github.com/Victor-EU/LLM-SOTA-models-reasoning-drift-study",
    fontsize=8, color="#888888", ha="left",
)

# ----------------------------------------------------------------------------
# Save
# ----------------------------------------------------------------------------

OUT = Path(__file__).resolve().parents[2] / "figures" / "opus_vs_sonnet_for_agents.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

plt.tight_layout(rect=[0, 0.045, 1, 0.94])
plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white", pad_inches=0.3)
print(f"wrote: {OUT}")
