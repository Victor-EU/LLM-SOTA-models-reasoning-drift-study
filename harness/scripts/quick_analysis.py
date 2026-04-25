"""Drift signal sanity check — pre-judge analysis of the collected data.

Aggregates per-cell metrics from arms/<arm>/data/raw and .../extracted to verify that:
1. The experiment captured a usable signal at each fill level.
2. Tier-1 numeric accuracy is measurable against ground truth.
3. Tier-1 cross-contamination from peer 10-Ks is detectable.
4. Output length / thinking depth varies with fill level.

This is NOT the judge stage — for graded analysis use scripts.drift_analysis.

Usage:
  python -m scripts.quick_analysis --arm opus-4-7
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Canonical MSFT FY2025 ground-truth (from 10-K, double-checked in smoke test).
TRUTH = {
    "MSFT-F-01": ("281724", "USD_millions", "total_revenue"),
    "MSFT-F-02": ("128528", "USD_millions", "operating_income"),
    "MSFT-F-03": ("13.64", "USD", "diluted_eps"),
    "MSFT-C-01": (None, "percent", "effective_tax_rate"),  # computed; ~17-18%
    "MSFT-C-02": ("14.9", "percent", "yoy_revenue_growth"),
}

# Peer revenue distractors — common-distractor numeric strings the model might
# attribute to MSFT under context pressure. Numbers from competitors' FY2025
# 10-Ks in the noise pool. (rough — flag any near match.)
PEER_REVENUE = {
    "AAPL": 391000,    # ~$391B FY24/25
    "GOOGL": 350000,   # ~$350B FY25
    "AMZN": 638000,    # ~$638B FY24
    "META": 165000,    # ~$165B FY25
    "NVDA": 130000,    # ~$130B FY25
    "ORCL": 53000,     # ~$53B FY25
    "CRM": 38000,      # ~$38B FY26
}


def near(a: float, b: float, tol: float = 0.02) -> bool:
    if b == 0: return a == 0
    return abs(a - b) / max(1, abs(b)) < tol


def num_or_none(s):
    if s is None: return None
    try:
        return float(str(s).replace(",", "").replace("$", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, help="analyst arm name (matches arms/<arm>/)")
    args = parser.parse_args()

    arm_data = PROJECT_ROOT / "arms" / args.arm / "data"
    raw_dir = arm_data / "raw"
    ext_dir = arm_data / "extracted"
    if not raw_dir.exists():
        print(f"no data at {arm_data} — has this arm been run?")
        return 2
    print(f"Quick analysis for arm: {args.arm}")

    # Index raw records by run_id for usage/length metrics.
    raw: dict[str, dict] = {}
    for f in raw_dir.glob("*.jsonl"):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            raw[r["run_id"]] = r

    # Group extracted by (cell_id, q_id).
    by_cell: dict[str, dict] = defaultdict(lambda: {
        "fill_pct": None, "position": None,
        "runs": set(),
        "answers": defaultdict(list),     # q_id -> [normalized_answer, ...]
        "parsed_count": 0, "expected_count": 0,
    })
    for f in ext_dir.glob("*.jsonl"):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            cid = r["cell_id"]
            c = by_cell[cid]
            c["fill_pct"] = r["fill_pct"]
            c["position"] = r.get("position")
            c["runs"].add(r["run_id"])
            c["expected_count"] += 1
            if r.get("parsed_ok") is not False:
                c["parsed_count"] += 1
                c["answers"][r["q_id"]].append(r.get("answer_normalized"))

    print(f"{'cell':<48} {'fill':>5} {'pos':>7} {'reps':>5} {'parse%':>7} "
          f"{'realf':>7} {'in_K':>7} {'out':>6} {'thnk':>6}  {'F01':>7} {'F02':>7} {'F03':>6} {'C02':>6}  {'peer':>4}")
    print("-" * 175)

    for cid in sorted(by_cell.keys(), key=lambda k: (by_cell[k]["fill_pct"], by_cell[k]["position"] or "")):
        c = by_cell[cid]
        run_ids = sorted(c["runs"])
        n_reps = len(run_ids)
        parse_pct = 100.0 * c["parsed_count"] / max(1, c["expected_count"])

        # Mean usage stats from raw.
        realf = statistics.mean(raw[r]["token_budget"]["realized_fill_pct"] for r in run_ids)
        in_k  = statistics.mean(raw[r]["usage"]["input_tokens"] + raw[r]["usage"]["cache_read_input_tokens"] + raw[r]["usage"]["cache_creation_input_tokens"] for r in run_ids) / 1000
        out   = statistics.mean(raw[r]["usage"]["output_tokens"] for r in run_ids)
        thnk  = statistics.mean((raw[r]["usage"].get("thinking_tokens") or 0) for r in run_ids)

        # Tier-1 accuracy across reps.
        def acc(qid, gt):
            ans_list = c["answers"].get(qid, [])
            gt_n = num_or_none(gt)
            if gt_n is None or not ans_list:
                return "n/a"
            hits = sum(1 for a in ans_list if (an := num_or_none(a)) is not None and near(an, gt_n))
            return f"{hits}/{len(ans_list)}"

        f01 = acc("MSFT-F-01", TRUTH["MSFT-F-01"][0])
        f02 = acc("MSFT-F-02", TRUTH["MSFT-F-02"][0])
        f03 = acc("MSFT-F-03", TRUTH["MSFT-F-03"][0])
        c02 = acc("MSFT-C-02", TRUTH["MSFT-C-02"][0])

        # Cross-contamination: count reps where Q1 or Q2 matches a peer revenue.
        peer_hits = 0
        for ans in c["answers"].get("MSFT-F-01", []):
            an = num_or_none(ans)
            if an and any(near(an, v, tol=0.05) for v in PEER_REVENUE.values()):
                peer_hits += 1
        for ans in c["answers"].get("MSFT-F-02", []):
            an = num_or_none(ans)
            if an and any(near(an, v, tol=0.05) for v in PEER_REVENUE.values()):
                peer_hits += 1

        pos = c["position"] or "-"
        print(f"{cid[:48]:<48} {c['fill_pct']:>5.2f} {pos:>7} {n_reps:>5} {parse_pct:>6.1f}% "
              f"{realf:>6.1%} {in_k:>6.0f}K {out:>6.0f} {thnk:>6.0f}  {f01:>7} {f02:>7} {f03:>6} {c02:>6}  {peer_hits:>4}")

    print()
    print("LEGEND: realf=realized fill%, in_K=mean input tokens (K), out=mean output tokens,")
    print("        thnk=mean thinking tokens (signature-derived), F01/F02/F03/C02=accuracy hits/reps,")
    print("        peer=count of (rep, F01|F02) answers matching a peer-company revenue (contamination).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
