"""
Verify the v3 isolation guarantee:
  - materials/materials.lock.json bytes are unchanged from v1/v2
    (expected SHA256 c13b5514279c9d8dbc5118ec9b3b1325a0cff56c4fb1cee8d66992a98cd25199).
  - No file in materials/noise/peer_materials/MSFT/ has been modified.
  - No file in materials/target/MSFT/ has been modified.
  - The new temporal_msft pool exists at the expected paths.

Per TEMPORAL_NOISE_ADDENDUM.md §7. Run after `build_materials.py --noise-type
temporal_msft` to confirm no v1/v2 surface was touched.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATERIALS = ROOT / "materials"

# v1/v2 lock hash recorded in pre_registration.v2.lock
EXPECTED_V12_LOCK_SHA = "c13b5514279c9d8dbc5118ec9b3b1325a0cff56c4fb1cee8d66992a98cd25199"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []

    # 1) v1/v2 lock file byte-identical
    lock_actual = sha(MATERIALS / "materials.lock.json")
    if lock_actual != EXPECTED_V12_LOCK_SHA:
        failures.append(
            f"materials.lock.json sha changed:\n"
            f"  expected: {EXPECTED_V12_LOCK_SHA}\n"
            f"  actual:   {lock_actual}"
        )
    else:
        print(f"[OK] materials.lock.json bytes unchanged ({lock_actual[:16]}…)")

    # 2) Every (sha, path) in the v1/v2 lock still matches the file on disk
    lock = json.loads((MATERIALS / "materials.lock.json").read_text(encoding="utf-8"))
    for relpath, info in lock["files"].items():
        f = MATERIALS / relpath
        if not f.exists():
            failures.append(f"missing file referenced by v1/v2 lock: {relpath}")
            continue
        s = hashlib.sha256(f.read_bytes()).hexdigest()
        if s != info["sha256"]:
            failures.append(
                f"v1/v2 file modified: {relpath}\n"
                f"  expected: {info['sha256']}\n"
                f"  actual:   {s}"
            )
    if not any("v1/v2 file modified" in x for x in failures):
        print(f"[OK] all {len(lock['files'])} v1/v2-locked files byte-identical to lock")

    # 3) Temporal corpus exists
    temporal_root = MATERIALS / "noise" / "temporal_msft" / "MSFT"
    if temporal_root.exists():
        n_txt = len(list(temporal_root.glob("*.txt")))
        n_meta = len(list(temporal_root.glob("*.meta.json")))
        print(f"[OK] temporal corpus dir exists with {n_txt} .txt + {n_meta} .meta.json files")
        # v0.2 attainable corpus = 34 (per addendum §3.1c source-availability ceiling)
        if n_txt == 34:
            print("     (v0.2 attainable corpus — see TEMPORAL_NOISE_ADDENDUM.md §3.1c)")
        elif n_txt < 34:
            print(f"     (note: v0.2 attainable count is 34; have {n_txt} — corpus incomplete)")
        elif n_txt > 34:
            print(f"     (note: have {n_txt} > v0.2 attainable count of 34 — sources extended; consider v0.3 lock)")
    else:
        print("[--] temporal corpus dir not yet created — addendum §3.2 not yet applied")

    # 4) materials_temporal.lock.json exists once collection is complete
    tl = MATERIALS / "materials_temporal.lock.json"
    tl_sha: str | None = None
    if tl.exists():
        tl_sha = sha(tl)
        n = len(json.loads(tl.read_text())["files"])
        print(f"[OK] materials_temporal.lock.json exists  sha={tl_sha[:16]}…  ({n} files locked)")
    else:
        print("[--] materials_temporal.lock.json not yet written")

    # 5) pre_registration.v3.lock pins both materials hashes correctly.
    v3 = ROOT / "pre_registration.v3.lock"
    if v3.exists():
        v3_data = json.loads(v3.read_text(encoding="utf-8"))
        if v3_data.get("materials_lock_hash") != EXPECTED_V12_LOCK_SHA:
            failures.append(
                f"pre_registration.v3.lock.materials_lock_hash != v1/v2 lock SHA\n"
                f"  expected: {EXPECTED_V12_LOCK_SHA}\n"
                f"  actual:   {v3_data.get('materials_lock_hash')}"
            )
        else:
            print(f"[OK] v3 lock pins materials_lock_hash = v1/v2 SHA")
        if tl_sha is not None:
            v3_temp = v3_data.get("materials_temporal_lock_hash")
            if v3_temp != tl_sha:
                failures.append(
                    f"pre_registration.v3.lock.materials_temporal_lock_hash != on-disk temporal lock SHA\n"
                    f"  v3 lock says: {v3_temp}\n"
                    f"  on-disk:      {tl_sha}"
                )
            else:
                print(f"[OK] v3 lock pins materials_temporal_lock_hash = on-disk SHA  ({v3_temp[:16]}…)")
        # Sanity: v3 methodology hash matches recipe.
        method_files = v3_data.get("methodology_files", [])
        if method_files:
            recomputed = hashlib.sha256(b"".join((ROOT / f).read_bytes() for f in method_files)).hexdigest()
            pinned = v3_data.get("methodology_hash")
            if recomputed != pinned:
                failures.append(
                    f"pre_registration.v3.lock.methodology_hash does not match recipe\n"
                    f"  pinned:     {pinned}\n"
                    f"  recomputed: {recomputed}\n"
                    f"  files:      {method_files}"
                )
            else:
                print(f"[OK] v3 methodology_hash recomputable from {len(method_files)} files  ({pinned[:16]}…)")

        # Pinned grading-module bytes match disk.
        gm = v3_data.get("instruments_held_constant_across_arms", {}).get("grading_modules", {})
        for name, info in gm.items():
            mod_path = ROOT / info["path"]
            if not mod_path.exists():
                failures.append(f"grading module {name} missing on disk: {mod_path}")
                continue
            actual = hashlib.sha256(mod_path.read_bytes()).hexdigest()
            pinned = info["sha256"]
            if actual != pinned:
                failures.append(
                    f"grading module {name} bytes diverge from v3 lock\n"
                    f"  pinned:  {pinned}\n"
                    f"  on-disk: {actual}\n"
                    f"  path:    {info['path']}"
                )
            else:
                print(f"[OK] grading_modules.{name} SHA matches disk  ({actual[:16]}…)")

        # Pinned disambiguation suffix bytes match disk.
        pa = v3_data.get("prompt_assembly", {})
        suf_pinned = pa.get("disambiguation_suffix_hash")
        if suf_pinned:
            sys.path.insert(0, str(ROOT / "harness"))
            try:
                from src.disambiguation import disambiguation_suffix_sha256
                actual_suf = disambiguation_suffix_sha256()
                if actual_suf != suf_pinned:
                    failures.append(
                        f"disambiguation suffix bytes diverge from v3 lock\n"
                        f"  pinned:  {suf_pinned}\n"
                        f"  on-disk: {actual_suf}"
                    )
                else:
                    print(f"[OK] disambiguation_suffix_hash matches disk    ({actual_suf[:16]}…)")
            except Exception as e:  # noqa: BLE001
                failures.append(f"could not verify disambiguation suffix: {e}")
    else:
        print("[--] pre_registration.v3.lock not yet written")

    if failures:
        print("\n--- FAILURES ---")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("\nAll v3 isolation invariants hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
