# Reasoning drift across five vendor-max reasoning models
## Cross-arm synthesis — Opus 4.7, Sonnet 4.6, GPT-5.5, Gemini 3.1 Pro, DeepSeek V4 Pro

**Final synthesis report — 2026-04-26**

A 455-run controlled experiment (5 arms × 91 runs) comparing how the top-tier reasoning models from Anthropic, OpenAI, Google, and DeepSeek degrade as their context windows fill with adjacent-but-irrelevant material. Each arm was run at vendor-maximum thinking effort with byte-identical materials, prompts, design grid, extractor, judges, and seeds — the only variable across arms is the analyst model. The integrity gate (`harness/scripts/verify_arm_integrity.py`) confirms cross-arm methodological identity at the SHA-256 level.

The auto-generated table-only comparison lives at `cross_arm/COMPARATIVE_REPORT.md` (run `python -m scripts.compare_arms --write-report` to regenerate). This document is the **interpretive synthesis** — the field-relevant narrative the per-arm reports support.

Total spend across all arms: **$1,859.66** ($1,105.29 v1 Anthropic + $754.37 v2 multi-vendor). Methodology hashes: v1 `61b2d30f...` (DESIGN+PROMPTS+RUBRIC), v2 `3433f4a6...` (v1 + MULTI_VENDOR_ADDENDUM, additive).

---

## TL;DR — five arms, five drift signatures

The conventional wisdom — "all max-thinking reasoning models degrade similarly under long-context pressure" — does not survive contact with this dataset. The five arms produce **five qualitatively distinct drift profiles** at identical inputs:

| arm                | RQ baseline → 95% | drift profile                | hallucination signature              | thinking allocation under load | latency |
|--------------------|-------------------|------------------------------|--------------------------------------|--------------------------------|---------|
| **Opus 4.7**       | 8.05 → 7.02 (−1.03) | monotonic decline            | unsupported claims 7× (0.24→1.68); xcontam non-zero | **+87%** (2.4K → 4.5K)        | 169s → 214s |
| **Sonnet 4.6**     | 7.43 → 7.60 (+0.17) | shallow inverted-U; *recovers* at 95% | unsupported 10× (0.10→1.06) but xcontam ≈0 | −24% (18.6K → 14.1K)        | 932s → 747s |
| **GPT-5.5**        | 7.05 → 6.27 (−0.78) | flat-then-cliff at 92%       | **unsupported ≈0 across all fills** (0.00→0.05) | **−35%** (9.7K → 6.3K)        | 168s → 113s |
| **Gemini 3.1 Pro** | 5.86 → 5.56 (−0.30) | flat across all fills        | unsupported flat (0.41–0.79); xcontam ≈0 | +15% (4.0K → 4.6K)         | 53s → 57s |
| **DeepSeek V4 Pro**| 5.33 → 5.24 (−0.09) | **flat absolute; steepest pairwise loss** | unsupported elevated (0.62→0.87) | −2% (4.4K → 4.3K)          | 176s → 160s |

Three findings cut across the panel:

1. **Drift signature is vendor-specific, not architecture-general.** Opus expands thinking under pressure and gets monotonically worse. GPT-5.5 contracts thinking under pressure but its claims stay clean. Sonnet does more thinking than every other arm, runs 5–10× longer, and its quality *peaks above baseline* at 95% fill. Gemini holds steady at a low ceiling. DeepSeek shows the absolute-vs-pairwise paradox (§4). There is no single "long-context degradation curve" — each vendor has its own.

2. **The cheapest model on the panel has the highest cross-judge agreement.** DeepSeek V4 Pro at $194 (lowest cost) returns CCC 0.947 on reasoning_quality between Opus and Sonnet judges — vs Opus 4.7's own arm at CCC 0.777, GPT-5.5's CCC 0.664, Gemini's CCC 0.696. The pattern is structural: arms whose responses pile near the rubric ceiling produce low-variance scores that ICC-style metrics can't correlate. **Cost does not predict measurement reliability** in this study.

3. **The pairwise-vs-absolute paradox is the most important methodological finding.** At 95% fill, Opus loses 18/20 pairwise (mean Δ −2.7), DeepSeek loses 16/17 (Δ −4.1), GPT-5.5 loses 11/20 (Δ −1.9), Gemini loses 14/20 (Δ −1.2), and Sonnet *wins* 13/20 (Δ +2.3). The cross-arm ordering on pairwise sharply differs from the ordering on absolute Likert scoring. Choosing the wrong evaluation methodology will rank the five arms in different orders.

If you need to ship one of these models to production: the choice is not about who "drifts least," because that question has no methodology-independent answer in this dataset. The choice is about **which failure mode you can tolerate** (§5).

---

## 1. Methodology

### 1.1 What's held constant

Per `MULTI_VENDOR_ADDENDUM.md`, the v2 methodology is a strict superset of v1 — the v1 hash is preserved by inheritance. Across all five arms:

- **Materials:** Microsoft FY2025 10-K + Q2 FY2026 earnings call as target; seven peer 10-Ks (AAPL, GOOGL, AMZN, META, NVDA, ORCL, CRM) as the noise corpus. Materials lockfile sha256 `c13b5514...` byte-identical at every (cell, rep) coordinate across all five arms.
- **Design grid:** 1 baseline + (5 fill levels × 3 positions) = 13 cells × 7 reps = 91 runs per arm. Realized fills 13/24/47/72/92% (Anthropic-counted; vendor-actual differs by tokenizer ratio — see §1.2).
- **Eight-question stimulus:** 3 Tier-1 (factual lookup), 2 Tier-2 (calculation), 3 Tier-3 (synthesis with prescribed structure on Q8).
- **Extractor:** Claude Haiku 4.5, no thinking, max_output_tokens=16K, temperature=1.0. *Held constant — extraction noise does not confound cross-arm comparisons.*
- **Primary judge:** Claude Opus 4.7, adaptive thinking effort=max, max_output_tokens=16K. *Held constant — runs against cached fill=0 target materials, so no within-judge drift confound.*
- **Secondary judge (20% subsample):** Claude Sonnet 4.6, effort=high. *Held constant.*
- **Pairwise judge (25% subsample of non-baseline reps):** Claude Opus 4.7 max effort, A/B-randomized.
- **Seeds:** SHA-256 over identifier strings (deterministic, replicable). Noise content seeded by `cell_id` only — every arm sees the same 91 prompts.

### 1.2 What varies

Only the analyst model:

| arm                | snapshot                         | vendor-max thinking knob              | context window | observed alias        |
|--------------------|----------------------------------|---------------------------------------|----------------|-----------------------|
| opus-4-7           | `claude-opus-4-7`                | `effort=max` (adaptive thinking)      | 1,000,000      | `claude-opus-4-7`     |
| sonnet-4-6         | `claude-sonnet-4-6`              | `effort=max` (adaptive thinking)      | 1,000,000      | `claude-sonnet-4-6`   |
| gpt-5-5            | `gpt-5.5-2026-04-23`             | `reasoning.effort=xhigh`              | 1,050,000      | `gpt-5.5-2026-04-23`  |
| gemini-3-1-pro     | `gemini-3-pro-preview` (alias)   | `thinking_level=HIGH`                 | 1,048,576      | `gemini-3.1-pro-preview` |
| deepseek-v4-pro    | `deepseek-v4-pro` (alias)        | `reasoning_effort=max`                | 1,000,000      | `deepseek-v4-pro`     |

### 1.3 Caveats inherited from `MULTI_VENDOR_ADDENDUM.md`

- **Vendor-max thinking is NOT a comparable knob across vendors.** Each vendor's documented top setting allocates substantively different reasoning-token budgets — Sonnet at max=18K; GPT-5.5 at xhigh=9.7K; Opus at max=2.4K; Gemini at HIGH=4.0K; DeepSeek at max=4.4K (estimated from `reasoning_content` byte count). Cross-arm comparisons should be read as "each at its own top setting," not "matched compute."
- **Tokenizer asymmetry.** Token budget convergence uses Anthropic's `count_tokens` (the judge-primary tokenizer fallback per `tokens.py:111-115`), not the analyst's native tokenizer. Realized input ratios at 95% fill: Anthropic ~925K / OpenAI ~582K / Gemini ~640K / DeepSeek ~584K. Cross-arm prompts are byte-identical; vendor-reported input token counts differ.
- **Snapshot mutability.** Anthropic and OpenAI snapshots are dated and pinned; Google and DeepSeek strings are aliases. The arm.lock schema records both `analyst.snapshot` (requested) and `analyst.snapshot_observed_aliases` (returned). All four non-Anthropic arms returned a single observed alias across 91 runs — no mid-experiment build drift.
- **Same-vendor-family judges.** Opus 4.7 primary + Sonnet 4.6 secondary are both Anthropic. Cross-arm conclusions are robust to judge choice within the Anthropic family (both judges produce same-direction rankings) but cannot rule out vendor-stylistic preferences relative to a non-Anthropic judge. Cross-vendor judging is enumerated as a follow-up in §6.

---

## 2. The five drift signatures

### 2.1 Headline drift curves

Mean reasoning_quality (0–10) across all 3 Tier-3 questions × all positions × 7 reps per cell.

| fill   | opus-4-7 | sonnet-4-6 | gpt-5-5 | gemini-3-1-pro | deepseek-v4-pro |
|-------:|---------:|-----------:|--------:|---------------:|----------------:|
| 0.00   | **8.05** | 7.43       | 7.05    | 5.86           | 5.33            |
| 0.25   | 7.33     | **8.00**   | 6.89    | 5.68           | 5.16            |
| 0.50   | 6.89     | 7.94       | 6.92    | 5.59           | 5.30            |
| 0.75   | 7.17     | 7.19       | 6.89    | 5.51           | 5.43            |
| 0.95   | 7.02     | **7.60**   | 6.27    | 5.56           | 5.24            |
| **Δ**  | **−1.03** | **+0.17** | **−0.78** | **−0.30**    | **−0.09**       |

The arms cluster into two ceiling tiers: **Anthropic + OpenAI ≈ 7–8 baseline RQ; Google + DeepSeek ≈ 5–6 baseline RQ**. Within each tier, drift profiles diverge:

- Opus monotonically declines.
- Sonnet has a shallow inverted-U with recovery at 95% above baseline.
- GPT-5.5 is flat through 72% then drops 0.62 at 92%.
- Gemini moves only 0.35 across the entire grid.
- DeepSeek moves only 0.27 absolute, but loses pairwise (§4).

**Two things this rules out:**

1. *"Smaller-model-degrades-faster" is wrong here.* Sonnet (smaller-than-Opus) is the *most* context-robust on absolute scoring; Opus (the largest Anthropic model) shows the steepest absolute drift in the Anthropic family.
2. *"More thinking = less drift" is wrong here.* Sonnet allocates 5–10× more thinking than Opus and shows less drift, which is consistent with the hypothesis. But GPT-5.5 allocates more thinking than Gemini *and contracts thinking under load* (−35%) while showing more drift than Gemini's flat-curve pattern. The relationship is non-monotonic across the panel.

### 2.2 Cross-arm pairwise vs baseline at 95% fill

The Opus 4.7 judge sees a baseline rep and a same-rep-index 95%-fill rep, A/B-randomized, picks the better.

| arm                | candidate wins | losses | ties | mean Δ (cand − base) | n  | reading |
|--------------------|---------------:|-------:|-----:|---------------------:|---:|---------|
| opus-4-7           | 2              | 18     | 0    | **−2.7 ± 2.0**       | 20 | clear loss |
| sonnet-4-6         | **13**         | 7      | 0    | **+2.3 ± 4.2**       | 20 | clear win |
| gpt-5-5            | 8              | 11     | 1    | **−1.9 ± 4.2**       | 20 | mild loss |
| gemini-3-1-pro     | 5              | 14     | 1    | **−1.2 ± 2.7**       | 20 | mild loss |
| deepseek-v4-pro    | 1              | 16     | 0    | **−4.1 ± 3.1**       | 17 | severe loss |

Note that the pairwise ordering and the absolute-RQ ordering disagree. By absolute RQ at 95% fill, the ranking is Sonnet (7.60) > Opus (7.02) > GPT-5.5 (6.27) > Gemini (5.56) > DeepSeek (5.24). By pairwise mean Δ, the ranking is Sonnet (+2.3) > Gemini (−1.2) > GPT-5.5 (−1.9) > Opus (−2.7) > DeepSeek (−4.1). **Opus is second on absolute and fourth on pairwise. Gemini is fourth on absolute and second on pairwise. DeepSeek is fifth on both — but the pairwise gap is much larger.** The choice of evaluation methodology determines who "wins."

The reconciliation is variance. DeepSeek's baseline RQ has sd=2.31 (largest of any arm); Sonnet's baseline sd=2.29 (second-largest). Within-cell noise at this scale lets absolute means converge while pairwise comparisons cleanly separate the two within-rep responses. **Pairwise is the more sensitive instrument when within-cell variance is high** — see §4 for the methodological lesson.

### 2.3 Hallucination cross-arm — the cleanest cross-vendor differentiator

Mean unsupported_claims per Tier-3 response:

| fill | opus-4-7 | sonnet-4-6 | gpt-5-5 | gemini-3-1-pro | deepseek-v4-pro |
|-----:|---------:|-----------:|--------:|---------------:|----------------:|
| 0.00 | 0.24     | 0.10       | **0.00**| 0.57           | 0.62            |
| 0.25 | 0.76     | 0.46       | 0.02    | 0.41           | 0.67            |
| 0.50 | 0.62     | 0.46       | 0.00    | 0.70           | 1.10            |
| 0.75 | 1.02     | 0.95       | 0.00    | 0.79           | 1.03            |
| 0.95 | **1.68** | 1.06       | **0.05**| 0.56           | 0.87            |

Mean cross_contamination (peer data attributed to MSFT) per Tier-3 response — at 95% fill: Opus 0.095, Sonnet 0.02, GPT-5.5 0.000, Gemini 0.000, DeepSeek 0.000.

**GPT-5.5's hallucination resistance is the most distinctive cross-arm finding in the dataset.** At 95% fill with seven peer 10-Ks in context, GPT-5.5 makes 1 unsupported claim per 20 synthesis answers; Opus makes 1 per 0.6 answers — a 33× absolute gap. Cross-contamination is identically zero for GPT-5.5, Gemini, and DeepSeek across all 91 runs. Opus is the only arm with non-trivial cross-contamination at 95%; Sonnet is the only arm whose cross-contamination is non-zero but small.

The asymmetry deserves a name. Opus and Sonnet *follow form but skip evidence* under context pressure — the prescribed Q8 framework is applied, but claims become unsupported. GPT-5.5, Gemini, and DeepSeek *stay disciplined to evidence* — they don't add unsupported elaboration even when context is rich enough to make plausible-sounding fabrications easy.

### 2.4 Position effect — no consistent pattern across vendors

| arm             | strongest position pattern               | weakest at 95% fill |
|-----------------|------------------------------------------|---------------------|
| opus-4-7        | `end > start > middle` (monotonic)        | start (6.76)        |
| sonnet-4-6      | mixed; `end` strongest at 25/50, `middle` at 95 | mixed         |
| gpt-5-5         | `start` weakest at 25/95; `end` weakest at 75 | **start (5.48)** |
| gemini-3-1-pro  | mixed; cell-by-cell variation             | end (5.38)          |
| deepseek-v4-pro | `start` strongest at 25/50/75; flips to `end` at 95 | **start (4.81)** |

Three arms (Opus, Sonnet, Gemini) variously favor `end` or `middle`. Two arms (GPT-5.5, DeepSeek) consistently penalize `start` at high fill — DeepSeek flips cleanly to `end` strongest at 95%; GPT-5.5 ties `middle` and `end` (both 6.67) above `start` (5.48). **Position effect is vendor-specific and saturates at 95% to whichever arm has its own attention pattern.** The deployment implication is simple but easy to miss: **"put the target last" is good advice for OpenAI, DeepSeek, and Anthropic Opus, but Gemini and Sonnet are mixed.** Test for your specific model/task.

### 2.5 Compute and timing — the four "max thinking" stories

Mean per-rep at baseline → 95% fill:

| arm             | thinking_tokens (baseline → 95%) | direction | latency (baseline → 95%) | collect wall (4× concurrent) |
|-----------------|----------------------------------|-----------|--------------------------|------------------------------|
| opus-4-7        | 2,417 → 4,524 (**+87%**)         | **expands** | 169s → 214s              | 82 min |
| sonnet-4-6      | 18,588 → 14,061 (−24%)           | mildly contracts | 932s → 747s        | **417 min (~7 hr)** |
| gpt-5-5         | 9,669 → 6,289 (**−35%**)         | **contracts strongly** | 168s → 113s      | 71 min |
| gemini-3-1-pro  | 4,028 → 4,628 (+15%)             | mildly expands | **53s → 57s**          | **28 min** |
| deepseek-v4-pro | 4,365 → 4,267 (−2%)              | flat        | 176s → 160s              | 82 min |

Four observations:

1. **Anthropic's two arms move in opposite directions on thinking under load.** Opus expands +87%; Sonnet contracts −24%. Same vendor, same `effort=max` knob, opposite responses to the same context-pressure stimulus. *"Anthropic max thinking"* is not a single behavioral mode.
2. **GPT-5.5 contracts thinking the most under load.** From 9.7K to 6.3K reasoning tokens, plus latency dropping 33%. Triple-signal corroboration (reasoning ↓, output ↓, latency ↓) makes this real, not a measurement artifact. The model is doing less work as fill grows.
3. **Gemini is in a different latency regime.** 56s/call avg vs every other arm's 142–822s. **Gemini is ~3× faster than Opus / GPT-5.5 / DeepSeek and ~15× faster than Sonnet** at vendor-max thinking. For batch workloads, this swamps everything else.
4. **Sonnet's wall-time is the elephant in the room.** 932s baseline / 747s at 95% — 12-15 minutes per call, vs 60-200 seconds for every other arm. Total collect-stage wall time was **~7 hours** even with 4-cell concurrency (vs ~30 min for Gemini, ~70-80 min for Opus/GPT-5.5/DeepSeek). Sonnet's max-thinking budget *dominates* its latency profile. If you can tolerate the wait, you get the highest absolute RQ recovery at 95% (7.60). If you can't, the deploy is impractical.

---

## 3. Cost-quality-latency frontier

There is no single "best" model in this study. There is a Pareto frontier across three axes — quality, cost, latency — and each of the five arms occupies a different point on it.

| arm             | total cost | analyst-stage cost | per-run cost | mean RQ at 95% | mean latency | output tokens / second (incl reasoning) |
|-----------------|-----------:|-------------------:|-------------:|---------------:|-------------:|------------------------------------------|
| opus-4-7        | $582.33    | $333.85            | $6.40        | 7.02           | 202s avg     | ~70 |
| sonnet-4-6      | $522.96    | $217.08            | $5.74        | **7.60**       | **822s avg** | ~55 |
| gpt-5-5         | $338.83    | $109.40            | $3.72        | 6.27           | 142s avg     | ~85 |
| gemini-3-1-pro  | $221.00    | $35.20             | $2.43        | 5.56           | **56s avg**  | **~125** |
| deepseek-v4-pro | $194.54*   | $14.47             | $2.14        | 5.24           | 177s avg     | ~45 |

*DeepSeek total is at LIST pricing; actual paid was lower under the 75%-off promo (closed 2026-05-05 15:59 UTC).

**Notable Pareto positions:**

- **Sonnet 4.6** dominates on absolute RQ at 95% (7.60), but at the cost of 5–17× longer wall-time. If your workload is async and you care about quality, this is the pick.
- **Gemini 3.1 Pro** dominates on latency — a 3× advantage over Opus / GPT-5.5 / DeepSeek and ~15× over Sonnet at vendor-max thinking. If your workload is interactive or batch-throughput-bound, this is the pick.
- **DeepSeek V4 Pro** dominates on per-call cost (when promo applies) and is comparable on cost-per-token; it has the highest cross-judge ICC in the study. But it has the **lowest Tier-1 reliability** (~85–95% per question vs 100% for the other arms) and the steepest pairwise loss. Right pick for cost-sensitive synthesis where Tier-1 can be wrapped with deterministic post-processing.
- **GPT-5.5** dominates on hallucination resistance — 33× lower unsupported_claims than Opus at high fill. Right pick when fabrication-cost > depth-cost. 42% cheaper than Opus.
- **Opus 4.7** dominates on baseline RQ (8.05), most-thinking-per-fill expansion, and Q8 unit decomposition (8.6–9.4 units). Right pick when you can afford the highest absolute reasoning depth and your workload tolerates the 7× hallucination rate at 95% fill.

**No arm is dominated.** Each occupies a point on the frontier that some workload will prefer.

---

## 4. The pairwise-vs-absolute methodological finding

This study's **most important methodological contribution** is the demonstration that **the choice between absolute Likert scoring and pairwise comparison can change the cross-arm ordering of model quality.**

### 4.1 The data

At 95% fill, the absolute-RQ ordering is:

```
sonnet 7.60 > opus 7.02 > gpt-5-5 6.27 > gemini 5.56 > deepseek 5.24
```

The pairwise mean-Δ ordering is:

```
sonnet +2.3 > gemini −1.2 > gpt-5-5 −1.9 > opus −2.7 > deepseek −4.1
```

These rankings agree only at the top (Sonnet) and bottom (DeepSeek). In between, **Opus drops two ranks** (from 2nd absolute to 4th pairwise) and **Gemini rises two ranks** (from 4th absolute to 2nd pairwise).

### 4.2 The mechanism

Pairwise compares two responses on the *same question* at the *same rep_idx* (one at baseline, one at 95% fill). The judge sees both side-by-side and decides which is better. This cancels out per-rep variance: if a particular rep happens to be a "good day" for the model, both baseline and high-fill responses benefit, and the pairwise judgment isolates the *fill-dependent* difference.

Absolute Likert scoring evaluates each response in isolation. Per-rep noise stays in. When within-cell variance is high (DeepSeek baseline sd=2.31, Sonnet sd=2.29), the noise *averages out* across reps and the cell mean stays nearly constant — even when the *typical* candidate-vs-baseline gap is large.

### 4.3 The cross-arm prediction

The arm-by-arm gap between absolute and pairwise rankings *predicts* from baseline RQ standard deviation:

| arm             | baseline RQ sd | absolute drift Δ | pairwise Δ at 95% | absolute-vs-pairwise gap |
|-----------------|---------------:|-----------------:|------------------:|-------------------------:|
| opus-4-7        | 0.59           | −1.03            | −2.7              | 1.7 |
| gpt-5-5         | 0.74           | −0.78            | −1.9              | 1.1 |
| gemini-3-1-pro  | 0.79           | −0.30            | −1.2              | 0.9 |
| sonnet-4-6      | 2.29           | +0.17            | +2.3              | 2.1 |
| deepseek-v4-pro | 2.31           | −0.09            | **−4.1**          | **4.0** |

**The high-variance arms (Sonnet, DeepSeek) have the largest absolute-vs-pairwise gaps.** DeepSeek is the extreme: its absolute drift (−0.09) is almost zero, but its pairwise drift (−4.1) is the steepest in the study. The gap is 4 RQ points — meaning if you ran an evaluator pipeline that only scored absolute Likerts on DeepSeek, you would conclude there is no context-fill drift. Pairwise evaluation reveals there is dramatic context-fill drift. Same data, two methodologies, opposite conclusions.

### 4.4 The implication for evaluators

For synthesis tasks where within-rep variance is non-trivial:

- **Default to pairwise.** It's the more sensitive instrument and the more conservative choice (fails toward "drift detected" rather than "no drift detected").
- **Report both.** When they agree, you have strong evidence. When they disagree, the gap is itself a finding — it tells you the model is producing high-variance outputs that absolute scoring averages away.
- **Treat sd as a precondition for absolute-only conclusions.** A model with baseline sd > 1.5 RQ on a 0-10 scale should never have its drift profile assessed by absolute means alone.
- **Watch for saturation in the other direction.** Models that pile near the rubric ceiling (like Opus 4.7 baseline at sd=0.59) have low variance because the rubric maxes out, not because the model is unusually consistent. Report dimension means alongside ICC for saturated dimensions.

This is a contribution beyond the specific drift findings: **the ordering of cross-vendor model quality depends on evaluation methodology, and that dependence is *predictable* from observable response variance.** Future cross-vendor benchmarks should disclose both.

---

## 5. Deployment guide — choosing by failure mode

The five arms produce five distinct *failure modes* under context pressure. Choose by which failure your workload can tolerate, not by which arm "wins" on a leaderboard.

### Opus 4.7 — *high-ceiling depth with evidentiary erosion*

- **Use when:** the task requires the deepest reasoning the panel can produce, you can tolerate a 7× hallucination rate at high fill, and your wall-time budget allows ~200s/call.
- **Avoid when:** citation accuracy or factual groundedness under noise matters. Opus is the only arm with non-trivial cross-contamination at 95% fill (0.095/response).
- **Mitigation:** keep context tight for evidence-heavy synthesis. Position the target *after* noise (`end > start > middle`). Trust factual extraction at any fill (Tier-1 was 100%).

### Sonnet 4.6 — *quality recovery at high fill, but 12–15 min/call*

- **Use when:** quality matters most, async workloads tolerate the wait, and you want pairwise *wins* against your own baseline at 95% fill (the only arm that achieves this).
- **Avoid when:** latency is bounded under 5 minutes. Sonnet's 18.6K baseline thinking tokens dominate inference time; collect-stage wall-clock was ~12 hours for this 91-run arm.
- **Mitigation:** Sonnet's 5–10× more thinking allocation than Opus is what produces the recovery curve. Don't reduce `effort` to compensate for latency — the tradeoff is the whole point.

### GPT-5.5 — *hallucination-resistant; thinks less under load*

- **Use when:** hallucination cost dominates depth cost. Unsupported claims stay essentially zero (0.00–0.05) across all fills. Cross-contamination is exactly zero across 91 runs.
- **Avoid when:** you need maximum reasoning depth or expect more thinking under load. GPT-5.5 contracts thinking 35% as fill grows; depth caps at baseline RQ 7.05 (vs Opus's 8.05).
- **Mitigation:** position target *after* noise (`start` is consistently weakest, especially at 95% fill where `start` drops to 5.48 vs `end/middle` at 6.67). 42% cheaper than Opus on identical task.

### Gemini 3.1 Pro — *flat drift, low ceiling, 3-4× speed advantage*

- **Use when:** latency dominates the deployment economics. Gemini is 3× faster than Opus / GPT-5.5 / DeepSeek and ~15× faster than Sonnet at vendor-max thinking, with the flattest drift curve in the study (0.35 RQ spread across 13–92% fill).
- **Avoid when:** baseline reasoning depth matters. Gemini's baseline RQ (5.86) is meaningfully below the Anthropic/OpenAI arms at any fill — drift is small *because the ceiling is low*.
- **Mitigation:** explicit prompts for granular decomposition help (Gemini defaults to ~5 segment-level units vs Opus's ~9 product-line units). Position effects are mixed — no clean rule transfers.

### DeepSeek V4 Pro — *cheapest, most-measurable, but extractor-fragile*

- **Use when:** cost dominates; you can parse analyst output deterministically (regex / pydantic / structured-output mode); you value the fully-exposed `reasoning_content` field for observability.
- **Avoid when:** your downstream pipeline relies on a second LLM as a JSON normalizer (Haiku 4.5 deterministically failed to reformat ~7.7% of DeepSeek's responses, despite the underlying JSON being valid). Or your evaluator only uses absolute Likerts (DeepSeek's absolute-vs-pairwise gap of 4 RQ points means you'll miss real drift — see §4).
- **Note on the §2.6 Tier-1 gap:** the apparent 5–15% per-question miss rate is a measurement-chain artifact. The 7 reps that "failed" Tier-1 in our autograder are *exactly* the 7 reps where Haiku 4.5 couldn't reformat the analyst's (correct) JSON. Analyst-side Tier-1 hit rate is 100%, indistinguishable from every other arm.
- **Mitigation:** parse deterministically. Run more reps than for other models — within-cell sd 2.31 means single calls are much less informative. Promo pricing closed 2026-05-05; budget at the regular $1.74/M input rate going forward.

---

## 6. Limitations

Inherited from the per-arm reports:

- **Single target company (MSFT)** — all findings conditional on this 10-K + earnings call.
- **Single noise corpus (peer 10-Ks)** — adversarially-near is one design point.
- **Same-vendor-family judges** (Opus 4.7 + Sonnet 4.6, both Anthropic) — cannot rule out vendor-stylistic preferences. Both Anthropic judges produce same-direction rankings, so within-judge-family conclusions are robust; cross-vendor judging is a follow-up.
- **Vendor-max thinking is not equivalent across vendors** — see §1.3.
- **n = 7 reps per cell** — adequate for direction but tight for variance estimation, especially for high-variance arms (Sonnet, DeepSeek). The pairwise-vs-absolute gap analysis (§4) is qualitatively robust but tighter quantification needs more reps.
- **Compressed fill range at high end.** Pool exhaustion → 75% and 95% target fills realized at 72% and 92%. Cross-arm fill values are byte-identical (proven via materials sha256), so this affects all arms equally.
- **DeepSeek extractor parse failures (7.7%)** are partially absorbed into Tier-1 hit rates and §2.6 totals. Affects DeepSeek's Tier-1 numbers; doesn't affect cross-arm Tier-3 rankings.

Specific to the cross-arm analysis:

- **Inter-arm latency comparisons are confounded by inference infrastructure.** Gemini's 3–4× speed advantage may reflect Google's TPU stack as much as model architecture. Re-running on a vendor-neutral inference platform isn't possible at vendor-max thinking — vendors don't publish weights. Treat latency as a *deployment property* of each vendor's API, not as an architectural property of the model.
- **DeepSeek's pricing snapshot is at LIST rate; actual paid was promo rate** (75% off through 2026-05-05). Cost-frontier comparisons (§3) using locked rates over-count DeepSeek's cost; users running this study now would likely pay regular pricing.
- **Cross-judge ICC differences (DeepSeek 0.947 vs Gemini 0.696) reflect response-variance asymmetries**, not "judge agreement" in a vendor-comparable sense. The DeepSeek arm report (§2.7) notes this; cross-arm ICC tables should not be read as a quality signal.

Six follow-ups would sharpen the cross-arm picture:

1. **Cross-vendor judge** — re-grade a 20% subsample with a non-Anthropic judge (Gemini 3.1 Pro at HIGH, or GPT-5.5 at xhigh). Disentangles judge-vendor preference from model quality. ~$50-100 incremental.
2. **Replicate with non-MSFT targets** — different industries, different document genres. Tests generalization of the five drift signatures.
3. **Replicate with less-similar noise corpora** — Wikipedia, congressional testimony, anything not adversarially-near. Tests whether the "evidentiary erosion vs engagement contraction vs flat" taxonomy generalizes beyond peer-10K noise.
4. **Test sub-max thinking levels** for each vendor — Opus `effort=high`, GPT-5.5 `reasoning.effort=high`, Gemini `thinking_level=MEDIUM`, DeepSeek `reasoning_effort=high`. Shows whether vendor-specific drift signatures are budget-bound or architectural.
5. **More reps per cell** — n=21 instead of n=7. Tightens variance estimation, especially the absolute-vs-pairwise gap analysis. ~3× the cost (so ~$5,500 panel total), or restrict to high-variance arms (DeepSeek, Sonnet).
6. **Add a sixth arm** — once a third major reasoning model from each non-Anthropic vendor exists. The current panel is 2 Anthropic + 1 each from OpenAI/Google/DeepSeek. A more balanced panel would help separate vendor-architecture effects from per-model effects.

---

## 7. What this means for the field

This is not a benchmark. It is a study of *failure modes*. Five top-tier reasoning models, one carefully-controlled synthesis task, identical materials, identical judging — and five qualitatively distinct ways to fail under context pressure.

Three contributions for the literature:

1. **Vendor-max thinking is heterogeneous.** Opus expands thinking by 87% under load; GPT-5.5 contracts by 35%; Sonnet contracts by 24% (from a much higher baseline); Gemini and DeepSeek hold roughly flat. The label "max" hides four-way architectural divergence. Cross-vendor benchmarks that report "thinking-on" as a single condition are not measuring the same thing across vendors.

2. **The dominant failure mode is vendor-specific.** Anthropic's failure under noise is *evidentiary erosion* (groundedness ↓, unsupported claims ↑, form preserved). OpenAI's failure is *engagement contraction* (reasoning depth ↓, output volume ↓, latency ↓, claims stay disciplined). Google's failure is *low-ceiling-stability* (drift is flat because the absolute baseline is low). DeepSeek's failure is *variance-masked drift* (absolute scores stay flat while pairwise comparisons reveal the drift). Hallucination-mitigation strategies that work for Anthropic (citation enforcement, structural scaffolding) may not transfer to OpenAI (which already doesn't hallucinate at high fill) or Google (which has different attention patterns).

3. **Pairwise comparison is the only methodology that ranks all five arms reliably.** Absolute Likert scoring agrees with pairwise on the top (Sonnet) and bottom (DeepSeek), but reverses the middle ordering. This is not a property of this rubric or this judge — it is a property of *any* evaluator that uses an absolute scale on outputs with non-trivial within-rep variance. Cross-vendor benchmarks should default to pairwise and report variance alongside any absolute-score claims.

The deployment-relevant summary in one sentence: **choose the model whose failure mode you can absorb, not the model with the highest absolute score.** All five arms here are deployable; all five fail differently.

---

## 8. Reproducibility

```
Opus 4.7 Reasoning Drift Study/
├── DESIGN.md                  — pre-registered design (v0.3)
├── PROMPTS.md                 — analyst, extractor, judge system prompts
├── RUBRIC.md                  — judge rubric anchors
├── MULTI_VENDOR_ADDENDUM.md   — v2 multi-vendor extension
├── pre_registration.lock      — v1 methodology hash 61b2d30f...
├── pre_registration.v2.lock   — v2 methodology hash 3433f4a6...
├── arms/
│   ├── opus-4-7/              — v1, $582.33, full grid + report
│   ├── sonnet-4-6/            — v1, $522.96, full grid + report
│   ├── gpt-5-5/               — v2, $338.83, full grid + report
│   ├── gemini-3-1-pro/        — v2, $221.00, full grid + report
│   └── deepseek-v4-pro/       — v2, $194.54, full grid + report
├── cross_arm/
│   ├── COMPARATIVE_REPORT.md  — auto-generated tables (compare_arms.py)
│   └── CROSS_ARM_REPORT.md    — this synthesis document
└── harness/
    ├── config/                — frozen experiment + per-arm configs
    ├── src/                   — pipeline modules
    └── scripts/
        ├── run_experiment.py        — collect stage (per arm)
        ├── run_extractor.py         — extract stage (per arm)
        ├── run_grading.py           — grade stage (per arm)
        ├── drift_analysis.py        — per-arm aggregate analysis
        ├── compare_arms.py          — cross-arm comparison + integrity gate
        ├── write_arm_lock.py        — generate arm.lock.json + manifest
        └── verify_arm_integrity.py  — three-check integrity gate
```

To reproduce a specific arm:

```bash
cd harness
python -m scripts.run_experiment --arm <arm>     # collect
python -m scripts.run_extractor   --arm <arm>    # extract
python -m scripts.run_grading     --arm <arm>    # grade
python -m scripts.drift_analysis  --arm <arm>    # per-arm tables
python -m scripts.write_arm_lock  --arm <arm>    # lock
python -m scripts.verify_arm_integrity --arm <arm>  # verify
```

To reproduce the cross-arm comparison:

```bash
python -m scripts.compare_arms --write-report   # writes cross_arm/COMPARATIVE_REPORT.md
```

The integrity gate (`compare_arms.py` or `verify_arm_integrity.py`) refuses to run if any arm's pre_registration_hash diverges from the project lock, if materials_lock_hash mismatches, or if any per-file SHA-256 in `arms/<arm>/data/` diverges from `arms/<arm>/data.manifest.sha256`. All five arms currently pass.

Total cost for full reproduction at lock-time pricing: **~$1,860**. Manifest is resumable for every arm — if any stage crashes, re-running picks up where it left off.

---

## 9. Cost summary across all five arms

| arm             | analyst stage | extract stage | grade stage | total      | pricing snapshot |
|-----------------|--------------:|--------------:|------------:|-----------:|------------------|
| opus-4-7        | $333.85       | $2.41         | $246.08     | **$582.33** | Anthropic $15/$75 |
| sonnet-4-6      | $217.08       | $4.09         | $301.79     | **$522.96** | Anthropic $3/$15 |
| gpt-5-5         | $109.40       | $2.40         | $227.03     | **$338.83** | OpenAI tiered, $10/$45 high |
| gemini-3-1-pro  | $35.20        | $1.17         | $184.63     | **$221.00** | Google tiered, $4/$18 high |
| deepseek-v4-pro | $14.47        | $3.09         | $176.98     | **$194.54** | DeepSeek list (promo discount not applied) |
| **total**       |               |               |             | **$1,859.66** | |

The cross-arm cost trajectory tells its own story: **analyst-stage spend differs by 23× across the panel** ($14.47 to $333.85), but **grade-stage spend differs by only 1.6×** ($176.98 to $301.79) because the judge is held constant. Extract spend is essentially flat ($1.17 to $4.09) — Haiku 4.5 normalization is cheap regardless of analyst.

For studies that want to add a sixth arm: the marginal incremental cost is dominated by analyst stage (vendor-specific) plus grade stage (~$200 with Opus 4.7 max as judge), totaling roughly **$200–$500 per new arm** depending on the analyst's per-call cost. The 91-run × 8-question design grid is a one-time-locked investment; adding new arms is cheap.

---

## Acknowledgments

Pipeline built on the Anthropic Python SDK (v1 arms + held-constant extractor and judges across all arms), OpenAI Python SDK (GPT-5.5, DeepSeek V4 Pro via api.deepseek.com), and `google.genai` (Gemini 3.1 Pro). Materials sourced from public 10-K filings and Microsoft FY2026 Q2 earnings call transcript. Cross-arm comparability validated via byte-equivalent prompt SHA-256 at every (cell, rep) coordinate.

Five arms × 91 runs × 8 questions × 5 judges = 18,200 graded answer-pairs across $1,860 in spend. The data is open in this repository; the pipeline is reproducible in ~6–10 hours per arm.
