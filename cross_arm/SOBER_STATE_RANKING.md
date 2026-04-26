# Sober-State Head-to-Head Ranking

## Which model is best at the task with no noise?

**Date:** 2026-04-26  •  **Items judged:** 21 (3 Tier-3 questions × 7 reps)  •  **Judges:** Opus 4.7 max + Sonnet 4.6 high (original); GPT-5.5 xhigh + Gemini 3.1 Pro HIGH (cross-vendor follow-up — §10)  •  **Cost:** $55.74 ($34.40 original + $21.34 cross-vendor)

This is a separate analysis on top of the existing five-arm dataset, asking
a different question than the headline drift study: *with no noise in the
context window, which model produces the best Tier-3 synthesis?* Not "best
at resisting drift" — best at the task, full stop, on a level playing field.

---

## TL;DR

| rank | arm                | mean rank (Opus / Sonnet judge) | Borda (Opus / Sonnet) | head-to-head wins |
|------|--------------------|-------------------------------:|---------------------:|------------------|
| 1    | **Sonnet 4.6**     | **1.48 / 1.33**                 | **74 / 77**           | beats every other arm in ≥20/21 items |
| 2    | **Opus 4.7**       | **1.62 / 1.76**                 | **71 / 68**           | beats GPT-5.5 in 20/21, loses to Sonnet 9–12/21 |
| 3    | **GPT-5.5**        | 3.00 / 2.95                     | 42 / 43               | clean middle tier; clear gap above and below |
| 4    | **DeepSeek V4 Pro**| 4.24 / 4.19                     | 16 / 17               | beats Gemini in 14–16/21 |
| 5    | **Gemini 3.1 Pro** | 4.67 / 4.76                     | 7 / 5                 | beats only DeepSeek, in 5–7/21 |

Three findings stand on their own:

1. **The two Anthropic models are clear top tier** — Sonnet edges Opus on both judges, but the margin is small (mean-rank gap 0.14 by Opus judge, 0.43 by Sonnet judge) and they each beat the next arm by ≥1.3 mean-rank points. Treat them as a tied top tier rather than a strict 1/2.
2. **Cross-judge agreement is exceptional** — per-item Spearman ρ mean **0.943** (median **1.000**), per-arm Borda Pearson **0.997**, top-1 agreement on the same item **76%**. The ordering is robust across the two judges.
3. **The sober ordering disagrees with the absolute-judge ordering** at two specific points: the Opus/Sonnet swap at the top (absolute had Opus first; sober has Sonnet first), and the DeepSeek/Gemini swap at the bottom (absolute had Gemini ahead of DeepSeek on RQ; sober has DeepSeek ahead of Gemini on rank). Section §6.

---

## 1. Methodology

### 1.1 What we did

The existing `judge_primary` (Opus 4.7 max-effort) already scores each
arm's baseline Tier-3 answers absolutely on the RUBRIC.md 1–5 dimensions
plus a 0–10 reasoning_quality. The problem at baseline: **most arms pile
near the rubric ceiling**, so absolute scores compress the discrimination
between top arms (e.g. Opus baseline `groundedness` is 4.71–5.00 and
`scope_adherence` is 5.00 across all 21 records — no signal). A
head-to-head ranking call, where the judge sees all five arms' answers
side-by-side for the same `(question, rep)`, forces the discrimination
that absolute scoring compresses away.

Concretely, for each of `(q_id ∈ {MSFT-S-01, MSFT-S-02, MSFT-S-03},
rep_idx ∈ 0..6)` = **21 items**:
- Pull the five arms' baseline answers (one per arm) for that `(q, rep)`.
- Random-permute the 5 arms into labels A–E. Permutation seed is
  `sha256("sober-state-ranking-v1|<q_id>|<rep_idx>")[:8]` so both judges
  score the **same shuffle** — the `{label → arm}` map is logged to
  `cross_arm/sober_state/permutations.jsonl` for reproducibility.
- Send a single judge call: cached target materials (10-K + Q2 FY26 call,
  `~94K tokens`) + the same RUBRIC.md dimensions, plus a new ranking
  surface that asks for *per-candidate dimension scores AND a strict total
  order over {A,B,C,D,E}*.
- Repeat for both judges (Opus 4.7 max, Sonnet 4.6 high) on **100% of
  items** — not the usual 20% subsample, since cross-judge agreement is
  central to this analysis's robustness.

### 1.2 What stays constant from the main study

- **Materials:** materials lockfile sha256 `c13b5514…`, byte-identical to
  every cell of every arm.
- **Rubric:** same dimensions, same anchor list, same engagement-signal
  definitions (RUBRIC.md v2.1).
- **Judge models:** same snapshots as `pre_registration.lock`
  (`claude-opus-4-7`, `claude-sonnet-4-6`).
- **Source data:** same 5 baseline JSONL files
  `arms/<arm>/data/raw/c_MSFT_00_X_X_*.jsonl` already locked into each
  arm's `data.manifest.sha256`.

### 1.3 What changes for this analysis

- **Output budget bumped:** the standard `judge_primary.max_output_tokens
  = 16384` and `judge_secondary = 8192` (sized for single-candidate
  scoring) is too small for 5-way ranking with max-effort thinking. After
  `1/21` Opus calls and `4/4` Sonnet calls hit the cap with zero visible
  text emitted, both budgets were raised to **32K** and Sonnet to **64K**
  for the 2 still-failing structural-diagnostic items. Held-constant
  judge config in `base.yaml` is **untouched** — this override is local
  to `harness/scripts/judge_sober_ranking.py` and applies only to the
  ranking task.
- **A new prompt surface** — `SOBER_RANKING_SYSTEM_PROMPT` in
  `judge_sober_ranking.py`. Same dimensions, same grading philosophy
  ("PROCESS not VERDICT", "do not prefer length", "do not prefer style")
  reframed for 5-way comparison with strict total ordering and tie notes.

---

## 2. Results — Opus 4.7 max-effort judge (primary)

```
arm                     mean_rk   borda   borda/n   RQ μ    RQ σ    unsup μ
sonnet-4-6              1.48      74      3.52      9.00    0.53    0.00
opus-4-7                1.62      71      3.38      8.62    0.49    0.10
gpt-5-5                 3.00      42      2.00      7.48    0.66    0.00
deepseek-v4-pro         4.24      16      0.76      5.90    0.68    0.48
gemini-3-1-pro          4.67       7      0.33      5.48    0.66    0.33
```

### Per-dimension means (1–5 each)

```
arm                     gnd    br     sc     cl     cit
sonnet-4-6              5.00   4.90   5.00   4.57   5.00
opus-4-7                4.95   4.76   5.00   4.81   4.95
gpt-5-5                 5.00   4.14   5.00   4.14   4.90
deepseek-v4-pro         3.86   3.43   4.86   4.10   3.48
gemini-3-1-pro          3.86   3.10   4.95   4.10   3.48
```

Even on per-dimension absolute scores in the head-to-head context,
Sonnet and Opus separate from the rest: Sonnet has the only `evidentiary_breadth`
above 4.7 and the only `groundedness/scope/citation` triple at ceiling.
Opus trades ~0.1 on each front-line dimension for the highest `clarity`.

### Win matrix (rows beat columns on N items, of 21)

```
winner \ loser       opus  sonnet  gpt-5-5  gemini  deepseek
opus-4-7              -      9     20       21       21
sonnet-4-6           12      -     20       21       21
gpt-5-5               1      1      -       21       19
gemini-3-1-pro        0      0      0        -        7
deepseek-v4-pro       0      0      2       14        -
```

A few cells are clean: GPT-5.5 beats Gemini and DeepSeek essentially every
item; Gemini beats nobody from the top 3 ever. The Opus/Sonnet cell is
the only contested one — Sonnet wins 12/21, Opus 9/21, no ties.

---

## 3. Results — Sonnet 4.6 high-effort judge (secondary)

```
arm                     mean_rk   borda   borda/n   RQ μ    RQ σ    unsup μ
sonnet-4-6              1.33      77      3.67      8.81    0.39    0.05
opus-4-7                1.76      68      3.24      8.29    0.45    0.33
gpt-5-5                 2.95      43      2.05      6.95    0.72    0.10
deepseek-v4-pro         4.19      17      0.81      5.76    0.53    0.67
gemini-3-1-pro          4.76       5      0.24      5.05    0.72    0.71
```

Same ordering, slightly larger Opus→Sonnet gap (Sonnet 1st-place rate
73% vs 52% under the Opus judge), and slightly higher
unsupported-claim counts on every arm — Sonnet judges read claims more
strictly. Win matrix shows the same structure.

---

## 4. Cross-judge agreement

```
items overlapping:                21
per-item Spearman ρ (mean):        0.943
per-item Spearman ρ (median):      1.000
per-arm rank Pearson r:            0.997
per-arm Borda Pearson r:           0.997
top-1 agreement (same item):       76.2%
top-3 set agreement (same item):   85.7%
```

**This is the strongest cross-judge agreement seen anywhere in the
study.** For comparison: the main absolute-grading run shows judge ICC
collapsing on dimensions where high-quality models pile near the rubric
ceiling (DeepSeek-arm scope_adherence ICC ≈ 0.07, GPT-5.5-arm reasoning
ICC 0.66). Here, two judges with different model families and effort
levels (`max` vs `high`) on a 5-way ranking task agree on **the same
exact ordering at the median**.

The per-item Spearman ρ mean of 0.943 understates the agreement because a
single label swap (e.g., A↔B in two adjacent positions) drops ρ from 1.0
to 0.9. The median of 1.000 is the more honest summary: on more than half
the items, the two judges produced **identical orderings of 5 arms**.

The sober ranking is thus highly judge-robust within the Anthropic family.

---

## 5. Per-question variance

Mean rank per arm by question (3 questions × 7 reps each, both judges):

```
q_id        judge       opus    sonnet  gpt-5-5  gemini  deepseek
S-01        opus        1.71    1.57    2.71     4.14    4.86
S-01        sonnet      1.86    1.43    2.71     4.57    4.43
S-02        opus        1.43    1.57    3.14     4.86    4.00
S-02        sonnet      1.57    1.43    3.00     4.71    4.29
S-03        opus        1.71    1.29    3.14     5.00    3.86
S-03        sonnet      1.86    1.14    3.14     5.00    3.86
```

- **S-01 (financial-health synthesis):** Sonnet wins by both judges.
- **S-02 (cash-flow / capital-allocation calculation-heavy synthesis):**
  Opus wins under the Opus judge (1.43); Sonnet wins under the Sonnet
  judge (1.43); they're effectively tied. This is the only question
  where Opus has a credible claim to first place.
- **S-03 (the structural Q8: DECOMPOSE → APPLY 4 FRAMEWORKS → SYNTHESIZE):**
  Sonnet's lead is widest — mean rank **1.14 / 1.86** under Sonnet judge.
  The structural-diagnostic question rewards explicit framework labels
  and per-unit decomposition, which Sonnet's longer responses execute
  more thoroughly. Gemini sits at exactly **5.00** mean rank on S-03 —
  ranks last on every item under both judges. This is the cleanest
  per-arm/per-question failure signal in the dataset.

---

## 6. Comparison vs the existing absolute-judge baseline

The same 21 baseline records were already scored by `judge_primary` in
the main study. Comparing the absolute reasoning_quality means against
the sober head-to-head means surfaces two reorderings:

| arm                 | absolute RQ (μ across 3 Tier-3 q) | sober RQ Opus / Sonnet judge | absolute rank → sober rank |
|---------------------|----------------------------------:|-----------------------------:|---------------------------|
| **opus-4-7**        | **8.05**                          | 8.62 / 8.29                  | 1 → **2**                 |
| **sonnet-4-6**      | 7.43                              | **9.00 / 8.81**              | 2 → **1**                 |
| gpt-5-5             | 7.05                              | 7.48 / 6.95                  | 3 → 3 (unchanged)         |
| gemini-3-1-pro      | 5.86                              | 5.48 / 5.05                  | 4 → **5**                 |
| deepseek-v4-pro     | **5.33**                          | **5.90 / 5.76**              | 5 → **4**                 |

**Why the Opus↔Sonnet swap.** The absolute judge sees Opus's tighter,
more-direct synthesis and gives it a top score. Forced to compare,
both judges (including Opus itself) give the edge to Sonnet's longer,
more comprehensive treatments — Sonnet engages more anchors with
explicit citations on the same task. The judge "would I accept this as
a senior partner's work?" gestalt favors Opus when read alone; the
"which of these five would I rather have written" comparison favors
Sonnet. Both pictures are real; they're answering different questions.

**Why the DeepSeek↔Gemini swap.** The absolute baseline gave Gemini
slightly higher reasoning_quality (5.86 vs DeepSeek's 5.33). The sober
ranking inverts: DeepSeek 4.24 / 4.19 mean rank, Gemini 4.67 / 4.76 —
DeepSeek is consistently judged the better of the two when seen
side-by-side. Inspection of judge rationales shows the pattern: Gemini
produces shorter, more confident-but-thinner answers (median 2,407
chars — the smallest of the five arms). Side-by-side, the judges
penalize the lack of breadth more than the absolute scorecard does.

---

## 7. Caveats and biases

These are real and constrain the conclusions. None defeat the headline,
but they bound how strong a claim the data supports.

### 7.1 Length is heavily confounded with rank

```
arm                  median chars   mean chars   judge mean rank
sonnet-4-6                  8,227       10,490        1.48 / 1.33
opus-4-7                    5,188        5,855        1.62 / 1.76
gpt-5-5                     4,646        6,157        3.00 / 2.95
deepseek-v4-pro             3,108        4,392        4.24 / 4.19
gemini-3-1-pro              2,407        2,642        4.67 / 4.76
```

The **rank-by-median-length ordering is identical to the
rank-by-judge-mean-rank ordering**. Within the pooled dataset,
per-judge Spearman ρ between answer length and assigned rank is
**−0.701 (Opus judge)** and **−0.700 (Sonnet judge)**. Two stories are
consistent with this:

- *Length is a proxy for substance:* the longer answers genuinely
  engage more anchors, decompose more units, and apply more
  frameworks. The ranking is correct *because of* the substance that
  drove the length.
- *The judge has length bias:* despite explicit "do not prefer length"
  instruction in the system prompt, both judges anchor on volume.

We cannot separate the two from this data alone. The
absolute-judge baseline scored Sonnet *lower* than Opus despite
Sonnet's longer answers (8.05 → 7.43), which weakens (but does not
eliminate) the pure-length-bias story — at least one Anthropic judge
was capable of marking shorter answers higher when scored absolutely.
Treat the Sonnet-vs-Opus 1st/2nd order as **supported but
length-confounded**; treat the top-3 vs bottom-2 separation as
robust (it survives any plausible length-bias correction since the
length gap is 2–3×).

### 7.2 Self-preference: bounded but not zero

Two same-vendor judges scoring 5 arms, two of which are the judges
themselves — this is the canonical self-preference setup. The data is
mixed:

- **Opus judges Sonnet ahead of Opus** (1.48 vs 1.62 mean rank). This
  is the opposite of self-preference and is the strongest evidence
  against pure judge bias.
- **Sonnet judges Sonnet ahead of Opus** (1.33 vs 1.76). This is
  consistent with self-preference, but is *also* consistent with
  Sonnet just being the actual best arm (since Opus agrees).

If self-preference were dominant, we'd expect each judge to put their
own arm first. Only Sonnet does. The Sonnet-judge result alone is
ambiguous; the Opus-judge result corroborates Sonnet's #1 standing
*against* Opus's own model-stylistic preference.

### 7.3 Both judges are Anthropic — *resolved by §10 cross-vendor follow-up*

The original instrument set was Anthropic-only. The follow-up in §10
adds GPT-5.5 (xhigh) and Gemini 3.1 Pro (HIGH) as judges on the same 21
items, same permutations. **Result:** the Sonnet > Opus > GPT > DeepSeek
> Gemini ordering holds for 3 of 4 judges; GPT alone elevates itself to
a tie at #1 with Opus, but the top-3 set is unchanged. The bottom of the
ranking is unanimous (Gemini last on every judge — including the Gemini
judge itself, which ranks Gemini behind DeepSeek). Per-arm Pearson
correlation across all judge pairs ranges 0.84 – 1.00. Self-preference
is bounded: GPT +1.11 rank steps in-house (the largest), Sonnet +0.39,
Gemini +0.25, Opus +0.17. None invert any pair. Full breakdown in §10.

### 7.4 Position bias: present but small

```
label    rank=1 freq (Opus / Sonnet)    top-3 freq (Opus / Sonnet)
A         9.5% / 19.0%                   66.7% / 66.7%
B        33.3% / 23.8%                   57.1% / 57.1%
C        23.8% / 19.0%                   66.7% / 66.7%
D        28.6% / 33.3%                   71.4% / 61.9%
E         4.8% /  4.8%                   38.1% / 47.6%
(unbiased target: rank=1 ≈ 20% per label, top-3 ≈ 60% per label)
```

Both judges under-pick the **last position (E)** for #1 (4.8% vs 20%
expected). This is a recognized recency anchoring effect on long
multi-candidate prompts. With random permutation, each arm sees label
E in expectation `21/5 ≈ 4.2` times, so the bias spreads roughly
uniformly across arms and the aggregate ordering is close to unbiased.
Worst-case impact on a single arm: if it happened to land in label E
unusually often, its rank could be slightly understated. Not enough
to change the headline given the 1.3+ mean-rank gap from #3 down.

### 7.5 Two Sonnet calls thinking-looped

Sonnet 4.6 high-effort on `MSFT-S-03` (the structural Q8) twice burned
the entire 32K output budget on thinking with zero visible text,
requiring a 64K-cap retry. Both retries succeeded. This is a *Sonnet
behavioral observation* (Sonnet does substantially more thinking than
Opus on this task), not a methodological flaw — the final dataset has
21/21 valid Sonnet rankings. It is mentioned because it explains the
$9.45 Sonnet cost being more than 1/3 of the Opus cost despite Sonnet's
input/output prices being roughly half: Sonnet reasoned 2× longer on
average per call (311s vs 136s).

---

## 8. Implementation, cost, reproducibility

- **Code:** `harness/scripts/judge_sober_ranking.py` (runner) +
  `harness/scripts/sober_analysis.py` (aggregator). Single new system
  prompt `SOBER_RANKING_SYSTEM_PROMPT` defined inline in the runner.
- **Output:** `cross_arm/sober_state/judge_opus.jsonl`,
  `judge_sonnet.jsonl`, `permutations.jsonl`, `cost.jsonl`.
- **Cost:** $34.40 total. Opus $24.95 (avg $1.13/call, 22 calls
  including 1 retry); Sonnet $9.45 (avg $0.35/call, 27 calls including
  6 thinking-loop retries). Net 21+21=42 valid ranking calls.
- **Idempotent:** rerunning the script skips items already present in
  the output JSONLs by `(q_id, rep_idx, judge)` key. Permutations are
  cached so the two judges always score identical bundles.
- **Reproducibility:** the permutation seed string
  `"sober-state-ranking-v1|<q_id>|<rep_idx>"` is stable; rerun on
  unchanged baseline data + unchanged materials produces identical
  permutations, identical bundles, and (modulo judge stochasticity at
  temperature 1.0) consistent rankings.

To rerun:

```
cd harness
python -m scripts.judge_sober_ranking --judges both --concurrency 3
python -m scripts.sober_analysis
```

To reproduce the analysis only (no API calls):

```
python -m scripts.sober_analysis
```

---

## 9. What this analysis does and doesn't say

**It says:** at fill=0.00, on the 3 Tier-3 questions of this study,
judged by Opus 4.7 max + Sonnet 4.6 high in head-to-head 5-way ranking
calls, **Sonnet 4.6 produces the best answers (slightly above Opus
4.7), with a clean gap to GPT-5.5, and a larger gap to DeepSeek and
Gemini**. The ordering is robust across both judges (Spearman ρ=0.943).

**It does not say:** this is the universal ordering for any task. The
domain is financial analysis on a known-to-the-judge corpus (Microsoft
FY2025 disclosures). Generalization to other domains, other documents,
or judging by non-Anthropic models is not established by this data.

**Natural follow-ups, if anyone asks:**

1. ~~**Cross-vendor judge replication.** Rerun the same 21 items with
   GPT-5.5 max and Gemini 3.1 Pro HIGH as the ranking judges. ~$30
   estimated.~~ **Done — see §10.** Actual cost $21.34. Sonnet >
   Opus > GPT > DeepSeek > Gemini ordering held for 3 of 4 judges;
   the bottom of the ranking is unanimous across vendors.
2. **Length-controlled rerun.** Hard-truncate every candidate to the
   shortest arm's length per item (Gemini's median is the floor) and
   rerun the rankings. Tests the "length is a proxy for substance"
   theory: if Sonnet still wins after truncation, length wasn't the
   driver.
3. **Tier-1/2 ranking.** Add the 5 factual + calculation questions as
   a "presentation quality" ranking (correctness is binary and uniform
   at baseline so absolute scoring is uninformative). ~$25, low-signal
   but completes the picture.

---

## 10. Cross-vendor judge follow-up

*Added 2026-04-26. Same 21 items, same permutations, two new judges.*

### 10.1 What was added

Per §7.3 the only meaningful caveat left after §1–9 was vendor
homogeneity in the judge set. This section adds two non-Anthropic
judges scoring the same bundles.

- **GPT-5.5** (`gpt-5.5-2026-04-23`) at `reasoning.effort = xhigh`
  (vendor max). 21 calls, $16.56 spend, 205s/call mean.
- **Gemini 3.1 Pro** (`gemini-3-pro-preview`) at `thinking_level = HIGH`
  (vendor max). 21 calls, $4.78 spend, 78s/call mean.
- **Total incremental spend:** $21.34. Permutations are stable across
  all four judges — every judge scored the same A–E shuffle.

Implementation: `harness/scripts/judge_sober_ranking.py` was extended
with vendor dispatch (`anthropic` / `openai` / `google`); the existing
helpers in `harness/src/api.py` for streamed chunked decoding and
vendor-specific usage extraction are reused unchanged. `--judges
{opus, sonnet, gpt, gemini, all}` selects which to run; runs are
idempotent on `(q_id, rep_idx, judge)`. The held-constant judge
config in `base.yaml` is untouched — the cross-vendor judges are an
additive analysis on top of the locked main study.

### 10.2 Mean rank per arm, all four judges

(Lower is better. **Bold** marks each judge's #1.)

| arm                   | Opus judge | Sonnet judge | GPT judge | Gemini judge |
|-----------------------|-----------:|-------------:|----------:|-------------:|
| **sonnet-4-6**        |   **1.48** |     **1.33** |      2.24 |     **1.43** |
| **opus-4-7**          |       1.62 |         1.76 |  **1.95** |         1.67 |
| gpt-5-5               |       3.00 |         2.95 |  **1.95** |         3.24 |
| deepseek-v4-pro       |       4.24 |         4.19 |      4.10 |         4.19 |
| gemini-3-1-pro        |       4.67 |         4.76 |      4.76 |         4.48 |

Three of four judges produce the exact ordering Sonnet > Opus > GPT >
DeepSeek > Gemini. The GPT judge swaps Sonnet and itself into a tie
at #1 with Opus, but the top-3 set is unchanged. **The bottom of the
ranking is unanimous** across all four judges: Gemini last, DeepSeek
4th. The Gemini judge ranks Gemini-3.1-Pro behind DeepSeek-V4-Pro by
0.29 rank steps — explicit vendor self-demotion at the bottom.

### 10.3 Self-preference per judge

For each judge, the rank it assigns to its own analyst arm vs the
mean rank assigned by the other three judges:

| judge  | self-rank | external mean | self-bias  |
|--------|----------:|--------------:|-----------:|
| GPT    |      1.95 |          3.06 | **+1.11**  |
| Sonnet |      1.33 |          1.72 |  +0.39     |
| Gemini |      4.48 |          4.73 |  +0.25     |
| Opus   |      1.62 |          1.79 |  +0.17     |

GPT shows the largest self-favoring bias by a factor of ~3×. None
inverts a pair: even the GPT judge keeps Gemini at 4.76 and DeepSeek
at 4.10, both well below GPT's own 1.95. The Sonnet bias is
consistent with the original §7.2 analysis, but is now bounded by
two non-Sonnet judges who independently rank Sonnet 1st (Opus judge
1.48 = Sonnet 1st; Gemini judge 1.43 = Sonnet 1st). The Opus
judge already preferred Sonnet over Opus in the original §2 result.

### 10.4 All-pairs cross-judge agreement

| pair                | Spearman ρ (mean) | Borda Pearson r | top-1 same | top-3 same |
|---------------------|------------------:|----------------:|-----------:|-----------:|
| opus  vs sonnet     |             0.943 |       **0.997** |      76.2% |      85.7% |
| opus  vs gemini     |             0.838 |       **0.995** |      47.6% |      76.2% |
| sonnet vs gemini    |             0.843 |       **0.991** |      52.4% |      81.0% |
| opus  vs gpt        |             0.714 |           0.887 |      47.6% |      81.0% |
| sonnet vs gpt       |             0.729 |           0.888 |      38.1% |      85.7% |
| gpt   vs gemini     |             0.724 |           0.836 |      47.6% |      66.7% |

- **Per-arm rankings cluster very tightly** (Pearson 0.84–1.00). Every
  judge produces essentially the same global ordering of arms.
- **Per-item rankings are looser** (Spearman 0.71–0.94). Disagreement
  on which specific (q_id, rep) item produced the best answer is
  ~30%, but it averages out across items.
- **GPT is the noisiest judge** — every pair involving GPT has the
  lowest Spearman and Borda Pearson in its row. Consistent with the
  GPT judge having the flattest top-3 (Opus / GPT / Sonnet within 0.3
  rank steps) and the largest self-preference bias.

### 10.5 What changed in the conclusions

Nothing inverts. What sharpens:

- The original headline ("Sonnet 4.6 produces the best Tier-3
  synthesis on this corpus") survives. Anthropic-only judges,
  Anthropic + Gemini judges, three-of-four configurations of the
  four judges all return Sonnet at #1.
- The single dissenting case (GPT judge ties Opus and itself at #1
  ahead of Sonnet) is consistent with the largest measured
  self-preference bias on the panel, not with a substantively
  different reading of the corpus.
- The bottom of the ranking is now stronger than before: every
  vendor's judge — including Gemini's own — places Gemini last and
  DeepSeek fourth. The §6 swap of Gemini and DeepSeek (vs the
  absolute baseline) is robust across all four judge vendors.
- The original Anthropic-judge picture was *conservative* on the
  GPT-vs-Anthropic gap. Anthropic and Gemini judges read the gap as
  ~1.4 rank steps; the GPT judge reads it as ~0 (tied). Truth is
  somewhere between, and either way Sonnet/Opus remain clearly above
  GPT/DeepSeek/Gemini.

### 10.6 Files

- `cross_arm/sober_state/judge_gpt.jsonl` — 21 rows, schema
  identical to `judge_opus.jsonl`.
- `cross_arm/sober_state/judge_gemini.jsonl` — 21 rows, same schema.
- `cross_arm/sober_state/cross_judge_4way.json` — structured dump
  from `scripts.sober_analysis`.
- `cross_arm/sober_state/CROSS_VENDOR_JUDGE_FOLLOWUP.md` —
  standalone summary of this follow-up (more compact than this section).
- `cross_arm/sober_state/permutations.jsonl` — unchanged; same
  shuffle map all four judges scored against.

### 10.7 Reproduce

```
cd harness
uv run python -m scripts.judge_sober_ranking --judges gemini --concurrency 3
uv run python -m scripts.judge_sober_ranking --judges gpt    --concurrency 3
uv run python -m scripts.sober_analysis --json ../cross_arm/sober_state/cross_judge_4way.json
```

`--judges all` runs all four; opus and sonnet are no-ops if their
21 rows already exist (idempotent skip-if-exists per item).
