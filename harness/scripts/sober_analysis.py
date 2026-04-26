"""
Sober-state ranking analysis.

Reads `cross_arm/sober_state/judge_{opus,sonnet}.jsonl` produced by
`scripts.judge_sober_ranking` and produces:
  - Mean rank per arm (per judge, and judge-averaged).
  - Borda count (5 - rank, summed; higher = better).
  - Pairwise win matrix derived from total orderings (per judge).
  - Per-question and per-arm dimension means (per judge).
  - Cross-judge agreement: Spearman ρ on per-item rankings; Borda Pearson r.
  - Per-position diagnostics (was the winning arm just sitting in label A?).

Usage:
    python -m scripts.sober_analysis                # prints to stdout
    python -m scripts.sober_analysis --json out.json # write structured output
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOBER_DIR = PROJECT_ROOT / "cross_arm" / "sober_state"

ARMS = ("opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro")
QIDS = ("MSFT-S-01", "MSFT-S-02", "MSFT-S-03")
JUDGES = ("opus", "sonnet")
DIMS_5 = ("groundedness", "evidentiary_breadth", "scope_adherence", "clarity", "citation_accuracy")
DIM_RQ = "reasoning_quality"


# ---- IO ------------------------------------------------------------------

def _load_judge(label: str) -> list[dict[str, Any]]:
    path = SOBER_DIR / f"judge_{label}.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


# ---- core derivations ----------------------------------------------------

def _ranking_to_ranks(ranking_arms: list[str]) -> dict[str, int]:
    """[best, ..., worst] -> {arm: rank} where rank=1 is best, rank=5 is worst.
    Arms missing from the ranking get rank=None (treated as 'not ranked')."""
    ranks: dict[str, int] = {}
    for i, arm in enumerate(ranking_arms):
        if arm in ARMS and arm not in ranks:
            ranks[arm] = i + 1
    return ranks


def _borda(ranking_arms: list[str], n_arms: int = 5) -> dict[str, int]:
    """Borda points: (n_arms - 1) for first, 0 for last. Higher is better."""
    points: dict[str, int] = {arm: 0 for arm in ARMS}
    for i, arm in enumerate(ranking_arms):
        if arm in points:
            points[arm] = (n_arms - 1) - i
    return points


def _pairwise_from_ranking(ranking_arms: list[str]) -> dict[tuple[str, str], int]:
    """For each ordered (winner, loser) pair, +1 if winner came before loser."""
    out: dict[tuple[str, str], int] = {}
    for i, w in enumerate(ranking_arms):
        for l in ranking_arms[i + 1:]:
            out[(w, l)] = out.get((w, l), 0) + 1
    return out


# ---- aggregations --------------------------------------------------------

@dataclass
class JudgeAggregate:
    judge: str
    n_items: int
    mean_rank: dict[str, float]
    borda_total: dict[str, int]
    borda_mean: dict[str, float]
    win_matrix: dict[tuple[str, str], int]      # (a, b): #items where a ranked above b
    per_dim_mean: dict[str, dict[str, float]]   # dim -> arm -> mean
    rq_mean: dict[str, float]
    rq_stdev: dict[str, float]
    unsup_mean: dict[str, float]
    rankings_by_item: dict[tuple[str, int], list[str]]  # (q_id, rep) -> ordering arms


def _aggregate(rows: list[dict[str, Any]]) -> JudgeAggregate:
    n = len(rows)
    judge_label = rows[0]["judge"] if rows else "?"

    # Rank stats
    rank_lists: dict[str, list[int]] = {arm: [] for arm in ARMS}
    borda_totals: dict[str, int] = {arm: 0 for arm in ARMS}
    win_matrix: dict[tuple[str, str], int] = {}
    rankings_by_item: dict[tuple[str, int], list[str]] = {}

    # Score stats (per dimension, per arm)
    dim_acc: dict[str, dict[str, list[float]]] = {d: {arm: [] for arm in ARMS} for d in DIMS_5}
    rq_acc: dict[str, list[float]] = {arm: [] for arm in ARMS}
    unsup_acc: dict[str, list[float]] = {arm: [] for arm in ARMS}

    for row in rows:
        ranking_arms = row.get("ranking_arms") or []
        if len(set(ranking_arms)) < len(ranking_arms):
            # Should not happen with strict total ordering, but guard.
            seen = set(); dedup = []
            for a in ranking_arms:
                if a not in seen:
                    seen.add(a); dedup.append(a)
            ranking_arms = dedup
        rankings_by_item[(row["q_id"], int(row["rep_idx"]))] = ranking_arms

        ranks = _ranking_to_ranks(ranking_arms)
        for arm, r in ranks.items():
            rank_lists[arm].append(r)
        for arm, pts in _borda(ranking_arms).items():
            borda_totals[arm] += pts
        for (w, l), c in _pairwise_from_ranking(ranking_arms).items():
            win_matrix[(w, l)] = win_matrix.get((w, l), 0) + c

        scores_by_arm = row.get("scores_by_arm") or {}
        for arm, sc in scores_by_arm.items():
            if not sc or arm not in ARMS:
                continue
            for d in DIMS_5:
                v = sc.get(d)
                if isinstance(v, (int, float)):
                    dim_acc[d][arm].append(float(v))
            rq = sc.get(DIM_RQ)
            if isinstance(rq, (int, float)):
                rq_acc[arm].append(float(rq))
            us = sc.get("unsupported_claims")
            if isinstance(us, (int, float)):
                unsup_acc[arm].append(float(us))

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else float("nan")

    def stdev(xs: list[float]) -> float:
        return statistics.pstdev(xs) if len(xs) >= 2 else 0.0

    return JudgeAggregate(
        judge=judge_label,
        n_items=n,
        mean_rank={arm: mean(rank_lists[arm]) for arm in ARMS},
        borda_total=borda_totals,
        borda_mean={arm: borda_totals[arm] / n if n else float("nan") for arm in ARMS},
        win_matrix=win_matrix,
        per_dim_mean={d: {arm: mean(dim_acc[d][arm]) for arm in ARMS} for d in DIMS_5},
        rq_mean={arm: mean(rq_acc[arm]) for arm in ARMS},
        rq_stdev={arm: stdev(rq_acc[arm]) for arm in ARMS},
        unsup_mean={arm: mean(unsup_acc[arm]) for arm in ARMS},
        rankings_by_item=rankings_by_item,
    )


# ---- cross-judge agreement -----------------------------------------------

def _spearman(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or len(a) < 2:
        return float("nan")
    n = len(a)
    ra = _ranks(a); rb = _ranks(b)
    mean_r = (n + 1) / 2
    num = sum((ra[i] - mean_r) * (rb[i] - mean_r) for i in range(n))
    den = math.sqrt(
        sum((ra[i] - mean_r) ** 2 for i in range(n))
        * sum((rb[i] - mean_r) ** 2 for i in range(n))
    )
    return num / den if den else float("nan")


def _ranks(xs: list[float]) -> list[float]:
    """Average-rank handling for ties."""
    n = len(xs)
    order = sorted(range(n), key=lambda i: xs[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + 1 + j + 1) / 2
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or len(a) < 2:
        return float("nan")
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((ai - ma) * (bi - mb) for ai, bi in zip(a, b))
    den = math.sqrt(sum((ai - ma) ** 2 for ai in a) * sum((bi - mb) ** 2 for bi in b))
    return num / den if den else float("nan")


@dataclass
class CrossJudge:
    n_overlap_items: int
    per_item_spearman_mean: float       # mean ρ over items (each item is a 5-vector)
    per_item_spearman_median: float
    per_arm_borda_pearson: float        # one Pearson over the 5 arms' Borda totals
    per_arm_rank_pearson: float         # one Pearson over the 5 arms' mean ranks
    rank_agreement_top1: float          # fraction of items where both judges pick same #1
    rank_agreement_topk_3: float        # fraction of items where top-3 sets match


def _cross_judge(opus: JudgeAggregate, sonnet: JudgeAggregate) -> CrossJudge:
    common = set(opus.rankings_by_item.keys()) & set(sonnet.rankings_by_item.keys())
    common_keys = sorted(common)
    if not common_keys:
        return CrossJudge(0, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"), float("nan"))

    item_spearmans: list[float] = []
    top1_match = 0
    top3_match = 0
    for k in common_keys:
        opus_order = opus.rankings_by_item[k]
        sonnet_order = sonnet.rankings_by_item[k]
        # Build rank vectors aligned to ARMS order
        opus_ranks = [opus_order.index(a) + 1 if a in opus_order else 6 for a in ARMS]
        sonnet_ranks = [sonnet_order.index(a) + 1 if a in sonnet_order else 6 for a in ARMS]
        item_spearmans.append(_spearman([float(r) for r in opus_ranks], [float(r) for r in sonnet_ranks]))
        if opus_order and sonnet_order and opus_order[0] == sonnet_order[0]:
            top1_match += 1
        if len(opus_order) >= 3 and len(sonnet_order) >= 3 and set(opus_order[:3]) == set(sonnet_order[:3]):
            top3_match += 1

    # Per-arm consistency: mean rank vector and Borda vector across arms
    arm_borda_opus = [opus.borda_total[a] for a in ARMS]
    arm_borda_sonnet = [sonnet.borda_total[a] for a in ARMS]
    arm_rank_opus = [opus.mean_rank[a] for a in ARMS]
    arm_rank_sonnet = [sonnet.mean_rank[a] for a in ARMS]

    return CrossJudge(
        n_overlap_items=len(common_keys),
        per_item_spearman_mean=sum(item_spearmans) / len(item_spearmans),
        per_item_spearman_median=statistics.median(item_spearmans),
        per_arm_borda_pearson=_pearson([float(x) for x in arm_borda_opus],
                                       [float(x) for x in arm_borda_sonnet]),
        per_arm_rank_pearson=_pearson(arm_rank_opus, arm_rank_sonnet),
        rank_agreement_top1=top1_match / len(common_keys),
        rank_agreement_topk_3=top3_match / len(common_keys),
    )


# ---- per-question slicing ------------------------------------------------

def _per_question_aggregate(rows: list[dict[str, Any]]) -> dict[str, JudgeAggregate]:
    out: dict[str, JudgeAggregate] = {}
    for q_id in QIDS:
        sub = [r for r in rows if r.get("q_id") == q_id]
        if sub:
            out[q_id] = _aggregate(sub)
    return out


# ---- position-bias diagnostic --------------------------------------------

def _position_bias(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """For each label A-E, what fraction of the time did the candidate in that
    label get rank=1 (or rank<=3)? If unbiased, ~20% on rank=1, ~60% on top-3."""
    label_top1 = Counter(); label_top3 = Counter(); label_total = Counter()
    for r in rows:
        ranking_labels = r.get("ranking_labels") or []
        if not ranking_labels:
            continue
        for i, lbl in enumerate(ranking_labels):
            label_total[lbl] += 1
            if i == 0:
                label_top1[lbl] += 1
            if i < 3:
                label_top3[lbl] += 1
    out: dict[str, dict[str, float]] = {"top1": {}, "top3": {}}
    for lbl in "ABCDE":
        t = label_total.get(lbl, 0) or 1
        out["top1"][lbl] = label_top1.get(lbl, 0) / t
        out["top3"][lbl] = label_top3.get(lbl, 0) / t
    return out


# ---- existing-baseline comparison ----------------------------------------

def _load_existing_baseline_rq(arm: str) -> dict[str, list[float]]:
    """Pull the original absolute-judge reasoning_quality scores for the 21
    Tier-3 baseline records, per question. For comparing absolute vs sober-
    ranking pictures."""
    path = PROJECT_ROOT / "arms" / arm / "data" / "graded" / "c_MSFT_00_X_X_af5a558f3d83491a.jsonl"
    by_q: dict[str, list[float]] = {q: [] for q in QIDS}
    if not path.exists():
        return by_q
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            qid = row.get("q_id")
            if qid in by_q:
                ab = row.get("absolute") or {}
                rq = ab.get("reasoning_quality")
                if isinstance(rq, (int, float)):
                    by_q[qid].append(float(rq))
    return by_q


# ---- pretty printing -----------------------------------------------------

def _fmt_table(headers: list[str], rows: Iterable[list[Any]], col_widths: list[int]) -> str:
    out = []
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    out.append(fmt.format(*headers))
    out.append("-" * (sum(col_widths) + 2 * (len(col_widths) - 1)))
    for row in rows:
        out.append(fmt.format(*row))
    return "\n".join(out)


def _print_judge(agg: JudgeAggregate) -> str:
    lines = []
    lines.append(f"\n=== JUDGE: {agg.judge} ({agg.n_items} items) ===")
    rows = []
    # Sort arms by mean_rank ascending (best first)
    sorted_arms = sorted(ARMS, key=lambda a: agg.mean_rank[a])
    for arm in sorted_arms:
        rows.append([
            arm,
            f"{agg.mean_rank[arm]:.2f}",
            f"{agg.borda_total[arm]}",
            f"{agg.borda_mean[arm]:.2f}",
            f"{agg.rq_mean[arm]:.2f}",
            f"{agg.rq_stdev[arm]:.2f}",
            f"{agg.unsup_mean[arm]:.2f}",
        ])
    lines.append(_fmt_table(
        ["arm", "mean_rk", "borda", "borda/n", "RQ μ", "RQ σ", "unsup μ"],
        rows, [22, 8, 6, 8, 6, 6, 8],
    ))

    # Per-dimension means
    lines.append(f"\nPer-dimension means (1-5 each):")
    rows = []
    for arm in sorted_arms:
        rows.append([arm] + [f"{agg.per_dim_mean[d][arm]:.2f}" for d in DIMS_5])
    lines.append(_fmt_table(["arm", "gnd", "br", "sc", "cl", "cit"], rows, [22, 5, 5, 5, 5, 5]))

    # Win matrix (row beats column, count of items)
    lines.append(f"\nWin matrix (row beats column on N items, of {agg.n_items}):")
    header = ["winner \\ loser"] + list(ARMS)
    lines.append("  ".join(f"{h[:14]:<14}" for h in header))
    for w in ARMS:
        cells = [f"{w[:14]:<14}"]
        for l in ARMS:
            if w == l:
                cells.append(f"{'-':<14}")
            else:
                v = agg.win_matrix.get((w, l), 0)
                cells.append(f"{v:<14}")
        lines.append("  ".join(cells))
    return "\n".join(lines)


def _print_cross(cj: CrossJudge) -> str:
    lines = ["\n=== CROSS-JUDGE AGREEMENT (Opus primary vs Sonnet secondary) ==="]
    lines.append(f"items overlapping:                {cj.n_overlap_items}")
    lines.append(f"per-item Spearman ρ (mean):        {cj.per_item_spearman_mean:.3f}")
    lines.append(f"per-item Spearman ρ (median):      {cj.per_item_spearman_median:.3f}")
    lines.append(f"per-arm rank Pearson r:            {cj.per_arm_rank_pearson:.3f}")
    lines.append(f"per-arm Borda Pearson r:           {cj.per_arm_borda_pearson:.3f}")
    lines.append(f"top-1 agreement (same item):       {cj.rank_agreement_top1:.1%}")
    lines.append(f"top-3 set agreement (same item):   {cj.rank_agreement_topk_3:.1%}")
    return "\n".join(lines)


def _print_position(pb: dict[str, dict[str, float]]) -> str:
    lines = ["\n=== POSITION-BIAS DIAGNOSTIC (label-level) ==="]
    lines.append(f"{'label':<8} {'rank=1 freq':<14} {'top-3 freq':<14}")
    for lbl in "ABCDE":
        lines.append(f"{lbl:<8} {pb['top1'][lbl]:.1%}{'':<8} {pb['top3'][lbl]:.1%}")
    lines.append("(unbiased target: rank=1 ≈ 20%, top-3 ≈ 60% per label)")
    return "\n".join(lines)


def _print_per_question(per_q: dict[str, dict[str, JudgeAggregate]]) -> str:
    lines = ["\n=== PER-QUESTION breakdown (mean rank, lower=better; 7 reps each) ==="]
    header = ["q_id", "judge"] + list(ARMS)
    lines.append("  ".join(f"{h[:18]:<18}" for h in header))
    for q_id in QIDS:
        for jl in JUDGES:
            agg = per_q.get(jl, {}).get(q_id)
            if not agg:
                continue
            cells = [f"{q_id:<18}", f"{jl:<18}"]
            for arm in ARMS:
                v = agg.mean_rank[arm]
                cells.append(f"{v:.2f}{'':<14}")
            lines.append("  ".join(cells))
    return "\n".join(lines)


# ---- main ----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="optional output path for structured JSON dump")
    args = parser.parse_args()

    opus_rows = _load_judge("opus")
    sonnet_rows = _load_judge("sonnet")

    if not opus_rows and not sonnet_rows:
        print("no judge output found in", SOBER_DIR, file=sys.stderr)
        return 1

    out_lines: list[str] = []
    out_lines.append(f"# Sober-State Ranking Analysis  (cross_arm/sober_state)")
    out_lines.append(f"items per judge: opus={len(opus_rows)} sonnet={len(sonnet_rows)}")

    if opus_rows:
        opus_agg = _aggregate(opus_rows)
        out_lines.append(_print_judge(opus_agg))
        out_lines.append(_print_position(_position_bias(opus_rows)))
    else:
        opus_agg = None

    if sonnet_rows:
        sonnet_agg = _aggregate(sonnet_rows)
        out_lines.append(_print_judge(sonnet_agg))
        out_lines.append(_print_position(_position_bias(sonnet_rows)))
    else:
        sonnet_agg = None

    if opus_agg and sonnet_agg:
        out_lines.append(_print_cross(_cross_judge(opus_agg, sonnet_agg)))

    per_q: dict[str, dict[str, JudgeAggregate]] = {"opus": {}, "sonnet": {}}
    if opus_rows:
        per_q["opus"] = _per_question_aggregate(opus_rows)
    if sonnet_rows:
        per_q["sonnet"] = _per_question_aggregate(sonnet_rows)
    if any(per_q.values()):
        out_lines.append(_print_per_question(per_q))

    out_lines.append("\n=== EXISTING ABSOLUTE-JUDGE BASELINE (reasoning_quality, for comparison) ===")
    out_lines.append(f"{'arm':<22} " + " ".join(f"{q:<14}" for q in QIDS))
    for arm in ARMS:
        cells = [f"{arm:<22}"]
        baseline = _load_existing_baseline_rq(arm)
        for q in QIDS:
            xs = baseline[q]
            if xs:
                cells.append(f"{statistics.mean(xs):.2f} (n={len(xs)})  ")
            else:
                cells.append("?              ")
        out_lines.append("".join(cells))

    print("\n".join(out_lines))

    if args.json:
        dump = {
            "opus": _agg_to_json(opus_agg) if opus_agg else None,
            "sonnet": _agg_to_json(sonnet_agg) if sonnet_agg else None,
            "cross_judge": _cross_judge(opus_agg, sonnet_agg).__dict__ if (opus_agg and sonnet_agg) else None,
        }
        Path(args.json).write_text(json.dumps(dump, indent=2))
        print(f"\nstructured dump → {args.json}")
    return 0


def _agg_to_json(agg: JudgeAggregate) -> dict[str, Any]:
    if agg is None:
        return None  # type: ignore[return-value]
    return {
        "judge": agg.judge,
        "n_items": agg.n_items,
        "mean_rank": agg.mean_rank,
        "borda_total": agg.borda_total,
        "borda_mean": agg.borda_mean,
        "win_matrix": {f"{w}->{l}": v for (w, l), v in agg.win_matrix.items()},
        "per_dim_mean": agg.per_dim_mean,
        "rq_mean": agg.rq_mean,
        "rq_stdev": agg.rq_stdev,
        "unsup_mean": agg.unsup_mean,
    }


if __name__ == "__main__":
    sys.exit(main())
