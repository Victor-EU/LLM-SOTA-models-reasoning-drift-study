# Reasoning drift in Gemini 3.1 Pro under context-window pressure
**Final report — 2026-04-26**

A 91-run controlled experiment on Google's Gemini 3.1 Pro Preview (1,048,576-token context, `thinking_level=HIGH` — vendor maximum) measuring how reasoning quality degrades as the context window fills with adjacent-but-irrelevant material.

This is the **third arm** of the Opus 4.7 Reasoning Drift Study and the second non-Anthropic arm under v2 methodology (`MULTI_VENDOR_ADDENDUM.md`). Materials, design grid, prompts, extractor, judge, and seeds are byte-equivalent to the Opus 4.7, Sonnet 4.6 (v1), and GPT-5.5 (v2) arms — only the analyst model varies. The cross-arm comparability proof is in `cross_arm/COMPARATIVE_REPORT.md` (5 arms, integrity-gated).

The task domain is **financial analysis** — a deliberately blended workload of factual retrieval, numeric calculation, evidence-grounded reasoning, and forward-looking thesis construction — run over Microsoft's FY2025 disclosures with adversarially-near big-tech peer 10-Ks (AAPL, GOOGL, AMZN, META, NVDA, ORCL, CRM) as the noise corpus.

Total spend: **$221.00** (62% cheaper than Opus 4.7's $582.33; cheapest non-DeepSeek fully-graded arm). Total runs: **91/91 successful** (zero exclusions, zero failures). Wall time end-to-end: **~1.2 hours** (collect 28 min wall with 4-cell concurrency, 56s avg latency per call; extract ~6 min; grade ~37 min). **Gemini's per-call latency was 3× faster than the OpenAI/DeepSeek/Opus arms (each ~142–202s avg) and ~15× faster than Sonnet 4.6 (~822s avg).**

---

## TL;DR — three converging findings

1. **Factual lookup is robust.** Tier-1 numeric questions hit **100% accuracy in every cell** from 13% realized fill to 92% realized fill. Cross-contamination is essentially zero (0.000 at all fills except 0.016 at 75% — a single instance across 91 runs). Same factual-robustness story as the Anthropic and OpenAI arms.

2. **Synthesis quality drift is the flattest of any arm in the study.** Tier-3 reasoning quality moves **5.86 → 5.56** (−5.1%, Δ = −0.30) — half the absolute drop of GPT-5.5 (−0.78) and a third of Opus 4.7 (−1.03). Gemini at high context fill is barely distinguishable from Gemini at baseline.

3. **But Gemini starts and stays a full point below the Anthropic/OpenAI arms.** Baseline reasoning_quality is 5.86 vs Opus 8.05 / Sonnet 7.43 / GPT-5.5 7.05. The drift gap is small *because the ceiling is low*. This is **not** the same trade as GPT-5.5 ("fewer-but-correct") — Gemini's groundedness (4.10 → 4.13) and citation_accuracy (3.65–4.00) sit notably below the Anthropic/OpenAI distributions, and unsupported_claims is the highest of the v2 arms (0.41–0.79 / response). The model holds steady under noise but holds steady at a meaningfully weaker baseline.

If you ship Gemini 3.1 Pro to users today: **(a)** trust factual extraction at any fill, same as the other top-tier models; **(b)** it is **2–3× faster wall-time** than any other top-tier arm in this study, which may dominate deployment economics; **(c)** for evidence-heavy synthesis where citation depth and groundedness matter, the absolute quality gap to Opus/GPT-5.5 should be weighed against the speed/cost advantage.

---

## 1. Methodology

Methodology is identical to the Opus 4.7 arm and inherited by reference. See `arms/opus-4-7/reports/FINAL_REPORT.md §1` and project-root `DESIGN.md`, `PROMPTS.md`, `RUBRIC.md`, `MULTI_VENDOR_ADDENDUM.md`. Only this arm's analyst differs.

### 1.1 Models

- **Analyst** — `gemini-3-pro-preview` requested; server-resolved to `gemini-3.1-pro-preview` (recorded in `arm.lock.json::analyst.snapshot_observed_aliases`). `thinking_level=HIGH` — vendor maximum, top of {MINIMAL, LOW, MEDIUM, HIGH}. The legacy `thinking_budget` integer was deprecated in Gemini 3. Encrypted thought signatures are exposed per part when `include_thoughts=true`; raw chain-of-thought is **not** exposed (analogous to Anthropic Opus redaction). `max_output_tokens=64000`, `temperature=1.0`. Wrapped via `google.genai` against the Gemini API.
- **Extractor** — `claude-haiku-4-5-20251001`, no thinking, max_output_tokens=16K, temperature=1.0. **Held constant across arms.**
- **Primary judge** — `claude-opus-4-7`, adaptive thinking `effort=max`, max_output_tokens=16K. **Held constant across arms.** Judge runs against cached fill=0 target materials — no within-judge drift confound.
- **Secondary judge** — `claude-sonnet-4-6`, `effort=high`, on a 20% subsample of (run, q_id) pairs for cross-model inter-rater reliability.

### 1.2 v2-specific notes

- **Snapshot alias drift, observed.** Requested `gemini-3-pro-preview` was server-resolved to `gemini-3.1-pro-preview` on every one of the 91 calls. The arm.lock schema captures both: `analyst.snapshot` (what we requested) and `analyst.snapshot_observed_aliases` (what the API returned). `verify_arm_integrity.py` accepts records matching either, so the integrity gate passes. A single observed alias means **no mid-experiment build drift**.
- **Tokenizer asymmetry.** Token budget convergence uses Anthropic's `count_tokens` (the judge-primary tokenizer fallback). Gemini's actual realized input is ~69% of the Anthropic-counted target. At 95% fill, Anthropic counts the prompt at ~925K but Gemini's API metered ~640K — a ~31% reduction. Cross-arm fill values are byte-identical at every (cell, rep) coordinate (verified via prompt sha256).
- **Pricing tier.** Gemini 3 Pro has tiered pricing: $2/$12 per M tokens below 200K input, $4/$18 above. 12/13 cells exceed 200K (Anthropic-counted). The locked pricing snapshot uses the high tier ($4/$18). Cache pricing is documented as zero in the dev guide as of lock date.
- **Output cap.** Gemini 3's `max_output_tokens` is documented up to 65,536. We use 64K headroom-safe. No truncation observed across 91 runs.

---

## 2. Results

### 2.1 Headline drift curve

Mean reasoning quality (0–10), aggregated across all three Tier-3 questions × all positions × 7 reps per cell.

| realized fill | n  | mean reasoning_quality | sd   | Δ vs baseline |
|--------------:|---:|-----------------------:|-----:|--------------:|
| 13% (baseline)| 21 | **5.86**               | 0.79 | —             |
| 24%           | 63 | 5.68                   | 0.78 | −0.18         |
| 47%           | 63 | 5.59                   | 0.93 | −0.27         |
| 72%           | 63 | **5.51** ← bottom       | 1.38 | −0.35         |
| 92%           | 63 | 5.56                   | 0.86 | −0.30         |

The drift curve is **nearly flat**: a 0.35-point spread between the highest (5.86 at baseline) and lowest (5.51 at 75%) cells. Compare GPT-5.5 (0.78 spread), Opus 4.7 (1.18 spread), Sonnet 4.6 (~0.81 spread per the comparative report).

Variance also stays remarkably tight — the 75% fill cell jumps to sd=1.38 (consistent with the cross-arm "variance balloons before mean drops" precursor signal seen in Opus and GPT-5.5), but every other cell holds sd ≤ 0.93. **Gemini at HIGH thinking is the most consistent of the five arms across context-fill conditions.**

### 2.2 Per-dimension drift

Aggregated across S-01, S-02, S-03; mean across 21 (baseline) or 63 (non-baseline) responses per fill.

| fill  | groundedness | breadth | scope | clarity | citation | reasoning | unsup    | xcontam  |
|------:|-------------:|--------:|------:|--------:|---------:|----------:|---------:|---------:|
| 0.00  | **4.24**     | 3.19    | 4.90  | 4.38    | **4.00** | 5.86      | 0.57     | 0.000    |
| 0.25  | 4.29         | 3.10    | 4.95  | 4.19    | 3.90     | 5.68      | 0.41     | 0.000    |
| 0.50  | 4.10         | 3.00    | 4.95  | 4.14    | 3.75     | 5.59      | 0.70     | 0.000    |
| 0.75  | **3.97**     | 3.08    | 4.94  | 4.14    | **3.65** | 5.51      | **0.79** | 0.016    |
| 0.95  | 4.13         | 3.03    | 4.90  | 4.14    | 3.75     | 5.56      | 0.56     | 0.000    |

- **Most-degraded dimensions:** citation_accuracy (−0.35), groundedness (−0.27 to its 75% bottom, recovers slightly), unsupported_claims (+0.22 to its 75% peak, recovers).
- **Most-robust dimensions:** scope_adherence (essentially flat at 4.90–4.95 across all fills), clarity (−0.24, sits at 4.14), evidentiary_breadth (essentially flat at 3.00–3.19).
- **Cross-contamination is non-zero in exactly one cell** (75% fill, 0.016/response = 1 instance across all 63 responses). Compare Opus's 0.095 at 95% fill (∼6 per 63 responses). Gemini almost never confuses peer data with target.
- **Unsupported claims pattern is non-monotonic with a 75% peak** (0.79) and recovery at 95% (0.56). This is the same fill where reasoning_quality bottoms out and variance peaks — the model is most uncertain at moderate-to-high fill, then stabilizes when noise saturates.

### 2.3 Position effect

Within each fill level, by noise position. n=21 per cell.

| fill | start    | middle   | end    |
|------|---------:|---------:|-------:|
| 0.25 | 5.62     | 5.62     | **5.81** ← strongest |
| 0.50 | **5.90** ← strongest | 5.62 | **5.24** ← weakest |
| 0.75 | **5.24** ← weakest   | **6.05** ← strongest | 5.24 |
| 0.95 | 5.62     | **5.67** | 5.38   |

- **No clean position pattern.** Unlike Opus (`end` consistently strongest) or GPT-5.5 (`start` consistently weakest), Gemini's position-best varies cell-by-cell. At 25% `end` wins; at 50% `start`; at 75% `middle`; at 95% `middle` again narrowly. Within-cell spreads are small (~0.4–0.7 RQ).
- **The 75% middle outlier** (6.05 — only cell better than baseline) is the same cell where the across-position mean dipped to 5.51 — meaning starts and ends were notably weak (5.24 each). High variance in this cell is consistent with the §2.1 sd=1.38.
- **At 95% all positions converge** to a tight 5.38–5.67 band — the same saturation pattern seen in the other arms.

### 2.4 Pairwise vs baseline

For 25% of non-baseline (run, q_id) pairs, the Opus 4.7 judge picks the better of (baseline rep, candidate rep) on the same question. A/B randomized.

| fill  | wins | losses | ties | mean Δ (cand−base) | n  |
|------:|-----:|-------:|-----:|-------------------:|---:|
| 0.25  | 7    | 9      | 1    | **−0.5 ± 2.4**     | 17 |
| 0.50  | 3    | 11     | 1    | **−1.7 ± 2.2**     | 15 |
| 0.75  | 6    | 11     | 1    | **−0.9 ± 2.6**     | 18 |
| 0.95  | 5    | 14     | 1    | **−1.2 ± 2.7**     | 20 |

Pairwise loss is **monotonic-ish but shallow**: every fill loses to baseline (max win share is 7/17 at 25%), but never as decisively as Opus (1/18 wins at 75%) or DeepSeek (1/17 wins at 95%). The 50% cell is the unexpected dip (−1.7) — judge consistently prefers baseline, but absolute RQ at 50% (5.59) is barely below 25% (5.68). This is the textbook case where **pairwise is more sensitive than absolute**: the Opus judge can detect a baseline-vs-50%-fill quality difference that doesn't show up clearly in absolute scoring.

### 2.5 Q8 structural diagnostics — form holds, units stay shallow

S-03 mandates a **decompose by unit → apply 4 frameworks → synthesize** structure.

| fill | units_decomposed | frameworks_applied | synthesis_consistent |
|------|------------------|--------------------|----------------------|
| 0.00 | 5.0 ± 1.2        | 4.0 ± 0.0          | 100% (7/7)           |
| 0.25 | 5.0 ± 0.9        | 4.0 ± 0.0          | 100% (21/21)         |
| 0.50 | 4.5 ± 1.3        | 4.0 ± 0.0          | 100% (21/21)         |
| 0.75 | 4.1 ± 1.2        | 3.8 ± 0.9          | 95% (20/21)          |
| 0.95 | 4.5 ± 1.3        | 4.0 ± 0.0          | 100% (21/21)         |

Frameworks are applied robustly (3.8–4.0 / 4 across all fills). **The notable difference from the other arms: Gemini decomposes only ~4.5–5.0 revenue units per response**, vs Opus's 8.6–9.4 and GPT-5.5's 7.2–8.6. The model tends toward higher-level segmentations (e.g., "Productivity & Business Processes / Intelligent Cloud / Personal Computing" — Microsoft's three reportable segments) rather than drilling down to product-line units. This is captured in lower `units_decomposed` and explains some of the gap to Opus/GPT-5.5 absolute scores: less granular evidence engagement, even when the prescribed structure is followed.

### 2.6 Tier 1/2 — no drift detected

| cell type | F-01 (revenue) | F-02 (op income) | F-03 (EPS) | C-01 (tax rate) | C-02 (growth) |
|-----------|---------------:|-----------------:|-----------:|----------------:|--------------:|
| All 13 cells | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |

**100% across the entire grid, identical to Opus 4.7 and GPT-5.5.** Cross-contamination on Tier 1/2: zero across all 91 runs.

### 2.7 Cross-model judge validation (Sonnet 4.6 secondary)

Paired Opus-vs-Sonnet ratings on 56 (run, q_id) responses (20% deterministic subsample).

| dimension                 | n  | Opus μ | Sonnet μ | Δ μ   | Pearson r | ICC(2,1) | Lin CCC  | flag |
|---------------------------|---:|-------:|---------:|------:|----------:|---------:|---------:|------|
| groundedness              | 56 | 3.96   | 3.95     | +0.02 | 0.681     | 0.670    | **0.666**| ⚠ |
| evidentiary_breadth       | 56 | 3.00   | 2.98     | +0.02 | 0.746     | 0.746    | **0.743**| ok |
| scope_adherence           | 56 | 4.89   | 4.98     | −0.09 | −0.032    | −0.017   | **−0.017**| ⚠ |
| clarity                   | 56 | 4.05   | 4.04     | +0.02 | 0.552     | 0.553    | **0.548**| ⚠ |
| citation_accuracy         | 56 | 3.77   | 3.82     | −0.05 | 0.474     | 0.468    | **0.464**| ⚠ |
| **reasoning_quality** (0–10) | 56 | 5.48   | 5.75     | −0.27 | 0.737     | 0.700    | **0.696**| ⚠ |

**Read this carefully:**

- **Only `evidentiary_breadth` clears the 0.70 bar** (CCC 0.743). On every other dimension, fall back to pairwise per RUBRIC §Judge-model agreement.
- **`reasoning_quality` lands at CCC 0.696** — fractionally below threshold. Direction agreement is strong (both judges see baseline > all other cells), but absolute calibration carries noise.
- **`groundedness`** at CCC 0.666 — close-but-no. Two judges with substantively similar ratings (Opus μ 3.96, Sonnet μ 3.95, Δ +0.02) but enough rep-by-rep noise to push correlation below the bar.
- **`scope_adherence`** at CCC −0.017 — the same saturation artifact seen in every arm. Both judges score scope ≥4.89/5; near-constant variables can't correlate.
- **Sonnet rates Gemini RQ ~0.27 higher than Opus does** (5.75 vs 5.48). Same direction as the Opus arm bias (~+0.5 from Opus to Sonnet) but smaller. Anthropic-vs-Anthropic judge bias is a level shift, not a directional disagreement.
- **Compared to GPT-5.5 arm:** GPT-5.5 had only 1/6 dimensions clear; Gemini also has 1/6 clear (`evidentiary_breadth`). Both arms are saturation-limited. The fix is pairwise — which Gemini also fails to win at any fill, in line with absolute scores.

### 2.8 Compute and timing

Mean per-rep across 7 reps per cell, aggregated by fill (3 positions averaged for non-baseline).

| fill | realized input (Anthropic-tok) | output | thinking_tokens | latency |
|-----:|-------------------------------:|-------:|----------------:|--------:|
| 0.00 | 87K  | 6,710 | 4,028 | **53 s** |
| 0.25 | 182K | 6,580 | 3,916 | 51 s |
| 0.50 | 326K | 6,802 | 4,175 | 54 s |
| 0.75 | 497K | 7,299 | **4,421** | 62 s |
| 0.95 | 640K | 7,244 | **4,628** | 57 s |

**Compute findings:**

- **Thinking allocation grows mildly with fill** (4,028 → 4,628, +15%) — between GPT-5.5's contraction (−35%) and Opus's expansion (+87%). Gemini takes the middle path: it does think slightly more under context pressure, but proportionally far less than Opus.
- **Output volume holds nearly constant** (6.6K–7.3K). Gemini doesn't write longer answers under pressure.
- **Latency is the headline number: 51–62 seconds across all fills.** Gemini is **3× faster wall-time** than Opus 4.7 (169–214s), GPT-5.5 (113–168s), and DeepSeek (160–200s), and **~15× faster** than Sonnet 4.6 (747–932s) on identical prompts. This holds at every fill level. Whether that's API-side throughput, hardware, or smaller per-step compute, Gemini 3.1 Pro is in a different latency regime than the other top-tier reasoning models in this study.
- **Sub-linear scaling.** Latency grows from 53s to 57s across an 8× input expansion (87K → 640K) — much flatter than Opus (1.27×) or DeepSeek (~0.9×, actually decreases — see DeepSeek arm report).

---

## 3. Actionable insights

### 3.1 For practitioners deploying Gemini 3.1 Pro

1. **Trust factual extraction at any fill.** Tier-1 was 100% across all 91 runs with zero cross-contamination on factual answers. Same conclusion as Opus and GPT-5.5.

2. **Latency advantage is the single biggest deployment factor.** If you're running this in production, 53s/call vs Opus's 200s/call is a 4× throughput multiplier. For batch jobs over long contexts, this can dominate.

3. **The drift curve is shallow — context fill is not your main quality concern.** RQ moves only 0.35 points across the 13–92% fill range. If your task is well-suited to Gemini's baseline quality, scaling context up doesn't hurt much.

4. **The baseline ceiling matters more than the drift.** Gemini's baseline RQ is 5.86 vs Opus 8.05. If your task needs depth, the absolute gap doesn't close at any fill level; Gemini under no noise is still meaningfully below Opus under heavy noise (5.86 vs 7.02). Choose the arm whose baseline matches your task.

5. **Granularity of evidence engagement is shallower.** S-03 decompositions averaged 4.5–5.0 units (vs Opus's 8.6–9.4). If your prompt asks for "comprehensive analysis," Gemini may default to top-level segmentations rather than drilling. Explicit instructions like "decompose by product line, not segment" may help.

6. **Variance peaks at 75% fill (sd 1.38).** The model becomes less predictable at moderate-high fill before re-stabilizing at 95%. If you're operating in this range, expect more cross-rep variance.

### 3.2 For prompt engineers

- **Scope markers work — same conclusion as the other arms.** Zero cross-contamination on factual questions and only 1 instance across 91 runs at any fill. The `<<< TARGET MATERIALS >>>` delimiter pattern transfers across vendors.
- **Citation accuracy is the lowest of the v2 arms** (3.65–4.00 vs GPT-5.5's 4.37–4.95). If precise citations matter, prompt explicitly: "Quote the exact phrase you're citing." Gemini complies with structural requirements but doesn't volunteer citation precision.
- **Encrypted thought signatures via `include_thoughts=true`** preserve the reasoning trace without exposing CoT. We didn't use this in scoring, but it's available for observability use cases.

### 3.3 For evaluators / researchers

- **Pairwise vs baseline catches what absolute scoring misses.** Gemini at 50% loses pairwise (−1.7) more decisively than absolute (−0.27 RQ vs baseline). This is the cleanest within-arm drift signal.
- **Saturation artifacts are pervasive across arms.** Five of six dimensions fall below the CCC 0.70 bar for Gemini, four of six for GPT-5.5, two of six for Opus. The pattern correlates with how tightly responses cluster near the rubric ceiling. Don't expect ICC to work on saturated dimensions; report mean differences separately.
- **Gemini's "model_version" field disambiguates alias drift.** We requested `gemini-3-pro-preview`; got `gemini-3.1-pro-preview` consistently. Always log the API-returned version, not just the requested string. Our `arm.lock.json::analyst.snapshot_observed_aliases` is the audit trail; the verify script accepts either.

### 3.4 For the Google API team (observations, not asks)

- Encrypted thought signatures via `include_thoughts=true` are a useful middle ground between full CoT exposure (DeepSeek) and full redaction (OpenAI/Anthropic). The format is consistent and downstream-friendly.
- The `model_version` field on responses correctly resolved our alias request to `gemini-3.1-pro-preview` on every call. Stable behavior; documented behavior worked as advertised.
- Cache pricing not documented in the dev guide as of lock date (2026-04-25). The locked snapshot lists cache_read=0 / cache_write=0 — if cache pricing rolls out and is non-zero, our cost reconstruction will need an addendum.
- The 65,536 max_output_tokens cap accommodates the workload here; we used 64K with no truncation.

---

## 4. Limitations

- **Single target company (MSFT).** All findings conditional on this 10-K + earnings call.
- **Single noise corpus (peer 10-Ks).** "Adversarially near" is one design point.
- **Same-vendor-family judges.** Opus 4.7 primary + Sonnet 4.6 secondary are both Anthropic. Cross-vendor judging (e.g., Gemini judging Gemini, or GPT judging Gemini) would be a stronger test of whether the absolute-score gap to Anthropic models is real or a vendor-stylistic preference. Within-Anthropic judge agreement is preserved (both Opus and Sonnet rank Gemini below Opus and GPT-5.5, with similar magnitudes).
- **Vendor-max thinking is not equivalent across vendors.** Gemini's `thinking_level=HIGH` (top of {MINIMAL, LOW, MEDIUM, HIGH}) is not numerically calibrated to OpenAI's `xhigh` or Anthropic's `effort=max`. Gemini's reasoning_token allocation (4,028–4,628) is roughly comparable to Opus's (2,417–4,524), but lower than GPT-5.5's (6,289–9,669). Cross-arm reasoning-quality comparisons should be read as "each at its own top setting."
- **n = 7 reps per cell.** Adequate for direction but tight for variance estimation, especially within (fill, position) cells.
- **Compressed fill range.** Pool exhaustion means 75% and 95% target fills realized at 72% and 92%. Cross-arm fill values are byte-identical (proven via materials sha256), so this affects all arms equally.
- **Three Tier-3 questions.** Synthesis genres sampled: descriptive (financial health), structural (segment positioning), forward-looking (AI impact). Other synthesis types might drift differently.
- **Extractor parse rate: 100% for Gemini.** Comparable to Opus (98.9%), Sonnet (98.8%), GPT-5.5 (100%); markedly better than DeepSeek (92.3%).
- **Methodology pre-registration:** v2 hash `3433f4a67cde4b24b92a1b41a78271aa5dbb4572beb2ee23e1d8c2c31d189e8e`. Locked 2026-04-25T23:35:00Z.

---

## 5. What this means for the field

Gemini 3.1 Pro contributes a third data point to the cross-vendor reasoning-drift comparison, with a distinct profile:

1. **The drift-vs-ceiling trade-off is real.** Three top-tier reasoning models, three different drift profiles, three different absolute ceilings. Opus 4.7 has the highest ceiling and the steepest drift. GPT-5.5 has a middle ceiling and middle drift. Gemini 3.1 Pro has the lowest ceiling and the flattest drift. If the cross-arm story were "all max-thinking models drift similarly," we'd see a tight band; instead we see vendor-specific signatures.

2. **Latency is a separable axis.** Gemini's 3–4× speed advantage is orthogonal to its quality profile — the model is doing real reasoning (4K+ thinking tokens, 4 frameworks applied at S-03), just *faster*. The trade-off in deployment isn't necessarily depth-vs-speed; it's also vendor-architectural (different inference stacks).

3. **Absolute and pairwise can disagree.** Gemini's pairwise loss at 50% (−1.7) is steeper than its absolute drop (−0.27 RQ). This is the textbook case for pairwise as the cleaner drift signal: relative judgments cancel out the rep-noise that absolute Likerts pick up. It's a lesson for evaluator design — saturated absolute scales hide drift that pairwise reveals.

Three follow-ups would sharpen this:

1. **Test other Gemini 3.1 Pro thinking levels** (LOW, MEDIUM) to see if more thinking would close the absolute-quality gap to Opus/GPT-5.5, or if the gap is architectural rather than budget-bound.
2. **Replicate with non-MSFT targets** to test whether Gemini's lower citation precision generalizes.
3. **Cross-vendor judge** (e.g., Gemini judging itself, or GPT judging Gemini) to disentangle judge-vendor preference from real quality differences. The Anthropic-judge-only design here is one limitation we can't resolve without additional spend.

---

## 6. Reproducibility

```
arms/gemini-3-1-pro/
├── arm.lock.json         — locked snapshot (schema v2.0)
├── data.manifest.sha256  — per-file integrity manifest (40 files)
├── data/
│   ├── raw/              — 13 cells × 7 reps = 91 jsonl records
│   ├── extracted/        — 728 normalized records (100% parsed_ok)
│   ├── graded/           — 728 graded + 70 pairwise + 56 secondary
│   └── manifest.sqlite   — run state, costs, audit log
└── reports/
    └── FINAL_REPORT.md   — this document
```

To reproduce:

```bash
cd harness
python -m scripts.run_experiment --arm gemini-3-1-pro    # collect: 91 runs (~$35, ~28 min wall with 4-cell concurrency)
python -m scripts.run_extractor   --arm gemini-3-1-pro   # extract: ~$1, ~6 min
python -m scripts.run_grading     --arm gemini-3-1-pro   # grade: ~$185, 37 min
python -m scripts.drift_analysis  --arm gemini-3-1-pro   # analysis tables
python -m scripts.write_arm_lock  --arm gemini-3-1-pro   # regenerate arm.lock.json + manifest
python -m scripts.verify_arm_integrity --arm gemini-3-1-pro  # verify byte-identical
```

`verify_arm_integrity` runs three checks (per-file SHA-256s, methodology-hash consistency, raw-record alignment via `analyst.snapshot` or `snapshot_observed_aliases`). Currently passes all three.

Total cost for full reproduction: **$221.00**. Manifest is resumable.

---

## 7. Cost summary

| stage | cost     | per-run / per-record |
|-------|---------:|---------------------:|
| Collect (analyst, Gemini 3.1 Pro HIGH)   | $35.20   | $0.39 / run     |
| Extract (Haiku 4.5)                      | $1.17    | $0.013 / run    |
| Grade — primary absolute (Opus 4.7 max)  | $133.38  | ~$0.49 / record |
| Grade — pairwise (Opus 4.7 max)          | $45.54   | ~$0.65 / pair   |
| Grade — secondary (Sonnet 4.6 high)      | $5.71    | ~$0.10 / record |
| **Total**                                | **$221.00** |              |

Budget configured at $700, hard stop $850. Spend ended at 32% of budget — substantially under (Opus arm 83%, GPT-5.5 arm 48%). The cost reduction is concentrated in the analyst stage: Gemini collect was $35 vs Opus's $334, a 90% reduction. Grade stages cost similarly because the judge is held constant (Opus 4.7 max) across arms.

---

## Acknowledgments

Pipeline built on `google.genai` for the analyst, Anthropic Python SDK for extraction and judging. Materials sourced from public 10-K filings and Microsoft FY2026 Q2 earnings call transcript. Cross-arm comparability validated via byte-equivalent prompt sha256 at every (cell, rep) coordinate.
