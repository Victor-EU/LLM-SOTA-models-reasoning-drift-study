"""
End-to-end smoke test: one real analyst call on the baseline cell.

Bypasses manifest persistence — just exercises the prompt-assembly,
budget-resolution, and analyst-call code path with a single live API call.

Usage:
    python -m scripts.smoke_test [--cell-fill 0.0]

Default uses fill=0.0 (baseline) for cheapest verification (~$3-5).
Use --cell-fill 0.5 to test a high-context cell (~$10).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))

from src.api import run_analyst  # noqa: E402
from src.cells import RunSpec, generate_cells, make_run_id  # noqa: E402
from src.config import load_arm_config  # noqa: E402
from src.materials import load_materials  # noqa: E402
from src.tokens import resolve_budget  # noqa: E402
from src.validation import validate_run  # noqa: E402


async def smoke(arm: str, cell_fill: float) -> int:
    load_dotenv()
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger("smoke")

    cfg = load_arm_config(arm)
    materials = load_materials(cfg.paths.materials_dir, cfg.paths.materials_lock)

    cells = generate_cells(cfg)
    matching = [c for c in cells if abs(c.fill_pct - cell_fill) < 0.01]
    if not matching:
        log.error("no cell with fill=%.2f", cell_fill)
        return 2
    cell = matching[0]
    run = RunSpec(run_id=make_run_id(cell.cell_id, 0), cell=cell, rep_idx=0)

    log.info("smoke cell: %s", cell.describe())

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return 2
    client = AsyncAnthropic(api_key=api_key)

    # Step 1: budget resolution (uses count_tokens — free).
    log.info("resolving budget...")
    t0 = time.monotonic()
    budget = await resolve_budget(client=client, run=run, materials=materials, cfg=cfg)
    log.info(
        "budget: target=%s realized=%s iters=%d pool_exhausted=%s is_baseline=%s (%.1fs)",
        f"{budget.target_input_tokens:,}",
        f"{budget.realized_input_tokens:,}",
        budget.iterations,
        budget.pool_exhausted,
        budget.is_baseline,
        time.monotonic() - t0,
    )
    log.info("noise docs packed: %s", budget.prompt.noise_doc_ids or "(none)")

    # Step 2: real analyst call.
    log.info("calling analyst (Opus 4.7, max thinking)...")
    t0 = time.monotonic()
    result = await run_analyst(client=client, prompt=budget.prompt, cfg=cfg)
    elapsed = time.monotonic() - t0
    log.info(
        "analyst: stop_reason=%s output_tokens=%d thinking_tokens=%s (%.1fs, %d attempts)",
        result.stop_reason,
        result.usage.output_tokens,
        result.usage.thinking_tokens,
        elapsed,
        result.attempts,
    )
    log.info(
        "usage: input=%d cache_read=%d cache_write=%d output=%d",
        result.usage.input_tokens,
        result.usage.cache_read_input_tokens,
        result.usage.cache_creation_input_tokens,
        result.usage.output_tokens,
    )

    # Cost calc.
    family = cfg.model_family(cfg.models.analyst.snapshot)
    p = cfg.cost.pricing[family]
    cost = (
        (result.usage.input_tokens - result.usage.cache_read_input_tokens) * p.input
        + result.usage.cache_read_input_tokens * p.cache_read
        + result.usage.cache_creation_input_tokens * p.cache_write
        + result.usage.output_tokens * p.output
    ) / 1_000_000
    log.info("estimated cost: $%.3f", cost)

    # Step 3: validation.
    expected_qids = [q.q_id for q in materials.questions[run.cell.report_id]]
    validation = validate_run(
        result=result,
        realized_input_tokens=budget.realized_input_tokens,
        target_input_tokens=budget.target_input_tokens,
        expected_question_ids=expected_qids,
        cfg=cfg,
        pool_exhausted=budget.pool_exhausted,
        is_baseline=budget.is_baseline,
    )
    log.info("validation: exclude=%s reason=%s flags=%s", validation.exclude, validation.reason, validation.flags)

    # Step 4: response peek.
    print()
    print("=" * 72)
    print("RESPONSE TEXT (first 1500 chars):")
    print("=" * 72)
    print(result.text[:1500])
    print("..." if len(result.text) > 1500 else "")
    print()
    print("=" * 72)
    print(f"THINKING TEXT preview (first 500 chars of {len(result.thinking_text):,} total):")
    print("=" * 72)
    print(result.thinking_text[:500])
    print("..." if len(result.thinking_text) > 500 else "")

    return 0 if not validation.exclude else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, help="analyst arm name (config/arms/<arm>.yaml)")
    parser.add_argument("--cell-fill", type=float, default=0.0,
                        help="fill_pct of cell to test (default 0.0 = baseline)")
    args = parser.parse_args()
    return asyncio.run(smoke(args.arm, args.cell_fill))


if __name__ == "__main__":
    raise SystemExit(main())
