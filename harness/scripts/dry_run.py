"""
Dry-run: two modes.

  --grid (default):    summarize the design grid and estimate cost. No API
                       calls. No prompt assembly. Catches config issues and
                       gives a $ sanity check before running anything.

  --assembly:          for each pilot cell, assemble the full prompt and
                       report realized token counts per segment. Catches
                       pool-exhaustion at 95% fill, budget-overshoot, and
                       noise-sampling issues. Uses the authoritative
                       Anthropic token-count API if ANTHROPIC_API_KEY is set;
                       otherwise falls back to rough char/4 estimates.

Use --assembly before burning money. The grid view is for planning; the
assembly check is for validating the plan actually fits.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))

from src.assembly import assemble, compute_noise_split  # noqa: E402
from src.cells import (  # noqa: E402
    CellSpec, RunSpec, filter_to_pilot, generate_cells, make_run_id, summarize,
)
from src.config import ExperimentConfig, load_arm_config  # noqa: E402
from src.materials import Materials, load_materials  # noqa: E402


# =========================================================================
# entrypoint
# =========================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, help="analyst arm name (config/arms/<arm>.yaml)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--grid", action="store_true", help="summarize design grid + cost estimate (default)")
    mode.add_argument(
        "--assembly",
        action="store_true",
        help="assemble pilot prompts and report realized token counts",
    )
    parser.add_argument("--pilot", action="store_true", help="(--grid only) restrict to pilot cells")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level="INFO", format="%(message)s")
    cfg = load_arm_config(args.arm)

    print(f"experiment: {cfg.name} v{cfg.version}")
    print(f"config hash: {cfg.config_sha256[:12]}")
    print()

    if args.assembly:
        return asyncio.run(_assembly_check(cfg))
    return _grid_summary(cfg, args.pilot)


# =========================================================================
# --grid: design-grid summary + cost estimate
# =========================================================================

def _grid_summary(cfg: ExperimentConfig, pilot: bool) -> int:
    all_cells = generate_cells(cfg)
    cells = filter_to_pilot(all_cells, cfg) if pilot else all_cells

    summary = summarize(cells, cfg.design.reps_per_cell)
    print(f"cells: {summary['total_cells']} "
          f"({summary['baseline_cells']} baseline + "
          f"{summary['non_baseline_cells']} non-baseline)")
    print(f"runs:  {summary['total_runs']} (reps_per_cell={cfg.design.reps_per_cell})")
    print()

    _estimate_cost(cfg, cells, pilot)
    print()
    _distribution_by_fill(cells, cfg.design.reps_per_cell)
    print()
    _distribution_by_position(cells, cfg.design.reps_per_cell)
    print()
    _distribution_by_noise(cells, cfg.design.reps_per_cell)
    return 0


def _estimate_cost(cfg: ExperimentConfig, cells: list[CellSpec], pilot: bool) -> None:
    """
    Rough cost model, updated for rubric v2.1:
      - Analyst: Opus 4.7 xhigh. Cache write once per cell, read on each rep.
      - Extractor: Haiku 4.5 per run.
      - Judge primary: Opus 4.7 xhigh, single-pass per tier-3 response.
        Target materials cached per cell session (amortized across reps*tier3).
      - Judge secondary: Sonnet 4.6, 20% cross-model ICC subsample, 1 pass.
      - Pairwise: Opus 4.7 xhigh, 25% subsample, 1 call.
    Numbers are ballpark — tolerates ~20% drift from reality.
    """
    reps = cfg.design.reps_per_cell
    opus = cfg.cost.pricing["opus_4_7"]
    sonnet = cfg.cost.pricing["sonnet_4_6"]
    haiku = cfg.cost.pricing["haiku_4_5"]
    # Analyst pricing varies by arm — judge stays Opus across all arms.
    analyst_pricing = cfg.cost.pricing[cfg.model_family(cfg.models.analyst.snapshot)]

    total_runs = len(cells) * reps
    n_tier3_per_run = 3                          # Q6, Q7, Q8

    # Analyst (collect) — priced with the arm's analyst family, not hardcoded Opus.
    avg_input_tokens = int(
        sum(int(cfg.tokens.total_context_target * c.fill_pct)
            if c.fill_pct > 0 else cfg.tokens.report_token_cap
            for c in cells) / max(1, len(cells))
    )
    per_cell_write_usd = avg_input_tokens * analyst_pricing.cache_write / 1_000_000
    per_cell_read_usd = (reps - 1) * avg_input_tokens * analyst_pricing.cache_read / 1_000_000
    collect_input_usd = len(cells) * (per_cell_write_usd + per_cell_read_usd)

    # Analyst output: adaptive thinking + answer. Opus 4.7 at effort=max
    # empirically produces ~800 tokens on a trivial prompt; on a complex
    # 10-K analysis we estimate 15-25K total output (thinking bundled into
    # output_tokens — the SDK does not expose a separate thinking counter).
    # Using 20K as the ballpark midpoint. Refine after pilot.
    effort_to_output_estimate = {
        None: 2000, "low": 500, "medium": 2000,
        "high": 8000, "xhigh": 15000, "max": 20000,
    }
    # Non-Anthropic vendors store effort in thinking_config (vendor-native shape)
    # rather than thinking_effort. They run at vendor-max per MULTI_VENDOR_ADDENDUM
    # §3 — estimate at "max" tier for cost projection.
    analyst_effort_for_est = cfg.models.analyst.thinking_effort
    if analyst_effort_for_est is None and cfg.models.analyst.vendor != "anthropic":
        analyst_effort_for_est = "max"
    avg_output_tokens = effort_to_output_estimate.get(analyst_effort_for_est, 20000)
    collect_output_usd = total_runs * avg_output_tokens * analyst_pricing.output / 1_000_000

    # Extractor
    extract_usd = total_runs * (5_000 * haiku.input + 500 * haiku.output) / 1_000_000

    # Judge primary (Opus xhigh, single pass per tier-3 response).
    # Per call: 94K cached target + ~5K user prompt + ~15K thinking + ~500 output.
    # Cache write amortized per cell session (reps × tier3 reads per write).
    target_tokens = 94_000  # 10-K + earnings call
    per_cell_judge_write = target_tokens * opus.cache_write / 1_000_000
    per_call_judge_read = target_tokens * opus.cache_read / 1_000_000
    per_call_judge_user = 5_000 * opus.input / 1_000_000
    # Thinking is bundled into output_tokens. Judge at effort=max on a grading
    # task produces an estimated ~15K thinking + ~500 JSON = ~15.5K output.
    judge_output_estimate = effort_to_output_estimate.get(
        cfg.models.judge_primary.thinking_effort, 15_000
    )
    judge_think_out = (judge_output_estimate + 500) * opus.output / 1_000_000

    n_tier3_responses = total_runs * n_tier3_per_run
    judge_primary_usd = (
        len(cells) * per_cell_judge_write
        + n_tier3_responses * (per_call_judge_read + per_call_judge_user + judge_think_out)
    )

    # Judge secondary (Sonnet 4.6, 20% cross-model ICC, no thinking)
    n_secondary = int(0.20 * n_tier3_responses)
    secondary_usd = n_secondary * (
        (target_tokens + 5_000) * sonnet.input + 500 * sonnet.output
    ) / 1_000_000

    # Pairwise (Opus 4.7 xhigh, 25% subsample). Input has TWO responses → ~10K user.
    n_pairwise = int(0.25 * n_tier3_responses)
    pairwise_usd = n_pairwise * (
        per_call_judge_read
        + 10_000 * opus.input / 1_000_000
        + judge_think_out
    )

    total = collect_input_usd + collect_output_usd + extract_usd + judge_primary_usd + secondary_usd + pairwise_usd

    print(f"estimated cost ({'pilot' if pilot else 'full'}):")
    print(f"  analyst input:  ${collect_input_usd:>9,.2f}  (write-once + reads/rep)")
    print(f"  analyst output: ${collect_output_usd:>9,.2f}  ({avg_output_tokens//1000}k tokens/run, thinking+answer)")
    print(f"  extractor:      ${extract_usd:>9,.2f}")
    print(f"  judge primary:  ${judge_primary_usd:>9,.2f}  ({n_tier3_responses} calls, Opus xhigh, cached)")
    print(f"  judge secondary:${secondary_usd:>9,.2f}  ({n_secondary} calls, Sonnet ICC)")
    print(f"  pairwise:       ${pairwise_usd:>9,.2f}  ({n_pairwise} calls, Opus xhigh)")
    print(f"  TOTAL:          ${total:>9,.2f}")
    print(f"  budget:         ${cfg.cost.budget_usd:>9,.2f}")
    print(f"  hard stop:      ${cfg.cost.hard_stop_usd:>9,.2f}")
    if total > cfg.cost.budget_usd:
        print(f"  WARNING: exceeds budget by ${total - cfg.cost.budget_usd:,.2f}")


def _distribution_by_fill(cells, reps: int) -> None:
    buckets: dict[float, int] = {}
    for c in cells:
        buckets[c.fill_pct] = buckets.get(c.fill_pct, 0) + reps
    print("runs by fill:")
    for fill in sorted(buckets):
        print(f"  {int(fill * 100):>3d}%: {buckets[fill]}")


def _distribution_by_position(cells, reps: int) -> None:
    buckets: dict[str, int] = {}
    for c in cells:
        key = c.position or "-"
        buckets[key] = buckets.get(key, 0) + reps
    print("runs by position:")
    for k, v in sorted(buckets.items()):
        print(f"  {k:>6}: {v}")


def _distribution_by_noise(cells, reps: int) -> None:
    buckets: dict[str, int] = {}
    for c in cells:
        key = c.noise_type or "-"
        buckets[key] = buckets.get(key, 0) + reps
    print("runs by noise:")
    for k, v in sorted(buckets.items()):
        print(f"  {k:>18}: {v}")


# =========================================================================
# --assembly: assemble pilot prompts, report realized token counts
# =========================================================================

async def _assembly_check(cfg: ExperimentConfig) -> int:
    materials = load_materials(cfg.paths.materials_dir, cfg.paths.materials_lock)
    print(f"materials lock: {materials.lock_sha256[:12]}")
    bundle = materials.target_bundles["MSFT"]
    print(f"target bundle: 10-K {bundle.report.token_count:,} + earnings {bundle.earnings_call.token_count:,} "
          f"= {bundle.combined_token_count:,} tokens")
    print(f"fill tolerance: ±{cfg.tokens.fill_tolerance_tokens:,} tokens")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        print("mode: AUTHORITATIVE (Anthropic count_tokens API)")
        from anthropic import AsyncAnthropic  # local import so non-API mode doesn't need it
        client = AsyncAnthropic(api_key=api_key)
    else:
        print("mode: ESTIMATE ONLY (no ANTHROPIC_API_KEY in env — using char/4)")
        client = None
    print()

    all_cells = generate_cells(cfg)
    pilot = filter_to_pilot(all_cells, cfg)

    # Also include one representative non-pilot edge cell to stress-test.
    max_fill_cells = [c for c in all_cells if c.fill_pct == max(cfg.design.fill_levels)]
    stress_samples = [c for c in max_fill_cells if c.position == "start"][:1]

    cells_to_check = pilot + [c for c in stress_samples if c not in pilot]

    any_warnings = False
    for cell in cells_to_check:
        warn = await _check_one_cell(cell, materials, cfg, client)
        any_warnings = any_warnings or warn
        print()

    print("=" * 60)
    if any_warnings:
        print("RESULT: warnings present — review before running the pilot.")
        return 1
    print("RESULT: all checked cells fit within budget + tolerance.")
    return 0


async def _check_one_cell(
    cell: CellSpec,
    materials: Materials,
    cfg: ExperimentConfig,
    client,  # AsyncAnthropic | None
) -> bool:
    """Assemble a prompt for this cell, print breakdown, return True if warnings."""
    print(f"--- cell: {cell.describe()} ---")

    # --- compute target + noise budgets (mirrors tokens.py logic) ---
    pool_max = _pool_max_tokens(materials, cell)
    bundle = materials.target_bundles[cell.report_id]
    overhead = bundle.combined_token_count + 1_500  # system (~500) + questions (~1000)
    target_input = _target_input_tokens(cfg, cell.fill_pct, overhead)
    total_noise_budget = max(0, target_input - overhead)
    noise_a, noise_b = compute_noise_split(cell.position, total_noise_budget)

    # --- assemble a RunSpec for rep 0 ---
    run = RunSpec(run_id=make_run_id(cell.cell_id, 0), cell=cell, rep_idx=0)
    prompt = assemble(run, materials, noise_a, noise_b)
    est = prompt.estimated_tokens

    # --- print breakdown ---
    print(f"  target input:        {target_input:>10,} tokens  ({int(cell.fill_pct*100)}% of 1M)")
    print(f"  noise budget total:  {total_noise_budget:>10,} tokens  (noise_a {noise_a:,} + noise_b {noise_b:,})")
    print(f"  noise pool max:      {pool_max:>10,} tokens  (peer materials available for MSFT)")
    print()
    print(f"  estimated segment sizes:")
    print(f"    system (analyst):  {est.get('system', 0):>10,}")
    print(f"    noise_a actual:    {est.get('noise_a_actual', 0):>10,}  (budget {est.get('noise_a_target', 0):,})")
    print(f"    target bundle:     {est.get('target', 0):>10,}  (10-K + earnings call)")
    print(f"    noise_b actual:    {est.get('noise_b_actual', 0):>10,}  (budget {est.get('noise_b_target', 0):,})")
    print(f"    questions block:   {est.get('questions', 0):>10,}")
    est_total = (
        est.get("system", 0)
        + est.get("noise_a_actual", 0)
        + est.get("target", 0)
        + est.get("noise_b_actual", 0)
        + est.get("questions", 0)
    )
    print(f"    estimate total:    {est_total:>10,}")

    # --- authoritative count if API available ---
    realized = None
    if client is not None:
        try:
            # See note in src/tokens.py — non-Anthropic arms use the judge
            # primary's Anthropic snapshot for fill-grid tokenization.
            tokenizer_model = (
                cfg.models.analyst.snapshot
                if cfg.models.analyst.vendor == "anthropic"
                else cfg.models.judge_primary.snapshot
            )
            resp = await client.messages.count_tokens(
                model=tokenizer_model,
                system=prompt.system,
                messages=prompt.messages,
            )
            realized = int(resp.input_tokens)
            print(f"    authoritative:     {realized:>10,}  (Anthropic count_tokens)")
        except Exception as e:
            print(f"    authoritative:     FAILED ({e!r})")
            realized = None

    # --- warnings ---
    total_for_checks = realized if realized is not None else est_total
    warnings: list[str] = []

    delta = total_for_checks - target_input
    if abs(delta) > cfg.tokens.fill_tolerance_tokens:
        noise_used = est.get("noise_a_actual", 0) + est.get("noise_b_actual", 0)
        exhausted = noise_used >= pool_max - 500 if pool_max > 0 else False
        if delta < 0 and exhausted:
            warnings.append(
                f"under-target by {-delta:,} tokens; noise POOL EXHAUSTED "
                f"({noise_used:,}/{pool_max:,}). "
                "pool_exhausted flag will fire; not an exclusion."
            )
        elif delta < 0:
            warnings.append(
                f"under-target by {-delta:,} tokens but pool has headroom "
                f"({pool_max - noise_used:,}). resolve_budget should iterate further."
            )
        else:
            warnings.append(
                f"OVER target by {delta:,} tokens — this run would be excluded per §7.5."
            )
    if total_for_checks > cfg.tokens.total_context_target:
        warnings.append(
            f"total {total_for_checks:,} exceeds 1M context window — will fail at runtime."
        )
    if target_input > pool_max + overhead:
        warnings.append(
            f"design-level: target {target_input:,} unreachable — pool max "
            f"{pool_max:,} + overhead {overhead:,} = {pool_max + overhead:,}. "
            "Expected for 95% fill; pool_exhausted cells are reported but not excluded."
        )

    if warnings:
        for w in warnings:
            print(f"  ! {w}")
    else:
        print("  OK within tolerance.")

    return bool(warnings) and not any(
        "pool_exhausted" in w or "pool EXHAUSTED" in w or "pool-EXHAUSTED" in w for w in warnings
    )


# --- helpers (mirrors private helpers in tokens.py) ----------------------

def _target_input_tokens(cfg: ExperimentConfig, fill_pct: float, overhead: int) -> int:
    # Mirrors tokens._target_input_tokens: baseline target equals the actual
    # non-noise overhead (bundle + system + questions) so the under-target
    # validation does not fire on baseline runs.
    if fill_pct == 0.0:
        return overhead
    raw = int(cfg.tokens.total_context_target * fill_pct)
    margin = int(raw * cfg.tokens.safety_margin_pct)
    return raw - margin


def _pool_max_tokens(materials: Materials, cell: CellSpec) -> int:
    if cell.noise_type is None:
        return 0
    pool = materials.noise.get(cell.noise_type, [])
    if cell.noise_type == "peer_materials":
        pool = [d for d in pool if d.pair_target in (cell.report_id, None)]
    return sum(d.token_count for d in pool)


if __name__ == "__main__":
    raise SystemExit(main())
