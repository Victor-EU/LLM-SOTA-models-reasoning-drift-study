# Qualitative Findings — Reasoning Drift Study

**Status:** PRE-JUDGE OBSERVATIONS. Raw analyst telemetry only.
**Date:** 2026-04-26
**Methodology:** v2 (`pre_registration.v2.lock`, hash `3433f4a6...`); v1 arms grandfathered per `v1_arms_inheritance` rule
**Scope:** 5 analyst arms × 91 runs each = 455 runs total

---

## 1. Headline finding

Five top-tier reasoning models, given byte-identical prompts at five context-fill levels (0%, 25%, 50%, 75%, 95%), exhibit **qualitatively divergent behavior on the primary endpoint** — the slope of thinking-token allocation across context fill ranges from **+87%** to **−35%** between the most and least context-additive arms.

| arm | thinking @ baseline | thinking @ fill=0.95 | Δ | direction |
|---|---|---|---|---|
| **opus-4-7** | 2,417 | 4,524 | **+87.2%** | ↑↑ adds reasoning under load |
| gemini-3-1-pro | 4,029 | 4,628 | +14.9% | ↑ adds slightly |
| deepseek-v4-pro | 4,366 | 4,268 | −2.3% | → flat |
| sonnet-4-6 | 18,589 | 14,061 | −24.4% | ↓ disengages |
| **gpt-5-5** | 9,670 | 6,289 | **−35.0%** | ↓↓ disengages strongly |

The slope direction is not predicted by vendor, by absolute thinking level, or by "reasoning-class" membership. All five arms ran with vendor-native max thinking effort (Anthropic max, OpenAI xhigh, Gemini HIGH, DeepSeek max).

---

## 2. The full per-fill profile

Mean thinking_tokens by fill, averaged across positions × reps within each fill bin (n=21 per fill except baseline n=7).

| fill | opus-4-7 | sonnet-4-6 | gpt-5-5 | gemini-3-1-pro | deepseek-v4-pro |
|---|---|---|---|---|---|
| 0.00 | 2,417 | 18,589 | 9,670 | 4,029 | 4,366 |
| 0.25 | 3,555 | 14,049 | 9,136 | 3,917 | 4,783 |
| 0.50 | 4,502 | 18,597 | 7,764 | 4,176 | 4,420 |
| 0.75 | 4,331 | 13,844 | 6,624 | 4,421 | 4,649 |
| 0.95 | 4,524 | 14,061 | 6,289 | 4,628 | 4,268 |

Opus 4.7 and Gemini 3.1 Pro show monotonic increase. GPT-5.5 shows monotonic decrease. Sonnet 4.6 oscillates within a ~5K-token band but trends down. DeepSeek V4 Pro is essentially flat with shallow internal variation.

---

## 3. Internal corroboration — three signals agree per arm

If thinking-token slope were a measurement artifact (tokenizer asymmetry, billing semantics, vendor-specific accounting), it would not be expected to correlate with behavior measured on independent dimensions. **It does.** Within each arm, thinking, output, and latency share the same direction across the fill range:

| arm | Δ thinking | Δ output | Δ latency |
|---|---|---|---|
| opus-4-7 | +87.2% | +24.9% | +26.3% |
| gemini-3-1-pro | +14.9% | +8.0% | +7.0% |
| deepseek-v4-pro | −2.3% | −7.6% | −9.4% |
| sonnet-4-6 | −24.4% | −20.4% | −19.8% |
| gpt-5-5 | −35.0% | −21.9% | −32.8% |

Output tokens are independently reported by the API and not derived from thinking. Latency is wall-clock from request to last byte. The triple-agreement across all five arms makes the slope direction a behavioral signal, not an accounting quirk.

---

## 4. Two dimensions that should NOT be conflated

**Absolute thinking level vs context-sensitivity of thinking are independent dimensions.**

- Sonnet 4.6 thinks ~3-4× more than Opus 4.7 across all fills, but their slopes go in opposite directions.
- Gemini 3.1 Pro thinks the least at fill=0% but adds the second-most under load (in % terms).
- "How much a model thinks" and "how a model adapts thinking to context" are orthogonal model properties.

This matters for any cross-arm "reasoning effort" benchmark that reports a single number per model.

---

## 5. Position effects (descriptive)

Mean thinking_tokens at fill=0.95, broken down by target position within the assembled prompt:

| arm | start | middle | end |
|---|---|---|---|
| opus-4-7 | 5,450 | 5,197 | 2,925 |
| sonnet-4-6 | 13,514 | 12,249 | 16,418 |
| gpt-5-5 | 5,555 | 6,235 | 7,077 |
| gemini-3-1-pro | 5,616 | 3,880 | 4,390 |
| deepseek-v4-pro | 3,545 | 4,938 | 4,320 |

No consistent cross-arm pattern. Some arms (opus, gemini) appear to think more when target is at the start; others (gpt-5-5) appear to think more when target is at the end. Sonnet shows U-shape with end-heavy bias. Position effects exist but do not factor into the headline slope direction.

---

## 6. Within-cell rep variance (noise floor for slope detection)

Within each cell (fixed materials, fixed noise pack — see §8.3), the 7 reps differ only in question-block ordering and analyst stochasticity (temperature=1.0). Coefficient of variation in thinking_tokens, averaged across the 12 noise cells per arm:

| arm | avg within-cell CV |
|---|---|
| gpt-5-5 | 19.9% |
| gemini-3-1-pro | 24.5% |
| deepseek-v4-pro | 38.9% |
| sonnet-4-6 | 41.4% |
| opus-4-7 | 51.2% |

The slope magnitudes in §1 (87%, 35%) sit comfortably above the within-cell rep noise floor for all five arms — directionally interpretable without formal significance testing. Arms with higher CV (opus, sonnet) need more reps for tight cell-level estimates; the +87% Opus slope is detectable through that noise; a hypothetical ±10% slope on Opus would not be.

---

## 7. What this finding does NOT yet show

**Answer quality.** Thinking-token allocation is an *input behavior*, not an output property. A model that disengages reasoning under load may still answer correctly (efficient retrieval); a model that reasons more under load may hallucinate more (motivated confabulation). The judge-stage analysis (Opus 4.7 max as primary, Sonnet 4.6 high as 20% subsample) on the extracted answers is required to map thinking-token slope to *correctness drift*. That stage has not been run.

**Causal mechanism.** This is observational data on five proprietary models. Slope differences may reflect training-data composition, RLHF reward shaping, post-training reasoning curricula, runtime budget enforcement, vendor-specific "thinking_effort" implementation, or interactions among these. The data does not adjudicate.

**Generalization beyond MSFT 10-K + earnings call.** The full v2 grid runs against one target company. Single-target findings are not single-domain findings — additional companies are not in the v2 lock and would require a v3.

---

## 8. Provenance

### 8.1 Methodology lock

| arm | pre_registration_hash | locked under |
|---|---|---|
| opus-4-7 | `61b2d30f...` | v1 (`pre_registration.lock`) |
| sonnet-4-6 | `61b2d30f...` | v1 (grandfathered into v2 per `v1_arms_inheritance`) |
| gpt-5-5 | `3433f4a6...` | v2 (`pre_registration.v2.lock`) |
| gemini-3-1-pro | `3433f4a6...` | v2 |
| deepseek-v4-pro | `3433f4a6...` | v2 |

v2 hash covers `DESIGN.md + PROMPTS.md + RUBRIC.md + MULTI_VENDOR_ADDENDUM.md` concatenated as raw bytes. Reproduce: see `pre_registration.v2.lock` field `methodology_hash_reproduce`.

### 8.2 Materials

`materials/materials.lock.json`, sha256 `c13b5514...`. Target: MSFT 10-K (FY2025) + Q2 FY2026 earnings call. Noise pool: 7 peer 10-Ks (aapl, amzn, crm, googl, meta, nvda, orcl). Identical across all 5 arms; no rehash between v1 and v2.

### 8.3 Cross-arm prompt equivalence

Verified empirically. At cell `c_MSFT_50_middle_*`, rep 0:
- v1 Opus 4.7: noise pack `['meta_10k_fy2025', 'meta_10k_fy2025']`, anthropic_realized=440,525
- v2 GPT-5.5 at the same cell+rep: identical noise pack, identical anthropic_realized=440,525
- The `judge_primary` tokenizer fallback in `harness/src/tokens.py:111-115` makes non-Anthropic analysts see byte-identical assembled prompts to v1 Opus at every (cell, rep) coordinate.

Sonnet 4.6 is a partial exception: v1 used Sonnet's own count_tokens for budget convergence (the v2 fallback didn't yet exist), so Sonnet's noise packs differ from Opus's at the same coordinates. Sonnet's slope direction is internally valid; cross-arm comparisons involving Sonnet against the other four are "same target fraction, different content," not "same content."

### 8.4 Validator policy

DESIGN §7.5, implemented in `harness/src/validation.py`. Exclusions: HTTP error not retried, output coverage <50% of questions, fill delta > tolerance with pool available. Flags (not exclusions): `pool_exhausted`, `malformed_json`, `partial_answers`, `truncated`, `baseline`. **Zero exclusions across all 455 runs.** Pool-exhausted flag fires on 84/84 noise runs per arm — the pre-registered normal regime.

### 8.5 Run-level integrity

| arm | runs | excl | mal_json | pool_exhaust | total cost |
|---|---|---|---|---|---|
| opus-4-7 | 91 | 0 | 2 | 84 | $333.85 |
| sonnet-4-6 | 91 | 0 | 6 | 84 | $217.08 |
| gpt-5-5 | 91 | 0 | 0 | 84 | $109.40 |
| gemini-3-1-pro | 91 | 0 | 0 | 84 | $35.20 |
| deepseek-v4-pro | 91 | 0 | 1 | 84 | $14.47 |

All raw runs persisted under `arms/<arm>/data/raw/*.jsonl`.

---

## 9. Methodology disclosures

### 9.1 "Vendor max" is not equivalent across vendors

Per MULTI_VENDOR_ADDENDUM §3, the cross-vendor thinking-token column is descriptive only. Anthropic's `thinking_effort=max`, OpenAI's `reasoning.effort=xhigh`, Gemini's `thinking_level=HIGH`, and DeepSeek's `reasoning_effort=max` are each the top of their respective vendor enums but represent different internal compute-budget constructs. The headline finding is about *slope across fill within an arm*, not absolute thinking-token comparisons across arms.

### 9.2 Lock-prose vs implementation discrepancy on noise seeding

The v1 + v2 lock prose states: `noise_seeding_scheme: sha256(report|fill|position|rep)`. The implementation in `harness/src/assembly.py:229,234` seeds noise on `cell_id` only — `rep_idx` does not enter the noise seed. Reps within a cell therefore receive byte-identical noise packs and vary only in question-block ordering and analyst stochasticity. v1 was published under this implementation; v2 inherits for cross-arm comparability. **The lock prose should be corrected at the next addendum revision.** This does not affect the §1 finding — replicate variance is purely on the analyst-output side, which is what we want to measure.

### 9.3 Tokenizer asymmetry

§4 of the addendum disclosed expected tokenizer ratios for non-Anthropic vendors. The full-grid data confirms ratios stable across fill levels (0.62-0.69 across all fill heights), validating that `judge_primary`-based fill targeting works as intended. The §4 caveat ("ratio measured at baseline only — pilot will confirm") can be retired at the next revision.

---

## 10. Next steps before this becomes a publishable finding

1. **Extractor** (`claude-haiku-4-5-20251001`, held constant across arms) on the 273 new raw responses (3 arms × 91).
2. **Judge primary** (`claude-opus-4-7` max thinking) on extracted answers, all 5 arms.
3. **Judge secondary** (`claude-sonnet-4-6` high thinking) on a 20% subsample for instrument-bias validation.
4. **arm.lock.json** for each of the 3 v2 arms — capture `execution_results`, `system_fingerprints_observed`, `data_integrity` sha256s, git anchor.
5. **Cross-arm formal analysis** via `compare_arms.py` — answer-quality drift slope per arm, mapped against the thinking-token slope reported here.

The §1 qualitative finding may strengthen, weaken, or invert at the answer-quality level. Possibilities:
- **Strengthen:** GPT-5.5's negative thinking slope tracks a negative correctness slope → context-load impairs reasoning models in proportion to their disengagement.
- **Decouple:** GPT-5.5's negative thinking slope yields *flat* correctness → the model has slack reasoning capacity at baseline that it sheds without quality loss under load.
- **Invert:** Opus 4.7's positive thinking slope yields a *negative* correctness slope → motivated reasoning failure mode where more thinking under load produces *worse* answers.

Each is a publishable finding in a different direction. The judge stage adjudicates.

---

*Working document. Numbers above are reproducible from `arms/<arm>/data/raw/*.jsonl` with the aggregator at `pre_judge_aggregate.py` (or inline Python — see git history for this file).*
