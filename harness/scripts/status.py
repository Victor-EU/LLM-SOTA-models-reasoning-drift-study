"""
Inspect the manifest and print experiment progress.

Usage:
    python -m scripts.status --arm opus-4-7
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))

from src.config import load_arm_config  # noqa: E402
from src.manifest import Manifest, Stage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, help="analyst arm name (config/arms/<arm>.yaml)")
    args = parser.parse_args()

    cfg = load_arm_config(args.arm)
    manifest = Manifest(cfg.paths.manifest_db)

    print(f"experiment: {cfg.name} v{cfg.version} (arm={cfg.arm_name})")
    config_sha = manifest.get_meta("config_sha256")
    pre_reg = manifest.get_meta("pre_registration_hash")
    lock = manifest.get_meta("materials_lock_sha256")
    print(f"  config sha:          {config_sha[:12] if config_sha else '(none)'}")
    print(f"  pre-registration:    {pre_reg[:12] if pre_reg else '(none)'}")
    print(f"  materials lock:      {lock[:12] if lock else '(none)'}")
    print()

    for stage in (Stage.COLLECT, Stage.EXTRACT, Stage.GRADE):
        counts = manifest.status_counts(stage)
        total = sum(counts.values()) or 1
        done = counts.get("completed", 0) + counts.get("excluded", 0)
        print(f"stage: {stage.value}")
        for status in ("pending", "in_progress", "completed", "excluded", "failed"):
            n = counts.get(status, 0)
            print(f"  {status:>12}: {n}")
        print(f"  progress:     {done}/{total}  ({100 * done / total:.1f}%)")
        print()

    print(f"cumulative cost: ${manifest.cumulative_cost():.2f}")
    print(f"budget:          ${cfg.cost.budget_usd:.2f}")
    print(f"hard stop:       ${cfg.cost.hard_stop_usd:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
