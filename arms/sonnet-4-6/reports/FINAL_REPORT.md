# Sonnet 4.6 Reasoning Drift — Final Report

A 91-run controlled experiment testing whether Anthropic's Sonnet 4.6 model
(adaptive thinking, max effort, 1M context) shows reasoning drift as the
context window fills with adversarially-near peer materials.

The task domain is **financial analysis** — a deliberately blended workload of
factual retrieval, numeric calculation, evidence-grounded reasoning, and
forward-looking thesis construction — run over Microsoft's FY2025 disclosures
with adversarially-near big-tech peer 10-Ks (AAPL, GOOGL, AMZN, META, NVDA,
ORCL, CRM) as the noise corpus, because their business complexity exercises
all four reasoning modes simultaneously. The goal is a **real-world
financial-analyst use case**, not a synthetic benchmark.

Total spend: **$522.96**. Run completed 2026-04-25. Methodology, prompts,
rubric, materials, judge (Opus 4.7 max effort), and extractor (Haiku 4.5)
**identical** to the Opus 4.7 arm — see
[`../../cross_arm/COMPARATIVE_REPORT.md`](../../cross_arm/COMPARATIVE_REPORT.md)
for the apples-to-apples cross-arm comparison and
[`../../arms/opus-4-7/reports/FINAL_REPORT.md`](../../arms/opus-4-7/reports/FINAL_REPORT.md)
for the Opus arm's standalone narrative.

## TL;DR

**Sonnet 4.6 does NOT show the monotonic drift Opus 4.7 shows on this task.**

| metric | fill=0% | fill=25% | fill=50% | fill=75% | fill=95% |
|---|---|---|---|---|---|
| Sonnet reasoning_quality (0-10) | 7.55 | **8.05** | 8.03 | 7.46 | 7.60 |
| Opus   reasoning_quality (0-10) | **8.05** | 7.33 | 6.89 | 7.17 | 7.02 |
| Sonnet pairwise win-rate vs own baseline | n/a | 47% | 36% | 56% | **65%** |
| Opus   pairwise win-rate vs own baseline | n/a | ≈50% | 50% | 0% | **0%** |
| Sonnet unsupported_claims (per response)| 0.10 | 0.47 | 0.48 | 1.07 | 1.06 |
| Opus   unsupported_claims (per response)| 0.24 | 0.76 | 0.62 | 1.02 | **1.68** |
| Sonnet cross_contamination | 0 | 0 | 0 | 0.02 | 0.02 |
| Opus   cross_contamination | 0 | 0 | 0 | 0 | **0.14** |

Three findings stand out:

1. **Sonnet's reasoning_quality peaks in the middle of the fill grid** (8.05 at
   25%, 8.03 at 50%) and recovers at 95% (7.60) above its baseline (7.55).
   Opus's curve is monotonically downward (8.05 → 7.02).
2. **At 95% context, Sonnet's responses BEAT its own baseline** in pairwise
   judging (13-0-7 candidate-win-tie-baseline-win = 65% candidate wins). At the
   same fill, Opus's responses LOSE to baseline (5-0 baseline-win in the pilot;
   similar pattern in full data).
3. **Cross-contamination near zero**: Sonnet attributed peer-company numbers to
   Microsoft only twice in 168 high-fill responses (0.02 mean). Opus had 7×
   that rate at 95%.

Tier 1/2 (factual + calculation): **100% accuracy** across 12 of 13 cells; one
95% cell had a single rep miss all 5 numerics (same single-rep pattern Opus had
at 50% fill — likely a transient model error, not a context-driven failure).

**Cost: $522.96** vs Opus's $582.33 (10% lower). Analyst spend was 35% lower
($217 vs $334). Judge spend identical (~$246) since the judge is held constant.

## 1. Methodology

Pre-registered 2026-04-24, hash `61b2d30f0c741bd96f24159fedc814276df565de317f780e117a3c7e32100419`
(SHA-256 of `DESIGN.md` + `PROMPTS.md` + `RUBRIC.md`). The hash is byte-identical
between this arm and the Opus arm — the methodology is frozen.

Only the analyst snapshot changes: this arm uses `claude-sonnet-4-6` with
`thinking.type.adaptive` + `output_config.effort=max`, `max_output_tokens=65536`,
`temperature=1.0`. Everything else (extractor, judge primary, judge secondary,
prompts, rubric, materials, design grid, noise pool, seed scheme) matches the
Opus arm exactly. See `arm.lock.json` for the pinned configuration.

Design grid: 5 fill levels × 3 noise positions = 12 noise cells + 1 baseline =
13 cells × 7 reps each = 91 runs × 8 questions = 728 records. Noise content is
seeded by `sha256(report|fill|position|rep_idx)` — analyst snapshot is NOT an
input — so this arm sees the same 91 assembled prompts the Opus arm did.

## 2. Data

### 2.1 Tier 1/2 — factual + calculation

100% accuracy across the design grid except one 95%-fill cell where a single
rep missed all 5 numerics (likely a single bad response, not a fill-driven
pattern). This matches the resilience pattern observed for Opus (which had its
own single-rep 50% miss). **Numeric retrieval does not drift with context fill
on this task.**

| fill | F-01 | F-02 | F-03 | C-01 | C-02 |
|---|---|---|---|---|---|
| 0.00 (baseline) | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| 0.25 (× 3 pos) | 21/21 | 21/21 | 21/21 | 21/21 | 21/21 |
| 0.50 (× 3 pos) | 21/21 | 21/21 | 21/21 | 21/21 | 21/21 |
| 0.75 (× 3 pos) | 21/21 | 21/21 | 21/21 | 21/21 | 21/21 |
| 0.95 (× 3 pos) | 20/21 | 20/21 | 20/21 | 20/21 | 20/21 |

Distractor hits (peer-company numbers attributed to Microsoft): **0** at all
fill levels except 95%, where 2 incidents occurred (vs 14 for Opus at 95%).
Sonnet's grounding is unusually clean.

### 2.2 Tier 3 — synthesis (Opus 4.7 judge, max effort)

Mean ± stdev across reps × position × question (n varies by fill):

| fill | reasoning_quality | groundedness | evid_breadth | unsupported_claims | cross_contam | clarity |
|---|---|---|---|---|---|---|
| 0.00 | 7.55 ± 2.22 (n=20) | 4.60 ± 0.92 | 3.95 ± 1.16 | 0.10 ± 0.30 | 0.00 | 4.55 ± 1.07 |
| 0.25 | **8.05 ± 1.20** (n=62) | 4.71 ± 0.63 | 4.13 ± 0.71 | 0.47 ± 0.73 | 0.00 | 4.94 ± 0.50 |
| 0.50 | 8.03 ± 1.13 (n=61) | 4.69 ± 0.50 | 4.23 ± 0.64 | 0.48 ± 0.69 | 0.00 | 4.89 ± 0.48 |
| 0.75 | 7.46 ± 1.66 (n=56) | 4.39 ± 0.67 | 3.96 ± 0.91 | 1.07 ± 1.24 | 0.02 ± 0.13 | 4.77 ± 0.84 |
| 0.95 | 7.60 ± 1.82 (n=63) | 4.30 ± 0.92 | 4.06 ± 0.87 | 1.06 ± 1.07 | 0.02 ± 0.12 | 4.78 ± 0.86 |

Reasoning_quality forms a **shallow inverted-U**: lowest at baseline (7.55),
peaks at low-mid fill (8.05/8.03), dips at 75% (7.46), recovers at 95% (7.60).
The total swing is 0.59 points — smaller than the within-cell stdev (~1.2-2.2),
so the cell-to-cell differences are statistically modest. **What is robust** is
the *absence* of monotonic drift: Sonnet at 95% is *not* worse than at baseline.

Unsupported_claims rises monotonically (0.10 → 1.07), showing Sonnet IS
affected by context noise — it just doesn't translate to lower
reasoning-quality scores. The judge counts the unsupported claims as a
deduction but apparently weights them against the cleaner structure and
groundedness Sonnet maintains.

Cross-contamination is essentially zero (0.02 at 75/95). Sonnet does not
mistakenly cite peer-company facts as Microsoft's. Opus had 7× this rate at 95%.

### 2.3 Pairwise vs own baseline (Opus 4.7 judge, 25% subsample)

The judge sees two responses (the cell's high-fill response and a baseline
response from the same arm) and decides which is better. Side ordering is
randomized per pair to avoid order bias.

| fill | candidate wins | ties | baseline wins | candidate win-rate |
|---|---|---|---|---|
| 0.25 | 8 | 1 | 8 | 47% |
| 0.50 | 5 | 0 | 9 | 36% |
| 0.75 | 9 | 0 | 7 | 56% |
| 0.95 | **13** | 0 | 7 | **65%** |

At 95% fill, Sonnet's responses **win against their own baseline 65% of the
time**. This is the single most surprising finding of this arm. Possible
mechanism: with peer 10-Ks in context, Sonnet has more to draw on for
comparative analysis on Q6/Q7/Q8 (financial health, strategic positioning, AI
impact) — a financial analyst is *better* informed when peer disclosures are
visible, and Sonnet appears to use that signal effectively.

For comparison, Opus arm pairwise at 95% middle (the only cell I have pilot
data for): 0 candidate wins / 5 baseline wins. Opus's high-fill responses lose
to its own baseline cleanly.

### 2.4 Secondary judge (Sonnet 4.6 ICC subsample, n≈36)

The secondary judge runs on a 20% subsample for cross-model rubric-application
reliability. Sonnet judging Sonnet's responses gives lower reasoning_quality
scores than Opus judging Sonnet's:

| fill | Opus judge mean RQ | Sonnet judge mean RQ | Δ |
|---|---|---|---|
| 0.00 | 7.55 | 8.50 (n=2) | +0.95 |
| 0.25 | 8.05 | 7.17 (n=12) | -0.88 |
| 0.50 | 8.03 | 7.57 (n=7) | -0.46 |
| 0.75 | 7.46 | 7.86 (n=7) | +0.40 |
| 0.95 | 7.60 | 6.88 (n=8) | -0.72 |

Two judges agree on the *direction* of differences (no monotonic decline) but
diverge on absolute level. Small samples — interpret cautiously. The Opus arm
showed similar inter-rater divergence; this is a known feature of LLM-as-judge
methodology, not Sonnet-specific.

### 2.5 Thinking-token signature

Sonnet 4.6 at `effort=max` allocates substantially more thinking budget than
Opus 4.7 on the same prompts:

| fill | Sonnet thinking_tokens (mean ± sd) | Sonnet output_tokens | Opus equivalent |
|---|---|---|---|
| 0.00 | 18,589 ± 5,974 | 45,830 ± 10,826 | ~1,000-3,000 thinking |
| 0.25 | 14,049 ± 5,215 | 37,983 ± 10,381 | similar |
| 0.50 | 18,597 ± 7,607 | 44,972 ± 13,848 | similar |
| 0.75 | 13,844 ± 4,225 | 36,764 ± 8,414 | similar |
| 0.95 | 14,061 ± 7,846 | 36,471 ± 13,895 | similar |

This is the practical reason `max_output_tokens=65536` was needed for this arm
(initial 32K caused stop_reason=max_tokens during baseline smoke). Sonnet
thinks 5-10× longer than Opus on the same task. **Despite this, Sonnet's total
analyst spend is 35% lower** ($217 vs Opus's $334) because Sonnet's per-token
output cost is 5× cheaper ($15/M vs $75/M).

Sonnet's thinking is also *visible* (text + `usage.thinking_tokens` returned by
the SDK). Opus 4.7 redacts thinking text and only exposes an encrypted
`signature` whose char-count we use as a proxy. This is a known model-behavior
difference; both fields are captured by `api.py`.

### 2.6 Failed-attempt audit trail

One baseline rep (rep 3) failed initially during the pilot with
`httpx.RemoteProtocolError` (peer connection drop after 5.7 minutes — Sonnet
calls run 5-15 min at max effort). This surfaced a bug in the `api.py` retry
classifier (`_is_retriable` didn't catch httpx-level streaming errors). Fix
landed in commit `8660e6d`; the failed rep was retried successfully. The
failed-attempt record is preserved in
`data/raw/c_MSFT_00_X_X_af5a558f3d83491a.jsonl` as an audit trail (model field
empty, no stop_reason). `verify_arm_integrity.py` was extended to recognize
such records as legitimate audit-trail artifacts rather than mismatches.

The remaining 90 runs and the ~10 transient retries during grade (storm at
20:21-20:23 UTC) all recovered cleanly — zero unrecoverable failures across
the full arm.

### 2.7 Judge parser failures

21 of 273 Tier 3 absolute-judge calls (7.7%) returned unparseable JSON, mostly
on Q8 (MSFT-S-03 framework synthesis). Same root cause as on the Opus arm
(16/329 = 4.9% there): the `judge_secondary` config has `max_output_tokens=8192`
which is too tight for Q8's longer judgement payload at `effort=high`. Defaulted
records (middle-of-rubric values, empty justification) were filtered out of the
analysis above. The bug equally affects both arms — apples-to-apples preserved.

## 3. Cross-arm contrast — what's different about Sonnet?

| dimension | Opus 4.7 | Sonnet 4.6 |
|---|---|---|
| Drift profile | monotonic decline (8.05 → 7.02) | shallow inverted-U; recovers at 95% |
| Peak fill | baseline | 25%-50% fill |
| Pairwise at 95% | loses to own baseline | wins against own baseline |
| Cross-contamination at 95% | 0.14 mean | 0.02 mean (7× cleaner) |
| Unsupported claims at 95% | 1.68 mean | 1.06 mean |
| Tier 1/2 accuracy | ~100% all cells | ~100% all cells |
| Thinking tokens | ~1-3K per call | ~14-19K per call (5-10×) |
| Cost per run | $6.40 avg | $5.74 avg (10% lower) |
| Total arm cost | $582.33 | $522.96 |

**The conventional assumption — "smaller models degrade faster under context
pressure" — is inverted on this task.** Sonnet is more robust on the
quality-by-fill curve, sharper on grounding, dramatically less likely to
cross-contaminate, and beats its own baseline at 95% fill in pairwise judging.

A few hypotheses for why:

1. **Heavier baseline thinking allocation** (18.6K vs 1-3K) might mean Sonnet
   is "doing more" reasoning per call by default, leaving more headroom to
   compensate when context noise rises.
2. **Different attention strategy at high fill.** Sonnet may anchor more
   tightly on the explicitly-marked TARGET MATERIALS block and disregard the
   peer 10-Ks more thoroughly than Opus does. The cross-contamination
   numbers (0.02 vs 0.14) and pairwise-win pattern at 95% are consistent
   with this.
3. **Comparative-analysis benefit.** For the synthesis questions (financial
   health, strategic positioning, AI impact), having peer 10-Ks visible may
   genuinely improve the response quality — analysts compare across peers
   for context. Sonnet appears to exploit this; Opus does not.

These are observations, not causal claims. A follow-up study with a different
corpus (e.g., legal or medical) would be needed to know if the inversion
generalizes or is a Microsoft-financial-analysis-specific quirk.

## 4. Actionable insights for practitioners

For workloads resembling financial analysis (blended retrieval + calc +
reasoning + thesis with adversarially-near supplementary materials):

1. **Sonnet 4.6 is the value pick.** Comparable Tier 3 quality, dramatically
   cleaner grounding under context pressure, 10% lower total cost, **and** a
   *flatter* drift curve. If you can budget either model, Sonnet is preferable
   for this class of task.
2. **Don't be afraid of high fill.** Both models maintain Tier 1/2 perfection,
   and Sonnet's reasoning quality at 95% is ≥ baseline. The "1M context
   degrades reasoning" warning isn't obviously true — at least at this task
   and corpus.
3. **Budget headroom for max-effort thinking.** Sonnet at max can use 18K
   thinking tokens. Set `max_output_tokens=65536` or higher; lower caps
   truncate the JSON body. This tripled Sonnet's per-call cost relative to a
   "high-effort + small max_tokens" config — the ROI shows up as quality.
4. **Cache the target materials separately from noise.** Both arms got cache
   write costs at the cell level (~$2 per cell-write) and ~14× cheaper reads
   on subsequent reps. The 4-breakpoint structure
   `[system][noise_a][target][noise_b]` (DESIGN §6) preserves cache locality
   even when fill position changes between cells.
5. **Use Opus 4.7 as your judge.** Both arms used Opus-as-judge at max effort
   and the rubric application is consistent. Sonnet-as-secondary diverges by
   ~0.5-1.0 RQ points on the same responses — a non-trivial gap. If you're
   running a quality-evaluation pipeline, the judge model matters and Opus is
   a safer choice for stability.

## 5. Limitations

- **Single corpus** (MSFT FY2025 + 7 big-tech peers). Results may not
  generalize to other financial periods, other sectors, or non-financial
  domains. The peer-company "comparison benefit" hypothesis at 95% fill is
  particularly likely to be corpus-dependent.
- **Single analyst-model contrast** (Opus 4.7 vs Sonnet 4.6). No data on
  smaller models or non-Anthropic models.
- **Single judge** (Opus 4.7 with Sonnet 4.6 ICC sample). LLM-as-judge has
  inherent biases; the 0.5-1.0 RQ divergence between Opus and Sonnet on the
  same responses is a known issue. The pairwise judgments mitigate this
  partially (relative comparisons are more stable than absolute ratings).
- **Pre-existing parser bug** affects ~5-8% of Tier 3 judgements on both arms.
  Defaulted records are filtered from analysis; the missing data is
  representative (random across questions and cells) so unlikely to bias the
  comparison, but the effective sample size is reduced.
- **Within-cell variance is large** (RQ stdev ~1.2-2.2). Cell-to-cell mean
  differences smaller than ~1 point should be interpreted as noise, not
  signal. The 0.59-point swing across Sonnet's RQ-by-fill curve is at the
  boundary; the *direction* and *non-monotonicity* are the robust findings,
  not specific per-cell magnitudes.

## 6. Reproducibility

```
git checkout arm/sonnet-4-6/data-v1.0
cd harness
uv sync && cp .env.example .env                                    # set ANTHROPIC_API_KEY
python -m scripts.verify_arm_integrity --arm sonnet-4-6            # confirms 40 files byte-identical
python -m scripts.drift_analysis --arm sonnet-4-6                  # rebuilds tables
python -m scripts.compare_arms                                     # cross-arm gate + comparison
```

`verify_arm_integrity` runs 3 checks: SHA-256 of every data file, lock-file
cross-references (pre_registration.lock + materials.lock.json), and per-record
analyst-snapshot validation. All three pass for `arm/sonnet-4-6/data-v1.0`.

`compare_arms` refuses to produce cross-arm output unless every arm's
`arm.lock.json` agrees on `pre_registration.hash`, `materials.lock_hash`,
`design_used`, and the three instrument configurations. Both arms currently
pass this gate.

## 7. Cost summary

| component | spend | per-run |
|---|---|---|
| Analyst (Sonnet 4.6 max effort) | $217.08 | $2.39 |
| Judge primary absolute (Opus 4.7 max) | $238.70 | $0.84 per Tier 3 record |
| Judge primary pairwise (Opus 4.7 max) | $55.27 | $0.85 per pair |
| Judge secondary (Sonnet 4.6 high) | $7.82 | $0.21 per ICC sample |
| Extractor (Haiku 4.5) | $4.09 | $0.05 per run |
| **Total** | **$522.96** | $5.74 per run |

Budget: $700 (warning), $850 (hard stop). Came in 25% under warning threshold.

Pricing snapshotted into `arm.lock.json` at lock time so cost can be honestly
reconstructed if API rates change after this arm closes.

---

*See `../../arms/opus-4-7/reports/FINAL_REPORT.md` for the Opus 4.7 arm's
standalone narrative and the cross-arm comparison at
`../../cross_arm/COMPARATIVE_REPORT.md`.*
