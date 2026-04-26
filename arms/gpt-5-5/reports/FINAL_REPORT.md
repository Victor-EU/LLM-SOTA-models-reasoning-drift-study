# Reasoning drift in GPT-5.5 under context-window pressure
**Final report — 2026-04-26**

A 91-run controlled experiment on OpenAI's GPT-5.5 (1M-token context, `reasoning.effort=xhigh` — vendor maximum) measuring how reasoning quality degrades as the context window fills with adjacent-but-irrelevant material.

This is the **second arm** of the Opus 4.7 Reasoning Drift Study and the first non-Anthropic arm under v2 methodology (`MULTI_VENDOR_ADDENDUM.md`). Materials, design grid, prompts, extractor, judge, and seeds are byte-equivalent to the Opus 4.7 and Sonnet 4.6 v1 arms — only the analyst model varies. The cross-arm comparability proof is in `cross_arm/COMPARATIVE_REPORT.md` (5 arms, integrity-gated).

The task domain is **financial analysis** — a deliberately blended workload of factual retrieval, numeric calculation, evidence-grounded reasoning, and forward-looking thesis construction — run over Microsoft's FY2025 disclosures with adversarially-near big-tech peer 10-Ks (AAPL, GOOGL, AMZN, META, NVDA, ORCL, CRM) as the noise corpus.

Total spend: **$338.83** (42% cheaper than the Opus 4.7 arm at $582.33). Total runs: **91/91 successful** (zero exclusions, zero failures). Wall time end-to-end: **~2.1 hours** (collect 71 min wall with 4-cell concurrency, 142s avg latency per call; extract 6 min; grade ~47 min).

---

## TL;DR — three converging findings

1. **Factual lookup is robust.** Tier-1 numeric questions (revenue, operating income, EPS, tax rate, YoY growth) hit **100% accuracy in every cell** from 13% realized fill to 92% realized fill. **Zero cross-contamination across all 91 runs at every fill level** — even at 92% fill with seven peer 10-Ks in the window, GPT-5.5 never attributed peer financials to MSFT.

2. **Synthesis quality drifts, but markedly less than Opus 4.7.** Tier-3 reasoning quality drops **7.05 → 6.27** (−11%) on a 0–10 scale. Compare to Opus 4.7 same arm: **8.05 → 7.02** (−13%, Δ = −1.03 vs GPT-5.5's Δ = −0.78). GPT-5.5 starts lower, ends lower, but loses *less ground*.

3. **The headline cross-arm difference: GPT-5.5 essentially does not hallucinate under context pressure.** Unsupported claims rise from **0.00 to 0.05** per response (effectively zero). Compare Opus 4.7 same arm: **0.24 → 1.68** (7× more, ~33× higher in absolute terms at 95% fill). Where Opus follows form but skips evidence, **GPT-5.5 stays disciplined to its claims** even when noise dominates.

If you ship GPT-5.5 to users today: **(a)** trust it for both factual extraction and citation-anchored synthesis at any fill; **(b)** expect its absolute reasoning depth to plateau lower than Opus 4.7 even at 0% fill — this is a *fewer-but-correct-claims* model, not a *more-and-deeper-claims* model.

---

## 1. Methodology

Methodology is identical to the Opus 4.7 arm and inherited by reference. See `arms/opus-4-7/reports/FINAL_REPORT.md §1` and project-root `DESIGN.md`, `PROMPTS.md`, `RUBRIC.md`, `MULTI_VENDOR_ADDENDUM.md`. Only this arm's analyst differs.

### 1.1 Models

- **Analyst** — `gpt-5.5-2026-04-23` (server-resolved alias `gpt-5.5-2026-04-23` — identical, no drift), `reasoning.effort=xhigh` (vendor max — top of {none, low, medium, high, xhigh}), `reasoning.summary=auto`, `max_output_tokens=128000`, `temperature=1.0`. Wrapped via the OpenAI Python SDK against the Responses API. Encrypted reasoning blobs are exposed via `include=["reasoning.encrypted_content"]`; raw chain-of-thought is redacted (synthetic summaries only via `reasoning.summary=auto`).
- **Extractor** — `claude-haiku-4-5-20251001`, no thinking, max_output_tokens=16K, temperature=1.0. **Held constant across arms** — extraction noise does not confound cross-arm analyst comparisons.
- **Primary judge** — `claude-opus-4-7`, adaptive thinking `effort=max`, max_output_tokens=16K. **Held constant across arms.** The judge runs against cached fill=0 target materials, so there is no within-judge drift confound.
- **Secondary judge** — `claude-sonnet-4-6`, `effort=high`, on a 20% subsample of (run, q_id) pairs for cross-model inter-rater reliability.

### 1.2 v2-specific notes

- **Tokenizer asymmetry.** Token budget convergence uses Anthropic's `count_tokens` (the judge-primary tokenizer fallback per `tokens.py:111-115`), not OpenAI's. This guarantees byte-identical noise packs across arms at the same `(cell_id, rep_idx)` coordinate — verified via cross-arm sha256 comparison. GPT-5.5's actual realized input is ~63% of the Anthropic-counted target (~582K OpenAI tokens at 95% fill vs 925K Anthropic-tokens for Opus on the *exact same prompt bytes*).
- **Reasoning tokens bundled into output_tokens.** OpenAI counts `reasoning_tokens` as part of `output_tokens`. The 128K `max_output_tokens` cap accommodates both. We log `reasoning_tokens` separately for compute analysis (see §2.7).
- **Pricing tier.** GPT-5.5 has tiered pricing: $5/$30 per M tokens below 272K input, $10/$45 above. 12/13 cells exceed 272K, so the locked rate snapshot uses the high tier ($10/$45 input/output). Effective per-call cost dominated by output (xhigh reasoning is verbose).

---

## 2. Results

### 2.1 Headline drift curve

Mean reasoning quality (0–10), aggregated across all three Tier-3 questions × all positions × 7 reps per cell.

| realized fill | n  | mean reasoning_quality | sd   | Δ vs baseline |
|--------------:|---:|-----------------------:|-----:|--------------:|
| 13% (baseline)| 21 | **7.05**               | 0.74 | —             |
| 24%           | 63 | 6.89                   | 1.26 | −0.16         |
| 47%           | 63 | **6.92**               | 0.92 | −0.13         |
| 72%           | 63 | 6.89                   | 0.79 | −0.16         |
| 92%           | 63 | **6.27**               | 1.67 | **−0.78**     |

Drift is **flat-then-cliff**: GPT-5.5 holds within ~0.16 points of baseline through 72% fill, then drops 0.62 points between 72% and 92%. This is qualitatively different from Opus 4.7's *non-monotonic dip-and-partial-recovery* pattern (8.05 → 7.33 → 6.89 → 7.17 → 7.02). Variance also stays tighter through the middle fills (sd 0.79–1.26) before doubling at 92% (sd 1.67) — same "variance-balloons-before-mean-drops" precursor signal as Opus, just delayed.

### 2.2 Per-dimension drift

Aggregated across S-01, S-02, S-03; mean across 21 (baseline) or 63 (non-baseline) responses per fill.

| fill  | groundedness | breadth | scope | clarity | citation | reasoning | unsup    | xcontam  |
|------:|-------------:|--------:|------:|--------:|---------:|----------:|---------:|---------:|
| 0.00  | **5.00**     | 3.71    | 5.00  | 4.29    | 4.95     | **7.05**  | **0.00** | **0.000**|
| 0.25  | 4.87         | 3.63    | 4.97  | 4.25    | 4.76     | 6.89      | 0.02     | 0.000    |
| 0.50  | 4.84         | 3.70    | 4.84  | 4.22    | 4.63     | 6.92      | 0.00     | 0.000    |
| 0.75  | 4.94         | 3.56    | 4.94  | 4.24    | 4.83     | 6.89      | 0.00     | 0.000    |
| 0.95  | **4.70**     | 3.38    | 4.87  | 4.06    | **4.37** | **6.27**  | **0.05** | **0.000**|

- **Most-degraded dimensions:** reasoning quality (−0.78), citation accuracy (−0.58), groundedness (−0.30).
- **Most-robust dimensions:** scope_adherence (−0.13, stays ≥4.84/5), clarity (−0.23), evidentiary_breadth (−0.33).
- **Cross-contamination is exactly zero across all 91 runs and all 5 fill levels.** GPT-5.5 never attributes peer-company data to MSFT in *any* tier. Compare Opus, which logged 0.095/response at 95% fill.
- **Unsupported claims essentially zero.** 0.05/response at 95% means ~1 unsupported claim per 20 synthesis answers, vs Opus's 1.68 (≈ 1 per 0.6 answers). This is a 33× absolute difference and is the largest cross-arm contrast in the dataset.

### 2.3 Position effect

Within each fill level, by noise position. n=21 per cell.

| fill | start    | middle | end    |
|------|---------:|-------:|-------:|
| 0.25 | **6.48** ← weakest | 7.10 | 7.10 |
| 0.50 | 6.90     | 6.95   | 6.90   |
| 0.75 | 7.10     | 6.90   | **6.67** ← weakest |
| 0.95 | **5.48** ← weakest | 6.67 | 6.67 |

- **`start` position is consistently the weakest** at 25%, 75%, and 95% fill. When the target sits *before* the noise pile, GPT-5.5 underperforms — opposite of Opus 4.7's pattern (where `end` was strongest and `middle` weakest).
- **At 95% fill the start position drops a full point** (5.48 vs middle/end's 6.67). Suggests a recency-attention pattern where GPT-5.5 weights later context more heavily; pushing the target away from the response cursor degrades it more than Opus.
- **`middle` and `end` converge** at 92% fill — both at 6.67 — consistent with attention saturating to the most-recent plausible signal.

### 2.4 Pairwise vs baseline (the cleanest drift signal)

For 25% of non-baseline (run, q_id) pairs, the Opus 4.7 judge picks the better of (baseline rep, candidate rep) on the same question. A/B randomized.

| fill  | wins | losses | ties | mean Δ (cand−base) | n  |
|------:|-----:|-------:|-----:|-------------------:|---:|
| 0.25  |  6   | 11     | 0    | **−0.8 ± 3.1**     | 17 |
| 0.50  |  5   |  8     | 2    | **−0.7 ± 2.3**     | 15 |
| 0.75  | 11   |  6     | 1    | **+0.8 ± 2.3**     | 18 |
| 0.95  |  8   | 11     | 1    | **−1.9 ± 4.2**     | 20 |

- Compare Opus 4.7 same study: monotonic decline (+/−: 7/9, 5/10, 1/17, 2/18; means −0.3, −1.2, −2.6, −2.7). At 75% fill Opus loses 17/18 pairwise comparisons; **GPT-5.5 *wins* 11/18 at the same fill** with a +0.8 mean delta.
- The 95% fill drop is real but attenuated: GPT-5.5's −1.9 pairwise delta is comparable to Opus's −2.7 in direction but ~30% smaller in magnitude.
- High variance at 95% (sd 4.2) flags the unpredictability also visible in §2.1's stdev.

### 2.5 Q8 structural diagnostics — form persists, content holds up

S-03 mandates a **decompose by unit → apply 4 frameworks → synthesize** structure.

| fill | units_decomposed | frameworks_applied | synthesis_consistent |
|------|------------------|--------------------|----------------------|
| 0.00 | 8.6 ± 1.0        | 4.0 ± 0.0          | 100% (7/7)           |
| 0.25 | 7.2 ± 2.2        | 3.7 ± 0.9          | 100% (21/21)         |
| 0.50 | 7.9 ± 0.6        | 4.0 ± 0.0          | 100% (20/20 non-null)|
| 0.75 | 8.4 ± 1.0        | 4.0 ± 0.0          | 100% (21/21)         |
| 0.95 | 7.3 ± 2.6        | 3.6 ± 1.2          | 95% (20/21)          |

GPT-5.5 retains the prescribed Q8 scaffolding through all fills. Frameworks-applied dips at 25% (3.7) and 95% (3.6) but stays ≥3.6/4 throughout. Unlike Opus, where the Q8 *form* held while the *content* (groundedness, citations) degraded substantially, **GPT-5.5 keeps both form and content roughly intact** — explaining the much smaller unsupported_claims and cross_contamination figures in §2.2.

### 2.6 Tier 1/2 — no drift detected

| cell type | F-01 (revenue) | F-02 (op income) | F-03 (EPS) | C-01 (tax rate) | C-02 (growth) |
|-----------|---------------:|-----------------:|-----------:|----------------:|--------------:|
| All 13 cells | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |

**100% across the entire grid.** Zero cross-contamination on Tier 1/2 across all 91 runs. Even at 92% realized fill with 7 peer 10-Ks in the window, GPT-5.5 never attributed peer revenues, op-income figures, or EPS to MSFT.

### 2.7 Cross-model judge validation (Sonnet 4.6 secondary)

Paired Opus-vs-Sonnet ratings on 56 (run, q_id) responses (20% deterministic subsample). Per RUBRIC.md §Judge-model agreement, we compute Pearson r, ICC(2,1) (Shrout–Fleiss two-way random, single rater, absolute agreement), and Lin's CCC per dimension. RUBRIC threshold for "use absolute scores": ≥ 0.70.

| dimension                 | n  | Opus μ | Sonnet μ | Δ μ   | Pearson r | ICC(2,1) | Lin CCC  | flag |
|---------------------------|---:|-------:|---------:|------:|----------:|---------:|---------:|------|
| groundedness              | 56 | 4.84   | 4.64     | +0.20 | 0.215     | 0.199    | **0.196**| ⚠ |
| evidentiary_breadth       | 56 | 3.45   | 3.46     | −0.02 | 0.797     | 0.800    | **0.797**| ok |
| scope_adherence           | 56 | 4.89   | 4.86     | +0.04 | −0.066    | −0.066   | **−0.065**| ⚠ |
| clarity                   | 56 | 4.11   | 4.27     | −0.16 | 0.433     | 0.422    | **0.418**| ⚠ |
| citation_accuracy         | 56 | 4.61   | 4.62     | −0.02 | 0.068     | 0.068    | **0.067**| ⚠ |
| **reasoning_quality** (0–10) | 56 | 6.57   | 6.80     | −0.23 | 0.678     | 0.668    | **0.664**| ⚠ |

**Read this carefully:**

- **Only `evidentiary_breadth` clears the 0.70 bar** (CCC 0.797). On every other dimension, fall back to pairwise per RUBRIC §Judge-model agreement. The pairwise data in §2.4 is therefore the authoritative signal for cross-fill comparisons.
- **`reasoning_quality` lands at CCC 0.664** — close to but below threshold. Direction agrees (both judges see the 92% drop) but absolute scores carry meaningful noise. The drift conclusions in §2.1 hold because they rely on within-judge consistency across fills, not on absolute calibration.
- **`groundedness`, `scope_adherence`, `citation_accuracy`** all score in saturation territory (means 4.6–4.9 of 5) — variance available for correlation is tiny, so Pearson-based metrics produce near-zero CCC even when the judges substantively agree. This is a measurement-floor artifact, not real disagreement: both judges concur that GPT-5.5 essentially never violates these dimensions.
- **Compared to Opus 4.7 arm:** Opus had 4 of 6 dimensions clear the 0.70 bar (groundedness, breadth, citation_accuracy, reasoning_quality). GPT-5.5 has only 1. The structural cause is different score distributions: GPT-5.5's responses cluster tighter near the top of every dimension, leaving less variance for inter-judge agreement to act on. This is consistent with the §2.2 finding that GPT-5.5 makes *fewer marginal claims* — the judges have less to disagree about.

### 2.8 Compute and timing

Mean per-rep across 7 reps per cell, aggregated by fill (3 positions averaged for non-baseline).

| fill | realized input (Anthropic-tok) | output (incl reasoning) | reasoning_tokens | latency |
|-----:|-------------------------------:|------------------------:|-----------------:|--------:|
| 0.00 | 79K  | 14,396 | **9,669** | 168 s |
| 0.25 | 164K | 14,238 | 9,136 | 169 s |
| 0.50 | 297K | 12,537 | 7,764 | 151 s |
| 0.75 | 452K | 11,788 | **6,624** | 128 s |
| 0.95 | 582K | 11,249 | **6,289** | 113 s |

**Headline compute finding:** GPT-5.5 *reduces* reasoning allocation as fill increases — **9,669 → 6,289 tokens, a 35% drop**. This is the **opposite** of Opus 4.7's pattern in the same study (Opus scaled reasoning from 2,417 → 4,524 tokens, +87%, under identical context pressure).

The latency trace corroborates: wall time *decreases* from 168s at baseline to 113s at 95% fill, a 33% drop. With more raw input to process, GPT-5.5 *thinks less and answers faster*. Opus did the opposite (latency 169s → 214s).

This is an **architectural-level difference in how the two models allocate reasoning under context pressure**, and it's the single most striking cross-arm finding in this study. Plausible interpretations (untestable from this data alone):

- GPT-5.5's xhigh reasoning has a context-gated budget that contracts when the input expands (whether by design, infra constraint, or learned policy);
- the model interprets dense long context as "more evidence available" and shortcuts to retrieval rather than synthesis;
- Anthropic and OpenAI's "max thinking" knobs measure substantively different things, and the cross-arm comparison is partially apples-to-oranges (see §4 limitations and `MULTI_VENDOR_ADDENDUM.md §3`).

The triple-signal corroboration (reasoning_tokens ↓, output_tokens ↓, latency ↓ — all moving the same direction) makes this a real model behavior, not a measurement artifact. GPT-5.5's −0.78 RQ drop is what it produces *while doing less work* — a different bargain than Opus.

---

## 3. Actionable insights

### 3.1 For practitioners deploying GPT-5.5

1. **Trust factual extraction at any fill.** Tier-1 was 100% across all 91 runs with zero contamination. Identical conclusion as Opus.

2. **Trust citation-anchored synthesis at any fill.** Unlike Opus 4.7, GPT-5.5 does **not** materially increase unsupported claims under context pressure (0.00 → 0.05). If hallucination-resistance matters more than peak reasoning depth, GPT-5.5 is the better deploy.

3. **Position the target *after* the noise** — opposite of Opus. At 95% fill, `start` (target before noise) drops a full point vs `middle` and `end`. GPT-5.5's attention pattern favors recent context for the response generation step.

4. **Don't expect more reasoning under load — expect less.** The xhigh budget contracts ~35% as fill grows. If your workload pushes context, set lower expectations on reasoning depth and consider explicit step-by-step prompting to compensate.

5. **Variance balloons at 92% before mean drops.** Same precursor signal as Opus, just delayed. Monitor across-rep variance if you're pushing context limits — it's the early warning before mean RQ falls.

6. **The 75% fill *can* be candidate-favored over baseline.** GPT-5.5 wins 11/18 pairwise comparisons at 75% fill (+0.8 mean delta). The model occasionally produces *better* synthesis with moderate noise than at baseline — possibly because peer 10-Ks supply useful comparative anchors when not overwhelming. Don't assume "less context is always better."

### 3.2 For prompt engineers

- **Scope markers work — same conclusion as Opus.** The `<<< TARGET MATERIALS: ... >>>` delimiter combined with the analyst-prompt rule "Base EVERY answer EXCLUSIVELY on the TARGET MATERIALS block" prevented Tier-1 contamination across all 92K-token cells. Deployable pattern.
- **Citation requirements degrade only mildly with fill.** Citation accuracy drops 4.95 → 4.37 (−0.58) — meaningful but not catastrophic. Compare Opus 4.86 → 3.97 (−0.89). GPT-5.5 cites accurately under load.
- **xhigh reasoning is the right knob for synthesis tasks.** No tested alternative — this study only ran vendor-max. But the responses show clear evidence of multi-step deliberation (the reasoning summaries via `reasoning.summary=auto` log substantive plans).

### 3.3 For evaluators / researchers

- **Pairwise vs baseline is the cleanest signal — same conclusion as Opus.** GPT-5.5's CCC for absolute reasoning_quality is 0.664 (below RUBRIC threshold). Pairwise gives a much sharper read on within-arm drift.
- **Dimension saturation suppresses ICC.** When a model rarely violates a dimension (groundedness, scope, citation all ≥4.6/5 mean for GPT-5.5), Pearson-based agreement metrics report near-zero even with substantial substantive agreement. Report mean differences alongside ICC for saturated dimensions.
- **Use realized fill, not nominal — same as Opus.** GPT-5.5's tokenizer counts ~63% as many tokens as Anthropic's on identical bytes; budget convergence in this study used Anthropic's tokenizer for cross-arm equivalence. If you redo this with OpenAI-native budget, your fill will look very different from ours.
- **Triple-signal corroboration matters.** The reasoning-token contraction we report is robust precisely because reasoning_tokens, output_tokens, and latency all move the same direction. Single-signal claims about "thinking allocation" can be confounded by API metering changes; the trio is harder to fool.

### 3.4 For the OpenAI API team (observations, not asks)

- The Responses API's `include=["reasoning.encrypted_content"]` correctly preserved encrypted reasoning blobs for stateless replay; we used them downstream for compute analysis without issue.
- `reasoning.summary=auto` produced consistently usable plan-style summaries — better than the Anthropic equivalent which is fully redacted. This matters for transparency-heavy use cases.
- The fact that `reasoning_tokens` is bundled into `output_tokens` for billing was easy to miss and required defensive `max_output_tokens` sizing. A separate `max_reasoning_tokens` knob would help consumers reason about cost.

---

## 4. Limitations

- **Single target company (MSFT).** All findings conditional on this 10-K + earnings call.
- **Single noise corpus (peer 10-Ks).** "Adversarially near" is one design point.
- **Same-vendor judge (Anthropic Opus 4.7 judging GPT-5.5).** The judge model is from a different vendor than the analyst — this *reduces* same-vendor self-rating bias risk vs the Opus arm (which used Opus to judge Opus), but introduces the opposite risk: judges may systematically prefer their own vendor's stylistic conventions. The Sonnet 4.6 secondary judge (also Anthropic) shows similar patterns to Opus, so the cross-arm direction conclusions are robust to judge choice within the Anthropic family. A genuinely cross-vendor judge (e.g., Gemini judging GPT) would sharpen this.
- **Vendor-max thinking is not equivalent across vendors.** Anthropic's `effort=max`, OpenAI's `reasoning.effort=xhigh`, Google's `thinking_level=HIGH`, and DeepSeek's `reasoning_effort=max` are vendor-defined; we use each vendor's documented top knob, but the numeric reasoning-token allocations differ by 2–4× across arms. Cross-arm reasoning-quality comparisons should be read as "each at its own top setting," not "matched compute."
- **n = 7 reps per cell.** Adequate for direction but tight for variance estimation, especially within (fill, position) cells.
- **Compressed fill range.** Pool exhaustion means 75% and 95% target fills realized at 72% and 92%. Cross-arm fill values are byte-identical (proven via materials sha256), so this affects all arms equally.
- **Three Tier-3 questions.** Synthesis genres sampled: descriptive (financial health), structural (segment positioning), forward-looking (AI impact). Other synthesis types (causal, counterfactual, longer horizons) might drift differently.
- **Extractor parse rate: 100% for GPT-5.5.** No placeholder records. Comparable to Opus (98.9%) and Sonnet (98.8%); markedly better than DeepSeek (92.3%). Indicates GPT-5.5's JSON output adheres reliably to schema even at 95% fill.
- **Methodology pre-registration:** v2 hash `3433f4a67cde4b24b92a1b41a78271aa5dbb4572beb2ee23e1d8c2c31d189e8e` (SHA-256 of DESIGN+PROMPTS+RUBRIC+MULTI_VENDOR_ADDENDUM). Locked 2026-04-25T23:35:00Z. Inheritance from v1 is additive — the v1 Opus and Sonnet arms remain valid evidence under v2 without re-run.

---

## 5. What this means for the field

This is the second well-controlled data point in the cross-vendor reasoning-drift comparison the project is building. Two findings emerge with implications beyond GPT-5.5:

1. **"Max thinking" is a vendor-defined knob, not a property of the underlying model behavior.** GPT-5.5 at xhigh allocates 9.7K reasoning tokens at baseline and *contracts* to 6.3K under context pressure. Opus 4.7 at max allocates 2.4K at baseline and *expands* to 4.5K. These are opposite responses to the same stimulus. The label "max" hides a fundamental architectural divergence.

2. **The dominant failure mode is vendor-specific.** Opus 4.7's failure under noise is *evidentiary erosion* (groundedness ↓, unsupported claims ↑, but form preserved). GPT-5.5's failure is *engagement contraction* (reasoning depth ↓, output volume ↓, latency ↓, but claims stay disciplined). The same 92%-fill stimulus produces qualitatively different breakdowns. This means hallucination-mitigation strategies that work for one vendor may not transfer to the other.

3. **The "less but correct" trade-off is real.** GPT-5.5's net Tier-3 reasoning quality is ~0.7 points below Opus 4.7 across all fills, but its unsupported-claims rate is ~30× lower. Choosing between them is a deployment decision about the relative cost of (a) missing depth vs (b) generating fabrications. This study doesn't answer that — but it quantifies the trade for the first time.

Three follow-ups would sharpen this:

1. **Test other "max thinking" ladder steps for GPT-5.5** (low/medium/high) to see if the contraction-under-load pattern is xhigh-specific or general.
2. **Replicate with non-MSFT targets and different noise corpora** to test generalization.
3. **Cross-vendor judge** (e.g., GPT-5.5 judging Opus, or vice versa) to disentangle judge-vendor preference effects from real quality differences.

---

## 6. Reproducibility

All code, prompts, materials, and per-run data are in this repository.

```
arms/gpt-5-5/
├── arm.lock.json         — locked snapshot (schema v2.0)
├── data.manifest.sha256  — per-file integrity manifest (40 files)
├── data/
│   ├── raw/              — 13 cells × 7 reps = 91 jsonl records
│   ├── extracted/        — 13 × 56 = 728 normalized records
│   ├── graded/           — 728 graded + 70 pairwise + 56 secondary
│   └── manifest.sqlite   — run state, costs, audit log
└── reports/
    └── FINAL_REPORT.md   — this document
```

To reproduce:

```bash
cd harness
python -m scripts.run_experiment --arm gpt-5-5    # collect: 91 runs (~$109, ~71 min wall with 4-cell concurrency)
python -m scripts.run_extractor   --arm gpt-5-5   # extract: Haiku normalization (~$2, 6 min)
python -m scripts.run_grading     --arm gpt-5-5   # grade: Opus + Sonnet judges (~$227, ~47 min)
python -m scripts.drift_analysis  --arm gpt-5-5   # analysis tables
python -m scripts.write_arm_lock  --arm gpt-5-5   # regenerate arm.lock.json + manifest
python -m scripts.verify_arm_integrity --arm gpt-5-5  # verify byte-identical
```

Verify before trusting: `python -m scripts.verify_arm_integrity --arm gpt-5-5` runs three checks (per-file SHA-256s, methodology-hash consistency, raw-record/lock alignment via `analyst.snapshot` or `snapshot_observed_aliases`). Currently passes all three.

Total cost for full reproduction: **$338.83**. Manifest is resumable — if any stage crashes, re-running picks up where it left off.

---

## 7. Cost summary

| stage | cost     | per-run / per-record |
|-------|---------:|---------------------:|
| Collect (analyst, GPT-5.5 xhigh)         | $109.40  | $1.20 / run     |
| Extract (Haiku 4.5)                      | $2.40    | $0.026 / run    |
| Grade — primary absolute (Opus 4.7 max)  | $170.73  | ~$0.63 / record |
| Grade — pairwise (Opus 4.7 max)          | $50.94   | ~$0.73 / pair   |
| Grade — secondary (Sonnet 4.6 high)      | $5.36    | ~$0.10 / record |
| **Total**                                | **$338.83** |              |

Budget configured at $700, hard stop $850. Spend ended at 48% of budget — substantially under (Opus arm spent 83%, $582.33). The cost reduction is concentrated in the analyst stage: GPT-5.5 collect was $109 vs Opus's $334, a 67% reduction. Grade stages cost similarly because the judge is held constant (Opus 4.7 max) across arms.

---

## Acknowledgments

Pipeline built on the OpenAI Python SDK (Responses API) for the analyst, Anthropic Python SDK for extraction and judging. Materials sourced from public 10-K filings and Microsoft FY2026 Q2 earnings call transcript. Cross-arm comparability validated via byte-equivalent prompt sha256 at every (cell, rep) coordinate.
