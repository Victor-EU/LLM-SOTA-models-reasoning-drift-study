"""
Re-run the v3 programmatic temporal_scan over an arm's existing graded JSONLs.

Use case: the scanner module SHA changed (bug fix or refinement), but the
expensive judge calls (Opus xhigh + Sonnet ICC) are still valid. Re-running
the entire grade stage would burn ~$100/arm. This script applies ONLY the
post-judge scanner override, in place, against existing graded records.

Specifically, per pre_registration.v3.lock §grading_modules.temporal_scan:
  - Replace `record["temporal"]`               (per-record scan result)
  - For tier-3 records: replace `record["absolute"]["temporal_contamination"]`
    and recompute `record["absolute"]["scope_adherence_capped"]` via
    grading.scope_cap.apply_scope_cap(scope_adherence, cross_contamination,
    temporal_contamination=new_count).
  - For tier-3 records that have a `secondary` Sonnet judgement: same
    override on `record["secondary"]`.
  - Pairwise records are left untouched (no scope dimension).

Inputs are read from `data/extracted/` (the parsed analyst answers); the
graded files in `data/graded/` are mutated in place. Originals are preserved
at <name>.<bak_suffix>.

Usage:
    python -m scripts.rescan_temporal --arm gpt-5-5-temporal
    python -m scripts.rescan_temporal --arm gpt-5-5-temporal --dry-run
    python -m scripts.rescan_temporal --arm gpt-5-5-temporal \
        --bak-suffix .v0-prescanfix-bak

Refuses to run if the arm's noise_types do not include 'temporal_msft' (peer
arms have no distractors loaded — there is nothing to rescan).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))

from src.config import load_arm_config  # noqa: E402
from src.grading import (  # noqa: E402
    apply_scope_cap,
    load_distractors,
    scan_record,
    temporal_scan_module_sha256,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and print delta without mutating files.")
    ap.add_argument("--bak-suffix", default=".v0-prescanfix-bak",
                    help="Suffix appended to original graded files (default: .v0-prescanfix-bak).")
    args = ap.parse_args()

    cfg = load_arm_config(args.arm)
    if "temporal_msft" not in (cfg.design.noise_types or ()):
        print(f"[skip] arm {args.arm} has noise_types={cfg.design.noise_types!r} — "
              f"no temporal distractors loaded; nothing to rescan.")
        return 0

    distractors_path = (
        Path(cfg.paths.materials_dir) / "ground_truth" / "MSFT_temporal_distractors.json"
    )
    if not distractors_path.exists():
        print(f"[error] distractors file missing: {distractors_path}")
        return 2
    distractors_by_qid = load_distractors(distractors_path)
    print(f"loaded distractors: {sum(len(v) for v in distractors_by_qid.values())} "
          f"across {len(distractors_by_qid)} q_ids")
    print(f"scanner SHA: {temporal_scan_module_sha256()[:24]}…")

    extracted_dir = Path(cfg.paths.data_dir) / "extracted"
    graded_dir = Path(cfg.paths.data_dir) / "graded"

    # 1) Build (run_id, q_id) → extracted record index.
    by_key: dict[tuple[str, str], dict] = {}
    for f in sorted(extracted_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            by_key[(r["run_id"], r["q_id"])] = r
    print(f"indexed {len(by_key)} extracted records from {extracted_dir}")

    # 2) Walk graded JSONLs; rewrite temporal + scope_adherence_capped.
    n_files = 0
    n_records = 0
    n_temporal_changed = 0
    n_count_increased = 0
    n_count_decreased = 0
    n_scope_cap_changed = 0
    sample_changes: list[str] = []

    for graded_f in sorted(graded_dir.glob("*.jsonl")):
        if graded_f.name.endswith(args.bak_suffix):
            continue  # skip prior backups
        n_files += 1
        new_lines: list[str] = []
        for line in graded_f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            n_records += 1
            key = (rec["run_id"], rec["q_id"])
            extracted = by_key.get(key)
            if extracted is None:
                # No extracted record (rare; e.g. excluded run). Leave as-is.
                new_lines.append(json.dumps(rec))
                continue

            scan = scan_record(extracted, distractors_by_qid)
            new_temporal = scan.to_dict()
            old_temporal = rec.get("temporal", {"count": 0, "hits": []})
            old_count = old_temporal.get("count", 0)
            new_count = new_temporal["count"]

            if old_count != new_count:
                n_temporal_changed += 1
                if new_count > old_count:
                    n_count_increased += 1
                else:
                    n_count_decreased += 1
                if len(sample_changes) < 10:
                    sample_changes.append(
                        f"  {rec['cell_id'][:50]} q={rec['q_id']} tier={rec['tier']} "
                        f"rep={rec['rep_idx']}: count {old_count}→{new_count}"
                    )

            rec["temporal"] = new_temporal

            # Tier-3: judge override on absolute + secondary.
            if rec.get("tier") == 3:
                for judge_key in ("absolute", "secondary"):
                    j = rec.get(judge_key)
                    if not isinstance(j, dict):
                        continue
                    j["temporal_contamination"] = new_count
                    new_capped = apply_scope_cap(
                        scope_adherence=j.get("scope_adherence", 5),
                        cross_contamination=j.get("cross_contamination", 0),
                        temporal_contamination=new_count,
                    )
                    if j.get("scope_adherence_capped") != new_capped:
                        n_scope_cap_changed += 1
                    j["scope_adherence_capped"] = new_capped

            new_lines.append(json.dumps(rec))

        if not args.dry_run:
            bak = graded_f.with_suffix(graded_f.suffix + args.bak_suffix)
            if not bak.exists():
                shutil.copy2(graded_f, bak)
            graded_f.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    print()
    print(f"=== rescan summary ({'DRY RUN' if args.dry_run else 'APPLIED'}) ===")
    print(f"  graded files:                {n_files}")
    print(f"  records scanned:             {n_records}")
    print(f"  temporal-count changed:      {n_temporal_changed}")
    print(f"    increased (new TPs):       {n_count_increased}")
    print(f"    decreased (FP removed):    {n_count_decreased}")
    print(f"  scope_adherence_capped Δ:   {n_scope_cap_changed}")
    if sample_changes:
        print(f"  sample changes:")
        for c in sample_changes:
            print(c)
    if not args.dry_run:
        print(f"  backups: <name>.jsonl{args.bak_suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
