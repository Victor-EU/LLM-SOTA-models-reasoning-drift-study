# Opus 4.7 vs Sonnet 4.6 under context pressure
## A field guide for agent builders

**Date:** 2026-04-27
**Companion figure:** [`figures/opus_vs_sonnet_for_agents.png`](../figures/opus_vs_sonnet_for_agents.png)
**Source data:** `arms/opus-4-7/` and `arms/sonnet-4-6/` (91 runs each, byte-identical inputs at every (cell, rep) coordinate)
**Methodology:** v1 lock (`pre_registration.lock`, sha256 `61b2d30f...`)
**Judges:** Opus 4.7 max-effort (primary), Sonnet 4.6 high-effort (20% subsample)

---

## TL;DR

Two Anthropic flagship reasoning models, same vendor, same `effort=max` knob, same prompts at every coordinate. They produce **two opposite drift profiles** under context pressure on a financial-analysis synthesis task:

- **Opus 4.7** declines monotonically. Reasoning quality drops from 8.05 to 7.02 (−1.03 RQ) as fill rises from baseline to 92%; unsupported claims rise 7×; cross-contamination (peer-10K facts attributed to MSFT) appears at non-trivial rates above 50% fill. At 95% fill, Opus loses 18 of 20 head-to-head comparisons against its own baseline (mean Δ −2.7).
- **Sonnet 4.6** has a shallow inverted-U and **recovers above baseline at 95% fill** (7.43 → 7.60). Unsupported claims still rise (10× — from a much lower floor), but cross-contamination stays effectively zero. At 95% fill, Sonnet *wins* 13 of 20 head-to-head comparisons against its own baseline (mean Δ +2.3).

The price-anchored intuition that "the bigger model handles long context better" is false on this dataset. **Sonnet is the more context-robust of the two.** That conclusion holds under both judges (Opus and Sonnet) and survives the cross-vendor judge follow-up.

The deployment tradeoff is **not cost** ($6.40/call Opus vs $5.74/call Sonnet — within 12%). The deployment tradeoff is **latency**: at vendor-max thinking, Sonnet runs ~4× longer wall-clock per call than Opus on average (5.5× at baseline, 3.5× at 95% fill — Sonnet contracts thinking under load while Opus expands it). For interactive agent loops, Sonnet at `effort=max` is impractical regardless of its quality. For asynchronous batch synthesis, the latency cost is recoverable and Sonnet's quality profile wins.

If you ship one of these two models in an agent today, choose by **the failure mode you can absorb**:

- *Opus's failure mode:* evidentiary erosion. Form preserved (frameworks applied, structure intact), evidence quality decays (groundedness ↓, unsupported claims ↑, peer contamination ↑). Failures are competent-looking and hard to catch in production.
- *Sonnet's failure mode:* latency. The same quality recovery that makes Sonnet attractive is bought with 12–15 minute response times at `effort=max`, dominated by 14–19K thinking tokens per call.

The rest of this report is the data behind those two paragraphs.

---

## 1. What the experiment measures (and why apples-to-apples)

Both arms are runs of the same controlled experiment. The single variable across them is the analyst model. Everything else is byte-identical:

- **Materials.** Microsoft FY2025 10-K + Q2 FY2026 earnings call as target; seven peer 10-Ks (AAPL, GOOGL, AMZN, META, NVDA, ORCL, CRM) as adversarially-near noise. Materials lockfile sha256 `c13b5514...`, identical for both arms.
- **Design grid.** 1 baseline cell + (5 fill levels × 3 noise positions) = 13 cells × 7 reps = 91 runs per arm. Realized fills 13/24/47/72/92% of the Anthropic-counted token budget.
- **Eight-question stimulus.** 3 Tier-1 (factual lookup), 2 Tier-2 (calculation), 3 Tier-3 (synthesis with prescribed structure on Q8).
- **Extractor.** Claude Haiku 4.5, no thinking, max_output_tokens=16K. Held constant across both arms.
- **Primary judge.** Claude Opus 4.7, `effort=max`, max_output_tokens=16K. Held constant. Runs against cached fill=0 target materials, so the judge itself is not under context pressure.
- **Secondary judge.** Claude Sonnet 4.6, `effort=high`, on a 20% subsample for inter-rater reliability.
- **Pairwise judge.** Opus 4.7 max-effort on 25% of non-baseline (run, q_id) pairs, A/B randomized, comparing baseline rep to high-fill rep on the same question.

The integrity gate at `harness/scripts/verify_arm_integrity.py` confirms cross-arm methodological identity at the SHA-256 level. `compare_arms.py` refuses to run if either arm's pre_registration_hash, materials_lock_hash, design grid, or instrument config diverges. Both arms currently pass.

The only thing that varies between the two arms is the analyst's `model` parameter — `claude-opus-4-7` vs `claude-sonnet-4-6`, both at `output_config.effort=max`, `max_output_tokens=32K` (Opus) / `65K` (Sonnet, raised because Sonnet's 18K thinking allocation overflowed the 32K cap during the pilot), `temperature=1.0`, streaming enabled.

This is what makes the comparison meaningful. Differences in the data are differences in what the analyst model did — not in materials, prompts, judge, extractor, or rubric.

---

## 2. The five quantitative findings

### 2.1 Reasoning quality drift — opposite directions

Mean reasoning_quality (0–10) on Tier-3 synthesis across all 3 questions × all positions × 7 reps per cell:

| realized fill | Opus 4.7 | Sonnet 4.6 |
|--------------:|---------:|-----------:|
| 13% (baseline) | **8.05** | 7.43 |
| 24%            | 7.33     | **8.00** |
| 47%            | 6.89     | 7.94 |
| 72%            | 7.17     | 7.19 |
| 92%            | **7.02** | **7.60** |
| **Δ baseline → 95%** | **−1.03** | **+0.17** |

Opus has the highest baseline RQ in the entire 5-arm panel and the **steepest absolute drift**. Sonnet has a lower baseline but a shallow inverted-U: it peaks at 25–50% fill, dips at 75%, and **recovers above its own baseline at 95% fill**. From 25% fill onward, Sonnet's mean RQ exceeds Opus's at every fill level.

Two intuitions this rules out:

1. **"Smaller model degrades faster"** is wrong here. Sonnet (the smaller of the two Anthropic flagships) is the more context-robust on absolute scoring; Opus (the larger) shows the steepest absolute decline.
2. **"More thinking = less drift"** is too simple. Sonnet allocates 3–8× more thinking than Opus across the fill grid and shows less drift, which is consistent with the hypothesis. But Sonnet *contracts* thinking under load (−24%) while Opus *expands* it (+87%), and Opus drifts more — so allocation slope is not the whole explanation either.

### 2.2 Hallucinations and cross-contamination

Mean unsupported_claims per Tier-3 response (claims without trace in the target materials):

| fill | Opus 4.7 | Sonnet 4.6 |
|-----:|---------:|-----------:|
| 0.00 | 0.24     | 0.10       |
| 0.25 | 0.76     | 0.46       |
| 0.50 | 0.62     | 0.46       |
| 0.75 | 1.02     | 0.95       |
| 0.95 | **1.68** | **1.06**   |
| **Multiplier** | **7×** | **10×** |

Both arms hallucinate more under load. Opus rises to a higher absolute peak (1.68 unsupported claims per response — roughly one made-up claim every 0.6 answers); Sonnet rises with a steeper multiplier but from a lower floor (1.06 claims per response at 95%, roughly one every 0.95 answers).

**Cross-contamination** (peer-10K facts attributed to MSFT) is the cleaner differentiator. At 95% fill:

- **Opus**: 0.095 incidents per response. Non-trivial. The Opus arm's per-arm report shows cross-contamination first appearing at ~50% fill (0.016) and growing through 75% (0.079) to 0.095 at 92%. Opus is the *only* Anthropic arm that crosses the threshold.
- **Sonnet**: 0.02 incidents per response — effectively zero across all high-fill (75% + 95%) Tier-3 responses.

This asymmetry — that Opus *both* hallucinates more *and* attributes peer data to the target while Sonnet keeps its scope clean — is the most operationally important difference between the two arms. For agent workloads that require evidentiary discipline (legal, financial, medical, citation-dependent research), Opus's cross-contamination at high fill is the failure mode that matters. Sonnet at high fill still hallucinates, but it does not confuse one company's filings for another's.

A subtler observation: Opus's failure pattern is **form preserved, content degraded**. Q8 mandates a *decompose by unit → apply 4 frameworks → synthesize* structure. At 95% fill, Opus still decomposes 9.4 units and applies all 4 frameworks (vs 8.9 / 4.0 at baseline). The scaffolding is intact. What degrades is the evidence inside the scaffolding. This is the hardest failure mode to detect in production: the answer *looks* well-structured.

### 2.3 Thinking allocation — opposite responses to load

Mean thinking_tokens per call by fill:

| fill | Opus 4.7 | Sonnet 4.6 |
|-----:|---------:|-----------:|
| 0.00 |  2,417   | 18,589 |
| 0.25 |  3,555   | 14,049 |
| 0.50 |  4,502   | 18,597 |
| 0.75 |  4,331   | 13,844 |
| 0.95 |  4,524   | 14,061 |
| **Δ baseline → 95%** | **+87.2%** | **−24.4%** |

Same vendor, same `effort=max` knob. Opus expands thinking under load (+87%); Sonnet contracts it (−24%). Sonnet's *baseline* thinking allocation is 7.7× Opus's — and Sonnet thinks more at 95% fill (14K) than Opus does at any fill level (max 4.5K).

This is corroborated by independent signals: output tokens and latency move in the same direction as thinking tokens within each arm (Opus: +25% output, +26% latency; Sonnet: −20% output, −20% latency). The slope direction is a behavioral signal, not a measurement artifact.

The label "Anthropic max-effort thinking" is not a single behavioral mode. It selects two different runtime postures depending on which model you give it to.

### 2.4 Latency — the deployment-relevant gap

Mean latency per call (wall-clock, request to last byte):

| fill  | Opus 4.7 | Sonnet 4.6 |
|------:|---------:|-----------:|
| 0.00  | 169 s    | 932 s      |
| 0.95  | 214 s    | 747 s      |
| **mean across grid** | **202 s** | **822 s** |

Sonnet at `effort=max` runs **3.5–5.5× slower** than Opus depending on fill (~4× on average). The 932 s baseline is 15.5 minutes per call. The 95% cell is the *fastest* Sonnet condition because Sonnet contracts thinking under load — but it is still 12.5 minutes per call. Total collect-stage wall time was ~7 hours for Sonnet's 91 runs at 4-cell concurrency, vs ~80 minutes for Opus.

For agent builders this is the single most decision-relevant number in the report:

- **Interactive agents** (chatbots, code assistants, anything user-facing on a real-time loop): Sonnet at `effort=max` is not a viable choice. The wait dominates the experience.
- **Asynchronous agents** (batch document processing, overnight research, background analysis): the latency cost is recoverable and the quality profile is the better pick.
- **Mixed agents** (interactive UI with backgrounded reasoning steps): consider routing the synthesis steps to Sonnet and the latency-sensitive steps to Opus or a non-max-effort Sonnet configuration.

If you reduce Sonnet's thinking effort to compensate for latency, you lose the recovery curve — Sonnet's drift profile *is* its 18K-thinking-token budget.

### 2.5 Cost — surprisingly similar per call

Per-run cost across the full 91-run grid:

| stage                              | Opus 4.7 arm | Sonnet 4.6 arm |
|------------------------------------|-------------:|---------------:|
| Analyst (per call)                 | $3.67        | $2.39          |
| Extract (Haiku, held constant)     | $0.03        | $0.04          |
| All judging (Opus + Sonnet judges, held constant) | $2.70 | $3.32 |
| **Total per run**                  | **$6.40**    | **$5.74**      |

Per-call cost is within 12%. Sonnet's lower per-token output rate ($15/M vs $75/M) more than offsets its 3–8× larger thinking and 2.5–4× larger output token counts on the analyst side. Judging costs more on the Sonnet arm because Sonnet's longer outputs (45K vs 14K output tokens at baseline) give the held-constant judge more text to score. Total arm spend: Opus $582.33, Sonnet $522.96 (10% lower).

The deployment tradeoff agent builders face is therefore **not** "pay more for Opus, get reliability under load." Opus is more expensive *and* less context-robust on this task. The genuine tradeoff is latency.

---

## 3. The pairwise paradox — same data, two different rankings

The cleanest signal in the dataset is pairwise comparison. The Opus 4.7 judge sees a baseline rep and a same-rep-index 95%-fill rep, A/B-randomized, picks the better.

| arm        | candidate wins | losses | ties | mean Δ (cand − base) | n  | reading        |
|------------|---------------:|-------:|-----:|---------------------:|---:|----------------|
| Opus 4.7   | 2              | **18** | 0    | **−2.7 ± 2.0**       | 20 | clear loss     |
| Sonnet 4.6 | **13**         | 7      | 0    | **+2.3 ± 4.2**       | 20 | clear win      |

This is striking. Forced to compare side-by-side, the same Opus judge that gave Sonnet 7.60 RQ at 95% fill (vs Opus's 7.02) sees the gap as much wider than the absolute Likert scores suggest. Sonnet's 95% rep beats its own baseline 65% of the time. Opus's 95% rep loses to its own baseline 90% of the time.

**Why the absolute and pairwise rankings diverge.** Within-cell variance is the explanation. Sonnet's baseline RQ has sd=2.29; Opus's is sd=0.59. When per-rep noise is high, the mean of 21 reps converges slowly and small Δs hide inside the noise. Pairwise comparison cancels per-rep noise: the judge sees both responses on the same question at the same rep_idx, so a "good day" for Sonnet benefits both responses equally and the judgment isolates the *fill-dependent* difference.

For evaluators of synthesis tasks, the lesson is portable beyond this study: **default to pairwise**. It is the more sensitive instrument and the more conservative choice (it fails toward "drift detected" rather than "no drift detected"). When pairwise and absolute scoring agree, you have strong evidence. When they disagree, the gap is itself a finding.

The numerical implication for agent builders deciding between Opus and Sonnet: **the absolute-RQ gap (0.58 points at 95% fill, Sonnet ahead) understates how much better Sonnet's 95%-fill answers are than Opus's 95%-fill answers in head-to-head comparison.** The pairwise data shows Sonnet *wins* against its own baseline while Opus loses to its own baseline — a 5-point swing in raw pairwise mean Δ. Anyone evaluating these models with a leaderboard-style absolute score is missing the larger fraction of the signal.

---

## 4. The sober-state result — what happens with no noise

A separate analysis on the same dataset re-judged every arm's 21 baseline (fill=0) Tier-3 responses head-to-head, in randomly-permuted 5-way A–E bundles, by both Anthropic judges. Same materials, same rubric, same judge snapshots — only the judge's *task* changes: 5-way ranking instead of single-answer absolute Likert.

| rank | arm                | mean rank (Opus / Sonnet judge) | Borda (of 84) | top-1 (of 21) |
|------|--------------------|--------------------------------:|--------------:|--------------:|
| 1    | **Sonnet 4.6**     | 1.48 / 1.33                     | 74 / 77       | 11 / 14       |
| 2    | **Opus 4.7**       | 1.62 / 1.76                     | 71 / 68       |  9 /  6       |
| 3    | GPT-5.5            | 3.00 / 2.95                     | 42 / 43       |  1 /  1       |
| 4    | DeepSeek V4 Pro    | 4.24 / 4.19                     | 16 / 17       |  0 /  0       |
| 5    | Gemini 3.1 Pro     | 4.67 / 4.76                     |  7 /  5       |  0 /  0       |

Cross-judge agreement is the strongest in the project: per-item Spearman ρ mean **0.943**, median **1.000**, top-1 same-item agreement 76%.

**The sober-state ranking flips the absolute-judge baseline at the top.** Absolute scoring on the fill=0 cell ranked Opus 1st (RQ 8.05) and Sonnet 2nd (7.43). Forced to compare side-by-side, both judges flipped them.

The judge rationales explain why. Opus is praised for *clarity*, *integrative synthesis*, and *tight risk framing* (e.g., surfacing the ~45% OpenAI share of MSFT's $625B commercial RPO as a concentration risk). Sonnet is praised for *substance density per anchor*: where Opus writes "operating cash flow grew sharply," Sonnet writes "$136,162M OCF, up $17.6B, with the cash-received-from-customers driver." Sonnet's median answer length is 8,227 chars, 60% longer than the next-longest arm. Length bias in the judge is acknowledged in the analysis — even granting it, Sonnet's substance density per anchor is the highest in the panel.

**The cross-vendor judge follow-up** added GPT-5.5 (xhigh) and Gemini 3.1 Pro (HIGH) as judges on the same 21 items, same permutations. Three of four judges (Opus, Sonnet, Gemini) returned the exact ordering above. The GPT judge moved itself from #3 to a tie at #1 with Opus, displacing Sonnet to #3 — but the top-3 set was unchanged. The Sonnet > Opus ordering survives 3 of 4 judges.

**Why this matters for agent builders.** It says the "Sonnet beats Opus under context pressure" finding is not a context-pressure-only artifact. *Even with no noise at all*, head-to-head, Sonnet's synthesis-task output is preferred over Opus's by both Anthropic judges and the Gemini judge. The pricing and naming hierarchy ("Opus" > "Sonnet") does not predict head-to-head quality on this synthesis task at vendor-max thinking. The conventional anchor — "use Opus when quality matters, use Sonnet when cost matters" — is the wrong frame on this task.

---

## 5. What didn't drift — the floor under both models

To keep the picture honest: both arms hit **effectively 100% accuracy** on Tier 1 (factual lookup) and Tier 2 (calculation) across all fill levels. Opus had zero distractor hits across 91 runs (the lone Tier 1/2 miss was a Haiku extraction truncation on a 50% start cell — the analyst response itself was correct). Sonnet had a single bad rep at 95% fill that missed all 5 numerics, with 2 of those 5 being peer-number distractor hits. Outside that single rep, Sonnet's Tier 1/2 was perfect across all fills.

This generalizes: **the explicit `<<< TARGET MATERIALS >>>` scope marker plus the analyst-prompt rule "Base EVERY answer EXCLUSIVELY on the TARGET MATERIALS block" prevented essentially all factual contamination across 910 Tier 1/2 records (91 runs × 5 questions × 2 arms).** The drift documented above is specifically a *synthesis* drift — open-ended Tier-3 questions where the model has discretion over what to include. Pointed factual questions with clear answer schemas don't drift on either model.

For agent builders, this means:

- Retrieval and structured factual extraction over long contexts: **safe for both Opus and Sonnet at vendor-max thinking**, even at near-saturation fill, given a clear scope marker.
- Open-ended synthesis, evidence-grounded reasoning, citation-dependent analysis: **drift-prone on both, more so on Opus**, regardless of how much you instruct citation.

This bifurcation maps directly to agent design. Tasks decomposable into "find this specific X in this specific document" remain reliable at any fill. Tasks that require the model to choose what is salient and reason from it degrade with fill, and the degradation is asymmetric between Opus and Sonnet.

---

## 6. Why this happens — three mechanism hypotheses

The data is observational. We cannot adjudicate causality from this dataset alone. But three hypotheses are consistent with what we see:

1. **Heavier baseline thinking allocation buys context-robustness headroom.** Sonnet at `effort=max` allocates 18K thinking tokens at baseline, vs Opus's 2.4K. Sonnet may be doing more reasoning per call by default, leaving more spare cognitive budget that absorbs context noise without quality loss. Consistent with: Sonnet's drift curve being shallow and recovering at 95%; Sonnet's contraction (-24%) leaving it with 14K thinking tokens at 95% fill — still 3× Opus's allocation at the same fill.

2. **Different attention strategies at high fill.** Sonnet may anchor more tightly to the explicitly-marked TARGET MATERIALS block and disregard peer 10-Ks more thoroughly than Opus. Consistent with: Sonnet's near-zero cross-contamination (0.02 vs Opus's 0.095 at 95% fill), and Sonnet's pairwise-win pattern at 95%. Opus seems to integrate peer signal more aggressively, occasionally to the point of misattribution.

3. **Comparative-analysis benefit at high fill.** For synthesis questions about MSFT (financial health, strategic positioning, AI impact), peer 10-K context could *help* Sonnet by giving it comparative anchors. A real financial analyst is better-informed when peer disclosures are visible. Sonnet appears to use this signal effectively; Opus appears to confuse it. Consistent with: Sonnet's 95%-fill RQ exceeding its own baseline; Opus's monotonic decline.

These are observational hypotheses, not causal claims. Distinguishing them would require:

- Replicating with non-MSFT targets and non-peer noise (separates "comparative benefit" from "robust attention").
- Testing sub-max thinking levels (separates "thinking budget headroom" from architectural attention behavior).
- Replicating with a different domain entirely (legal, medical, technical) to test whether the inversion generalizes.

None of those are in the current dataset.

---

## 7. Deployment guide for agent builders

Choose by failure mode and workload posture, not by leaderboard rank.

### When to ship Opus 4.7

- **Interactive agents with tight latency budgets.** Opus's 169–214 s/call is on the high end of what users tolerate, but Sonnet at `effort=max` is 3.5–5.5× longer and not viable. If your agent must respond inside a few minutes and you want Anthropic max-effort, Opus is the only option.
- **Tasks whose context stays small.** Opus dominates baseline RQ (8.05 vs 7.43) and ranks 1st under absolute scoring at fill=0. If your agent operates on tight, curated context (under ~25% of the budget), Opus's quality lead is real on absolute Likert and the drift hasn't kicked in yet.
- **Tasks where unit decomposition matters.** Q8's framework decomposition stayed within 7.8–9.4 units across all fills for Opus, hitting its peak (9.4) at 95% fill — the structural scaffolding is robust under load even though evidence quality decays. If your synthesis task rewards exhaustive structural breakdown, Opus is the more reliable scaffolder.

Avoid Opus when:

- Your agent's context fills with adjacent material as it works (tool outputs, prior reasoning, retrieved documents). The drift kicks in at 25% fill and gets worse monotonically through 95%.
- Citation accuracy and groundedness are part of your trust model. At 95% fill, Opus produces ~1.68 unsupported claims per synthesis answer and 0.095 cross-contamination incidents — failures that *look* well-structured because the framework scaffolding stays intact.

Mitigations for Opus:

- Position the target *after* noise. The `end > start > middle` ordering held at every fill level in the Opus arm. If you control prompt assembly, place the target last.
- Keep context tight. The drop from baseline to 25% fill alone costs 0.7 RQ points and 3× more unsupported claims.
- Don't rely on structural compliance as a quality signal. Q8's structure was preserved at every fill; the drift is in the evidence inside the structure.

### When to ship Sonnet 4.6

- **Asynchronous agents.** Batch document analysis, overnight research, background synthesis. The 12–15 min/call latency is acceptable here, and Sonnet's quality recovery at high fill is the strongest signal in the panel.
- **Tasks where the agent's context will fill with adjacent material.** Sonnet's drift curve is shallow and *recovers* above baseline at 95% fill. If your agent loops on a document corpus or accumulates context as it reasons, Sonnet's profile is what you want.
- **Tasks where evidentiary discipline matters more than pure depth.** Sonnet's cross-contamination is effectively zero (0.02) across all fills. Sonnet's substance-per-anchor density is the highest in the 5-arm panel. If your task is "cite the actual figure with the actual driver," Sonnet wins.

Avoid Sonnet when:

- Your agent loop has a tight wall-clock budget per step. 12+ minute response times will dominate the agent's pace.
- Your output is constrained to a small token cap. Sonnet's 18K-thinking-token budget plus 36K-output budget overflows 32K total and burns the budget without emitting a visible answer (this happened twice in the sober-state ranking experiment; both retried successfully at 64K). Set `max_output_tokens=65K+` if running Sonnet at `effort=max`.

Mitigations for Sonnet:

- Set max_output_tokens generously. 32K is too tight. Use 64K or higher.
- Don't reduce `effort` to compensate for latency. Sonnet's drift profile *is* its 18K-thinking-token budget; lower effort means a flatter, lower curve, not a faster equivalent.
- Variance is high. Within-cell sd is 2.29 RQ at baseline. If you single-shot Sonnet on a critical step, expect more variance per call than Opus. Pairwise evaluation reveals what single-shot RQ scoring averages away — see §3.

### Hybrid deployments

Several agent topologies make sense given the data:

- **Latency-sensitive interactive layer (Opus) + asynchronous synthesis layer (Sonnet).** Use Opus for the user-facing reasoning step and route deeper synthesis (e.g., a final report after multiple tool calls) to Sonnet asynchronously. The user sees Opus's lower latency; the heavy thinking happens in the background.
- **Opus for tight-context steps (under 25% fill) + Sonnet for full-corpus synthesis.** If your agent works in stages — gather, analyze, synthesize — use Opus for early-stage steps where context is curated and Sonnet for the final synthesis where the full corpus is in scope.
- **Opus as judge over Sonnet's analyst output.** Sonnet at `effort=max` produces high-substance, high-variance synthesis. Opus at `effort=max` is a more reliable judge (lower within-call variance, sharper absolute scoring). The drift study uses this exact pairing. The combined per-step cost is ~$5.74 + $2.60 ≈ $8.34, and the wall-clock is dominated by Sonnet's analyst step.

---

## 8. Limitations

This is one experiment on one task domain with one corpus. Specifics:

- **Single target company (MSFT FY2025 + Q2 FY2026).** Generalization to other companies, industries, document genres is plausible but untested.
- **Single noise corpus (peer 10-Ks, adversarially-near).** Less-similar noise (e.g., random Wikipedia) would likely show less drift; more-similar noise (e.g., MSFT's own historical 10-Ks) might show more.
- **Same-vendor-family judges.** The primary judge is Opus 4.7; the secondary is Sonnet 4.6. Both Anthropic. The cross-vendor judge follow-up (Gemini and GPT judges on the sober-state ranking) corroborates the Sonnet > Opus head-to-head result on 3 of 4 judges. Within-judge-family conclusions are robust; vendor-stylistic preferences cannot be ruled out absolutely.
- **n = 7 reps per cell.** Adequate for direction but tight for variance estimation, particularly for Sonnet (baseline sd=2.29) and Opus's 50% middle outlier cell.
- **Compressed fill range at high end.** Pool exhaustion meant 75% and 95% target fills realized at 72% and 92%. Cross-arm fill values are byte-identical (proven via materials sha256), so this affects both arms equally.
- **Vendor-max thinking is one configuration.** Sub-max thinking levels (Opus `effort=high`, Sonnet `effort=high` or `medium`) are not in this dataset. The conclusions hold for `effort=max` deployment only. A practitioner who reduces effort to gain latency may see a different ordering.
- **Three Tier-3 questions only.** Synthesis dimensions sampled: financial health, strategic positioning, AI impact. Other synthesis genres (causal, counterfactual, predictive over longer horizons) might drift differently.
- **Inter-arm latency comparisons reflect API infrastructure as well as model architecture.** Anthropic's pre-warming, prompt caching, and inference fleet shape the wall-clock numbers. The 3.5–5.5× Sonnet/Opus gap is a property of vendor-max-thinking deployment of these two specific snapshots, not a portable architectural property.

The most consequential follow-up for the conclusion in §7 would be **non-MSFT replication** — a single new target company would say whether the inversion generalizes or is corpus-specific. The sober-state ranking suggests it's not corpus-specific (Sonnet > Opus head-to-head holds even at fill=0), but a second corpus would close the loop.

---

## 9. Bottom line

The price-anchored intuition that more expensive Anthropic models handle long context better is wrong on this dataset. **At vendor-max thinking on a synthesis task with adversarially-near noise, Sonnet 4.6 is the more context-robust model, has lower cross-contamination, and wins head-to-head against its own baseline at 95% fill.** Opus 4.7 has a higher baseline ceiling and stays lower-latency, but it drifts monotonically under fill and develops non-trivial cross-contamination by 50% fill.

The deployment decision for agent builders is therefore not "Opus = quality, Sonnet = budget." It is:

| if your agent is...                       | use         | because                                                                      |
|-------------------------------------------|-------------|------------------------------------------------------------------------------|
| **interactive** (user-facing real-time)   | Opus 4.7    | Sonnet at `effort=max` is 12–15 min/call. Not deployable in interactive loops. |
| **asynchronous** (batch, overnight)       | Sonnet 4.6  | Quality recovers above baseline at 95% fill. Cleaner cross-contamination. The latency cost is recoverable in batch mode. |
| **light-context** (under ~25% fill)       | Opus 4.7    | Drift hasn't kicked in. Opus's baseline lead on absolute Likert is real for tight-context tasks. |
| **fill-heavy** (loops over a corpus)      | Sonnet 4.6  | Opus drifts monotonically; Sonnet recovers. Largest gap is at the operating point that matters. |
| **citation-dependent** (regulated workloads) | Sonnet 4.6  | Cross-contamination at 95% fill: Opus 0.095, Sonnet 0.02. ~5× cleaner. |
| **structurally rigorous** (frameworks, taxonomies, scoring rubrics) | Opus 4.7 | Q8 unit decomposition robust under load (7.8–9.4 across all fills, peaks at 95%). Opus's structural scaffolding holds even when evidence quality decays. |

If you can only ship one and your workload is mixed: **default to Sonnet for any synthesis-heavy step, Opus for any interactive or structural-scaffolding step**. The latency gap is the hard constraint; the quality gap (in Sonnet's favor) is the soft one.

The methodology lesson is portable beyond agent deployment: **default to pairwise comparison when evaluating high-variance synthesis output**. Single-shot absolute Likert scoring put Opus 1st on baseline RQ (8.05); head-to-head ranking flipped it. Same data, two methodologies, two answers. Whichever side of that you trust changes which model you ship. We'd choose pairwise.

---

## Provenance

- **Per-arm reports:** [`arms/opus-4-7/reports/FINAL_REPORT.md`](../arms/opus-4-7/reports/FINAL_REPORT.md), [`arms/sonnet-4-6/reports/FINAL_REPORT.md`](../arms/sonnet-4-6/reports/FINAL_REPORT.md)
- **Cross-arm synthesis (5 arms):** [`CROSS_ARM_REPORT.md`](./CROSS_ARM_REPORT.md)
- **Sober-state ranking (no-noise head-to-head):** [`SOBER_STATE_FINAL_REPORT.md`](./SOBER_STATE_FINAL_REPORT.md), [`SOBER_STATE_RANKING.md`](./SOBER_STATE_RANKING.md)
- **Methodology lock:** `pre_registration.lock` (v1, sha256 `61b2d30f...`)
- **Materials lock:** `materials/materials.lock.json` (sha256 `c13b5514...`)
- **Integrity verifier:** `harness/scripts/verify_arm_integrity.py` — recomputes SHA-256 of every per-arm data file against `arms/<arm>/data.manifest.sha256` and confirms cross-arm methodology identity. Both Opus and Sonnet arms currently pass.
- **Headline figure:** [`figures/opus_vs_sonnet_for_agents.png`](../figures/opus_vs_sonnet_for_agents.png) — two-panel chart (RQ + unsupported claims vs context fill) with pairwise win-rates and cross-contamination as callouts.
- **Total spend across both arms:** $1,105.29 (Opus $582.33 + Sonnet $522.96).
