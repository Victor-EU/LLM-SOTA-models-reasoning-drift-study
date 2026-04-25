"""
Main entrypoint — collect stage.

Usage:
    python -m scripts.run_experiment --arm opus-4-7 --pilot           # pilot cells
    python -m scripts.run_experiment --arm opus-4-7 --full            # full grid
    python -m scripts.run_experiment --arm opus-4-7 --cell <cell_id>  # single cell

The --arm flag selects which analyst arm to run. Per-arm config lives at
config/arms/<arm>.yaml and is overlaid on config/base.yaml. Output goes to
arms/<arm>/data/. See ARMS.md for the integrity model.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))

from src.cells import CellSpec, filter_to_pilot, generate_cells, summarize  # noqa: E402
from src.config import load_arm_config  # noqa: E402
from src.cost import CostTracker  # noqa: E402
from src.manifest import Manifest  # noqa: E402
from src.materials import load_materials  # noqa: E402
from src.persistence import WriterCache  # noqa: E402
from src.runner import run_collect_stage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, help="analyst arm name (config/arms/<arm>.yaml)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot", action="store_true", help="only run pilot cells")
    mode.add_argument("--full", action="store_true", help="run the full design grid")
    mode.add_argument("--cell", metavar="CELL_ID", help="run a single cell by id")
    args = parser.parse_args()

    load_dotenv()
    cfg = load_arm_config(args.arm)
    logging.basicConfig(
        level=cfg.observability.log_level,
        format="%(asctime)s %(levelname)-5s %(name)s %(message)s",
    )
    log = logging.getLogger("run_experiment")

    materials = load_materials(cfg.paths.materials_dir, cfg.paths.materials_lock)
    log.info("materials loaded (lock sha256=%s)", materials.lock_sha256[:12])

    manifest = Manifest(cfg.paths.manifest_db)
    manifest.set_meta("config_sha256", cfg.config_sha256)
    manifest.set_meta("pre_registration_hash", cfg.pre_registration_hash)
    manifest.set_meta("materials_lock_sha256", materials.lock_sha256)

    all_cells = generate_cells(cfg)
    if args.pilot:
        cells = filter_to_pilot(all_cells, cfg)
        log.info("pilot mode: %d cells", len(cells))
    elif args.full:
        cells = all_cells
    else:
        cells = [c for c in all_cells if c.cell_id == args.cell]
        if not cells:
            log.error("no cell with id %s", args.cell)
            return 2

    summary = summarize(cells, cfg.design.reps_per_cell)
    log.info("plan: %s", summary)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return 2
    client = AsyncAnthropic(api_key=api_key)

    cost_tracker = CostTracker(cfg, manifest)
    writers = WriterCache(cfg.paths.data_dir)

    asyncio.run(run_collect_stage(
        client=client,
        cells=cells,
        materials=materials,
        cfg=cfg,
        manifest=manifest,
        cost_tracker=cost_tracker,
        writers=writers,
    ))
    log.info("done. cumulative cost: $%.2f", cost_tracker.total())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
