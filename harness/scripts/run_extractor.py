"""
Run the extraction stage over all completed collect-stage runs.

Usage:
    python -m scripts.run_extractor
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
from src.extractor import run_extract_stage  # noqa: E402
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

    materials = load_materials(cfg.paths.materials_dir, cfg.paths.materials_lock)
    manifest = Manifest(cfg.paths.manifest_db)
    cost_tracker = CostTracker(cfg, manifest)
    writers = WriterCache(cfg.paths.data_dir)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2
    client = AsyncAnthropic(api_key=api_key)

    asyncio.run(run_extract_stage(
        client=client,
        materials=materials,
        cfg=cfg,
        manifest=manifest,
        cost_tracker=cost_tracker,
        writers=writers,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
