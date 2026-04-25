# Harness (v0.3 — multi-arm)

Executes the experiment described in `../DESIGN.md` for any single analyst
arm. Produces a JSONL dump of **91 analyst runs** (13 cells × 7 reps) plus
extractor and judge outputs, written under `../arms/<arm>/data/`.

The Opus 4.7 arm is locked. Sonnet 4.6 arm is configured but not yet
executed — see `../ARMS.md` for the cross-arm integrity model and for why
Haiku 4.5 was considered but excluded.

## Layout

- `config/base.yaml` — shared design grid, extractor, judge, paths (with
  `{arm}` placeholder), pricing. Held constant across arms.
- `config/arms/<arm>.yaml` — per-arm analyst overrides (snapshot, thinking
  effort, context window). Deep-merged onto base at load time.
- `src/` — pipeline modules. Each module header documents its contract.
- `scripts/` — CLI entrypoints. All take `--arm <arm-name>`.
- `../arms/<arm>/data/` — per-arm outputs. Manifest, raw responses,
  extracted JSON, judge scores, logs.

## Pipeline stages

| Stage   | Script                        | Output                                                    |
| ------- | ----------------------------- | --------------------------------------------------------- |
| Collect | `scripts/run_experiment.py`   | `../arms/<arm>/data/raw/<cell_id>.jsonl`                  |
| Extract | `scripts/run_extractor.py`    | `../arms/<arm>/data/extracted/<cell_id>.jsonl`            |
| Grade   | `scripts/run_grading.py`      | `../arms/<arm>/data/graded/<cell_id>.jsonl`               |
| Analyze | `scripts/drift_analysis.py`   | stdout / `../arms/<arm>/reports/`                         |
| Compare | `scripts/compare_arms.py`     | `../cross_arm/COMPARATIVE_REPORT.md`                      |

Each stage is **resumable and idempotent**. `<arm>/data/manifest.sqlite` is
the single source of truth for run state within an arm.

## First-run flow (per arm)

```
uv sync
cp .env.example .env                                       # add ANTHROPIC_API_KEY
python -m scripts.dry_run --arm <arm>                      # validate + cost estimate
python -m scripts.run_experiment --arm <arm> --pilot       # 3 cells × 7 = 21 runs, ~$50
# gate: review pilot, decide go/no-go per DESIGN §11
python -m scripts.run_experiment --arm <arm> --full        # 13 cells × 7 = 91 runs
python -m scripts.run_extractor --arm <arm>
python -m scripts.run_grading --arm <arm>
python -m scripts.status --arm <arm>
python -m scripts.drift_analysis --arm <arm>
```

## Budget

- Estimated full run: **~$575** (collect + extract + judge).
- Configured budget: **$700**.
- Hard stop: **$850**. `CostTracker` aborts if cumulative spend crosses this.

## Invariants (do not break)

- **Cache locality:** within a cell, the prefix
  `[system][noise_a][target][noise_b]` is byte-identical across the 7 reps.
  Only the question block varies (shuffled by `run_id`).
- **Per-cell noise seed:** noise content is drawn with seed `cell_id`, never
  `run_id`.
- **Material immutability:** `materials.lock.json` pins SHA-256 of every
  target file, noise document, question, and ground-truth key.
- **Pinned model snapshot:** a new snapshot = new experiment, not a resume.
- **Target bundle:** one `TargetBundle` per report — 10-K + latest earnings
  call rendered as a single `<<< TARGET MATERIALS: ... >>>` block with one
  cache breakpoint.

## Design (v0.2)

Single company (**Microsoft**), single noise class (**adversarial-near** —
competitor 10-Ks). 4 fill levels (25/50/75/95%) × 3 positions (start/middle/
end) = 12 noise scenarios + 1 baseline = 13 cells. 7 reps per cell. 8
questions (3 factual + 2 calc + 3 synthesis: financial health, strategic
positioning, AI impact).
