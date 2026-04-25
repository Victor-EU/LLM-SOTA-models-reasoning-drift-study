"""
Verify the integrity of an arm's locked data.

Three checks:
  1. Recompute SHA-256 of every file under arms/<arm>/data/ and confirm it
     matches arms/<arm>/data.manifest.sha256.
  2. Confirm arm.lock.json's pre_registration.hash matches the project-wide
     pre_registration.lock.methodology_hash.
  3. Confirm arm.lock.json's materials.lock_hash matches the project-wide
     pre_registration.lock.materials_lock_hash AND matches the actual
     SHA-256 of materials/materials.lock.json on disk.

Exits 0 on success, non-zero on any drift. Useful as a CI gate or before
running cross-arm comparison.

Usage:
  python -m scripts.verify_arm_integrity --arm opus-4-7
  python -m scripts.verify_arm_integrity --arm opus-4-7 --quiet
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_manifest(text: str) -> dict[str, tuple[str, int]]:
    """Parse a SHA-256 manifest file: '<sha>  <size>  <path>' lines."""
    out: dict[str, tuple[str, int]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        sha, size, rel = parts
        out[rel] = (sha, int(size))
    return out


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_data_manifest(arm_dir: Path, *, quiet: bool) -> int:
    manifest_path = arm_dir / "data.manifest.sha256"
    data_root = arm_dir / "data"
    if not manifest_path.exists():
        print(f"FAIL: missing manifest {manifest_path}")
        return 1
    if not data_root.exists():
        print(f"FAIL: missing data root {data_root}")
        return 1

    expected = parse_manifest(manifest_path.read_text(encoding="utf-8"))
    if not expected:
        print(f"FAIL: manifest {manifest_path} is empty")
        return 1

    missing = []
    mismatches = []
    extra = []
    actual_files = {p.relative_to(data_root).as_posix() for p in data_root.rglob("*") if p.is_file()}
    expected_files = set(expected.keys())

    for rel in expected_files - actual_files:
        missing.append(rel)
    for rel in actual_files - expected_files:
        extra.append(rel)
    for rel in expected_files & actual_files:
        exp_sha, exp_size = expected[rel]
        p = data_root / rel
        got_sha = hash_file(p)
        got_size = p.stat().st_size
        if got_sha != exp_sha or got_size != exp_size:
            mismatches.append((rel, exp_sha, got_sha))

    n_ok = len(expected_files & actual_files) - len(mismatches)
    if not quiet:
        print(f"  data files in manifest:  {len(expected)}")
        print(f"  data files on disk:      {len(actual_files)}")
        print(f"  byte-identical:          {n_ok}")
        print(f"  missing from disk:       {len(missing)}")
        print(f"  extra on disk:           {len(extra)}")
        print(f"  hash mismatches:         {len(mismatches)}")

    failed = bool(missing or mismatches)
    if missing and not quiet:
        for rel in missing[:5]:
            print(f"    MISSING: {rel}")
        if len(missing) > 5:
            print(f"    ...and {len(missing)-5} more")
    if mismatches and not quiet:
        for rel, exp, got in mismatches[:5]:
            print(f"    MISMATCH: {rel}")
            print(f"      expected: {exp}")
            print(f"      got:      {got}")
        if len(mismatches) > 5:
            print(f"    ...and {len(mismatches)-5} more")
    if extra and not quiet:
        for rel in extra[:5]:
            print(f"    EXTRA (not in manifest): {rel}")
        if len(extra) > 5:
            print(f"    ...and {len(extra)-5} more")
        print(f"  NOTE: extra files are a warning, not a failure — manifest is the lock spec.")

    return 1 if failed else 0


def verify_arm_lock_consistency(arm_dir: Path, *, quiet: bool) -> int:
    lock_path = arm_dir / "arm.lock.json"
    pre_reg_path = PROJECT_ROOT / "pre_registration.lock"
    materials_lock_path = PROJECT_ROOT / "materials" / "materials.lock.json"

    if not lock_path.exists():
        print(f"FAIL: missing {lock_path}")
        return 1
    if not pre_reg_path.exists():
        print(f"FAIL: missing {pre_reg_path}")
        return 1
    if not materials_lock_path.exists():
        print(f"FAIL: missing {materials_lock_path}")
        return 1

    arm_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    pre_reg = json.loads(pre_reg_path.read_text(encoding="utf-8"))

    # Check 1: arm methodology hash matches project pre-reg
    arm_method = arm_lock["pre_registration"]["hash"]
    proj_method = pre_reg["methodology_hash"]
    method_ok = (arm_method == proj_method)

    # Check 2: arm materials hash matches project pre-reg
    arm_mat = arm_lock["materials"]["lock_hash"]
    proj_mat = pre_reg["materials_lock_hash"]
    mat_lock_ok = (arm_mat == proj_mat)

    # Check 3: project materials hash matches actual file on disk
    actual_mat_hash = hash_file(materials_lock_path)
    actual_ok = (proj_mat == actual_mat_hash)

    if not quiet:
        print(f"  methodology_hash (arm == project):       {'OK' if method_ok else 'FAIL'}")
        if not method_ok:
            print(f"    arm:     {arm_method}")
            print(f"    project: {proj_method}")
        print(f"  materials_lock_hash (arm == project):    {'OK' if mat_lock_ok else 'FAIL'}")
        if not mat_lock_ok:
            print(f"    arm:     {arm_mat}")
            print(f"    project: {proj_mat}")
        print(f"  materials_lock_hash (project == on-disk): {'OK' if actual_ok else 'FAIL'}")
        if not actual_ok:
            print(f"    project: {proj_mat}")
            print(f"    on-disk: {actual_mat_hash}")

    # Check 4: data.manifest.sha256 file's own hash matches arm.lock.json
    manifest_self_expected = arm_lock.get("data_integrity", {}).get("data_manifest_sha256_self")
    manifest_self_ok = True
    if manifest_self_expected:
        manifest_path = arm_dir / "data.manifest.sha256"
        actual_manifest_self = hash_file(manifest_path)
        manifest_self_ok = (actual_manifest_self == manifest_self_expected)
        if not quiet:
            print(f"  data.manifest.sha256 self-hash:          {'OK' if manifest_self_ok else 'FAIL'}")
            if not manifest_self_ok:
                print(f"    expected: {manifest_self_expected}")
                print(f"    actual:   {actual_manifest_self}")

    return 0 if (method_ok and mat_lock_ok and actual_ok and manifest_self_ok) else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify integrity of an arm's locked data and lock-file consistency."
    )
    parser.add_argument("--arm", required=True, help="arm name (matches arms/<arm>/)")
    parser.add_argument("--quiet", action="store_true", help="only report failures")
    args = parser.parse_args()

    arm_dir = PROJECT_ROOT / "arms" / args.arm
    if not arm_dir.exists():
        print(f"FAIL: arm directory does not exist: {arm_dir}")
        return 2

    print(f"Verifying arm: {args.arm}")
    print(f"Arm directory: {arm_dir.relative_to(PROJECT_ROOT)}")
    print()
    print("Check 1/2: data file SHA-256s vs data.manifest.sha256")
    rc1 = verify_data_manifest(arm_dir, quiet=args.quiet)
    print()
    print("Check 2/2: arm.lock.json consistency with pre_registration.lock + materials")
    rc2 = verify_arm_lock_consistency(arm_dir, quiet=args.quiet)
    print()
    if rc1 == 0 and rc2 == 0:
        print(f"PASS — arm {args.arm} integrity OK")
        return 0
    print(f"FAIL — arm {args.arm} integrity check failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
