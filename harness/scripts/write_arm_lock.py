"""
Generate arms/<arm>/data.manifest.sha256 and arms/<arm>/arm.lock.json for a v2 arm.

Mirrors the structure of arms/opus-4-7/arm.lock.json (v1) with v2 extensions:
  - analyst.vendor field
  - analyst.thinking_config dict (vendor-native max thinking knob)
  - pricing snapshot keyed by vendor
  - execution_results includes vendor-observed model strings as a one-line audit

Usage:
    python -m scripts.write_arm_lock --arm gpt-5-5
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import glob
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import yaml

HARNESS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = HARNESS_ROOT.parent
sys.path.insert(0, str(HARNESS_ROOT))

from src.config import load_arm_config  # noqa: E402

V2_LOCK_PATH = PROJECT_ROOT / "pre_registration.v2.lock"


def hash_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    sz = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            sz += len(chunk)
    return h.hexdigest(), sz


def write_data_manifest(arm: str, arm_dir: Path) -> Path:
    data_root = arm_dir / "data"
    files = sorted(p for p in data_root.rglob("*") if p.is_file())
    lines = [
        f"# {arm} arm — data integrity manifest",
        f"# Generated: {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d')}",
        f"# Files: {len(files)}",
        "# Format: <sha256>  <size_bytes>  <path_relative_to_data_root>",
        "#",
    ]
    for p in files:
        sha, size = hash_file(p)
        rel = p.relative_to(data_root).as_posix()
        lines.append(f"{sha}  {size}  {rel}")
    out = arm_dir / "data.manifest.sha256"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def cumulative_cost(arm_dir: Path) -> float:
    db = arm_dir / "data" / "manifest.sqlite"
    c = sqlite3.connect(str(db))
    try:
        row = c.execute("SELECT COALESCE(SUM(total_usd), 0) FROM costs").fetchone()
    except sqlite3.OperationalError:
        return 0.0
    finally:
        c.close()
    return float(row[0] if row else 0.0)


def collect_runs_completed(arm_dir: Path) -> int:
    db = arm_dir / "data" / "manifest.sqlite"
    c = sqlite3.connect(str(db))
    try:
        row = c.execute(
            "SELECT COUNT(*) FROM runs WHERE stage='collect' AND status='completed'"
        ).fetchone()
    finally:
        c.close()
    return int(row[0] if row else 0)


def count_extracted(arm_dir: Path) -> tuple[int, int]:
    total = ok = 0
    for f in glob.glob(str(arm_dir / "data" / "extracted" / "*.jsonl")):
        for line in open(f):
            r = json.loads(line)
            total += 1
            if r.get("parsed_ok", True):
                ok += 1
    return total, ok


def count_graded(arm_dir: Path) -> int:
    n = 0
    for f in glob.glob(str(arm_dir / "data" / "graded" / "*.jsonl")):
        n += sum(1 for _ in open(f))
    return n


def observed_models(arm_dir: Path) -> list[str]:
    seen: set[str] = set()
    for f in glob.glob(str(arm_dir / "data" / "raw" / "*.jsonl")):
        for line in open(f):
            r = json.loads(line)
            m = r.get("model")
            if m:
                seen.add(m)
    return sorted(seen)


VENDOR_PRICING_KEY = {
    "anthropic": None,
    "openai": "gpt_5_5",
    "google": "gemini_3_1_pro",
    "deepseek": "deepseek_v4_pro",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    args = ap.parse_args()

    cfg = load_arm_config(args.arm)
    arm_dir = PROJECT_ROOT / "arms" / args.arm
    if not arm_dir.exists():
        print(f"FAIL: arm dir not found: {arm_dir}", file=sys.stderr)
        return 2

    v2_lock = json.loads(V2_LOCK_PATH.read_text())
    materials_lock_hash = v2_lock["materials_lock_hash"]

    arm_yaml = yaml.safe_load((HARNESS_ROOT / "config" / "arms" / f"{args.arm}.yaml").read_text())
    arm_description = arm_yaml.get("arm", {}).get("description", "")

    print(f"writing data.manifest.sha256 for {args.arm} ...")
    manifest_path = write_data_manifest(args.arm, arm_dir)
    self_sha, _ = hash_file(manifest_path)
    print(f"  manifest self-sha256: {self_sha}")

    extract_total, extract_ok = count_extracted(arm_dir)
    pct = round(100 * extract_ok / extract_total, 1) if extract_total else 0.0

    analyst_pricing_key = VENDOR_PRICING_KEY[cfg.models.analyst.vendor]
    pricing = {
        "opus_4_7": dataclasses.asdict(cfg.cost.pricing["opus_4_7"]),
        "sonnet_4_6": dataclasses.asdict(cfg.cost.pricing["sonnet_4_6"]),
        "haiku_4_5": dataclasses.asdict(cfg.cost.pricing["haiku_4_5"]),
    }
    if analyst_pricing_key:
        pricing[analyst_pricing_key] = dataclasses.asdict(cfg.cost.pricing[analyst_pricing_key])

    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT).decode().strip()
    except Exception:
        git_sha = "unknown"

    lock = {
        "$schema_version": "2.0",
        "arm_name": cfg.arm_name,
        "arm_description": arm_description,
        "pre_registration": {
            "hash": cfg.pre_registration_hash,
            "lock_file": "../../pre_registration.v2.lock",
            "note": "MUST match pre_registration.v2.lock.methodology_hash. compare_arms.py refuses to run if any arm's hash differs.",
        },
        "materials": {
            "lock_hash": materials_lock_hash,
            "lock_path": "../../materials/materials.lock.json",
            "note": "MUST match pre_registration.v2.lock.materials_lock_hash.",
        },
        "analyst": {
            "vendor": cfg.models.analyst.vendor,
            "snapshot": cfg.models.analyst.snapshot,
            "snapshot_observed_aliases": observed_models(arm_dir),
            "snapshot_observed_aliases_note": "Some vendors return a build-resolved model ID (e.g., a versioned alias) different from the requested snapshot string. The verify script accepts records whose model matches snapshot OR any value here. A single value indicates no mid-experiment build drift.",
            "context_window": cfg.models.analyst.context_window,
            "thinking_effort": cfg.models.analyst.thinking_effort,
            "thinking_config": cfg.models.analyst.thinking_config,
            "max_output_tokens": cfg.models.analyst.max_output_tokens,
            "temperature": cfg.models.analyst.temperature,
        },
        "instruments_used": {
            "extractor": {
                "snapshot": cfg.models.extractor.snapshot,
                "max_output_tokens": cfg.models.extractor.max_output_tokens,
                "temperature": cfg.models.extractor.temperature,
                "thinking_effort": cfg.models.extractor.thinking_effort,
            },
            "judge_primary": {
                "snapshot": cfg.models.judge_primary.snapshot,
                "max_output_tokens": cfg.models.judge_primary.max_output_tokens,
                "temperature": cfg.models.judge_primary.temperature,
                "thinking_effort": cfg.models.judge_primary.thinking_effort,
            },
            "judge_secondary": {
                "snapshot": cfg.models.judge_secondary.snapshot,
                "max_output_tokens": cfg.models.judge_secondary.max_output_tokens,
                "temperature": cfg.models.judge_secondary.temperature,
                "thinking_effort": cfg.models.judge_secondary.thinking_effort,
                "subsample_pct": 20,
            },
        },
        "design_used": {
            "fill_levels": list(cfg.design.fill_levels),
            "positions": list(cfg.design.positions),
            "noise_types": list(cfg.design.noise_types),
            "reports": list(cfg.design.reports),
            "reps_per_cell": cfg.design.reps_per_cell,
            "tokens_total_context_target": cfg.tokens.total_context_target,
            "tokens_report_token_cap": cfg.tokens.report_token_cap,
        },
        "pricing_at_lock_usd_per_million_tokens": pricing,
        "pricing_note": "Snapshotted to allow honest cost reconstruction even if API pricing changes after this arm closes.",
        "execution_results": {
            "collect_runs_completed": collect_runs_completed(arm_dir),
            "extract_records_total": extract_total,
            "extract_records_parsed_ok": extract_ok,
            "extract_records_parsed_ok_pct": pct,
            "grade_records_completed": count_graded(arm_dir),
            "cumulative_cost_usd": round(cumulative_cost(arm_dir), 2),
            "budget_usd": cfg.cost.budget_usd,
            "hard_stop_usd": cfg.cost.hard_stop_usd,
            "analyst_models_observed": observed_models(arm_dir),
        },
        "data_integrity": {
            "data_root": "data/",
            "data_manifest_path": "data.manifest.sha256",
            "data_manifest_sha256_self": self_sha,
            "data_manifest_sha256_self_recipe": f"sha256 of arms/{args.arm}/data.manifest.sha256 file bytes",
            "verify_command": f"python3 -m scripts.verify_arm_integrity --arm {args.arm}",
        },
        "git_anchor": {
            "commit": git_sha,
            "tag": f"arm/{args.arm}/data-v2.0",
            "note": "Tag pending; create with `git tag -a arm/<arm>/data-v2.0 -m 'lock' <commit>` after lock review.",
        },
        "locked_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "locked_by": "Victor Zhang <victor.zhang.eu@gmail.com>",
        "reports": [],
    }

    out = arm_dir / "arm.lock.json"
    out.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    er = lock["execution_results"]
    print(f"  collect={er['collect_runs_completed']}/91")
    print(f"  extract_ok={er['extract_records_parsed_ok']}/{er['extract_records_total']} ({er['extract_records_parsed_ok_pct']}%)")
    print(f"  grade={er['grade_records_completed']}")
    print(f"  cost=${er['cumulative_cost_usd']}")
    print(f"  models_observed={er['analyst_models_observed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
