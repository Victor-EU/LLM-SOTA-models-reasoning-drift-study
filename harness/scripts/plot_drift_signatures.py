"""Generate the drift-signatures hero chart.

Single-shot reproducible plot of mean Tier-3 reasoning_quality vs realized
context fill, one line per arm. Source data is the cross-arm headline table
in `cross_arm/CROSS_ARM_REPORT.md §2.1` (already aggregated and sha256-locked
per arm). This script only renders; it does not re-aggregate.

Output: `figures/drift_signatures.png` (1800x1050 @ 150 DPI).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import rcParams

# ----------------------------------------------------------------------------
# Data — pinned to CROSS_ARM_REPORT.md §2.1 headline drift table.
# ----------------------------------------------------------------------------

FILLS = [13, 24, 47, 72, 92]  # realized, Anthropic-counted

ARMS = [
    # (display name, RQ-by-fill, vendor color, qualitative descriptor)
    ("Opus 4.7",        [8.05, 7.33, 6.89, 7.17, 7.02], "#C84630",
     "monotonic decline · 7× hallucinations"),
    ("Sonnet 4.6",      [7.43, 8.00, 7.94, 7.19, 7.60], "#E89B47",
     "only arm that recovers above baseline"),
    ("GPT-5.5",         [7.05, 6.89, 6.92, 6.89, 6.27], "#10A37F",
     "flat then cliff at 92% · ~0 hallucinations"),
    ("Gemini 3.1 Pro",  [5.86, 5.68, 5.59, 5.51, 5.56], "#4285F4",
     "flat at low ceiling · 3–15× faster"),
    ("DeepSeek V4 Pro", [5.33, 5.16, 5.30, 5.43, 5.24], "#7C3AED",
     "flat absolute · steepest pairwise loss"),
]

# ----------------------------------------------------------------------------
# Style
# ----------------------------------------------------------------------------

rcParams["font.family"] = "DejaVu Sans"
rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
fig.patch.set_facecolor("white")
ax.set_facecolor("#FAFAFA")

# ----------------------------------------------------------------------------
# Lines + endpoint labels (model name only, vendor-colored, bold)
# ----------------------------------------------------------------------------

# Manual y-offsets prevent the Gemini/DeepSeek labels from colliding
# (their endpoints are only 0.32 RQ apart at fill=92%).
LABEL_Y_OFFSETS = {
    "Opus 4.7":         0.00,
    "Sonnet 4.6":       0.00,
    "GPT-5.5":          0.00,
    "Gemini 3.1 Pro":  +0.10,
    "DeepSeek V4 Pro": -0.10,
}

for name, vals, color, descriptor in ARMS:
    ax.plot(
        FILLS, vals,
        marker="o", markersize=8, markeredgecolor="white", markeredgewidth=1.2,
        linewidth=2.6, color=color, solid_capstyle="round", zorder=3,
    )
    y_anchor = vals[-1] + LABEL_Y_OFFSETS[name]
    # Endpoint label sits to the right of the last marker
    ax.annotate(
        name,
        xy=(FILLS[-1] + 1.5, y_anchor),
        color=color, fontsize=11, fontweight="bold",
        va="center", ha="left",
    )
    # Descriptor sits one line below the name
    ax.annotate(
        descriptor,
        xy=(FILLS[-1] + 1.5, y_anchor - 0.18),
        color="#555555", fontsize=8.5,
        va="center", ha="left", style="italic",
    )

# ----------------------------------------------------------------------------
# Axes
# ----------------------------------------------------------------------------

ax.set_xlabel("Context fill — % of vendor-counted token budget",
              fontsize=11, color="#333333")
ax.set_ylabel("Mean reasoning quality on Tier-3 synthesis (0–10)",
              fontsize=11, color="#333333")

ax.set_xticks(FILLS)
ax.set_xticklabels([f"{f}%" for f in FILLS], fontsize=10)
ax.tick_params(axis="y", labelsize=10)

ax.set_xlim(8, 145)
ax.set_ylim(4.5, 8.6)
ax.grid(True, alpha=0.25, linestyle="--", zorder=1)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_color("#999999")
ax.spines["bottom"].set_color("#999999")

# ----------------------------------------------------------------------------
# Title block + footnote
# ----------------------------------------------------------------------------

fig.suptitle(
    "Five frontier reasoning models. Five different ways to fail under context pressure.",
    fontsize=14.5, fontweight="bold", x=0.06, y=0.965, ha="left", color="#111111",
)
ax.set_title(
    "Identical inputs at every coordinate. Each vendor at its own maximum thinking effort. "
    "n = 21 baseline + 63 per noise cell, 7 reps × 3 positions.",
    fontsize=10, color="#666666", pad=10, loc="left",
)

fig.text(
    0.06, 0.025,
    "Source: 5 arms × 91 runs, MSFT FY2025 10-K target + 7 peer 10-Ks as adversarially-near noise. "
    "Held-constant judge: Opus 4.7 max-effort. "
    "Repo: github.com/Victor-EU/LLM-SOTA-models-reasoning-drift-study",
    fontsize=8, color="#888888", ha="left",
)

# ----------------------------------------------------------------------------
# Save
# ----------------------------------------------------------------------------

OUT = Path(__file__).resolve().parents[2] / "figures" / "drift_signatures.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

plt.tight_layout(rect=[0, 0.04, 1, 0.93])
plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white", pad_inches=0.3)
print(f"wrote: {OUT}")
