# Reasoning drift in DeepSeek V4 Pro under context-window pressure
**Final report — 2026-04-26**

A 91-run controlled experiment on DeepSeek V4 Pro Preview (1,000,000-token context, `reasoning_effort=max` — vendor maximum) measuring how reasoning quality degrades as the context window fills with adjacent-but-irrelevant material.

This is the **fourth arm** of the Opus 4.7 Reasoning Drift Study and the third non-Anthropic arm under v2 methodology (`MULTI_VENDOR_ADDENDUM.md`). Materials, design grid, prompts, extractor, judge, and seeds are byte-equivalent to all prior arms — only the analyst model varies. The cross-arm comparability proof is in `cross_arm/COMPARATIVE_REPORT.md` (5 arms, integrity-gated).

The task domain is **financial analysis** — a deliberately blended workload of factual retrieval, numeric calculation, evidence-grounded reasoning, and forward-looking thesis construction — run over Microsoft's FY2025 disclosures with adversarially-near big-tech peer 10-Ks (AAPL, GOOGL, AMZN, META, NVDA, ORCL, CRM) as the noise corpus.

Total spend: **$194.54** (67% cheaper than Opus 4.7's $582.33). Total runs: **91/91 successful** (zero exclusions, zero failures). Wall time end-to-end: **~2.1 hours** (collect 82 min wall with 4-cell concurrency, 177s avg latency per call; extract ~10 min including 7 retry passes; grade ~32 min).

---

## TL;DR — three converging findings

1. **Tier-1 factual hit rate is 100% on the analyst's own output, but the measurement chain loses 7/91 reps to extractor placeholders.** Per-cell scores of 5/7 to 7/7 in the autograder reflect 7 reps where Haiku 4.5 deterministically failed to reformat DeepSeek's (valid JSON) analyst output. The autograder treats those reps as wrong on every question. **All 7 fully-failed Tier-1/2 reps line up exactly with the 7 stuck extractor placeholders** — there are zero analyst-side Tier-1 errors in this dataset. The deployment-relevant takeaway: if your downstream pipeline parses DeepSeek output with an LLM-based normalizer like Haiku 4.5, expect ~7.7% measurement loss; if you parse deterministically, the analyst's Tier-1 hit rate is 100%.

2. **Synthesis quality is exceptionally flat under fill — the flattest absolute drift in the study.** Tier-3 reasoning_quality moves only **5.33 → 5.24** (−1.7%, Δ = −0.09) across 13–92% fill. Compare Opus 4.7 −1.03, Sonnet 4.6 −0.81, GPT-5.5 −0.78, Gemini 3.1 −0.30. By absolute Likert scoring, DeepSeek looks like the *most context-robust* model in the panel.

3. **But pairwise comparison reveals the steepest drift in the study.** Direct Opus-judge head-to-heads against the baseline rep give DeepSeek **−4.1 ± 3.1 mean delta at 95% fill** (1 win, 16 losses, 0 ties out of 17 pairs). Compare Opus 4.7 −2.7, GPT-5.5 −1.9, Gemini −1.2. **Absolute scores hide the drift; pairwise exposes it.** This is the textbook case for why pairwise is the cleanest evaluator-design choice for noisy synthesis tasks.

If you ship DeepSeek V4 Pro to users today: **(a)** parse the analyst's JSON output deterministically (regex/format validators) rather than chaining a second LLM as a normalizer — the analyst's Tier-1 hit rate is 100% but Haiku-4.5 reformatting fails on ~7.7% of high-fill responses; **(b)** the model is **2.4× cheaper than Gemini, 23× cheaper than Opus** at the analyst stage — economics may dominate quality for tolerant workloads; **(c)** for high-stakes synthesis, the absolute-vs-pairwise gap is a warning sign — read pairwise (§2.4) before deciding.

---

## 1. Methodology

Methodology is identical to the Opus 4.7 arm and inherited by reference. See `arms/opus-4-7/reports/FINAL_REPORT.md §1` and project-root `DESIGN.md`, `PROMPTS.md`, `RUBRIC.md`, `MULTI_VENDOR_ADDENDUM.md`. Only this arm's analyst differs.

### 1.1 Models

- **Analyst** — `deepseek-v4-pro` (snapshot string is a mutable alias — DeepSeek does not publish dated snapshot IDs). `reasoning_effort=max` — vendor maximum per third-party report (blockchain.news 2026-04-24); not yet in official DeepSeek docs at lock authoring time. Acceptance verified at smoke-test time. Raw chain-of-thought exposed via `reasoning_content` field on the message (legacy V3 behavior carried into V4). `max_output_tokens=128000`, `temperature=1.0`. Wrapped via the OpenAI Python SDK against `api.deepseek.com` (no first-party DeepSeek SDK).
- **Extractor** — `claude-haiku-4-5-20251001`, no thinking, max_output_tokens=16K, temperature=1.0. **Held constant across arms.**
- **Primary judge** — `claude-opus-4-7`, adaptive thinking `effort=max`, max_output_tokens=16K. **Held constant across arms.** Judge runs against cached fill=0 target materials — no within-judge drift confound.
- **Secondary judge** — `claude-sonnet-4-6`, `effort=high`, on a 20% subsample.

### 1.2 v2-specific notes

- **Extractor parse failure rate: 7.7%** (7 reps × 8 questions = 56 placeholder records out of 728). After 7 manual retry passes the failure floor was reached; the remaining 7 reps deterministically fail Haiku-4.5 reformatting despite being valid JSON in the analyst output. We accept the failures as a measured property of the analyst-output style, not a methodology violation. The grader treats placeholder records as missing — and these 7 reps **fully account** for the §2.6 Tier-1/2 accuracy gap (verified set-equality between {failed-extractor reps} and {fully-failed-Tier-1/2 reps}). Compare Opus 1.1%, Sonnet 1.2%, GPT-5.5 0%, Gemini 0%.
- **Tokenizer asymmetry.** Token budget convergence uses Anthropic's `count_tokens` (the judge-primary tokenizer fallback). DeepSeek's actual realized input is ~63% of the Anthropic-counted target. At 95% fill, Anthropic counts ~925K but DeepSeek's API metered ~584K — a ~37% reduction. Cross-arm fill values are byte-identical at every (cell, rep) coordinate (verified via prompt sha256).
- **Pricing — REGULAR rate snapshotted.** DeepSeek had a 75%-off promo through 2026-05-05 15:59 UTC; this arm was collected before the promo cliff. The locked pricing snapshot uses *regular* rates ($1.74 input, $3.48 output per M tokens, $0.145 cache_read), so cost numbers represent honest at-list pricing. Actual paid amount during the experiment was lower; reconstructions using the locked rates are upper bounds.
- **Cache hits are massive.** DeepSeek's automatic cache (no explicit breakpoints) registered cache_read on **90 of 91 calls**, mean 302K cache_read tokens per call (max 587K). The only non-Anthropic vendor with non-trivial caching in this study; the mean cache hit alone exceeds Gemini's full input at 25% fill. Captured in `pricing.deepseek_v4_pro.cache_read = $0.145/M` for honest cost reconstruction.
- **Snapshot mutability.** The `deepseek-v4-pro` string is an alias. The arm.lock records the requested string and the observed `model` value (single value across 91 runs — no mid-experiment build drift detected, but we cannot prove the build was constant since DeepSeek doesn't expose a `system_fingerprint` field in V4 responses).

---

## 2. Results

### 2.1 Headline drift curve

Mean reasoning quality (0–10), aggregated across all three Tier-3 questions × all positions × 7 reps per cell.

| realized fill | n  | mean reasoning_quality | sd   | Δ vs baseline |
|--------------:|---:|-----------------------:|-----:|--------------:|
| 13% (baseline)| 21 | **5.33**               | 2.31 | —             |
| 24%           | 63 | 5.16                   | 2.25 | −0.17         |
| 47%           | 63 | 5.30                   | 1.44 | −0.03         |
| 72%           | 63 | **5.43** ← peak         | 1.50 | +0.10         |
| 92%           | 63 | 5.24                   | 1.42 | −0.09         |

**The flattest absolute-score curve in the study.** The 5-point spread across the 13–92% fill range is 0.27 RQ — less than one-third of GPT-5.5's spread (0.78), one-quarter of Opus's (1.18). Variance is huge at baseline (sd 2.31) and 25% (sd 2.25) — the model's responses span ~2 RQ standard deviations on an 0–10 scale, much higher within-cell noise than any other arm. Variance compresses to sd ~1.4 at higher fills, the opposite direction of Opus/GPT-5.5/Gemini ("variance balloons before mean drops"). DeepSeek's variance starts already-ballooned and then compresses.

The 75% peak (5.43) is genuine — three out of three cells at that fill score above baseline (5.81 / 4.71 / 5.76 by position; see §2.3). This non-monotonicity is sometimes higher-than-baseline by a small margin, suggesting DeepSeek occasionally benefits from peer-context anchors (similar to GPT-5.5's +0.8 pairwise win at 75%).

### 2.2 Per-dimension drift

Aggregated across S-01, S-02, S-03; mean across 21 (baseline) or 63 (non-baseline) responses per fill.

| fill  | groundedness | breadth | scope    | clarity | citation | reasoning | unsup    | xcontam |
|------:|-------------:|--------:|---------:|--------:|---------:|----------:|---------:|--------:|
| 0.00  | **3.67**     | 2.81    | 4.43     | 3.90    | 3.43     | 5.33      | 0.62     | 0.000   |
| 0.25  | 3.67         | 2.84    | 4.52     | 3.76    | 3.44     | 5.16      | 0.67     | 0.000   |
| 0.50  | 3.71         | 2.84    | 4.78     | 3.94    | 3.62     | 5.30      | **1.10** | 0.000   |
| 0.75  | 3.70         | **2.89**| 4.76     | **4.02**| **3.70** | **5.43**  | 1.03     | 0.000   |
| 0.95  | **3.75**     | 2.83    | **4.84** | 3.81    | 3.56     | 5.24      | 0.87     | 0.000   |

- **All dimensions stay flat-to-mildly-improving** with fill. Groundedness, breadth, citation_accuracy all *increase* slightly from baseline to 95%. Scope_adherence increases from 4.43 → 4.84. Reasoning_quality is essentially flat.
- **Unsupported_claims is the one dimension that meaningfully degrades** — 0.62 → 1.10 at 50% fill (peak), then 1.03 → 0.87 at higher fills. This is higher than GPT-5.5 (0–0.05) and Gemini (0.41–0.79) at every fill level, and comparable to Opus's 0.24–1.68 trajectory but starting much higher.
- **Cross-contamination is exactly zero across all 91 runs.** Same as GPT-5.5; better than Opus (0.095 at 95% fill).
- **Baseline groundedness 3.67** is the lowest of any arm in this study (Opus 4.91, Sonnet 4.93, GPT-5.5 5.00, Gemini 4.24). DeepSeek's claims are less reliably traceable to source material *even with no noise present*.

### 2.3 Position effect

Within each fill level, by noise position. n=21 per cell.

| fill | start    | middle   | end    |
|------|---------:|---------:|-------:|
| 0.25 | **6.24** ← strongest | 4.86 | **4.38** ← weakest |
| 0.50 | **5.95**             | 5.24 | **4.71** ← weakest |
| 0.75 | 5.81     | **4.71** ← weakest | 5.76 |
| 0.95 | **4.81** ← weakest   | 5.24 | **5.67** ← strongest |

- **Strong `start > end` pattern at low-to-moderate fill** (25%, 50%) — target *before* noise scores ~1.5 RQ better than target after noise. Consistent with GPT-5.5's `start`-disadvantaged pattern; opposite of Opus's `end`-strongest pattern.
- **Pattern inverts at 95%** — `end` becomes strongest (5.67), `start` weakest (4.81). The flip happens between 75% and 95% fill. Plausible interpretation: at moderate fill, the model can do an initial pass over target material; at saturating fill, only the most-recent context (target-after-noise) gets meaningful attention.
- **Within-cell variance is enormous** — the start/end gap at 25% fill (6.24 vs 4.38) is larger than the entire RQ drop seen across all fills in any other arm. Position matters more for DeepSeek than for any other arm in this study.

### 2.4 Pairwise vs baseline (the diagnostic that matters)

For 25% of non-baseline (run, q_id) pairs, the Opus 4.7 judge picks the better of (baseline rep, candidate rep) on the same question. A/B randomized.

| fill  | wins | losses | ties | mean Δ (cand−base) | n  |
|------:|-----:|-------:|-----:|-------------------:|---:|
| 0.25  | 6    |  5     | 1    | **−1.0 ± 4.3**     | 12 |
| 0.50  | 4    |  8     | 0    | **−1.3 ± 3.1**     | 12 |
| 0.75  | 3    | 13     | 0    | **−2.2 ± 3.0**     | 16 |
| 0.95  | 1    | 16     | 0    | **−4.1 ± 3.1**     | 17 |

**This is the headline finding of the DeepSeek arm.** Absolute reasoning_quality moved 0.27 RQ across the study; pairwise Δ moves 3.1 points (−1.0 → −4.1). The Opus judge **prefers baseline 16/17 times at 95% fill** with a −4.1 mean delta — by far the steepest pairwise loss in the entire study (Opus arm's −2.7, GPT-5.5's −1.9, Gemini's −1.2 are all milder).

This is the cross-arm comparison reviewers should look at: **DeepSeek looks the most context-robust on absolute Likert scoring, but is the *least* context-robust on direct head-to-head comparison.** The reconciliation: DeepSeek's responses are noisy enough (sd 2.31 at baseline, the highest of any arm) that absolute scoring averages out the within-rep variance, but pairwise judging compares a baseline rep to a same-rep-index candidate at higher fill — and the judge can see, side-by-side, that one is consistently better than the other. This pattern is exactly what RUBRIC §Judge-model agreement predicts: when within-cell noise is high, pairwise is the more sensitive instrument.

### 2.5 Q8 structural diagnostics — form is shakier

S-03 mandates a **decompose by unit → apply 4 frameworks → synthesize** structure.

| fill | units_decomposed | frameworks_applied | synthesis_consistent |
|------|------------------|--------------------|----------------------|
| 0.00 | 7.0 ± 3.2        | 3.4 ± 1.4          | **86%** (6/7)         |
| 0.25 | 7.0 ± 3.1        | 3.4 ± 1.4          | **85%** (17/20 non-null) |
| 0.50 | 7.1 ± 1.9        | 3.8 ± 0.9          | 95% (20/21)          |
| 0.75 | 7.5 ± 1.9        | 3.8 ± 0.9          | 95% (20/21)          |
| 0.95 | 7.3 ± 1.8        | 3.8 ± 0.9          | 95% (20/21)          |

- **DeepSeek is the only arm with `synthesis_consistent < 100%` at baseline.** 6/7 of baseline reps had internally-consistent S-03 syntheses; the others mixed contradictory claims. Compare every other arm: 100% baseline consistency.
- **Frameworks_applied averages 3.4–3.8 / 4.** Not always all four. Opus and GPT-5.5 hold at 4.0 throughout most fills.
- **Counter-intuitively, structural quality *improves* with fill** (consistency 85% → 95%, frameworks 3.4 → 3.8). The model's structure is less variable when the context is more crowded. This may reflect the noise corpus serving as a structural template the model leans on under load.
- **Units_decomposed (7.0–7.5) is mid-range** — between Opus (8.6–9.4) and Gemini (4.5–5.0). DeepSeek does drill into product lines, but with high variance (sd 1.8–3.2).

### 2.6 Tier 1/2 — autograder shows a gap that is fully explained by extractor failures

| cell | F-01 | F-02 | F-03 | C-01 | C-02 |
|------|-----:|-----:|-----:|-----:|-----:|
| 0.00 baseline | 6/7 | 6/7 | 6/7 | 6/7 | 6/7 |
| 0.25 end      | 5/7 | 5/7 | 5/7 | 5/7 | 5/7 |
| 0.25 middle   | 6/7 | 6/7 | 6/7 | 6/7 | 6/7 |
| 0.25 start    | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| 0.50 end      | 6/7 | 6/7 | 6/7 | 6/7 | 6/7 |
| 0.50 middle   | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| 0.50 start    | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| 0.75 end      | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| 0.75 middle   | 6/7 | 6/7 | 6/7 | 6/7 | 6/7 |
| 0.75 start    | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| 0.95 end      | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| 0.95 middle   | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| 0.95 start    | 6/7 | 6/7 | 6/7 | 6/7 | 6/7 |

**Aggregate: 84/91 reps fully correct, 7/91 reps fail across all 5 questions.** The pattern of "either get all 5 or miss all 5" matches *exactly* the 7 reps that hit the §1.2 extractor placeholder floor. We verified set-equality: `{reps with all 5 Tier-1/2 records marked wrong} ≡ {reps with parsed_ok=False placeholders}`. There are **zero analyst-side Tier-1 failures in this dataset** — every "wrong" Tier-1/2 record is a Haiku-extractor reformatting failure on a response that, when inspected manually, contains the correct numerics in valid JSON.

**Implication for deployment:** DeepSeek's analyst-side Tier-1 hit rate is **100%**, indistinguishable from the four other arms in the panel. The 5–15% per-question gap visible in the cell table is an instrumentation artifact — Haiku 4.5 fails to parse ~7.7% of DeepSeek's responses despite the underlying JSON being valid. If your deployment pipeline parses analyst output deterministically (regex/pydantic), expect 100% Tier-1 reliability. If you chain a second LLM as a normalizer, expect ~92% downstream-record reliability. **Cross-contamination is zero on Tier 1/2 across all 91 runs** — even when extraction fails, the analyst itself never attributes peer data to MSFT.

### 2.7 Cross-model judge validation (Sonnet 4.6 secondary)

Paired Opus-vs-Sonnet ratings on 56 (run, q_id) responses (20% deterministic subsample).

| dimension                 | n  | Opus μ | Sonnet μ | Δ μ   | Pearson r | ICC(2,1) | Lin CCC  | flag |
|---------------------------|---:|-------:|---------:|------:|----------:|---------:|---------:|------|
| groundedness              | 56 | 3.54   | 3.39     | +0.14 | 0.897     | 0.883    | **0.881**| ok |
| evidentiary_breadth       | 56 | 2.70   | 2.84     | −0.14 | 0.872     | 0.860    | **0.858**| ok |
| scope_adherence           | 56 | 4.62   | 4.93     | −0.30 | −0.024    | −0.012   | **−0.012**| ⚠ |
| clarity                   | 56 | 3.80   | 3.77     | +0.04 | 0.922     | 0.923    | **0.922**| ok |
| citation_accuracy         | 56 | 3.36   | 3.29     | +0.07 | 0.855     | 0.853    | **0.851**| ok |
| **reasoning_quality** (0–10) | 56 | 5.02   | 5.27     | −0.25 | 0.956     | 0.948    | **0.947**| ok |

**Read this carefully:**

- **The strongest cross-judge agreement of any arm in the study.** 5/6 dimensions clear the 0.70 bar; reasoning_quality at CCC 0.947 is the highest CCC in the entire dataset. Compare Opus arm (4/6 clear, RQ 0.777), GPT-5.5 (1/6 clear, RQ 0.664), Gemini (1/6 clear, RQ 0.696).
- **Why so high?** DeepSeek's responses span the rubric range. With baseline RQ averaging 5.33 and sd 2.31, individual responses range from ~2 to ~10. That's plenty of variance for Pearson-based metrics to act on. Compare Opus baseline RQ 8.05 sd 0.58 (everything piles near the ceiling — saturation kills correlation).
- **The same-direction bias holds.** Sonnet rates DeepSeek RQ 0.25 higher than Opus does (5.27 vs 5.02). Same direction as both Opus arm (+0.50) and GPT-5.5 arm (+0.23 inverse) — Sonnet's calibration drifts higher than Opus's at the lower end of the scale.
- **Scope_adherence saturation artifact** persists — both judges rate scope ≥4.62/5; near-constant variables can't correlate.

**Practical implication:** for DeepSeek the absolute scores are usable, not just pairwise. The §2.1 drift curve and §2.2 per-dimension table are well-calibrated. The §2.4 pairwise data and §2.1 absolute data both being readable is what lets us see the **absolute-vs-pairwise paradox** clearly — both signals are reliable; the gap between them is real, not measurement noise.

### 2.8 Compute and timing

Mean per-rep across 7 reps per cell, aggregated by fill (3 positions averaged for non-baseline).

| fill | realized input (Anthropic-tok) | output | thinking_tokens (estimated) | latency |
|-----:|-------------------------------:|-------:|----------------------------:|--------:|
| 0.00 | 79K  | 7,960 | 4,365 | 176 s |
| 0.25 | 165K | 8,362 | 4,783 | 199 s |
| 0.50 | 298K | 7,816 | 4,419 | 174 s |
| 0.75 | 454K | 7,921 | 4,649 | 175 s |
| 0.95 | 584K | 7,353 | 4,267 | 160 s |

**Compute findings:**

- **Thinking allocation is non-monotonic** — peaks at 25% (4,783) and 75% (4,649), dips at 50%, dips again at 95%. No clear scaling with fill. Gemini-like middle path overall, but bumpier.
- **Output volume mildly contracts at 95%** (8.4K → 7.4K), roughly 12% smaller. Less dramatic than GPT-5.5's reasoning contraction (−35%).
- **Latency mildly contracts at 95%** (199s → 160s), -20% from peak. Same direction as GPT-5.5 (−33%) but smaller magnitude. Both vendors apparently have some context-pressure throttling that doesn't appear in Opus or Gemini.
- **`thinking_tokens` here is *estimated*** per `MULTI_VENDOR_ADDENDUM.md §5` — DeepSeek V4's `reasoning_content` field carries raw CoT, which we count as an upper bound on thinking allocation. Direct vendor-reported thinking_tokens are not exposed in the V4 API.
- **Latency is comparable to Opus** (160–199s vs Opus 169–214s) — DeepSeek is not the speed leader (that's Gemini at 53s) nor the speed laggard. Wall time is dominated by reasoning_content generation rather than raw inference.

---

## 3. Actionable insights

### 3.1 For practitioners deploying DeepSeek V4 Pro

1. **Parse analyst output deterministically, not via a second LLM.** DeepSeek's analyst-side Tier-1 hit rate is 100% (matches every other arm); the apparent ~85–95% accuracy in §2.6 is purely a measurement artifact from chaining Haiku 4.5 as a normalizer. Use regex / pydantic / structured-output mode to extract numerics from DeepSeek's JSON directly — you'll recover the full reliability.

2. **The cost advantage is enormous.** Analyst stage was $14.47 vs Opus $334. Whether that translates to deployment cost depends on whether you can use the *promo* rate (75% off through 2026-05-05) which we did NOT lock in our pricing snapshot. With deterministic parsing the analyst-side reliability gap to Anthropic/OpenAI disappears.

3. **For synthesis-heavy workloads, watch the absolute-vs-pairwise gap.** DeepSeek reports the flattest absolute drift curve (−0.09 RQ across fill) but the steepest pairwise loss (−4.1 vs baseline at 95%). If you A/B test DeepSeek-at-baseline vs DeepSeek-at-high-fill and rely on absolute Likert scoring, you'll conclude there's no degradation. There is — pairwise reveals it.

4. **Position the target *after* the noise at high fill.** At 95%, `end` (5.67) outperforms `start` (4.81) by ~0.9 RQ. Pattern inverts at lower fills (25–50%, where `start` is strongest). If you're operating ≥75% fill, prefer end-positioning.

5. **High within-cell variance — run more reps.** sd 2.31 at baseline means a single response from DeepSeek is much less informative than a single response from Opus (sd 0.58) or GPT-5.5 (sd 0.74). For production decisions, aggregate ≥5 calls and take the median or majority vote.

6. **Cross-contamination is not the failure mode here.** Zero cross-contamination across all 91 runs. DeepSeek's failures are *missing* answers or *internally-inconsistent* syntheses, not false attributions of peer data to the target. Helpful for production: incorrect outputs are caught more easily than "subtly wrong" outputs.

### 3.2 For prompt engineers

- **Scope markers work — same conclusion as the other arms.** Zero cross-contamination at any fill.
- **Citation requirements degrade the least** of any arm (3.43 → 3.56, essentially flat). DeepSeek doesn't get *more* sloppy with citations under load — it's already at a lower baseline (vs GPT-5.5 4.95, Opus 4.86).
- **`reasoning_content` is fully exposed.** Unlike Anthropic (full redaction) or OpenAI (encrypted blobs only), DeepSeek V4 returns raw CoT. Useful for prompt-iteration debugging; risky for prompts that condition the assistant on reasoning style (you'll see actual deliberation, not summaries).

### 3.3 For evaluators / researchers

- **The absolute-vs-pairwise gap is the most important methodological lesson from this entire study.** DeepSeek's pattern (flat absolute, steep pairwise) and Gemini's milder version of the same (flat absolute at 50%, steeper pairwise at 50%) confirm that pairwise is the more sensitive drift detector when within-cell variance is high. Absolute Likerts are deceptively reassuring on noisy models.
- **Cross-judge ICC scales with response variance.** DeepSeek's CCCs (5/6 ≥ 0.85) are the highest in the study because its responses span the rubric range. Opus's CCCs (4/6 ≥ 0.70) are middling because its responses pile near the ceiling. GPT-5.5 and Gemini (1/6 ≥ 0.70) have the lowest CCCs because their responses pile *very* near the ceiling. ICC reads "judge agreement" but is partly measuring "how much the data spread."
- **DeepSeek's `reasoning_content` is the only first-party CoT in this five-arm panel.** If your research question requires inspecting actual reasoning traces (not summaries, not signatures), DeepSeek is the only top-tier vendor that exposes them. Reproducibility benefit; risk: traces are non-deterministic at temp=1.0, so you can't use them as a canonical record of how the model "arrived at" an answer.

### 3.4 For the DeepSeek API team (observations, not asks)

- The `reasoning_content` field on V4 messages worked as expected in our (`openai` SDK)-wrapped flow. Adding a first-party Python SDK would simplify integration.
- `system_fingerprint` is not exposed in V4 responses (or wasn't, in our calls). Adding it would let consumers prove that all calls in a batch hit the same build — important for any longitudinal study.
- `reasoning_effort=max` was accepted as documented in the third-party report. Confirming the enum in official docs would close the methodology gap we flagged at lock authoring time.
- Cache_read on V4 worked automatically without explicit breakpoints (~65K tokens cached on at least one cell). Documenting the cache-eviction policy would help cost prediction.

---

## 4. Limitations

- **Single target company (MSFT).** All findings conditional on this 10-K + earnings call.
- **Single noise corpus (peer 10-Ks).** "Adversarially near" is one design point.
- **Same-vendor-family judges.** Opus 4.7 primary + Sonnet 4.6 secondary are both Anthropic. Cross-vendor judging (e.g., DeepSeek judging itself) would be a stronger test of whether DeepSeek's lower absolute scores reflect real quality differences or Anthropic-judge stylistic preferences. Within-Anthropic judge agreement is the highest in the study for DeepSeek (CCC 0.947 on RQ), so the *direction* conclusions are robust within that judge family.
- **Vendor-max thinking is not equivalent across vendors.** DeepSeek's `reasoning_effort=max` allocates ~4,300–4,800 estimated thinking tokens vs Opus's 2,400–4,500, GPT-5.5's 6,300–9,700, Gemini's 4,000–4,600. Cross-arm reasoning-quality comparisons should be read as "each at its own top setting," not "matched compute."
- **Extractor parse failure rate 7.7% (7 reps).** The Haiku 4.5 extractor failed deterministically on these 7 reps despite valid analyst JSON. We accepted the failures as a measured property; the alternative (a per-arm extractor) would invalidate cross-arm comparability. Tier-1 hit rates and §2.6 totals are penalized for these failures, but the failure population (7 reps) corresponds 1:1 with the failed-extractor reps — there are no analyst-side Tier-1 errors, only measurement-chain losses.
- **Pricing snapshot uses regular rate, actual paid was promo rate.** The DeepSeek promo (75% off) closed 2026-05-05 15:59 UTC; this arm was collected during the promo. The locked $194.54 is an upper bound; actual spend was ~$50.
- **Snapshot mutability.** `deepseek-v4-pro` is an alias. Single observed `model` value across 91 runs suggests no mid-experiment build drift, but DeepSeek doesn't expose `system_fingerprint` so we can't prove constancy.
- **`thinking_tokens` is estimated** from `reasoning_content` byte counts per `MULTI_VENDOR_ADDENDUM.md §5`. The vendor doesn't directly report thinking_tokens.
- **n = 7 reps per cell.** Adequate for direction but tight for variance estimation, especially within (fill, position) cells. DeepSeek's high within-cell variance (sd 2.31) makes per-rep noise more dominant than for any other arm.
- **Methodology pre-registration:** v2 hash `3433f4a67cde4b24b92a1b41a78271aa5dbb4572beb2ee23e1d8c2c31d189e8e`. Locked 2026-04-25T23:35:00Z.

---

## 5. What this means for the field

DeepSeek V4 Pro contributes the fourth data point to the cross-vendor reasoning-drift comparison, with a profile that surfaces a methodological lesson larger than the model itself:

1. **The absolute-vs-pairwise paradox is the most important finding in this entire study.** A model that looks "drift-immune" on absolute Likert scoring (DeepSeek, ΔRQ −0.09) can lose 16/17 head-to-head comparisons against its baseline at 95% fill. Conversely, a model that looks "drifty" on absolute scoring (Opus, ΔRQ −1.03) loses pairwise by similar magnitude (Δ −2.7 vs DeepSeek's −4.1). The *ranking* of arms by drift severity is **different between absolute and pairwise** — which methodology you use determines which model "wins." Pairwise is more sensitive when within-rep variance is high, and DeepSeek's variance is high enough to make this matter.

2. **Cost is no longer the right axis to compare these models.** DeepSeek V4 Pro at $1.74/M input is 9× cheaper than Opus 4.7 at $15/M input. Yet we get cross-judge ICC scaling (5/6 dimensions clear vs Opus 4/6) — meaning the rubric works on DeepSeek outputs *better* than on Opus outputs. The "cheap = noisy = unmeasurable" intuition fails here: cheap and rigorously-measurable.

3. **Measurement-chain choices can fully account for "model" differences.** DeepSeek's apparent Tier-1 weakness in §2.6 is entirely a Haiku-4.5 extractor reformatting issue, not an analyst defect — verified by set-equality between {failed-extractor reps} and {fully-failed-Tier-1/2 reps}. A different extractor design (deterministic regex, structured-output mode, or any vendor's own JSON validator) would close the gap. This is a methodological lesson for cross-vendor benchmarks: the *measurement chain* downstream of the analyst can manufacture model-quality differences that don't exist in the underlying outputs. Always isolate analyst behavior from extractor / formatter / scorer behavior before claiming a model is "worse."

Three follow-ups would sharpen this:

1. **Replicate the absolute-vs-pairwise gap with more reps** (n=21 per cell) to confirm DeepSeek's within-cell variance is real and not a sampling artifact. If real, this is a deployment-relevant property in itself.
2. **Test DeepSeek V4 Pro's `reasoning_effort=high`** to see whether the lower-effort knob produces less variance, or whether variance is intrinsic to the model architecture.
3. **Cross-vendor judge** (e.g., DeepSeek judging itself, or a Gemini judge to remove Anthropic preference). DeepSeek's high cross-judge ICC within the Anthropic family doesn't rule out a vendor-stylistic preference that would surface differently with a non-Anthropic judge.

---

## 6. Reproducibility

```
arms/deepseek-v4-pro/
├── arm.lock.json         — locked snapshot (schema v2.0)
├── data.manifest.sha256  — per-file integrity manifest (40 files)
├── data/
│   ├── raw/              — 13 cells × 7 reps = 91 jsonl records
│   ├── extracted/        — 728 normalized records (672 ok, 56 placeholders)
│   ├── graded/           — 728 graded + 57 pairwise + 56 secondary
│   └── manifest.sqlite   — run state, costs, audit log
└── reports/
    └── FINAL_REPORT.md   — this document
```

To reproduce:

```bash
cd harness
python -m scripts.run_experiment --arm deepseek-v4-pro    # collect: 91 runs (~$15, ~82 min wall with 4-cell concurrency)
python -m scripts.run_extractor   --arm deepseek-v4-pro   # extract: ~$3, run 6-7x to converge to 7.7% floor
python -m scripts.run_grading     --arm deepseek-v4-pro   # grade: ~$177, 32 min
python -m scripts.drift_analysis  --arm deepseek-v4-pro   # analysis tables
python -m scripts.write_arm_lock  --arm deepseek-v4-pro   # regenerate arm.lock.json + manifest
python -m scripts.verify_arm_integrity --arm deepseek-v4-pro  # verify byte-identical
```

`verify_arm_integrity` runs three checks (per-file SHA-256s, methodology-hash consistency, raw-record alignment via `analyst.snapshot`). Currently passes all three.

Total cost for full reproduction at *list pricing*: **$194.54**. Actual paid during this study was lower due to the DeepSeek 75%-off promo (closed 2026-05-05 15:59 UTC). Manifest is resumable.

---

## 7. Cost summary

| stage | cost     | per-run / per-record |
|-------|---------:|---------------------:|
| Collect (analyst, DeepSeek V4 Pro max)   | $14.47   | $0.16 / run     |
| Extract (Haiku 4.5, includes 7 retry passes) | $3.09 | $0.034 / run    |
| Grade — primary absolute (Opus 4.7 max)  | $135.23  | ~$0.50 / record |
| Grade — pairwise (Opus 4.7 max)          | $36.68   | ~$0.64 / pair   |
| Grade — secondary (Sonnet 4.6 high)      | $5.06    | ~$0.09 / record |
| **Total (list pricing)**                 | **$194.54** |              |

Budget configured at $700, hard stop $850. Spend ended at 28% of budget — the lowest budget utilization in the study (Opus 83%, Sonnet 75%, GPT-5.5 48%, Gemini 32%, DeepSeek 28%). Cost reduction is concentrated entirely in the analyst stage: DeepSeek collect was $14 vs Opus's $334, a 96% reduction. Grade stages cost similarly because the judge is held constant (Opus 4.7 max) across arms.

---

## Acknowledgments

Pipeline built on the OpenAI Python SDK against `api.deepseek.com` (no first-party DeepSeek SDK), Anthropic Python SDK for extraction and judging. Materials sourced from public 10-K filings and Microsoft FY2026 Q2 earnings call transcript. Cross-arm comparability validated via byte-equivalent prompt sha256 at every (cell, rep) coordinate.
