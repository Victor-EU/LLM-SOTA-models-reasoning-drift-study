# Multi-Arm Architecture

This document explains the multi-arm design of the reasoning drift study,
the integrity guarantees, and the procedure for adding a new arm.

## What is an "arm"?

An arm is one analyst-model variant of the same experiment. Three arms are
currently configured:

| Arm       | Analyst snapshot               | Thinking effort | Context  | Status |
| --------- | ------------------------------ | --------------- | -------- | ------ |
| opus-4-7  | claude-opus-4-7                | max             | 1M       | Locked |
| sonnet-4-6| claude-sonnet-4-6              | max             | 1M*      | Configured |
| haiku-4-5 | claude-haiku-4-5-20251001      | max*            | 200K*    | Configured |

*requires verification before kicking off — see comments in
`harness/config/arms/<arm>.yaml`.

## What stays constant across arms

The whole point of the cross-arm comparison is to attribute observed
differences to the analyst. Anything else changing would confound that
attribution. So these are frozen by `pre_registration.lock` and re-verified
by `compare_arms.py` before producing any cross-arm output:

| Frozen quantity              | Where it lives                          | Hash mechanism                                  |
| ---------------------------- | --------------------------------------- | ----------------------------------------------- |
| Methodology                  | DESIGN.md + PROMPTS.md + RUBRIC.md      | sha256 of concatenation                         |
| Corpus                       | materials/* via materials.lock.json     | sha256 of materials.lock.json                   |
| Design grid                  | base.yaml `design`, `pilot`             | embedded in each arm.lock.json                  |
| Extractor                    | base.yaml `models.extractor`            | embedded in each arm.lock.json                  |
| Judge primary (Opus 4.7 max) | base.yaml `models.judge_primary`        | embedded in each arm.lock.json                  |
| Judge secondary (Sonnet)     | base.yaml `models.judge_secondary`      | embedded in each arm.lock.json                  |
| Noise seeding scheme         | `cells.py` — sha256 over (report, fill, position, rep) | code-level invariant (analyst NOT an input) |

The judge stays Opus 4.7 in every arm because **the judge is the measuring
instrument**. If the judge varies with the analyst, you can't tell whether
differences are in what's being measured or in the measuring tool. The 20%
Sonnet 4.6 secondary subsample still runs per-arm as a within-arm
rubric-application consistency check (cross-judge ICC).

## What varies across arms

Only the analyst's API call:

- `models.analyst.snapshot`
- `models.analyst.context_window`
- `models.analyst.thinking_effort`
- `models.analyst.max_output_tokens`
- `tokens.total_context_target` (only when context window differs — Haiku
  4.5 at 200K cannot do fill=0.95 of 1M)
- `tokens.report_token_cap` (proportionally scaled when total target shrinks)

When `total_context_target` differs, the fill grid is preserved in
*relative* terms — `fill=0.95` means "95% of available context" regardless
of arm. Drift is measured relative to model capacity. This means absolute
token counts at, say, fill=0.50 differ across arms (500K for Opus, 100K for
Haiku); the cross-arm comparison is over the *shape* of the drift curve,
not absolute thresholds.

## Per-arm directory layout

```
arms/<arm>/
├── arm.lock.json            # canonical arm metadata + integrity references
├── data.manifest.sha256     # one line per data file: <sha256> <size> <relpath>
├── data/
│   ├── manifest.sqlite      # run-state state machine (resumable, idempotent)
│   ├── raw/<cell>.jsonl     # analyst raw responses (one line per run)
│   ├── extracted/<cell>.jsonl  # Haiku-normalized records (one line per (run, q_id))
│   ├── graded/<cell>.jsonl     # judge + autograder output
│   └── logs/                # JSONL append-only audit logs
└── reports/
    └── FINAL_REPORT.md      # arm-specific narrative
```

The arm directory is the integrity boundary. After lock, **nothing inside
should change**. `verify_arm_integrity.py` confirms by recomputing
SHA-256s.

## The arm.lock.json contract

Every arm has an `arm.lock.json`. The file is required for the arm to be
discoverable by `compare_arms.py`. Required fields:

```json
{
  "arm_name": "<must match directory name>",
  "pre_registration": { "hash": "<must match pre_registration.lock>" },
  "materials":        { "lock_hash": "<must match pre_registration.lock>" },
  "analyst":          { "snapshot": "...", "thinking_effort": "...", ... },
  "instruments_used": {
    "extractor":       { "snapshot": "...", "thinking_effort": null, ... },
    "judge_primary":   { "snapshot": "claude-opus-4-7", ... },
    "judge_secondary": { "snapshot": "claude-sonnet-4-6", ... }
  },
  "design_used": { "fill_levels": [...], "positions": [...], ... },
  "pricing_at_lock_usd_per_million_tokens": { ... },
  "execution_results": { "cumulative_cost_usd": ..., ... },
  "data_integrity": {
    "data_manifest_path": "data.manifest.sha256",
    "data_manifest_sha256_self": "<sha256 of the manifest file itself>"
  },
  "git_anchor": { "tag": "arm/<arm>/data-vN" },
  "locked_at": "<ISO 8601>",
  "locked_by": "<email>"
}
```

`compare_arms.py` reads this and refuses to compare if any of:
- `pre_registration.hash` differs across arms
- `materials.lock_hash` differs across arms
- `design_used` differs across arms
- `instruments_used.extractor` differs across arms
- `instruments_used.judge_primary` differs across arms
- `instruments_used.judge_secondary` differs across arms

## Adding a new arm — full procedure

1. **Choose the analyst snapshot.** Pin to a specific dated version if
   possible. A new snapshot is a new arm — never overwrite an existing arm's
   data with a different snapshot.

2. **Write the arm config.** Create
   `harness/config/arms/<arm-name>.yaml`. Mirror the structure of
   `opus-4-7.yaml`. Override only what differs from base. Document any
   assumptions that need verification.

3. **Verify thinking schema.** Run
   `scripts/probe_effort.py` (adapt the snapshot string) to confirm the
   model accepts `thinking.type.adaptive` with the chosen effort. If it
   doesn't, decide whether to drop to a supported effort (and document
   that as a known difference) or skip the arm.

4. **Smoke test one cell.**
   ```
   python -m scripts.smoke_test --arm <arm> --cell-fill 0.0
   ```
   Confirms the budget converges, the API call succeeds, and the JSON
   parses. Cost ~$3-5.

5. **Pilot.**
   ```
   python -m scripts.run_experiment --arm <arm> --pilot
   ```
   3 cells × 7 reps = 21 runs, ~$50. Review pilot per `DESIGN.md §11`
   before proceeding.

6. **Full collect + extract + grade.**
   ```
   python -m scripts.run_experiment --arm <arm> --full
   python -m scripts.run_extractor --arm <arm>
   python -m scripts.run_grading --arm <arm>
   python -m scripts.status --arm <arm>
   ```

7. **Generate the data integrity manifest.**
   ```
   python3 -c "
   import hashlib
   from pathlib import Path
   arm = '<arm>'
   root = Path(f'arms/{arm}/data')
   files = sorted(p for p in root.rglob('*') if p.is_file())
   lines = [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.stat().st_size:>10}  {p.relative_to(root).as_posix()}' for p in files]
   header = f'# {arm} arm — data integrity manifest\n# Files: {len(files)}\n#\n'
   Path(f'arms/{arm}/data.manifest.sha256').write_text(header + '\n'.join(lines) + '\n')
   "
   ```

8. **Hand-write `arms/<arm>/arm.lock.json`** mirroring
   `arms/opus-4-7/arm.lock.json`. Fill in actual cost and execution results
   from the manifest:
   ```
   python -m scripts.status --arm <arm>
   ```

9. **Tag and verify.**
   ```
   git add arms/<arm>/
   git commit -m "Lock <arm> arm — N runs, $X.XX"
   git tag arm/<arm>/data-v1.0
   python -m scripts.verify_arm_integrity --arm <arm>
   ```

10. **Cross-arm compare.**
    ```
    python -m scripts.compare_arms --write-report
    ```
    Output lands at `cross_arm/COMPARATIVE_REPORT.md`.

## Cost expectations per arm

Estimates assume the same 91-run grid + 8-question rubric. Most spend lands
on the JUDGE (Opus 4.7 max-effort, held constant across arms) — not the
analyst. The analyst's family only swings the analyst-side fraction.

| Arm        | Full-run estimate | Driver                                              |
| ---------- | ----------------- | --------------------------------------------------- |
| opus-4-7   | $582 (actual)     | Opus analyst @ $75/M output, 91 long thinking runs  |
| sonnet-4-6 | ~$300-350         | Sonnet analyst @ $15/M output (~5× cheaper)         |
| haiku-4-5  | ~$260-280         | Haiku analyst @ $4/M, smaller 200K context per call |

Judge (Opus 4.7 primary + Sonnet 4.6 secondary subsample + Opus pairwise)
contributes ~$246 of the Opus arm's $582. That floor applies to every arm
because the judge config is identical.

**Always run `python -m scripts.dry_run --arm <arm>` for a fresh estimate
before kicking off** — pricing can change, and the dry-run output reflects
the actual base.yaml + arm overlay you're about to run.
