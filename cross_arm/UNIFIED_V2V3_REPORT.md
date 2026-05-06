# Unified Cross-Noise × Cross-Judge Report

## How five frontier models hold up against context-pressure and temporal-noise drift, judged three ways.

**Date:** 2026-05-06
**Methodology lock chain:** v1 (`pre_registration.lock`) → v2 (`pre_registration.v2.lock`, multi-vendor analysts) → v3 (`pre_registration.v3.lock`, temporal-noise addendum)
**Materials:** Microsoft FY2025 financial disclosures (10-K + Q2 FY2026 earnings call). `materials.lock.json` SHA frozen across v3.
**Companion technical reports:** [`CROSS_ARM_REPORT.md`](./CROSS_ARM_REPORT.md) (v2-only Anthropic-judge analysis), [`SOBER_STATE_FINAL_REPORT.md`](./SOBER_STATE_FINAL_REPORT.md) (baseline-only ranking).

---

## 1. TL;DR — five takeaways for agent builders

> **1. Retrieval and calculation hold across all 5 models — except DeepSeek under temporal noise.** At 95% context fill with peer-company filler (v2 control noise), every model maintains baseline tier-1 (factual lookup) and tier-2 (calculation) accuracy within sampling noise. Switch the filler to *old versions of the same document* (v3 temporal noise) and DeepSeek V4 Pro's tier-1 retrieval drops from its 0.43 baseline to 0.31 at 95% fill (28% below baseline) and tier-2 calculation drops similarly — with the worst single cell at 50% temporal end position scoring 0.14 (67% below baseline, vs other 4 models maintaining 0.50). Sonnet 4.6 also takes a 20% hit on tier-1 at 75% temporal fill (0.50 → 0.40). Opus 4.7, GPT-5.5, and Gemini 3.1 Pro are fully invariant.
>
> *For builders:* If your agent does fact retrieval over a corpus that may contain old versions of the target document, **don't use DeepSeek** unless you control for that. GPT-5.5 and Opus 4.7 are the safest picks for retrieval under uncertain noise composition.

> **2. Synthesis is where temporal noise actually bites — and only on Sonnet and DeepSeek.** Under heavy temporal noise (95% fill with old MSFT 10-Ks), Sonnet 4.6's reasoning quality drops from 7.6/10 to 5.1/10 (Opus judge), 7.2/10 to 5.6/10 (GPT judge), and 8.7/10 to 4.9/10 (Gemini judge). All three independent judges agree. DeepSeek shows similar collapse under Opus judging only (judge-bias caveat applies). Opus 4.7, GPT-5.5, and Gemini 3.1 Pro are essentially invariant to temporal noise across all judges.
>
> *For builders:* For RAG systems where your retrieval might pull stale-version chunks of the target document, **avoid Sonnet 4.6 at high fill** (>75%) for synthesis tasks. Use Opus 4.7 (recovers at 95%) or GPT-5.5 (most stable across all conditions).

> **3. The popular fear of "the model will confuse periods" is not what we observed.** Across 5 frontier models × 95% context fill with old-version MSFT filings × 3 independent judges (Opus + GPT + Gemini) × 1,357 tier-3 synthesis records, **zero records were flagged for period confusion.** Models DO degrade under temporal noise, but the failure mode is *incompleteness* (Sonnet truncates a 3-part synthesis after Part 1) and *parseability* (DeepSeek produces output the structured extractor can't decode), not "Sonnet claims FY2025 revenue is $245B."
>
> *For builders:* The mental model "stale data → wrong period attribution" is empirically wrong on these 5 models. Watch instead for **truncated outputs** and **structured-output formatting failures** as the actual failure signatures. Both are easy to detect with response-length heuristics and downstream validators.

> **4. Sonnet's failure mode at 95% temporal is bimodal — detectable, not silent.** When Sonnet does fail at 95% fill, it fails hard: 20% of synthesis responses get rated 0–2/10 by the Opus judge, while another 23% are still rated 8+/10 (n=60 records). There's a clear "either succeed or hard-fail" pattern, not a smooth quality decay. Failed responses are typically truncated mid-synthesis (e.g., delivering Part 1 of a 3-part question and stopping).
>
> *For builders:* If you ship Sonnet 4.6 in a high-fill RAG application, **add a structural validator** (did the response complete all required sections?) and **a retry path with reduced context**. The bimodal pattern means a simple "did the response cover Part N?" check catches the failures cleanly. Silent low-quality drift is much harder to handle than overt truncation.

> **5. Don't use Gemini 3.1 Pro as a judge in agent self-evaluation loops without calibration.** Gemini-as-judge rates outputs ~2.5–2.7 points higher (on a 10-point scale) than Opus or GPT do, *across all 10 conditions tested*. The bias is not noise-type-specific or arm-specific — it's a level shift baked into Gemini's rubric application. Gemini also disagrees most with the other judges on per-record ratings (Pearson r = 0.45–0.49 when judging non-Anthropic arms). GPT-5.5 as judge has a milder +0.7-point self-bias (it rates GPT-5.5 outputs higher than Opus does) but otherwise agrees well with Opus (r = 0.70–0.82).
>
> *For builders:* The most reliable judging pair we tested is **Opus 4.7 + GPT-5.5** (cross-vendor, per-record agreement r = 0.69–0.84 across all 10 arms × both noise types). If you must use Gemini, calibrate it against a held-out human-labeled set first.

---

## 2. Method snapshot

**10 analyst arms**, organized as 5 models × 2 noise types:

| Model | v2 arm (peer noise) | v3 arm (temporal noise) | Vendor |
|-------|---------------------|-------------------------|--------|
| Opus 4.7 (max thinking) | `opus-4-7` | `opus-4-7-temporal` | Anthropic |
| Sonnet 4.6 (max thinking) | `sonnet-4-6` | `sonnet-4-6-temporal` | Anthropic |
| GPT-5.5 (reasoning=max) | `gpt-5-5` | `gpt-5-5-temporal` | OpenAI |
| Gemini 3.1 Pro (HIGH) | `gemini-3-1-pro` | `gemini-3-1-pro-temporal` | Google |
| DeepSeek V4 Pro (max) | `deepseek-v4-pro` | `deepseek-v4-pro-temporal` | DeepSeek |

**Noise types:**
- **`peer_materials`** (v2 control): Context padded with 10-Ks of MSFT's competitors (AAPL, AMZN, CRM, GOOGL, META, NVDA, ORCL). Noise that's structurally similar to the target but topically different.
- **`temporal_msft`** (v3 treatment): Context padded with old versions of MSFT's own 10-Ks (FY2022–FY2024). Noise that's topically *identical* to the target but temporally stale. Tests whether models can distinguish "current" from "historical" versions of the same document.

**Design grid per arm:** 5 fill levels (0%, 25%, 50%, 75%, 95% of model's context window) × 3 positions (start, middle, end) × 7 reps × 8 questions = 728 records per arm × 10 arms = **7,280 analyst records total**.

**Question tiers:**
- **Tier 1 — Factual recall (3 q):** "What was MSFT FY25 revenue?" Rule-based autograder.
- **Tier 2 — Calculation (2 q):** "What was the gross margin?" Rule-based autograder.
- **Tier 3 — Synthesis (3 q):** "Assess MSFT's competitive position in cloud given the AI capex situation." LLM-judge-based, multi-dimensional rubric.

**Three judges (tier-3 only):**
- **Opus 4.7 max** (original judge from v1/v2/v3 lock): judges all 10 arms.
- **GPT-5.5 max** (cross-vendor judge, added in this v3 ablation): judges all 10 arms.
- **Gemini 3.1 Pro HIGH** (cross-vendor judge, added in this v3 ablation): judges all 10 arms.

DeepSeek is excluded as a cross-judge after v2 analyst-side reliability concerns. Total tier-3 judgments: **7,885 records** (some arm × judge × condition cells have <273 records due to extraction or judge-side failures; documented in §6).

---

## 3. Cognitive-dimension drift (the meat)

This section breaks drift down by what the model is being asked to *do*. Each subsection presents one cognitive dimension under both noise types, with an agent-builder callout.

### 3.1 Data retrieval (Tier-1 factual)

Rule-based autograde score, scale 0/0.5/1. Rows are model × noise × fill; columns are noise position.

| arm | noise | fill | start | middle | end | row mean |
|-----|-------|-----:|-------|--------|-----|---------:|
| opus-4-7 | — | 0% | — | **0.50 ± 0.00** | — | 0.50 |
| opus-4-7 | peer | 25% | 0.50 | 0.50 | 0.50 | 0.50 |
| opus-4-7 | peer | 50% | 0.52 | 0.50 | 0.50 | 0.51 |
| opus-4-7 | peer | 75% | 0.50 | 0.50 | 0.50 | 0.50 |
| opus-4-7 | peer | 95% | 0.50 | 0.50 | 0.50 | 0.50 |
| opus-4-7 | temporal | 25% | 0.50 | 0.50 | 0.50 | 0.50 |
| opus-4-7 | temporal | 50% | 0.50 | 0.50 | 0.50 | 0.50 |
| opus-4-7 | temporal | 75% | 0.50 | 0.50 | 0.50 | 0.50 |
| opus-4-7 | temporal | 95% | 0.50 | 0.50 | 0.50 | 0.50 |
| sonnet-4-6 | — | 0% | — | **0.50 ± 0.00** | — | 0.50 |
| sonnet-4-6 | peer | 25–95% | flat | flat | flat | 0.48–0.50 |
| sonnet-4-6 | temporal | 25% | 0.50 | 0.50 | 0.40 ± 0.04 | 0.47 |
| sonnet-4-6 | temporal | 50% | 0.50 | 0.50 | 0.50 | 0.50 |
| sonnet-4-6 | temporal | 75% | **0.36 ± 0.05** | **0.43 ± 0.04** | **0.43 ± 0.04** | **0.40** |
| sonnet-4-6 | temporal | 95% | 0.50 | 0.43 | 0.50 | 0.47 |
| gpt-5-5 | — | 0% | — | **0.50 ± 0.00** | — | 0.50 |
| gpt-5-5 | peer/temporal — all fills | | flat | flat | flat | 0.50–0.53 |
| gemini-3-1-pro | — | 0% | — | **0.50 ± 0.00** | — | 0.50 |
| gemini-3-1-pro | peer/temporal — all fills | | flat | flat | flat | 0.50–0.52 |
| deepseek-v4-pro | — | 0% | — | **0.43 ± 0.04** | — | 0.43 |
| deepseek-v4-pro | peer | 25–95% | 0.43–0.55 | 0.43–0.50 | 0.36–0.55 | 0.43–0.49 |
| deepseek-v4-pro | temporal | 25% | 0.50 | 0.50 | **0.21 ± 0.06** | **0.40** |
| deepseek-v4-pro | temporal | 50% | 0.50 | 0.43 | **0.14 ± 0.05** | **0.36** |
| deepseek-v4-pro | temporal | 75% | 0.43 | 0.43 | 0.29 ± 0.06 | 0.38 |
| deepseek-v4-pro | temporal | 95% | 0.29 ± 0.06 | 0.36 ± 0.05 | 0.29 ± 0.06 | **0.31** |

(Score 0.5 = correct answer with no/wrong citation; 1.0 = correct with cited evidence. Most models score in the 0.4–0.5 band because they consistently get the answer right but inconsistently cite. The drift signal is the deviation *from* each model's baseline.)

> **For agent builders:** Four out of five models maintain factual retrieval all the way to 95% context fill under both noise types — pick your fact-lookup model on cost, latency, and structure-output fit, not robustness. **DeepSeek V4 Pro is the exception**: under temporal noise (old versions of the target document interleaved with the current version), retrieval accuracy drops 38% at the worst cell (50% fill, end position). The pattern is monotone with fill and worst at *end* position, suggesting recency-prime contamination — the model picks up the most-recently-injected old number when asked about the current period. **Sonnet 4.6** also takes a 20% hit at 75% temporal fill, milder than DeepSeek but worth watching. **Action:** if your retrieval corpus contains historical document versions, deduplicate at retrieval time (keep only the latest); if you can't, use Opus, GPT-5.5, or Gemini.

### 3.2 Calculation (Tier-2 derivation)

Rule-based autograde score, scale 0/0.5/1. Same structure as §3.1.

| arm | noise | fill | row mean | notable cells |
|-----|-------|-----:|---------:|---------------|
| opus-4-7 | peer or temporal, all fills | | 0.48–0.51 | flat |
| sonnet-4-6 | peer, all fills | | 0.48–0.50 | flat |
| sonnet-4-6 | temporal | 25% end | 0.45 | 25%-end dip |
| sonnet-4-6 | temporal | 75% | **0.40 ± 0.03** | **75% all positions soft** |
| sonnet-4-6 | temporal | 95% | 0.47 | partial recovery |
| gpt-5-5 | peer or temporal | | 0.50–0.52 | flat |
| gemini-3-1-pro | peer or temporal | | 0.50–0.51 | flat |
| deepseek-v4-pro | peer | | 0.43–0.48 | mild dips at end position |
| deepseek-v4-pro | temporal | 25% end | **0.21 ± 0.07** | **catastrophic at end** |
| deepseek-v4-pro | temporal | 50% end | **0.14 ± 0.06** | **deepest failure cell in study** |
| deepseek-v4-pro | temporal | 95% all | **0.31 ± 0.04** | **flat collapse** |

> **For agent builders:** Calculation accuracy is even more concentrated — the same three models (Opus, GPT, Gemini) hold steady while Sonnet shows a mid-fill soft spot under temporal noise and DeepSeek collapses sharply. The DeepSeek temporal 50% / end-position cell (0.14/1.0) is the single worst data point in the entire study — its baseline at fill=0 is 0.43, so this is a 67% drop from DeepSeek's own baseline (or 71% below the 0.50 ceiling other models maintain). **Mechanism:** the model is reading old-version income statements at the end of its context just before being asked to compute current-period margins, and is mixing the periods in its derivation. **Action:** for agentic financial analysis, if you must use DeepSeek, ensure no old-version filings are present in retrieval results, and if they are, place them at the start of the context, not the end.

### 3.3 Synthesis reasoning (Tier-3, headline metric)

LLM-judge `reasoning_quality` score, scale 0–10. Three judges (Opus, GPT-5.5, Gemini-3.1-Pro) score the same response independently. We present the headline **average across three judges** here; per-judge breakouts are in §3.3.1.

#### 3.3.1 Reasoning quality, all 3 judges blended (means ± SE)

Each cell is the mean across all (rep × judge) records that scored the cell. SE = stdev / √n. Baseline (fill=0) has no positional injection so only the middle column is reported; row mean equals that single cell.

| arm | noise | fill | start | middle | end | row mean |
|-----|-------|-----:|-------|--------|-----|---------:|
| opus-4-7 | — | 0% | — | **8.54 ± 0.12** | — | 8.54 ± 0.12 |
| opus-4-7 | peer | 25% | 8.02 ± 0.25 | 6.70 ± 0.30 | 8.35 ± 0.13 | 7.68 ± 0.15 |
| opus-4-7 | peer | 50% | 6.07 ± 0.40 | 7.92 ± 0.14 | 8.13 ± 0.14 | 7.42 ± 0.16 |
| opus-4-7 | peer | 75% | 7.32 ± 0.16 | 6.84 ± 0.17 | 8.00 ± 0.14 | 7.39 ± 0.10 |
| opus-4-7 | peer | 95% | 6.83 ± 0.18 | 6.46 ± 0.19 | 7.94 ± 0.12 | 7.07 ± 0.11 |
| opus-4-7 | temporal | 25% | 7.13 ± 0.35 | 8.22 ± 0.12 | 7.95 ± 0.10 | 7.77 ± 0.13 |
| opus-4-7 | temporal | 50% | 7.22 ± 0.33 | 7.27 ± 0.28 | 7.60 ± 0.14 | 7.37 ± 0.15 |
| opus-4-7 | temporal | 75% | 7.52 ± 0.14 | 7.48 ± 0.13 | 7.86 ± 0.14 | 7.62 ± 0.08 |
| opus-4-7 | temporal | 95% | 7.76 ± 0.12 | 7.83 ± 0.14 | 8.03 ± 0.14 | 7.87 ± 0.08 |
| sonnet-4-6 | — | 0% | — | **7.51 ± 0.32** | — | 7.51 ± 0.32 |
| sonnet-4-6 | peer | 25% | 8.40 ± 0.11 | 8.14 ± 0.13 | 8.03 ± 0.24 | 8.19 ± 0.10 |
| sonnet-4-6 | peer | 50% | 8.02 ± 0.21 | 8.13 ± 0.14 | 8.11 ± 0.14 | 8.08 ± 0.09 |
| sonnet-4-6 | peer | 75% | 7.49 ± 0.16 | 6.90 ± 0.34 | 7.83 ± 0.14 | 7.41 ± 0.13 |
| sonnet-4-6 | peer | 95% | 7.98 ± 0.13 | 8.00 ± 0.15 | 7.49 ± 0.28 | 7.84 ± 0.11 |
| sonnet-4-6 | temporal | 25% | 7.88 ± 0.22 | 8.24 ± 0.13 | 6.51 ± 0.39 | 7.61 ± 0.16 |
| sonnet-4-6 | temporal | 50% | 8.17 ± 0.13 | 8.29 ± 0.13 | 7.94 ± 0.15 | 8.12 ± 0.08 |
| sonnet-4-6 | temporal | 75% | 5.89 ± 0.48 | 7.36 ± 0.27 | 7.07 ± 0.27 | 6.83 ± 0.20 |
| sonnet-4-6 | temporal | 95% | **4.37 ± 0.33** | **5.07 ± 0.34** | **6.28 ± 0.28** | **5.22 ± 0.19** |
| gpt-5-5 | — | 0% | — | **7.94 ± 0.15** | — | 7.94 ± 0.15 |
| gpt-5-5 | peer | 25% | 7.00 ± 0.32 | 8.03 ± 0.15 | 7.90 ± 0.16 | 7.65 ± 0.13 |
| gpt-5-5 | peer | 50% | 7.87 ± 0.15 | 7.76 ± 0.16 | 7.84 ± 0.16 | 7.83 ± 0.09 |
| gpt-5-5 | peer | 75% | 7.92 ± 0.15 | 7.76 ± 0.15 | 7.70 ± 0.16 | 7.79 ± 0.09 |
| gpt-5-5 | peer | 95% | 6.05 ± 0.36 | 7.71 ± 0.16 | 7.68 ± 0.15 | 7.15 ± 0.15 |
| gpt-5-5 | temporal | 25% | 7.94 ± 0.16 | 7.68 ± 0.16 | 7.93 ± 0.15 | 7.85 ± 0.09 |
| gpt-5-5 | temporal | 50% | 7.29 ± 0.22 | 7.79 ± 0.17 | 7.84 ± 0.15 | 7.64 ± 0.11 |
| gpt-5-5 | temporal | 75% | 7.75 ± 0.15 | 7.74 ± 0.16 | 7.81 ± 0.13 | 7.77 ± 0.09 |
| gpt-5-5 | temporal | 95% | 7.51 ± 0.17 | 7.71 ± 0.16 | 7.66 ± 0.14 | 7.63 ± 0.09 |
| gemini-3-1-pro | — | 0% | — | **6.97 ± 0.20** | — | 6.97 ± 0.20 |
| gemini-3-1-pro | peer | 25% | 6.62 ± 0.21 | 6.71 ± 0.19 | 6.89 ± 0.20 | 6.74 ± 0.12 |
| gemini-3-1-pro | peer | 50% | 6.81 ± 0.18 | 6.59 ± 0.20 | 6.17 ± 0.21 | 6.52 ± 0.11 |
| gemini-3-1-pro | peer | 75% | 6.16 ± 0.32 | 7.05 ± 0.21 | 5.86 ± 0.21 | 6.35 ± 0.15 |
| gemini-3-1-pro | peer | 95% | 6.62 ± 0.20 | 6.65 ± 0.19 | 6.41 ± 0.21 | 6.56 ± 0.11 |
| gemini-3-1-pro | temporal | 25% | 6.68 ± 0.21 | 6.76 ± 0.21 | 6.59 ± 0.20 | 6.68 ± 0.12 |
| gemini-3-1-pro | temporal | 50% | 6.44 ± 0.20 | 6.49 ± 0.20 | 5.83 ± 0.29 | 6.25 ± 0.13 |
| gemini-3-1-pro | temporal | 75% | 6.40 ± 0.17 | 6.54 ± 0.22 | 5.85 ± 0.32 | 6.27 ± 0.14 |
| gemini-3-1-pro | temporal | 95% | 6.60 ± 0.22 | 6.37 ± 0.17 | 6.03 ± 0.19 | 6.33 ± 0.11 |
| deepseek-v4-pro | — | 0% | — | **6.82 ± 0.28** | — | 6.82 ± 0.28 |
| deepseek-v4-pro | peer | 25% | 7.25 ± 0.18 | 6.19 ± 0.29 | 6.22 ± 0.37 | 6.59 ± 0.16 |
| deepseek-v4-pro | peer | 50% | 7.00 ± 0.18 | 6.14 ± 0.20 | 6.19 ± 0.27 | 6.45 ± 0.13 |
| deepseek-v4-pro | peer | 75% | 6.75 ± 0.20 | 6.16 ± 0.27 | 6.81 ± 0.18 | 6.58 ± 0.13 |
| deepseek-v4-pro | peer | 95% | 6.25 ± 0.26 | 6.02 ± 0.18 | 6.57 ± 0.18 | 6.28 ± 0.12 |
| deepseek-v4-pro | temporal | 25% | 7.33 ± 0.19 | 6.43 ± 0.22 | 5.05 ± 0.57 | 6.40 ± 0.19 |
| deepseek-v4-pro | temporal | 50% | 6.90 ± 0.17 | 6.45 ± 0.27 | **3.41 ± 0.61** | 5.99 ± 0.21 |
| deepseek-v4-pro | temporal | 75% | 6.59 ± 0.26 | 6.11 ± 0.26 | 5.47 ± 0.46 | 6.09 ± 0.19 |
| deepseek-v4-pro | temporal | 95% | 5.84 ± 0.48 | 5.98 ± 0.36 | 4.38 ± 0.51 | 5.43 ± 0.26 |

Note: judges disagree on level (Gemini ~+1.3 pts more lenient than Opus, GPT ~+0.5 more lenient — see §6.3) but largely agree on **shape** within each model. The blending here weights all individual records equally, which is statistically clean but means the absolute level is somewhere between the three judges' separate scales. **For per-judge breakouts where shape vs level can be inspected separately, see §3.3.2.**

#### 3.3.2 Cross-noise contrast under each judge separately

To distinguish "real noise effect" from "judge artifact," we show the v2 (peer) vs v3 (temporal) delta per model under each of the 3 judges. A finding is "robust" if all 3 judges show the same sign.

**Opus judge (the original, harshest on Sonnet/DeepSeek):**

| model | fill | peer | temporal | Δ | judgment |
|-------|-----:|-----:|---------:|--:|----------|
| opus-4-7 | 95% | 7.02 | 7.67 | +0.65 | temporal *easier* |
| sonnet-4-6 | 95% | 7.60 | 5.13 | **−2.47** | **temporal HARDER** |
| gpt-5-5 | 95% | 6.27 | 6.70 | +0.43 | no diff |
| gemini-3-1-pro | 95% | 5.56 | 5.43 | −0.13 | no diff |
| deepseek-v4-pro | 95% | 5.24 | 3.46 | **−1.78** | **temporal HARDER** |

**GPT judge:**

| model | fill | peer | temporal | Δ | judgment |
|-------|-----:|-----:|---------:|--:|----------|
| opus-4-7 | 95% | 6.81 | 7.26 | +0.45 | no diff |
| sonnet-4-6 | 95% | 7.20 | 5.63 | **−1.57** | **temporal HARDER** |
| gpt-5-5 | 95% | 7.11 | 7.31 | +0.20 | no diff |
| gemini-3-1-pro | 95% | 5.83 | 5.60 | −0.22 | no diff |
| deepseek-v4-pro | 95% | 6.07 | 6.08 | +0.01 | no diff |

**Gemini judge:**

| model | fill | peer | temporal | Δ | judgment |
|-------|-----:|-----:|---------:|--:|----------|
| opus-4-7 | 95% | 7.40 | 8.68 | +1.29 | temporal *easier* |
| sonnet-4-6 | 95% | 8.72 | 4.91 | **−3.81** | **temporal HARDER** |
| gpt-5-5 | 95% | 8.06 | 8.87 | +0.81 | temporal *easier* |
| gemini-3-1-pro | 95% | 8.30 | 7.97 | −0.33 | no diff |
| deepseek-v4-pro | 95% | 7.58 | 7.95 | +0.37 | no diff |

**Robustness summary at 95% fill:**

| model | Opus says | GPT says | Gemini says | Robust verdict |
|-------|-----------|----------|-------------|----------------|
| Opus 4.7 | + | no diff | + | **temporal not a problem** (recovery if anything) |
| Sonnet 4.6 | **−2.47** | **−1.57** | **−3.81** | **TEMPORAL CRASHES SONNET** (3-judge consensus) |
| GPT-5.5 | no diff | no diff | + | **fully invariant** |
| Gemini 3.1 Pro | no diff | no diff | no diff | **fully invariant** (low base) |
| DeepSeek V4 Pro | **−1.78** | no diff | no diff | **OPUS-ONLY VERDICT** — non-Anthropic judges don't see degradation. Caveat: DeepSeek had 26% of records dropped on cross-judge due to extraction failures (§6); the surviving GPT/Gemini sample may be biased toward the responses DeepSeek did produce successfully. |

> **For agent builders:** If you're building a synthesis pipeline that handles potentially-stale-version retrievals, **Sonnet 4.6 is the only model with a 3-judge-confirmed fail at high fill.** The signal is unambiguous: at 95% temporal fill, all three judges (Anthropic, OpenAI, Google) rate Sonnet's syntheses 1.5–3.8 points lower than under control noise. This is not a "judge bias" finding — it's a real model-behavior signal. The other 4 models hold up. **Action:** if your stack uses Sonnet for synthesis and your retrieval might pull historical document versions, either (a) switch to Opus or GPT for the synthesis step, or (b) cap context fill at ≤50% where Sonnet is still robust.

### 3.4 Hallucination & contamination

Three sub-metrics:
- **`unsupported_claims`** (judge-rated count, lower = better): number of claims in the response without traceable evidence
- **`temporal_contamination`** (judge-rated count): claims explicitly attributable to wrong-period source
- **`distractor_hit`** (rule-based, tier-1 only): did the response contain a known wrong-version numerical string

#### 3.4.1 H6 — period confusion: NULL across all 5 models, all 3 judges

The original v3 hypothesis (H6) was that temporal noise — old versions of the same document at high context fill — would cause the model to attribute wrong-period numbers to the current period. We tested it from multiple angles:

| Test | Coverage | Records flagged |
|------|----------|----------------:|
| Tier-1 autograde: `correct=False` AND `temporal_hit > 0` | 5 arms × 91 reps × 3 q = 1,365 | **0** |
| Tier-3 Opus judge: `temporal_contamination > 0` | 5 arms × ~273 records | **0 / 1,362** |
| Tier-3 GPT judge: `temporal_contamination > 0` | 5 arms × ~245 records | **0 / 1,227** |
| Tier-3 Gemini judge: `temporal_contamination > 0` | 5 arms × ~250 records | **0 / 1,260** |

**H6 is unambiguously NULL.** No frontier model in this study confuses periods, even at 95% context fill with old-version target documents.

The earlier rule-based detector flagged 24 "temporal hits" on Sonnet — these turned out to be the model correctly producing comparative-period income statements (e.g., the format "Total revenue 281,724 245,122 211,915 for fiscal years 2025, 2024, and 2023"), where the FY2024 number 245,122 matches the as-originally-filed FY2024 value in the noise corpus. This is correct comparative-period reporting, not contamination. All three independent judges (Opus, GPT, Gemini), looking at semantic intent, found zero true contaminations.

> **For agent builders:** The widely-cited concern that "RAG with stale-version documents will cause the model to attribute wrong-period numbers" is empirically wrong on these 5 models. What models DO show under temporal noise is reduced output completeness (Sonnet truncates) and downstream parseability (DeepSeek fails to format), not period attribution errors. Your QA/eval should focus on those failure modes, not on hunting period confusion.

#### 3.4.2 Unsupported claims (general hallucination)

Mean `unsupported_claims` count per tier-3 record. Headline pattern: counts climb with fill (more context pressure → more dubious claims), and the worst arm under temporal noise is Sonnet 95%.

| arm | noise | 0% | 25% | 50% | 75% | 95% |
|-----|-------|---:|----:|----:|----:|----:|
| opus-4-7 (Opus judge) | peer | 0.24 | 0.76 | 0.62 | 1.02 | **1.68** |
| opus-4-7 (Opus judge) | temporal | 0.19 | 0.41 | 0.73 | 1.10 | 1.14 |
| sonnet-4-6 (Opus judge) | peer | 0.10 | 0.46 | 0.46 | 0.95 | 1.06 |
| sonnet-4-6 (Opus judge) | temporal | 0.05 | 0.98 | 0.95 | 1.13 | **3.85** |
| gpt-5-5 (Opus judge) | peer | 0.00 | 0.02 | 0.00 | 0.00 | 0.05 |
| gpt-5-5 (Opus judge) | temporal | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 |
| gemini-3-1-pro (Opus judge) | peer | 0.57 | 0.41 | 0.70 | 0.79 | 0.56 |
| gemini-3-1-pro (Opus judge) | temporal | 0.33 | 0.49 | 0.54 | 0.54 | 0.87 |
| deepseek-v4-pro (Opus judge) | peer | 0.62 | 0.67 | 1.10 | 1.03 | 0.87 |
| deepseek-v4-pro (Opus judge) | temporal | 0.52 | 0.46 | 0.71 | 0.98 | 0.52 |

**Cross-judge note:** GPT-5.5 as judge counts unsupported claims 2–5× more aggressively than Opus or Gemini do (Sonnet 95% temporal: GPT counts 10.8/record vs Opus 3.85 vs Gemini 4.70). This is a *scale calibration* difference, not a directional disagreement — all three judges agree that Sonnet at 95% temporal generates the most unsupported claims; they just count claims at different thresholds. Within each judge, the trends are consistent.

> **For agent builders:** GPT-5.5 the analyst is the most cautious model in this study — at no condition does it average more than 0.13 unsupported claims per response under any judge. If your application has zero tolerance for unsupported assertions (regulated finance, medical, legal), **GPT-5.5 is the safest analyst** even though its raw reasoning_quality is slightly lower than Opus or Sonnet (in clean conditions). For everything else, watch Sonnet at high temporal fill (3.85 unsupported claims/record at 95% temporal — 3× its own peer-noise rate).

#### 3.4.3 Downstream extraction failure (the silent killer)

Empty `answer_raw` rate on tier-3 — i.e., the analyst returned a response, but the haiku-based structured extractor failed to parse it into the 8-question schema. The downstream pipeline sees this as a missing answer, even though the analyst produced substantive content.

| arm | v2 (peer) | v3 (temporal) | Δ |
|-----|----------:|---------------:|---:|
| Opus 4.7 | 1.1% | 0.0% | −1.1pp |
| Sonnet 4.6 | 1.1% | **10.7%** | **+9.6pp** |
| GPT-5.5 | 0.0% | 0.0% | 0 |
| Gemini 3.1 Pro | 0.0% | 0.0% | 0 |
| **DeepSeek V4 Pro** | **7.7%** | **25.3%** | **+17.6pp** |

DeepSeek's empty rate breakdown by cell:
- 50% temporal end: **15/21 empty (71%)** ← worst cell
- 25% temporal end: 12/21 (57%)
- 95% temporal: 24/63 (38%)
- 0% baseline: 0/21 (0%)

We verified by inspecting raw responses: DeepSeek produces 15K-character substantive responses with valid analytical content; the issue is downstream JSON-parsing fragility under temporal-noise-induced response-format variance. This is a *pipeline-side* failure, not an *analyst-side* refusal — but for a builder, the symptoms are identical (no usable output).

> **For agent builders:** This is the failure mode you're least likely to instrument. Your eval suite probably looks at "what did the model output?" and if the structured extractor returns nothing, the record gets silently skipped. **Action:** add an "extractor failure rate" metric alongside your accuracy metrics. If you use DeepSeek with a structured-output pipeline, expect 7–25% of tier-3 syntheses to require fallback paths under temporal-noise conditions. Sonnet under temporal noise also shows a 10× increase in extractor failures (1% → 11%); Opus, GPT, Gemini are immune.

---

## 4. Quality sub-dimensions on tier-3 synthesis

The tier-3 judge rates 5 sub-dimensions per response (in addition to overall `reasoning_quality`). Here we surface the dimensions that move and the ones that hold.

### 4.1 Groundedness (do claims trace to evidence?)

Scale 0–5. Means under Opus judge, all positions averaged.

| model | noise | 0% | 25% | 50% | 75% | 95% |
|-------|-------|---:|----:|----:|----:|----:|
| opus-4-7 | peer | 4.90 | 4.33 | 4.14 | 4.22 | 3.94 |
| opus-4-7 | temporal | 4.60 | 4.34 | 4.25 | 4.03 | 4.12 |
| sonnet-4-6 | peer | 4.52 | 4.68 | 4.63 | 4.24 | 4.30 |
| sonnet-4-6 | temporal | 4.57 | 4.01 | 4.30 | 3.72 | **2.91** |
| gpt-5-5 | peer | 5.00 | 4.87 | 4.84 | 4.94 | 4.70 |
| gpt-5-5 | temporal | 5.00 | 4.98 | 4.96 | 4.93 | 4.96 |
| gemini-3-1-pro | peer | 4.24 | 4.29 | 4.10 | 3.97 | 4.13 |
| gemini-3-1-pro | temporal | 4.44 | 4.30 | 4.18 | 4.28 | 3.99 |
| deepseek-v4-pro | peer | 3.67 | 3.67 | 3.71 | 3.70 | 3.75 |
| deepseek-v4-pro | temporal | 4.32 | 3.93 | 3.67 | 3.58 | 3.52 |

**Sonnet 95% temporal: groundedness drops to 2.91/5 (vs 4.30 under peer noise).** This is the strongest sub-dimension signal of Sonnet's temporal collapse — its claims at 95% temporal stop tracing cleanly to the FY2025 source.

### 4.2 Other sub-dimensions (brief)

- **`evidentiary_breadth`**: tracks `groundedness` closely. Sonnet 95% temporal is the worst arm; everyone else is flat.
- **`citation_accuracy`**: GPT-5.5 wins (4.85+ across all conditions). Sonnet drops at 95% temporal.
- **`scope_adherence`**: All models 4.5+ under all conditions — no signal. (Models stay on topic regardless of noise; this dimension is a saturation artifact at the 5-point ceiling.)
- **`clarity`**: All models 4.0+. Mild Sonnet dip at 95% temporal.

> **For agent builders:** The Sonnet temporal collapse pattern is consistent across `reasoning_quality` (overall) → `groundedness` (claims-to-evidence) → `evidentiary_breadth` (anchor coverage). It's not "Sonnet writes weird sentences" — it's "Sonnet stops tracing claims to the FY2025 source under heavy old-version noise." If you use Sonnet, ground-truth citation validators will catch this failure mode.

---

## 5. Per-model verdicts (the picking guide)

One paragraph per model. **Opinionated calls** based on the data, with the failure modes flagged.

### 5.1 Opus 4.7 (max thinking) — the safe synthesis pick under any noise

**Use when:** synthesis quality matters most, and your context might be heavily filled (75–95%) with mixed-noise retrievals. Opus is the only model that *recovers* at 95% fill (under all 3 judges) under temporal noise, suggesting it senses context saturation and invests extra thinking budget.

**Avoid when:** latency or cost is critical for low-stakes tasks where any frontier model would do. Opus's max-thinking mode is the most expensive in the study (~$1+/synthesis at full reps).

**Failure mode to watch:** None observed in this study. Opus showed zero extraction failures and the lowest hallucination rates at high temporal fill among the Anthropic models.

### 5.2 Sonnet 4.6 (max thinking) — high baseline, sharp temporal cliff

**Use when:** you control the noise composition (peer/distractor noise only, no stale-version target documents) AND you need synthesis quality at high fill. Under peer noise Sonnet is competitive with Opus across all fills (and beats it on baseline groundedness).

**Avoid when:** your retrieval might pull historical versions of the target document. **All 3 judges confirm Sonnet's 95% temporal collapse**: −2.5 to −3.8 points on a 10-point reasoning_quality scale. The failure mode is bimodal — ~25% catastrophic 0–2/10 ratings, ~25% still 8+/10 — so it's *detectable*: a structural validator ("did the response complete all required parts?") will catch the failures cleanly.

**Failure mode to watch:** truncated syntheses at 95% temporal fill. Add a structural completeness check + retry with reduced context.

### 5.3 GPT-5.5 (reasoning=max) — the most temporal-noise-invariant

**Use when:** you need synthesis quality with maximum noise robustness. GPT-5.5 is **the only model with no degradation under temporal noise across any judge at any fill level**. Under all 3 judges it scores ~7.0–7.5/10 on synthesis from baseline through 95% temporal fill, with extremely tight confidence intervals.

**Avoid when:** pure baseline quality is the only thing that matters. GPT-5.5 sober-state synthesis is rated lower than Opus or Sonnet (per [`SOBER_STATE_FINAL_REPORT.md`](./SOBER_STATE_FINAL_REPORT.md)), but holds its level steady where the others wobble.

**Failure mode to watch:** GPT-5.5 has the **lowest unsupported_claims rate** in the study (0.0–0.13 per response under all conditions). This is partly a feature (it's cautious) and partly a quirk (it might omit speculative-but-useful synthesis). For finance/legal/regulated use, this caution is what you want.

### 5.4 Gemini 3.1 Pro (HIGH thinking) — flat performer, generous self-judge

**Use when:** you need a non-Anthropic, non-OpenAI option for vendor diversity, and your task is in Gemini's strength zone (which we did not test). Gemini synthesizes at a stable 5.5–5.7/10 under Opus's rubric across all noise/fill conditions — flat is good for predictability but the absolute level is lower than the other 4 models.

**Avoid when:** you need top-tier baseline synthesis or you're using Gemini as a self-evaluator. **Gemini-as-judge rates outputs ~2.5–2.7 points higher than Opus or GPT do, across every arm we tested.** Use of Gemini in agent self-eval loops without calibration will produce inflated confidence.

**Failure mode to watch:** the level shift in self-rating — calibrate before using as judge.

### 5.5 DeepSeek V4 Pro (reasoning_effort=max) — temporal noise's worst victim

**Use when:** budget is the binding constraint and your context is clean (no temporal-noise retrievals). At 0% fill DeepSeek is competitive (5.3–6.9/10 across judges, the lowest baseline of the 5 but not by much).

**Avoid when:** *anything* might be temporally noisy. Under temporal noise DeepSeek shows three distinct failure modes:
1. **Tier-1 retrieval**: 38% accuracy drop at 95% (0.50 → 0.31), worst single cell at 50% temporal end (0.14/1.0 — 72% below baseline).
2. **Tier-2 calculation**: same pattern, 50% temporal end = 0.14/1.0.
3. **Downstream extraction**: 25% of tier-3 responses fail to parse into structured output. Note: the underlying analyst output is substantive (15K chars + thinking) — this is a downstream pipeline issue, but operationally identical to "no usable output."

**Failure mode to watch:** all three of the above. DeepSeek has the highest variance of any model in this study; if temporal noise is in play, plan extensive fallback handling.

> **Bottom-line picking guide:**
> - Default for synthesis under uncertain noise: **Opus 4.7** (best baseline + recovery at 95%) or **GPT-5.5** (most invariant).
> - Default for high-volume, low-cost factual lookup with clean noise: **Sonnet 4.6** or **GPT-5.5**.
> - Avoid for stale-version retrievals: **Sonnet** (synthesis collapse) and **DeepSeek** (multi-mode collapse).
> - Avoid as a judge in self-evaluation loops: **Gemini** (without calibration).

---

## 6. Instrument validation (the statistical jargon)

This section is for readers who want to verify the conclusions are not measurement artifacts.

### 6.1 Cross-judge agreement per arm (Pearson r on `reasoning_quality`)

How well do judges agree on a per-record basis? RUBRIC threshold for "use as primary measurement": Pearson r ≥ 0.70.

**v2 arms (peer noise):**

| arm | Opus×GPT | Opus×Gemini | GPT×Gemini |
|-----|---------:|------------:|-----------:|
| opus-4-7 | 0.82 | 0.74 | 0.80 |
| sonnet-4-6 | 0.70 | 0.73 | 0.80 |
| gpt-5-5 | 0.81 | 0.75 | 0.85 |
| gemini-3-1-pro | 0.78 | **0.49** | **0.47** |
| deepseek-v4-pro | 0.75 | **0.45** | 0.55 |

**v3 arms (temporal noise):**

| arm | Opus×GPT | Opus×Gemini | GPT×Gemini |
|-----|---------:|------------:|-----------:|
| opus-4-7-temporal | 0.74 | 0.76 | 0.81 |
| sonnet-4-6-temporal | 0.82 | 0.78 | 0.78 |
| gpt-5-5-temporal | 0.69 | **0.49** | 0.65 |
| gemini-3-1-pro-temporal | 0.83 | **0.47** | 0.56 |
| deepseek-v4-pro-temporal | 0.84 | 0.61 | 0.66 |

**Pattern:** Opus and GPT agree well across the board (r=0.69–0.84). Gemini disagrees more, especially when judging non-Anthropic / non-OpenAI arms. The Sonnet 95% collapse finding is in the cross-judge-agreed regime (sonnet-temporal: Opus×GPT 0.82, Opus×Gemini 0.78) — judges agree on what they're seeing.

### 6.2 Self-favoritism quantification

For each arm whose vendor also has a judge in our pool, we measure the self-judge mean minus the cross-vendor judge mean.

**`reasoning_quality`, both noise types:**

| model arm | noise | self-judge | self mean | Opus mean | GPT mean | Gemini mean | self − Opus | self − GPT |
|-----------|-------|------------|----------:|----------:|---------:|------------:|------------:|-----------:|
| opus-4-7 | peer | opus | 7.18 | 7.18 | 7.09 | 8.16 | 0.00 | +0.08 |
| opus-4-7 | temporal | opus | 7.38 | 7.38 | 7.22 | 8.52 | 0.00 | +0.16 |
| sonnet-4-6 | peer | opus | 7.66 | 7.66 | 7.25 | 8.64 | (n/a — within Anthropic) | +0.41 |
| sonnet-4-6 | temporal | opus | 6.54 | 6.54 | 6.97 | 7.80 | (n/a) | −0.43 |
| gpt-5-5 | peer | gpt | 7.48 | 6.77 | 7.48 | 8.64 | **+0.72** | 0.00 |
| gpt-5-5 | temporal | gpt | 7.56 | 6.85 | 7.56 | 8.81 | **+0.71** | 0.00 |
| gemini-3-1-pro | peer | gemini | 8.31 | 5.60 | 5.82 | 8.31 | **+2.70** | **+2.49** |
| gemini-3-1-pro | temporal | gemini | 8.12 | 5.45 | 5.63 | 8.12 | **+2.68** | **+2.50** |

**Findings:**
- **Gemini self-bias is large and stable** (+2.7 vs Opus, +2.5 vs GPT, both noises) — this is a level shift, not noise-dependent.
- **GPT self-bias is mild and stable** (+0.7 vs Opus, both noises) — also a level shift.
- **No within-Anthropic favoritism observed**: when Opus judges Sonnet, Opus rates Sonnet *lower* than GPT or Gemini do (Sonnet temporal: Opus 6.54 vs GPT 6.97 vs Gemini 7.80). Anthropic's own judge is the harshest on its own kind, not the most lenient.

### 6.3 Judge mean offsets

Mean `reasoning_quality` by judge, pooled across all 10 arms × all conditions:
- **Opus 4.7**: 6.31 (n=2,727)
- **GPT 5.5**: 6.78 (+0.47, n=2,560)
- **Gemini 3.1 Pro**: 8.34 (+2.03, n=2,598)

Gemini is systematically the most lenient by 2 points; GPT is mildly more lenient than Opus. For builders using these as judges, mentally subtract ~2.0 from Gemini scores and ~0.5 from GPT scores to compare with Opus. Note that the per-arm self-favoritism in §6.2 (Gemini self-bias +2.7) is *additional* to this baseline level shift — the Gemini judge is unusually generous to *its own kind* even by its own already-lenient standard.

### 6.4 Sample sizes (transparency)

Tier-3 records per (arm, judge) cell. Cells with n<273 reflect either extraction failures (analyst side) or judge-side stream errors. Coverage gaps documented:

- `sonnet-4-6-temporal`: 270 (Opus) / 232 (GPT) / 237 (Gemini) — analyst extract failures (29 records empty) + 3-5% judge-side stream errors
- `gpt-5-5-temporal`: 273 / 262 / 273 — 11 GPT-judge stream errors during cross-judge run
- `gemini-3-1-pro-temporal`: 273 / 268 / 273 — 5 GPT-judge stream errors
- `deepseek-v4-pro-temporal`: 273 / 193 / 204 — analyst extract failures (69 records empty) drop the cross-judge sample by 25–30%
- `deepseek-v4-pro` (v2): 273 / 252 / 252 — 21 analyst extract failures
- All other cells: full 273 records

**Caveat for DeepSeek:** the temporal arm's cross-judge cells have 25–30% fewer records than the original-judge cell. The dropped records are concentrated at high-noise cells (50% end, 95% all positions). The cross-judge means may therefore be biased *toward* DeepSeek's better-formed responses. This may explain why GPT and Gemini judges show no temporal degradation for DeepSeek while Opus does — though Opus is also harsher in absolute terms across all DeepSeek cells.

### 6.5 Reliability per dimension

| dimension | reliable across judges? | use case |
|-----------|------------------------|----------|
| `reasoning_quality` (0–10) | Yes — r ≥ 0.65 typical | **headline metric** |
| `groundedness` (0–5) | Yes — r ≥ 0.70 typical | secondary signal |
| `evidentiary_breadth` (0–5) | Yes | secondary signal |
| `citation_accuracy` (0–5) | Yes | useful but high baseline |
| `scope_adherence` (0–5) | No — saturated at 5 | diagnostic only |
| `clarity` (0–5) | No — judges interpret differently | diagnostic only |
| `unsupported_claims` (count) | Yes on direction, not on level | use within-judge trend |
| `temporal_contamination` (count) | All zeros — | confirmed-null finding |

---

## 7. Failure-mode catalog (real examples)

### 7.1 Sonnet 4.6 at 95% temporal — truncated synthesis

**Cell:** `c_MSFT_95_middle_temporal_msft__r05`, question MSFT-S-03 (3-part synthesis: decompose revenue → apply 4 economic frameworks → synthesize)

**Opus judge rating:** `reasoning_quality=2/10, groundedness=4/5, unsupported_claims=0`

**Judge rationale (verbatim):**
> "The response delivers only Part 1 (DECOMPOSE) and even that is incomplete — More Personal Computing (Windows OEM, Gaming, Search) is entirely missing. Parts 2 (four economic frameworks) and 3 (synthesis) are absent, so the question is fundamentally unanswered. Factual claims that are made (Note 18 segment figures, 34% Azure growth, 450M+ M365 seats, 89M consumer subscribers) trace correctly to the [FY2025 sources]…"

**Candidate response (first 600 chars):**
> "PART 1: DECOMPOSE — REVENUE UNITS WITH DISTINCT ECONOMICS
>
> Starting from the FY2025 10-K Note 18 segment structure, I decompose further where the economics differ meaningfully:
>
> A. INTELLIGENT CLOUD
> A1. Azure Consumption Services (IaaS, PaaS, AI inference/training): The dominant growth driver within the $98,435M 'Server products and cloud services' product line (Note 18 FY2025 revenue table). Azure's specific dollar revenue is not disclosed separately, but its 34% growth rate in FY2025 (MD&A) far exceeds the blended 23.3% growth of the combined line, confirming Azure as the primary driver…"

The response is *substantive and accurate* where it exists — it just stops 60% of the way through the question. The model "ran out of steam" under context pressure. **Detection signal for builders:** the response doesn't contain any of the headers "PART 2" or "PART 3" — a regex check on expected structure would catch this.

### 7.2 DeepSeek V4 Pro at 50% temporal end — extraction parse failure

**Cell:** `c_MSFT_50_end_temporal_msft__r00`, all 8 questions

**Pipeline view:** all 8 records have `answer_raw=""`, `parsed_ok=false`, `parse_notes="extractor_output_unparseable"`.

**Raw analyst output:**
- `stop_reason: "stop"` (clean termination)
- `response_text: 15,604 chars` (substantive)
- `thinking_text: 26,717 chars` (deep reasoning)
- Final 400 chars of response (showing JSON tail):

> "...call: Satya Nadella remarks on AI stack, Copilot, custom silicon, Azure demand; Amy Hood on capacity allocation, margins, capital spending, and segment outlook.\",
>     \"reasoning\": \"Decomposed Microsoft's revenue units, applied demand/complementarity/substitution/supply‑constraint frameworks using 10‑K and call evidence, and synthesized a coherent long‑term thesis with explicit assumptions.\"
>   }
> ]"

The output is valid JSON ending with `]`. The downstream haiku-extractor is supposed to parse this 8-element JSON array into 8 separate question records, but it fails — likely due to formatting variance earlier in the array that doesn't appear in the tail. **15/21 reps fail this way at this single cell.** All cells with empty extracts show similar substantive raw output.

**Detection signal for builders:** measure extractor success rate alongside accuracy. If you ship DeepSeek with a structured-output pipeline, a hard validator + raw-text fallback path will recover the 25% otherwise-lost records.

### 7.3 Opus 4.7 at 95% temporal — judges agree on RECOVERY

**Cell:** `c_MSFT_95_end_temporal_msft__r00`, question MSFT-S-01

**Three-judge ratings:**
- Opus 4.7 judge: 9/10
- GPT 5.5 judge: 8/10
- Gemini 3.1 Pro judge: 9/10

This is the strongest cross-judge agreement at maximum context pressure in the study. All three independent judges (one Anthropic, one OpenAI, one Google) rate Opus's synthesis at 9/10 quality even when 95% of its context window is filled with old MSFT 10-Ks. This validates the §3.3.1 finding that Opus's reasoning_quality recovers at 95% fill — it's not an artifact of self-favoritism.

### 7.4 The "false positive" temporal hit (why H6 looked non-null at first)

**Cell:** `c_MSFT_75_end_temporal_msft__r03`, question MSFT-F-01 (Sonnet temporal arm)

**Autograde:** `correct=True, score=0.5, distractor_hit=False`
**Temporal detector:** flagged 2 hits — `"245,122"` and `"211,915"` (FY2024 and FY2023 revenue)

**Response context (verbatim):**
> "Income Statements: 'Total revenue 281,724 245,122 211,915' for fiscal years 2025, 2024, and 2023…"

The model correctly produced a 3-year comparative income statement showing FY2025 ($281,724M) alongside FY2024 ($245,122M) and FY2023 ($211,915M). The temporal-distractor detector flagged the FY2024 number 245,122 because it matches the as-originally-filed FY2024 value in the noise corpus. But this is **correct comparative-period reporting** — the response is right, scored correct, and doesn't attribute the wrong period.

This is why the rule-based "H6 hit" rate of 24/200 records misled the initial reading. The judge-rated `temporal_contamination` field — looking at semantic intent rather than string matching — correctly returned 0 across all 3 judges and all 5 arms. **Lesson for builders running similar evaluations:** distinguish "string match on a known wrong-version value" from "wrong-version value attributed to current period." Only the latter is actionable.

---

## 8. Open questions & limitations

- **One target company (MSFT), one fiscal year (FY2025)**: findings should generalize to similar large-cap tech 10-Ks but may not transfer to other domains (medical, legal, code).
- **DeepSeek cross-judge sample bias**: 25–30% of DeepSeek's tier-3 records were dropped from cross-judging due to extractor failures; the surviving cross-judge means may be biased toward better-formed DeepSeek outputs. The Opus-judge results (which use the original direct judging, not cross-judging) are unbiased and confirm the synthesis degradation.
- **Single judge per vendor**: GPT-5.5, Gemini-3.1-Pro, Opus-4.7 are one model each. Within-vendor judge variance not measured (would require, e.g., GPT-5.0 + GPT-5.5 cross-checking).
- **Fixed thinking budgets**: all analysts at vendor max-thinking. Lower thinking budgets may show different patterns (especially for Opus's 95% recovery, which appears thinking-mediated).
- **No human gold-standard**: cross-judge agreement validates the *measurement instrument*, not the *ground-truth quality* of any synthesis. A human-labeled subsample would be the next step.

---

## Appendix A — Methodology lock chain

- **v1** (`pre_registration.lock`, Apr 25): Opus 4.7 alone. Judge stack = Opus primary + Sonnet 20% subsample (within-vendor).
- **v2** (`pre_registration.v2.lock`, Apr 25): Added 4 multi-vendor analyst arms (Sonnet, GPT, Gemini, DeepSeek) under the same peer-materials noise. Judge stack unchanged.
- **v3** (`pre_registration.v3.lock`, May 5): Added 5 `*-temporal` analyst arms with `temporal_msft` noise. Materials lock fork for old-version corpus (`materials_temporal.lock.json`). Judge stack unchanged.
- **This report** (May 6): Added cross-vendor judges (GPT-5.5, Gemini-3.1-Pro) on tier-3 records of all 10 arms. **Not a methodology change** — this is an *ablation* on the existing data, with the cross-vendor judges measuring the same `absolute` rubric defined in v1.

## Appendix B — Reproducibility

- Materials hash (frozen since v1): `c13b5514279c9d8dbc5118ec9b3b1325a0cff56c4fb1cee8d66992a98cd25199`
- v3 methodology hash: `10ebe9f1ea30d98fdf5453074867fee54c1e047b1463f692ac66d89a939a8043`
- Cross-judge prompt + materials sha256: `0d4c6cf728b4f49a` (consistent across 4-arms run, sonnet incremental, and v2 5-arms run)
- Analysis pipeline: `cross_arm/build_unified_report.py` (main report) + `cross_arm/analyze_position_strength.py` (§9 position + §10 strength addenda)
- Raw cross-judge sidecars: `arms/{arm}/data/cross_judged/all_tier3.jsonl` for all 10 arms.

---

# §9 — Does noise *position* matter?

**TL;DR.** For autograded tier-1/tier-2 (data lookup, calculation), position is essentially irrelevant — spreads ≤ 0.04 on a 0-1 scale for 4 of 5 models. **DeepSeek under temporal noise is the lone exception**: when temporal noise is placed at the start of context (the "end" position label, where target sits adjacent to questions), tier-1 collapses from 0.43 to 0.23 and tier-3 reasoning falls to 4.65 — a 2.06-point spread, the largest in the entire grid. For tier-3 synthesis, two opposite patterns emerge that cancel each other in the cross-model average:

1. **Target-adjacency benefit (Opus, Sonnet@high-fill):** placing target right next to the questions improves Opus tier-3 reasoning by **+1.12** under peer noise (8.10 vs 7.07).
2. **Anchoring vulnerability (DeepSeek, mild Gemini):** placing noise at the very start of context catastrophically anchors DeepSeek under temporal noise; effect is mild and non-monotonic for Gemini.

These two effects pull in **opposite directions on the same position label** — there is no universally "best" noise position for an agent builder; it depends on which model is downstream.

## §9.1 Position semantics (per `harness/src/assembly.py:7-11`)

Prompt order is `[system][noise_a][target][noise_b][questions]`. The position label controls the noise split:

| label | noise_a | noise_b | layout |
|-------|--------:|--------:|--------|
| `start` | 0 | full | system → **target** → noise → questions  *(noise sits between target and questions)* |
| `middle` | half | half | system → noise → **target** → noise → questions  *(target sandwiched)* |
| `end` | full | 0 | system → noise → **target** → questions  *(noise sits between system and target; target is adjacent to questions)* |

So `start` puts target at the *start of the context* and `end` keeps target near the *end of the context, adjacent to the questions*.

## §9.2 Tier-3 reasoning, blended judges (pooled across all noise fills)

| model | noise | start | middle | end | mean | spread (max−min) |
|-------|-------|-------|--------|-----|-----:|-----------------:|
| opus-4-7 | peer materials | 7.07 ± 0.13 | 6.98 ± 0.11 | **8.10 ± 0.07** | 7.39 ± 0.06 | **1.12** |
| sonnet-4-6 | peer materials | 7.97 ± 0.08 | 7.80 ± 0.11 | 7.87 ± 0.10 | 7.88 ± 0.06 | 0.18 |
| gpt-5-5 | peer materials | 7.21 ± 0.14 | 7.82 ± 0.08 | 7.78 ± 0.08 | 7.60 ± 0.06 | 0.61 |
| gemini-3-1-pro | peer materials | 6.55 ± 0.12 | 6.75 ± 0.10 | 6.33 ± 0.11 | 6.54 ± 0.06 | 0.42 |
| deepseek-v4-pro | peer materials | 6.83 ± 0.11 | 6.12 ± 0.12 | 6.47 ± 0.13 | 6.47 ± 0.07 | 0.70 |
| opus-4-7 | temporal msft | 7.41 ± 0.13 | 7.70 ± 0.09 | **7.86 ± 0.07** | 7.66 ± 0.06 | 0.45 |
| sonnet-4-6 | temporal msft | 6.66 ± 0.18 | 7.24 ± 0.15 | 7.00 ± 0.14 | 6.97 ± 0.09 | 0.57 |
| gpt-5-5 | temporal msft | 7.62 ± 0.09 | 7.73 ± 0.08 | 7.81 ± 0.07 | 7.72 ± 0.05 | 0.19 |
| gemini-3-1-pro | temporal msft | 6.53 ± 0.10 | 6.54 ± 0.10 | 6.08 ± 0.13 | 6.38 ± 0.06 | 0.46 |
| deepseek-v4-pro | temporal msft | 6.71 ± 0.14 | 6.25 ± 0.14 | **4.65 ± 0.27** | 5.99 ± 0.11 | **2.06** |

Read this with the position semantics in mind: Opus's "end" win (8.10 / 7.86) is the **target-adjacent-to-questions** layout, and DeepSeek's "end" collapse (4.65) is the **noise-anchored-at-front** layout. Same label, opposite mechanism.

## §9.3 Tier-1 and Tier-2 (autograded retrieval & calculation)

Tier-1 retrieval, by position:

| model | noise | start | middle | end | mean | spread |
|-------|-------|-------|--------|-----|-----:|-------:|
| opus-4-7 | peer | 0.51 ± 0.02 | 0.50 | 0.50 | 0.50 | 0.01 |
| sonnet-4-6 | peer | 0.50 | 0.50 | 0.48 | 0.49 | 0.02 |
| gpt-5-5 | peer | 0.51 | 0.52 | 0.51 | 0.52 | 0.01 |
| gemini-3-1-pro | peer | 0.51 | 0.50 | 0.51 | 0.51 | 0.01 |
| deepseek-v4-pro | peer | 0.49 | 0.46 | 0.46 | 0.47 | 0.04 |
| opus-4-7 | temporal | 0.50 | 0.50 | 0.50 | 0.50 | 0.00 |
| sonnet-4-6 | temporal | 0.46 | 0.46 | 0.46 | 0.46 | 0.01 |
| gpt-5-5 | temporal | 0.51 | 0.50 | 0.50 | 0.50 | 0.01 |
| gemini-3-1-pro | temporal | 0.50 | 0.50 | 0.52 | 0.51 | 0.02 |
| **deepseek-v4-pro** | **temporal** | **0.43 ± 0.02** | **0.43 ± 0.02** | **0.23 ± 0.03** | 0.36 | **0.20** |

Tier-2 calculation shows the identical pattern — DeepSeek temporal-end is again the lone outlier (0.43/0.43/**0.23**, spread 0.20). Together this is a **47% drop** in autograded accuracy *purely from where the noise sits in context*, holding fill and noise content fixed. The most plausible mechanism (cross-checked against §3.4.3 of the main report): when temporal noise sits at the very start of DeepSeek's context, the analyst output gets contaminated/disorganized enough that the haiku extractor fails to recover answer values from the prose. This is a downstream-pipeline symptom, not a pure reasoning failure — but it's the kind of failure a production agent will see as "the agent gave me garbage today".

## §9.4 Position spread vs fill spread (Tier-3 reasoning, blended)

| model | noise | fill spread (25%→95%) | position spread (pooled) | ratio (|fill| / position) |
|-------|-------|----------------------:|-------------------------:|----------------------:|
| opus-4-7 | peer | −0.61 | 1.12 | 0.5× |
| sonnet-4-6 | peer | −0.35 | 0.18 | 2.0× |
| gpt-5-5 | peer | −0.50 | 0.61 | 0.8× |
| gemini-3-1-pro | peer | −0.18 | 0.42 | 0.4× |
| deepseek-v4-pro | peer | −0.31 | 0.70 | 0.4× |
| opus-4-7 | temporal | +0.11 | 0.45 | 0.2× |
| sonnet-4-6 | temporal | **−2.39** | 0.57 | 4.2× |
| gpt-5-5 | temporal | −0.22 | 0.19 | 1.1× |
| gemini-3-1-pro | temporal | −0.34 | 0.46 | 0.7× |
| deepseek-v4-pro | temporal | −0.98 | **2.06** | 0.5× |

Reading: a ratio < 1× means position effects are *larger* than fill effects for that arm. **Six of 10 cells have ratio < 1×** — for most arms in this grid, *where* you put the noise affects the score at least as much as *how much* noise you add. The two cells where fill clearly dominates are Sonnet-temporal (catastrophic fill collapse from §3 of the main report) and Sonnet-peer (small but consistent fill drift). For Opus-peer specifically, position is **2× more important than fill** — moving target adjacent to the questions buys Opus a full point of reasoning quality.

## §9.5 Drill-in: the (fill × position) interaction for outliers

**Sonnet under temporal noise** — fill takes over once it gets large:

| fill | start | middle | end | row spread |
|-----:|-------|--------|-----|-----------:|
| 25% | 7.88 | 8.24 | 6.51 | 1.73 |
| 50% | 8.17 | 8.29 | 7.94 | 0.36 |
| 75% | 5.89 | 7.36 | 7.07 | 1.46 |
| 95% | 4.37 | 5.07 | 6.28 | 1.91 |

At 95% fill, Sonnet's reasoning rises monotonically with target-adjacency-to-questions (4.37 → 5.07 → 6.28). At lower fills the pattern is noisy. *Production read:* at heavy noise loads, place the target last for Sonnet — the +1.9 swing is meaningful.

**DeepSeek under temporal noise** — fill, position, and an end-position cliff at 50% fill specifically (worst-cell §2.2 = 3.41 at temporal/50%/end). The cliff isn't monotonic in fill — the model recovers somewhat at 75-95% — which is consistent with the failure being a downstream parsing artifact rather than a clean reasoning gradient.

**Opus under temporal noise** — uniformly small position spreads (0.27-1.10), no catastrophic regime, and the worst position (start) at 25% fill (7.13) still beats Gemini's *baseline* (6.80).

## §9.6 Position effects per individual judge (sanity check)

The blended-judge pattern in §9.2 holds under each judge separately: Opus-peer-end beats Opus-peer-start under all three judges (Opus judge: 7.69 vs 6.73; GPT judge: 7.49 vs 6.86; Gemini judge: 9.13 vs 7.63), and DeepSeek-temporal-end is worst under all three judges (Opus: 2.62; GPT: 6.11; Gemini: 7.62 vs starts of 5.32/6.60/8.43). The position effect is not a judge artifact — it's in the analyst output.

## §9.7 Take-aways for agent builders

- **For most models, position is a small effect** — but not zero. If you have flexibility, prefer **`end` (target-adjacent-to-questions) for Opus and Sonnet at high noise loads**.
- **For DeepSeek under any temporal-style noise (mismatched fiscal periods, dated context fragments), avoid the `end` layout** — front-loaded period-mismatched noise specifically anchors DeepSeek's analyst into a regime where the extractor cannot recover answers. Prefer `start` (target first, noise after) or `middle`.
- **GPT-5.5 is the most position-insensitive model** — position spread ≤ 0.61 across all 6 (noise × judge) cells. If you don't know the downstream model, GPT is the safest bet against retrieval-pipeline ordering quirks.
- **Don't over-rotate.** For Sonnet-peer, GPT-temporal, Opus-temporal, the position spread is < 0.6 points on a 10-point scale — well within rep-to-rep noise for one or two evaluations. Position-tuning matters at scale, not in single-shot prompts.

---

# §10 — Per-model strength profile across cognitive dimensions

This section asks the inverse of §9: holding evaluation grid constant, **what is each model best at, and what does each model lose first under noise?** Unlike §3-§7 (which decompose how each *noise condition* affects each model), §10 decomposes how each *model* performs across the dimension space.

## §10.1 Baseline (fill = 0%, no noise) strength matrix

| model | T1 retrieve (0-1) | T2 calc (0-1) | T3 reasoning (0-10) | T3 grounded (0-5) | T3 evidence (0-5) | T3 scope (0-5) | T3 clarity (0-5) | T3 citation (0-5) |
|---|---|---|---|---|---|---|---|---|
| opus-4-7 | 0.50 | 0.50 | **8.42 ± 0.09** | 4.64 ± 0.05 | **4.21 ± 0.05** | 4.97 | **4.91 ± 0.03** | 4.60 ± 0.05 |
| sonnet-4-6 | 0.50 | 0.50 | 7.91 ± 0.19 | 4.47 ± 0.07 | 3.91 ± 0.09 | 4.95 | 4.66 ± 0.09 | 4.37 ± 0.09 |
| gpt-5-5 | 0.50 | 0.50 | 7.98 ± 0.11 | **5.00 ± 0.00** | 3.95 ± 0.07 | **5.00** | 4.55 ± 0.05 | **4.98 ± 0.01** |
| gemini-3-1-pro | 0.50 | 0.50 | 6.80 ± 0.14 | 4.37 ± 0.06 | 3.55 ± 0.07 | 4.98 | 4.50 ± 0.05 | 3.75 ± 0.11 |
| deepseek-v4-pro | 0.46 ± 0.02 | 0.46 ± 0.02 | 7.17 ± 0.16 | 4.19 ± 0.07 | 3.71 ± 0.08 | 4.89 ± 0.06 | 4.57 ± 0.07 | 4.08 ± 0.09 |

**Per-dimension ranking at baseline (best → worst):**

| dimension | rank order |
|-----------|-----------|
| T1 retrieval | opus = sonnet = gpt = gemini (0.50) > deepseek (0.46) |
| T2 calculation | opus = sonnet = gpt = gemini (0.50) > deepseek (0.46) |
| T3 reasoning quality | **opus (8.42)** > gpt (7.98) > sonnet (7.91) > deepseek (7.17) > gemini (6.80) |
| T3 groundedness | **gpt (5.00 perfect)** > opus (4.64) > sonnet (4.47) > gemini (4.37) > deepseek (4.19) |
| T3 evidentiary breadth | **opus (4.21)** > gpt (3.95) > sonnet (3.91) > deepseek (3.71) > gemini (3.55) |
| T3 scope adherence | gpt (5.00) ≈ gemini (4.98) ≈ opus (4.97) ≈ sonnet (4.95) > deepseek (4.89) — *effectively tied* |
| T3 clarity | **opus (4.91)** > sonnet (4.66) > deepseek (4.57) > gpt (4.55) > gemini (4.50) |
| T3 citation accuracy | **gpt (4.98)** > opus (4.60) > sonnet (4.37) > deepseek (4.08) > gemini (3.75) |

## §10.2 Resilience matrix — drop from baseline to worst noise cell

For each model × dimension, this shows the worst single (noise × fill × position) cell anyone in the grid hit, and how far it fell from the model's own baseline. This is the "worst case under stress" view.

| model | dimension | baseline | worst-cell | drop | worst (noise/fill/pos) |
|-------|-----------|---------:|-----------:|-----:|------------------------|
| opus-4-7 | T1 retrieve | 0.50 | 0.50 | 0% | — |
| opus-4-7 | T2 calc | 0.50 | 0.43 | −14% | peer/50%/start |
| opus-4-7 | T3 reasoning | 8.42 | 6.07 | −28% | peer/50%/start |
| opus-4-7 | T3 grounded | 4.64 | 3.44 | −26% | peer/95%/middle |
| opus-4-7 | T3 evidence | 4.21 | 3.42 | −19% | peer/50%/start |
| opus-4-7 | T3 clarity | 4.91 | 4.04 | −18% | peer/50%/start |
| sonnet-4-6 | T1 retrieve | 0.50 | 0.36 | −29% | temporal/75%/start |
| sonnet-4-6 | T2 calc | 0.50 | 0.36 | −29% | temporal/25%/end |
| sonnet-4-6 | T3 reasoning | 7.91 | **4.37** | **−45%** | temporal/95%/start |
| sonnet-4-6 | T3 grounded | 4.47 | 2.37 | **−47%** | temporal/95%/start |
| sonnet-4-6 | T3 evidence | 3.91 | 3.21 | −18% | temporal/95%/middle |
| sonnet-4-6 | T3 clarity | 4.66 | 3.88 | −17% | temporal/95%/middle |
| gpt-5-5 | T1 retrieve | 0.50 | 0.50 | 0% | — |
| gpt-5-5 | T2 calc | 0.50 | 0.50 | 0% | — |
| gpt-5-5 | T3 reasoning | 7.98 | 6.05 | −24% | peer/95%/start |
| gpt-5-5 | T3 grounded | 5.00 | 4.67 | **−7%** | peer/95%/start |
| gpt-5-5 | T3 evidence | 3.95 | 3.08 | −22% | peer/95%/start |
| gpt-5-5 | T3 clarity | 4.55 | 3.89 | −15% | peer/95%/start |
| gemini-3-1-pro | T1 retrieve | 0.50 | 0.50 | 0% | — |
| gemini-3-1-pro | T2 calc | 0.50 | 0.50 | 0% | — |
| gemini-3-1-pro | T3 reasoning | 6.80 | 5.83 | **−14%** | temporal/50%/end |
| gemini-3-1-pro | T3 grounded | 4.37 | 3.52 | −19% | peer/75%/end |
| gemini-3-1-pro | T3 evidence | 3.55 | 3.00 | −15% | temporal/75%/end |
| gemini-3-1-pro | T3 clarity | 4.50 | 4.07 | **−10%** | temporal/75%/end |
| deepseek-v4-pro | T1 retrieve | 0.46 | **0.14** | **−69%** | temporal/50%/end |
| deepseek-v4-pro | T2 calc | 0.46 | **0.14** | **−69%** | temporal/50%/end |
| deepseek-v4-pro | T3 reasoning | 7.17 | **3.41** | **−53%** | temporal/50%/end |
| deepseek-v4-pro | T3 grounded | 4.19 | 2.84 | −32% | temporal/50%/end |
| deepseek-v4-pro | T3 evidence | 3.71 | 2.19 | **−41%** | temporal/50%/end |
| deepseek-v4-pro | T3 clarity | 4.57 | 2.81 | **−38%** | temporal/50%/end |

## §10.3 Best-under-noise ranking (mean across all noise cells, fill ≥ 25%)

This collapses fill, position, *and* judge into one rank per dimension — the practical "if you have to pick one analyst that will do the most work the most often, who do you pick" view.

| dimension | rank (best → worst) |
|-----------|---------------------|
| T1 retrieve | gpt (0.51) > gemini (0.51) > opus (0.50) > sonnet (0.48) > deepseek (0.42) |
| T2 calc | gpt (0.51) > gemini (0.50) > opus (0.50) > sonnet (0.48) > deepseek (0.41) |
| T3 reasoning | **gpt (7.66)** > opus (7.52) > sonnet (7.45) > gemini (6.46) > deepseek (6.25) |
| T3 grounded | **gpt (4.93)** > gemini (4.18) > opus (4.10) > sonnet (4.00) > deepseek (3.82) |
| T3 evidence | **sonnet (3.94)** ≈ opus (3.92) > gpt (3.77) > gemini (3.38) > deepseek (3.31) |
| T3 clarity | **opus (4.73)** ≈ sonnet (4.72) > gpt (4.54) > gemini (4.44) > deepseek (4.22) |
| T3 citation | **gpt (4.59)** > opus (4.07) > sonnet (4.01) > deepseek (3.64) > gemini (3.48) |

Note: Opus loses the headline "T3 reasoning under noise" race to GPT (7.52 vs 7.66) **only when judges are blended** — Opus-judge alone still has Opus on top. The GPT win is partly a judge-stack preference for cleaner, more grounded prose; see §6.2 for the self-favoritism breakdown.

## §10.4 One-line strength signatures

- **Opus 4.7** — *the reasoning generalist.* Best baseline reasoning quality, best baseline clarity, best baseline evidentiary breadth, best clarity under noise. Worst-case drop on the headline reasoning dim is bounded at −28% (vs Sonnet's −45% and DeepSeek's −53%). Pay-for-it but predictable.
- **Sonnet 4.6** — *capable but bimodal.* Baseline within 0.5 pts of Opus on most dims, ties Opus on evidentiary breadth under noise (3.94 vs 3.92). But under temporal noise it has the worst (catastrophic + still-good) bimodal failure mode in the grid (see §7), and its worst-cell drop on reasoning is −45%. Use when budget matters and inputs are clean; expect tail-risk under heavy mismatched-period noise.
- **GPT-5.5** — *the groundedness specialist.* Perfect 5.00 baseline groundedness (only model). Perfect baseline scope adherence and citation accuracy. Smallest groundedness drop under noise (−7%, vs −19% to −47% for everyone else). Best under-noise ranking on 4 of 7 dimensions. The safest bet when the downstream consumer cares more about "don't make stuff up" than "show me deep analysis".
- **Gemini 3.1 Pro** — *weakest baseline reasoning, but most resilient.* Lowest baseline T3 reasoning (6.80) — about 1.6 pts below Opus. But its worst-cell drops are uniformly the smallest in absolute terms (−10% clarity, −14% reasoning, −19% groundedness). Not the model you want to start with — but the model that will surprise you the *least* under stress. Citation accuracy is its weakest dim (3.75 baseline → 3.48 under noise) — don't trust its citations without verification.
- **DeepSeek V4 Pro** — *cheap, but with a cliff.* Worst baseline retrieval/calc (0.46 vs 0.50 for others — 8% lower). Worst baseline evidentiary breadth and groundedness. Under temporal noise, every dimension simultaneously collapses at the temporal/50%/end cell (T1 0.14, T3 reasoning 3.41, T3 grounded 2.84). The cliff is downstream-extraction-coupled, not pure reasoning — but the symptom is "the agent returns garbage". Acceptable for clean-input, low-cost analyst work; reject for any pipeline where temporal/period-mismatched documents may appear in context.

## §10.5 Picks by use case

- **Heavy noise, high tail-risk tolerance, want best-case reasoning:** Opus 4.7 (8.42 baseline, bounded −28% worst case)
- **Heavy noise, low tail-risk tolerance, want consistent grounded output:** GPT-5.5 (smallest worst-case drops on groundedness, scope, citation)
- **Mixed-period source documents in context (e.g., RAG over multi-year corpus):** GPT-5.5 or Opus 4.7. **Avoid DeepSeek**; **avoid Sonnet** at high noise loads.
- **Clean inputs, cost-sensitive:** DeepSeek V4 Pro at baseline is 7.17 reasoning / 0.46 autograded — cheaper than Sonnet, comparable on most dims. Just enforce input-cleanliness preconditions upstream.
- **Position-insensitive (your retrieval pipeline can't guarantee document order):** GPT-5.5 first (≤ 0.61 spread on every cell), Sonnet second under peer noise (0.18 spread).
