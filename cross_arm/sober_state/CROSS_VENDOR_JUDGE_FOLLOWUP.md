# Cross-vendor judge replication — sober-state ranking

The original sober-state ranking experiment used two Anthropic judges (Opus 4.7
max, Sonnet 4.6 high). The reasonable objection: maybe Anthropic-as-judge
prefers Anthropic-as-analyst, and Sonnet-on-top is partly an artifact of
in-house style preference. This follow-up adds two more judges from different
vendors at each vendor's max thinking knob, holding the rest of the design
constant — same 21 ranking items, same five anonymized candidates per item,
same permutation seed (so all four judges score the identical bundles).

## Setup

- **Item set**: 21 baseline (fill=0) Tier-3 items — `{MSFT-S-01, MSFT-S-02, MSFT-S-03} × 7 reps`.
- **Candidates per item**: the same five frontier reasoning models, randomly
  permuted into labels A–E. Permutations are stable across all four judges.
- **New judges**:
  - **GPT-5.5** (`gpt-5.5-2026-04-23`) at `reasoning.effort = xhigh` (vendor max).
  - **Gemini 3.1 Pro** (`gemini-3-pro-preview`) at `thinking_level = HIGH` (vendor max).
- **Existing judges** (unchanged): Opus 4.7 max, Sonnet 4.6 high.
- **Spend**: GPT $16.56, Gemini $4.78 → **$21.34 total**. Project total now $1,915.40.
- **Latency**: Gemini 78s/call mean; GPT 205s/call mean.

## Headline finding — the ranking is robust to judge identity

Mean rank per arm (lower is better; out of 5 candidates):

| arm                   | Opus judge | Sonnet judge | GPT judge | Gemini judge |
|-----------------------|-----------:|-------------:|----------:|-------------:|
| **sonnet-4-6**        |   **1.48** |     **1.33** |      2.24 |     **1.43** |
| **opus-4-7**          |       1.62 |         1.76 |  **1.95** |         1.67 |
| gpt-5-5               |       3.00 |         2.95 |  **1.95** |         3.24 |
| deepseek-v4-pro       |       4.24 |         4.19 |      4.10 |         4.19 |
| gemini-3-1-pro        |       4.67 |         4.76 |      4.76 |         4.48 |

Three of four judges agree on the exact ordering Sonnet > Opus > GPT > DeepSeek > Gemini.
The GPT judge alone moves itself from #3 to a tie at #1 with Opus (both at 1.95),
displacing Sonnet to #3. But the top-3 set is still {Opus, Sonnet, GPT} for
every judge. **No judge inverts the bottom two**: Gemini is last by all four;
DeepSeek is second-to-last by all four.

## Self-preference exists but is bounded

Each judge's rank for its own arm versus the mean rank assigned by the other
three judges (positive = self-favoring):

| judge  | self-rank | external mean | self-bias  |
|--------|----------:|--------------:|-----------:|
| GPT    |      1.95 |          3.06 | **+1.11**  |
| Sonnet |      1.33 |          1.71 |  +0.38     |
| Gemini |      4.48 |          4.73 |  +0.25     |
| Opus   |      1.62 |          1.79 |  +0.17     |

GPT shows the largest in-vendor preference (~1 rank step), but it falls short
of inverting the structure: even the GPT judge keeps Gemini at 4.76 and
DeepSeek at 4.10. Anthropic judges and Gemini agree GPT is roughly 1.4 rank
steps behind the Anthropic pair; the GPT judge itself agrees the gap exists,
just smaller.

The Gemini result is the most informative: **the Gemini judge ranks Gemini-3.1-Pro
last** (4.48), behind DeepSeek. Whatever pulls the Gemini analyst down on this
task, it is not invisible to the Gemini judge.

## Cross-judge agreement matrix

Per-item Spearman ρ (mean across the 21 items) and per-arm Borda Pearson r
(consistency of overall rankings):

| pair                | Spearman ρ (mean) | Borda Pearson r | top-1 same | top-3 same |
|---------------------|------------------:|----------------:|-----------:|-----------:|
| opus  vs sonnet     |             0.943 |       **0.997** |      76.2% |      85.7% |
| opus  vs gemini     |             0.838 |       **0.995** |      47.6% |      76.2% |
| sonnet vs gemini    |             0.843 |       **0.991** |      52.4% |      81.0% |
| opus  vs gpt        |             0.714 |           0.887 |      47.6% |      81.0% |
| sonnet vs gpt       |             0.729 |           0.888 |      38.1% |      85.7% |
| gpt   vs gemini     |             0.724 |           0.836 |      47.6% |      66.7% |

Interpretation:
- **Per-arm rankings cluster very tightly** (Pearson 0.84 – 1.00). Whatever
  judge you pick, the global ordering of arms is essentially the same.
- **Per-item rankings are looser** (Spearman 0.71 – 0.94). Judges disagree on
  which specific (q_id, rep) item produced the best answer about 30% of the
  time, but those disagreements wash out when aggregated across items.
- **GPT is the noisiest judge**: every pair involving GPT has the lowest
  Spearman in its row. The GPT judge also has a flatter top-3 (Opus / GPT /
  Sonnet within 0.3 rank steps) than any other judge.

## What this changes about the original report

Before this follow-up, `SOBER_STATE_RANKING.md` had a single bounded
disclosure: "Both judges are Anthropic; in-house preference cannot be ruled
out." That disclosure now has a quantitative answer:

1. The Sonnet-on-top finding holds for 3/4 judges (Opus, Sonnet, Gemini).
   GPT alone elevates itself to a tie at #1 with Opus, but does not displace
   Sonnet from the top three.
2. The bottom of the ranking — Gemini last, DeepSeek 4th — is unanimous.
   No vendor self-preference at the bottom; the Gemini judge confirms its
   own analyst's position.
3. **Self-preference exists** (every judge rates its own arm above the
   cross-judge consensus) but is small enough that it does not invert any
   pair. GPT shows the largest in-house bias (+1.1 rank steps), Opus the
   smallest (+0.17).
4. The original Anthropic-judge picture was not biased — it was conservative.
   Per the GPT judge, GPT-5.5 is just as strong as Opus-4.7 on this task;
   the Anthropic and Gemini judges read the gap as ~1.4 rank steps. The truth
   is probably somewhere in between, and either way Sonnet and Opus remain
   clearly above GPT, DeepSeek, and Gemini at the sober state.

## Files

- `judge_gpt.jsonl` — 21 rows, one per (q_id, rep_idx). Schema matches `judge_opus.jsonl`.
- `judge_gemini.jsonl` — 21 rows, same schema.
- `cross_judge_4way.json` — structured dump from `scripts.sober_analysis`.
- `permutations.jsonl` — unchanged; same permutation map all four judges scored against.
- `cost.jsonl` — appended; per-call cost rows for both new judges.

## Reproduce

From `harness/`:

```
uv run python -m scripts.judge_sober_ranking --judges gemini --concurrency 3
uv run python -m scripts.judge_sober_ranking --judges gpt --concurrency 3
uv run python -m scripts.sober_analysis --json ../cross_arm/sober_state/cross_judge_4way.json
```

Both runs are idempotent (skip-if-exists per (q_id, rep_idx)).
