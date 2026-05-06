"""Build unified v2+v3 cross-noise × cross-judge report.

Loads:
- Tier-1/2 autograde from arms/{arm}/data/graded/c_*.jsonl
- Tier-3 original judge (Opus) from arms/{arm}/data/graded/c_*.jsonl, field `absolute`
- Tier-3 cross-judges (gpt-5.5, gemini-3.1-pro) from arms/{arm}/data/cross_judged/all_tier3.jsonl

Emits aggregated stats per (arm, noise, fill, position, judge, dimension).
"""
from __future__ import annotations
import json, glob, statistics, math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path("/Users/vz/LLM Reasoning Drift Study")
ARMS_V2 = ["opus-4-7", "sonnet-4-6", "gpt-5-5", "gemini-3-1-pro", "deepseek-v4-pro"]
ARMS_V3 = [a + "-temporal" for a in ARMS_V2]
ALL_ARMS = ARMS_V2 + ARMS_V3

# Map arm name → (model, noise_type)
ARM_INFO = {a: (a, "peer_materials") for a in ARMS_V2}
ARM_INFO.update({a: (a.replace("-temporal", ""), "temporal_msft") for a in ARMS_V3})

# Judge names
JUDGES = ["opus-4.7", "gpt-5.5", "gemini-3.1-pro"]

# Dimensions
T3_DIMS = [
    "reasoning_quality",      # 0-10 headline
    "groundedness",            # 0-5
    "evidentiary_breadth",     # 0-5
    "scope_adherence",         # 0-5
    "clarity",                 # 0-5
    "citation_accuracy",       # 0-5
    "unsupported_claims",      # count
    "cross_contamination",     # count
    "temporal_contamination",  # count (v3 only)
]

FILLS = [0.00, 0.25, 0.50, 0.75, 0.95]
POSITIONS = ["start", "middle", "end"]


def load_tier12(arm: str) -> list[dict]:
    """Load tier-1/2 records (autograde-based)."""
    rows = []
    for p in sorted((ROOT / f"arms/{arm}/data/graded").glob("c_*.jsonl")):
        with p.open() as f:
            for line in f:
                r = json.loads(line)
                if r["tier"] in (1, 2) and r.get("autograde"):
                    rows.append({
                        "arm": arm,
                        "model": ARM_INFO[arm][0],
                        "noise": ARM_INFO[arm][1],
                        "tier": r["tier"],
                        "run_id": r["run_id"],
                        "q_id": r["q_id"],
                        "fill_pct": r["fill_pct"],
                        "position": r["position"],
                        "score": r["autograde"].get("score") or 0.0,
                        "correct": bool(r["autograde"].get("correct")),
                        "distractor_hit": bool(r["autograde"].get("distractor_hit")),
                    })
    return rows


def load_tier3_original(arm: str) -> list[dict]:
    """Load tier-3 records judged by Opus (original judge in graded files)."""
    rows = []
    for p in sorted((ROOT / f"arms/{arm}/data/graded").glob("c_*.jsonl")):
        with p.open() as f:
            for line in f:
                r = json.loads(line)
                if r["tier"] == 3 and r.get("absolute"):
                    abs_ = r["absolute"]
                    rows.append({
                        "arm": arm,
                        "model": ARM_INFO[arm][0],
                        "noise": ARM_INFO[arm][1],
                        "tier": 3,
                        "judge": "opus-4.7",
                        "run_id": r["run_id"],
                        "q_id": r["q_id"],
                        "fill_pct": r["fill_pct"],
                        "position": r["position"],
                        **{d: abs_.get(d) for d in T3_DIMS},
                        "temporal_hits": (r.get("temporal", {}).get("count", 0)),
                    })
    return rows


def load_tier3_cross(arm: str) -> list[dict]:
    """Load tier-3 records from cross-judge sidecar (gpt-5.5, gemini-3.1-pro)."""
    p = ROOT / f"arms/{arm}/data/cross_judged/all_tier3.jsonl"
    if not p.exists():
        return []
    rows = []
    with p.open() as f:
        for line in f:
            r = json.loads(line)
            abs_ = r.get("absolute") or {}
            if "_error" in abs_:
                continue
            rows.append({
                "arm": arm,
                "model": ARM_INFO[arm][0],
                "noise": ARM_INFO[arm][1],
                "tier": 3,
                "judge": r["judge"],
                "run_id": r["run_id"],
                "q_id": r["q_id"],
                "fill_pct": r["fill_pct"],
                "position": r["position"],
                **{d: abs_.get(d) for d in T3_DIMS},
            })
    return rows


def mean_se(xs: list[float]) -> tuple[float, float, int]:
    """Return (mean, se, n). SE = stdev / sqrt(n). Returns (nan, nan, 0) if empty."""
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n == 0:
        return (float("nan"), float("nan"), 0)
    m = statistics.mean(xs)
    if n < 2:
        return (m, float("nan"), n)
    sd = statistics.stdev(xs)
    return (m, sd / math.sqrt(n), n)


def fmt(m: float, se: float) -> str:
    if math.isnan(m):
        return "—"
    if math.isnan(se):
        return f"{m:.2f}"
    return f"{m:.2f} ± {se:.2f}"


def aggregate(records: list[dict], value_key: str, group_keys: list[str]) -> dict:
    """Group records by `group_keys` tuple, return {group: (mean, se, n)}."""
    buckets = defaultdict(list)
    for r in records:
        key = tuple(r.get(k) for k in group_keys)
        v = r.get(value_key)
        if v is not None:
            buckets[key].append(v)
    return {k: mean_se(vs) for k, vs in buckets.items()}


def render_dimension_table(records: list[dict], value_key: str, *, scale_label: str = "") -> str:
    """One markdown table per dimension: rows = (arm × noise × fill), cols = positions + row mean.

    Baseline (fill=0) appears once per arm with all-position cells merged.
    """
    # Aggregate by (arm, noise, fill, position)
    cell = aggregate(records, value_key, ["arm", "noise", "fill_pct", "position"])
    # Aggregate row means by (arm, noise, fill)
    row_mean = aggregate(records, value_key, ["arm", "noise", "fill_pct"])

    out = [f"| arm | noise | fill | start | middle | end | row mean |",
           f"|-----|-------|-----:|-------|--------|-----|---------:|"]
    for arm in ALL_ARMS:
        model, noise = ARM_INFO[arm]
        # Baseline row
        bk = (arm, noise, 0.0, None)
        bm = cell.get(bk)
        if bm:
            rm = row_mean.get((arm, noise, 0.0))
            out.append(f"| {model} | — | 0% | — | **{fmt(*bm[:2])}** | — | {fmt(*rm[:2])} |")
        for f in FILLS[1:]:
            row_cells = []
            for pos in POSITIONS:
                k = (arm, noise, f, pos)
                ms = cell.get(k)
                row_cells.append(fmt(*ms[:2]) if ms else "—")
            rm = row_mean.get((arm, noise, f))
            out.append(f"| {model} | {noise} | {int(f*100)}% | {row_cells[0]} | {row_cells[1]} | {row_cells[2]} | {fmt(*rm[:2]) if rm else '—'} |")
    return "\n".join(out)


def cross_judge_pearson(t3_records: list[dict], dim: str) -> dict:
    """For each arm, compute Pearson r between judge pairs on the same (run_id, q_id)."""
    # Build paired: (arm, run_id, q_id) -> {judge: score}
    paired = defaultdict(dict)
    for r in t3_records:
        v = r.get(dim)
        if v is not None:
            paired[(r["arm"], r["run_id"], r["q_id"])][r["judge"]] = v
    out = {}
    for arm in ALL_ARMS:
        keys = [k for k in paired if k[0] == arm]
        arm_out = {}
        for j1, j2 in [("opus-4.7", "gpt-5.5"), ("opus-4.7", "gemini-3.1-pro"), ("gpt-5.5", "gemini-3.1-pro")]:
            xs, ys = [], []
            for k in keys:
                if j1 in paired[k] and j2 in paired[k]:
                    xs.append(paired[k][j1])
                    ys.append(paired[k][j2])
            if len(xs) >= 3:
                mx, my = statistics.mean(xs), statistics.mean(ys)
                num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
                dx = math.sqrt(sum((x - mx)**2 for x in xs))
                dy = math.sqrt(sum((y - my)**2 for y in ys))
                r = num / (dx * dy) if dx > 0 and dy > 0 else None
                arm_out[(j1, j2)] = (r, len(xs), mx - my)
            else:
                arm_out[(j1, j2)] = (None, len(xs), None)
        out[arm] = arm_out
    return out


def empty_extract_rates() -> str:
    """Tier-3 empty answer_raw rates per arm (downstream pipeline failure indicator)."""
    out = ["| arm | model | noise | empty / total | empty % |",
           "|-----|-------|-------|--------------:|--------:|"]
    for arm in ALL_ARMS:
        model, noise = ARM_INFO[arm]
        n_total = n_empty = 0
        for p in (ROOT / f"arms/{arm}/data/extracted").glob("c_*.jsonl"):
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip(): continue
                r = json.loads(line)
                if r.get("q_id", "").startswith("MSFT-S"):
                    n_total += 1
                    if not r.get("answer_raw"):
                        n_empty += 1
        pct = 100 * n_empty / n_total if n_total else 0
        out.append(f"| {arm} | {model} | {noise} | {n_empty} / {n_total} | {pct:.1f}% |")
    return "\n".join(out)


def cross_noise_contrast(t3_records: list[dict], dim: str, judge: str) -> str:
    """Per model: peer-noise vs temporal-noise mean ± SE per fill, under one judge."""
    by_key = defaultdict(list)
    for r in t3_records:
        if r.get("judge") == judge and r.get(dim) is not None:
            by_key[(r["model"], r["noise"], r["fill_pct"])].append(r[dim])

    out = [f"| model | fill | peer (v2)        | temporal (v3)    | Δ (temp − peer) |",
           f"|-------|-----:|------------------|------------------|----------------:|"]
    models = sorted({r["model"] for r in t3_records})
    for model in models:
        for f in FILLS:
            p_vals = by_key.get((model, "peer_materials", f), [])
            t_vals = by_key.get((model, "temporal_msft", f), [])
            if p_vals and t_vals:
                pm, ps, _ = mean_se(p_vals)
                tm, ts, _ = mean_se(t_vals)
                d = tm - pm
                tag = " **temporal HARDER**" if d < -0.5 else (" *temporal easier*" if d > 0.5 else "")
                out.append(f"| {model} | {int(f*100)}% | {fmt(pm,ps)} | {fmt(tm,ts)} | {d:+.2f}{tag} |")
    return "\n".join(out)


def self_favoritism(t3_records: list[dict], dim: str) -> str:
    """For each model arm, mean (self-judge − Opus-judge) and (self-judge − GPT-judge)."""
    JUDGE_OF_VENDOR = {"opus-4-7": "opus-4.7", "sonnet-4-6": "opus-4.7",
                       "gpt-5-5": "gpt-5.5", "gemini-3-1-pro": "gemini-3.1-pro",
                       "deepseek-v4-pro": None}
    out = ["| model arm | noise | self-judge | mean self | mean opus | mean gpt | mean gemini | self − opus | self − gpt |",
           "|-----------|-------|------------|----------:|----------:|---------:|------------:|------------:|-----------:|"]
    by = defaultdict(lambda: defaultdict(list))
    for r in t3_records:
        if r.get(dim) is not None:
            by[(r["model"], r["noise"])][r["judge"]].append(r[dim])
    for model in sorted({r["model"] for r in t3_records}):
        sj = JUDGE_OF_VENDOR.get(model)
        if sj is None:
            continue
        for noise in ["peer_materials", "temporal_msft"]:
            judges = by[(model, noise)]
            if sj not in judges:
                continue
            ms = statistics.mean(judges[sj])
            mo = statistics.mean(judges["opus-4.7"]) if "opus-4.7" in judges else float("nan")
            mg = statistics.mean(judges["gpt-5.5"]) if "gpt-5.5" in judges else float("nan")
            mge = statistics.mean(judges["gemini-3.1-pro"]) if "gemini-3.1-pro" in judges else float("nan")
            def _f(x): return f"{x:.2f}" if not math.isnan(x) else "—"
            self_minus_opus = ms - mo if not math.isnan(mo) else float("nan")
            self_minus_gpt = ms - mg if not math.isnan(mg) else float("nan")
            sopus = f"{self_minus_opus:+.2f}" if not math.isnan(self_minus_opus) else "—"
            sgpt = f"{self_minus_gpt:+.2f}" if not math.isnan(self_minus_gpt) else "—"
            out.append(f"| {model} | {noise} | {sj} | {_f(ms)} | {_f(mo)} | {_f(mg)} | {_f(mge)} | {sopus} | {sgpt} |")
    return "\n".join(out)


def bimodal_check(t3_records: list[dict], model: str, noise: str, fill: float, dim: str = "reasoning_quality") -> str:
    """Histogram of dim values for (model, noise, fill) per judge — is the failure mode bimodal?"""
    out = [f"### {model} / {noise} / fill={int(fill*100)}% — {dim} histogram by judge"]
    for judge in JUDGES:
        vs = [r.get(dim) for r in t3_records if r["model"]==model and r["noise"]==noise and r["fill_pct"]==fill and r.get("judge")==judge and r.get(dim) is not None]
        if not vs:
            continue
        from collections import Counter
        cts = Counter(int(v) for v in vs)
        out.append(f"\n**{judge} judge** (n={len(vs)}):")
        for v in sorted(cts):
            bar = "█" * cts[v]
            out.append(f"  {v}/10 │ {cts[v]:>3} {bar}")
    return "\n".join(out)


def main():
    # Load all
    t12 = []
    t3 = []
    for arm in ALL_ARMS:
        t12.extend(load_tier12(arm))
        t3.extend(load_tier3_original(arm))
        t3.extend(load_tier3_cross(arm))
    from collections import Counter
    print("# diagnostic")
    print(f"# tier12 records: {len(t12)}")
    print(f"# tier3 records: {len(t3)}")
    print(f"# tier3 by (arm, judge): {dict(Counter((r['arm'], r['judge']) for r in t3))}")

    print("\n# == Empty extraction rates (Tier-3) ==")
    print(empty_extract_rates())

    print("\n# == Reasoning Quality (all judges blended) ==")
    print(render_dimension_table(t3, "reasoning_quality"))

    print("\n# == Cross-noise contrast (Opus judge): peer vs temporal ==")
    print(cross_noise_contrast(t3, "reasoning_quality", "opus-4.7"))

    print("\n# == Cross-noise contrast (GPT judge) ==")
    print(cross_noise_contrast(t3, "reasoning_quality", "gpt-5.5"))

    print("\n# == Cross-noise contrast (Gemini judge) ==")
    print(cross_noise_contrast(t3, "reasoning_quality", "gemini-3.1-pro"))

    print("\n# == Self-favoritism on reasoning_quality ==")
    print(self_favoritism(t3, "reasoning_quality"))

    print("\n# == Bimodal failure check — Sonnet 95% temporal ==")
    print(bimodal_check(t3, "sonnet-4-6", "temporal_msft", 0.95))

    print("\n# == Tier-1 retrieval score ==")
    print(render_dimension_table([r for r in t12 if r["tier"] == 1], "score"))

    print("\n# == Tier-2 calculation score ==")
    print(render_dimension_table([r for r in t12 if r["tier"] == 2], "score"))

    print("\n# == cross-judge pearson r per arm (reasoning_quality) ==")
    pj = cross_judge_pearson([r for r in t3 if r["tier"] == 3], "reasoning_quality")
    for arm in ALL_ARMS:
        print(f"\n## {arm}")
        for (j1, j2), (r, n, d) in pj[arm].items():
            rstr = f"{r:.3f}" if r is not None else "n/a"
            dstr = f"{d:+.2f}" if d is not None else "n/a"
            print(f"  {j1} vs {j2}: r={rstr}  n={n}  mean_diff={dstr}")


if __name__ == "__main__":
    main()
