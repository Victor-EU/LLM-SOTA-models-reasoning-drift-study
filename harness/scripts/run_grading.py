"""
Grading stage entry point.

Routes Tier 1/2 records to the local autograder and Tier 3 records to the
Opus 4.7 absolute judge (cached target materials), with deterministic
subsamples going to Sonnet 4.6 secondary (ICC) and Opus pairwise (vs baseline).

Usage:
    python -m scripts.run_grading
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

from src.config import load_config  # noqa: E402
from src.cost import CostTracker  # noqa: E402
from src.judge import run_grade_stage  # noqa: E402
from src.manifest import Manifest  # noqa: E402
from src.materials import load_materials  # noqa: E402
from src.persistence import WriterCache  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(HARNESS_ROOT / "config" / "experiment.yaml"))
    args = parser.parse_args()

    load_dotenv()
    cfg = load_config(args.config)
    logging.basicConfig(level=cfg.observability.log_level,
                        format="%(asctime)s %(levelname)-5s %(name)s %(message)s")
    log = logging.getLogger("run_grading")

    materials = load_materials(cfg.paths.materials_dir, cfg.paths.materials_lock)
    manifest = Manifest(cfg.paths.manifest_db)
    cost_tracker = CostTracker(cfg, manifest)
    writers = WriterCache(cfg.paths.data_dir)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return 2
    client = AsyncAnthropic(api_key=api_key)

    log.info("starting grade stage. cumulative cost so far: $%.2f", cost_tracker.total())

    asyncio.run(run_grade_stage(
        client=client,
        materials=materials,
        cfg=cfg,
        manifest=manifest,
        cost_tracker=cost_tracker,
        writers=writers,
    ))

    log.info("grade stage done. cumulative cost: $%.2f", cost_tracker.total())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
