# Harness (v0.2 simplified)

Executes the experiment described in `../DESIGN.md`. Produces a JSONL dump of
**91 analyst runs** (13 cells × 7 reps) plus extractor and judge outputs, from
which the pre-registered analysis is computed.

## Layout

- `config/experiment.yaml` — frozen pre-registered configuration.
- `src/` — pipeline modules. Each module header documents its contract.
- `scripts/` — CLI entrypoints.
- `data/` — created at runtime. Manifest, raw responses, extracted JSON,
  judge scores, logs.

## Pipeline stages

| Stage   | Script                        | Output                                   |
| ------- | ----------------------------- | ---------------------------------------- |
| Collect | `scripts/run_experiment.py`   | `data/raw/<cell_id>.jsonl`               |
| Extract | `scripts/run_extractor.py`    | `data/extracted/<cell_id>.jsonl`         |
| Grade   | `scripts/run_grading.py`      | `data/graded/<cell_id>.jsonl`            |
| Analyze | (separate R notebook)         | `../analysis/*.Rmd`                      |

Each stage is **resumable and idempotent**. `data/manifest.sqlite` is the
single source of truth for run state.

## First-run flow

```
uv sync
cp .env.example .env                            # add ANTHROPIC_API_KEY
python -m scripts.dry_run                       # validate + cost estimate
python -m scripts.run_experiment --pilot        # 3 cells × 7 = 21 runs, ~$50
# gate: review pilot, decide go/no-go per DESIGN §11
python -m scripts.run_experiment --full         # 13 cells × 7 = 91 runs
python -m scripts.run_extractor
python -m scripts.run_grading
python -m scripts.status
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
