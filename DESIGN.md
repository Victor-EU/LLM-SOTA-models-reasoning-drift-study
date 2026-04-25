# Opus 4.7 Reasoning Drift Study — Experimental Design

**Version:** 0.2 (simplified)
**Date:** 2026-04-24
**Status:** Design phase; pending pilot before full execution
**Supersedes:** v0.1 (4 reports × 3 noise types × 148 cells × 10 reps, ~$12–15K)
**Budget cap:** $700

---

## 1. Executive summary

Test whether Opus 4.7 (1M context, extended thinking at xhigh) degrades on a
realistic financial + strategic analysis task as the context window fills
with the kind of adjacent material a real enterprise user would paste.
Single target company (**Microsoft**); noise pool is **peer materials** —
latest 10-Ks from seven large-cap tech peers an analyst would realistically
bundle alongside Microsoft (AAPL, GOOGL, AMZN, NVDA, CRM, META, ORCL). Task:
produce a **financial + strategic analysis plus an AI-impact assessment**,
grounded in Microsoft's most recent 10-K and latest quarterly earnings call.

Design: **3 positions × 4 fill levels = 12 noise scenarios**, plus **1
baseline** (target materials only, no noise) for drift measurement = 13
cells × 7 replicates = **91 analyst runs**. Tiers 1–2 auto-graded against
a ground-truth key; tier 3 (synthesis) graded by Opus 4.7 (max-effort
adaptive thinking) judge with 20% Sonnet 4.6 cross-model ICC check.
Primary analysis: mixed-effects model on per-response quality scores
with `fill × position` interaction.

**Expected contribution:** a numeric answer to *"at what fill level, and
with the target materials in what position, does Opus 4.7 xhigh stop being
trustworthy for due-diligence-style analysis of a public company?"*

---

## 2. What changed from v0.1 and why

v0.1 was over-powered for a first pass:

- **4 reports → 1 report (MSFT).** Industry generalization becomes a
  follow-up study. First question: does the effect exist at all on one
  high-quality target?
- **3 noise types → 1 (peer_materials).** Realistic enterprise noise is
  *adjacent content* — the peer 10-Ks a user would already be looking at,
  not engineered distractors. A finding that MSFT analysis degrades with
  Apple/Alphabet/Amazon filings in context is directly actionable; a
  finding about behavior under synthetic adversarial noise is not.
- **15 questions → 8.** Three factual + two calculation + three synthesis.
  The three synthesis questions map directly to the three task objectives
  (financial, strategic, AI-impact). No padding.
- **10 reps → 7.** Still adequate for within-cell variance estimation given
  the tighter grid; saves 30% of run cost.
- **10-K only → 10-K + earnings call.** Enterprise users paste both.
  Earnings-call commentary is where AI-impact evidence lives — essential
  for the new task.

Net effect: 91 runs instead of 1,480; $575 estimated vs $12–15K.

---

## 3. Task

Single prompt per run asks the analyst to answer 8 numbered questions about
Microsoft, grounded strictly in the provided **target materials** (10-K +
earnings call). The prompt embeds a scope-adherence constraint: other
documents in context are labeled and present "for scenario realism" — the
analyst is instructed to ground all claims in the target materials only.

**Question mix (8 total):**

| Tier | Type         | Count | Purpose                                                 |
| ---- | ------------ | ----- | ------------------------------------------------------- |
| 1    | Factual      | 3     | Direct extraction — detects retrieval drift.            |
| 2    | Calculation  | 2     | 2–3 step arithmetic — detects reasoning drift.          |
| 3    | Synthesis    | 3     | Financial health / strategic positioning / AI-impact.   |

See `PROMPTS.md` for exact question text and `RUBRIC.md` for scoring.

### 3.1 Ground-truth philosophy (important)

Financial analysis contains two kinds of claims, graded differently:

- **Verifiable facts** (Tier 1 + Tier 2): disclosed figures, derivations.
  Have ground truth. Binary right/wrong. **Auto-graded** against a
  ground-truth key.
- **Grounded judgments** (Tier 3): forecasts, strategic assessments,
  causal claims. *No ground-truth verdict.* A sound analysis is
  **grounded in evidence but reaches its own conclusions**; reasonable
  analysts disagree. These are **judge-graded on process**, not verdict.

For Tier 3, the ground-truth key contains `evidentiary_anchors` — specific
material disclosures a sound analysis should engage with. Anchors are
*disclosures that exist*, not conclusions the analyst must reach. Two
responses that cite the same anchors but reach opposite conclusions both
score high on groundedness.

Drift then decomposes into specific, measurable failure modes:

- **Retrieval drift** — Tier 1 accuracy drops (can't find disclosed numbers).
- **Reasoning drift** — Tier 2 accuracy drops (can't perform derivations).
- **Evidentiary drift** — Tier 3 engagement drops; fewer anchors
  referenced at higher fills.
- **Fabrication drift** — Tier 3 claims cite evidence that doesn't exist.
- **Misattribution drift** — peer-company data cited as Microsoft's.

Each is a distinct, production-relevant failure mode.

---

## 4. Variables and design

### 4.1 Independent variables

| Factor              | Levels                                                 | Notes                                                   |
| ------------------- | ------------------------------------------------------ | ------------------------------------------------------- |
| Context fill        | 0.00 (baseline), 0.25, 0.50, 0.75, 0.95                | Baseline = target materials alone, no noise.           |
| Target position     | start / middle / end (relative to noise)               | N/A at baseline. Question block always appended last.  |
| Replicates          | 7 per cell                                             | Required for within-cell variance under temp=1.        |

### 4.2 Fixed parameters

- **Model:** `claude-opus-4-7` (1M context, snapshot locked before pilot).
- **Extended thinking:** xhigh (token budget confirmed and locked).
- **Temperature:** 1.0 (forced by thinking; matches Claude Code default).
- **Target company:** Microsoft.
- **Target materials:** Microsoft 10-K (FY2025) + latest quarterly
  earnings-call transcript (Q2 FY2026). Combined ≈ 95K tokens.
- **Noise pool:** `peer_materials` — latest 10-Ks from seven large-cap tech
  peers an analyst would realistically bundle alongside MSFT.
  Pool totals **~628K tokens**; earnings-call supplement (future extension)
  extends this to ~770K.

### 4.3 Design grid

- Non-baseline cells: 4 fills × 3 positions × 1 noise × 1 report = **12**.
- Baseline cells: 1 (fill = 0).
- **Total cells: 13.**
- Total analyst runs: 13 × 7 = **91**.
- Total (response, question) pairs: 91 × 8 = **728**.

**Fill-target vs realized fill (important):** The noise pool is 628K tokens.
At 25/50/75% fill targets, the pool comfortably supplies the required noise
budget. At **95% fill (noise budget ~835K), the pool is exhausted** before
target is reached; realized fill at 95%-target cells caps at ~73–76% of
context (realized total ~730–760K). This is treated as a feature, not a bug:
realized fill is honestly recorded, and the analysis uses `realized_fill_pct`
as a continuous covariate rather than the nominal target. Pool exhaustion is
a **flag**, not an exclusion (see §7.5).

### 4.4 Randomization and caching

- Question order within the 8-item probe: shuffled per run (seed = run_id).
- Noise content: drawn per cell (seed = cell_id), **byte-identical across
  the 7 replicates of a cell** so the prefix stays in the Anthropic prompt
  cache. Cache breakpoints: system, noise_a, target_materials, noise_b.
- Reps within a cell run serially (back-to-back) to preserve the 5-minute
  cache TTL; different cells run in parallel.

---

## 5. Research questions and hypotheses

| ID   | Question                                                       | Hypothesis                                                                              |
| ---- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| RQ1  | Does quality decline as fill increases?                        | H1: mean quality at 95% < baseline (fill main effect negative and significant).         |
| RQ2  | Does position matter?                                          | H2: target-in-middle scores lowest at fill ≥ 50% ("lost in the middle").                |
| RQ3  | Does reasoning degrade faster than retrieval?                  | H3: Tier-2 accuracy slope vs fill is steeper than Tier-1's.                             |
| RQ4  | Is reasoning allocation itself context-sensitive?              | H4 (two-sided): thinking-token usage varies systematically with fill_pct.               |
| RQ5  | Does within-cell consistency decline with fill?                | H5: variance in numeric answers and pairwise similarity on tier-3 decline with fill.     |

Dropped from v0.1 (insufficient power at this grid size): cross-company
generalization (RQ on `report` random effect), cross-noise-type
comparison.

Hypotheses are pre-registered and locked before pilot.

### 5.1 Reframe: failure-mode classification, not pass/fail

v0.1 framed RQ4 as "does extended thinking compensate at high fill?" — a
one-directional hypothesis assuming thinking-budget usage is a dial the
model turns up under pressure. That framing is fragile: if Opus 4.7
self-allocates reasoning adaptively, the same drop in quality at 95% fill
could reflect two very different mechanisms:

1. **Context drift** — the model tries to reason at full depth but the
   noisy context degrades its work. Thinking-token usage is flat, quality
   drops. A pure retrieval/attention failure.
2. **Reasoning withdrawal** — the model reasons *less* under context
   pressure, either because it fails to recognize the difficulty or
   because internal routing favors shallower processing at high context
   load. Thinking tokens fall AND quality drops.

These are different findings. Conflating them wastes the experiment.

The 2×2 we actually want to map:

|                               | quality stable         | quality declines                     |
| ----------------------------- | ---------------------- | ------------------------------------ |
| thinking-tokens stable/rising | drift-resistant (null) | **pure context drift** (RQ1∧¬RQ4)   |
| thinking-tokens falling       | efficient adaptation    | **compound failure** (RQ1∧RQ4 neg)  |

Any of the four quadrants is a legitimate finding. The experiment's job is
to identify which quadrant Opus 4.7 lands in — not to confirm a
pre-specified direction.

### 5.2 Measurement addendum

`thinking_tokens` is captured per run, either from the SDK's usage field
directly (when exposed) or via a char/4 estimate over the response's
thinking content blocks. The provenance is recorded in
`thinking_tokens_source ∈ {"sdk", "estimated_char_per_4"}`. The estimate
is rough (~10% noise vs true tokenizer counts) but sufficient to detect
the macro trend across fill levels. If the SDK surfaces direct counts for
some runs and not others, that inconsistency is flagged and mixed-provenance
cells get a sensitivity analysis (§10.3).

---

## 6. Materials

### 6.1 Target materials (single bundle per cell)

Combined into one labeled block at the target position:

```
<<< TARGET MATERIALS: Microsoft Corporation >>>
  <<< 10-K FY2025 >>>
  [10-K text, ~100K tokens]
  <<< END 10-K >>>

  <<< EARNINGS CALL: Q2 FY2026 (latest) >>>
  [call transcript, ~30K tokens]
  <<< END EARNINGS CALL >>>
<<< END TARGET MATERIALS >>>
```

Version selection (to be locked before pilot):

- 10-K: MSFT FY2025 (filed ~Aug 2025).
- Earnings call: latest available as of lock date (likely Q2 FY2026, reported
  late Jan 2026).

Extracted to plain text, normalized, tokenized with Anthropic tokenizer,
SHA-256 hashed into `materials.lock.json`.

### 6.2 Noise corpus (peer_materials — realistic adjacent content)

Latest 10-Ks from seven large-cap tech peers an enterprise analyst would
realistically bundle alongside Microsoft for strategic and financial review:

| Peer       | Ticker | FY      | Tokens  | Why in the pool                                     |
| ---------- | ------ | ------- | ------- | --------------------------------------------------- |
| Apple      | AAPL   | FY2025  | 51,644  | #1 peer by market cap; AI-narrative counterpart.    |
| Alphabet   | GOOGL  | FY2025  | 86,080  | Most direct AI + cloud competitor (GCP, Gemini).    |
| Amazon     | AMZN   | FY2025  | 70,682  | AWS is Azure's most direct peer.                    |
| NVIDIA     | NVDA   | FY2026  | 85,094  | AI-infrastructure supplier; capex-cycle peer.       |
| Salesforce | CRM    | FY2026  | 102,063 | SaaS + Copilot-style AI product peer.               |
| Meta       | META   | FY2025  | 128,945 | AI-infrastructure capex + consumer-AI peer.         |
| Oracle     | ORCL   | FY2025  | 104,101 | Enterprise-software / Oracle Cloud peer.            |
|            |        |         |**628,609**| **pool total**                                   |

All sourced from SEC EDGAR inline-XBRL filings; converted to plain text via
the same pipeline as the target 10-K. Hashes and source URLs are pinned in
`materials/materials.lock.json`.

Documents **deliberately excluded** from the pool:

- **Prior-year MSFT 10-K.** Conflates same-company time-series with the
  cross-company scope test (a reader asking "FY25 revenue" while MSFT FY24
  is in context is legitimately ambiguous). Keep the scope test clean:
  noise is strictly other companies.
- **Sell-side analyst reports.** Copyright aside, they're *about* MSFT, so
  they don't test scope.
- **Off-domain or unrelated documents.** Not what real users paste.

Sampled greedily first-fit-decreasing with deterministic seed per cell.

**Future extension (not in v0.2 scope):** add the latest quarterly earnings
call transcript for each of the 7 peers (~140K additional tokens), bringing
the pool to ~770K and letting 95%-target cells hit ~88% realized.

### 6.3 Question bank and ground truth

8 questions about Microsoft, authored and ground-truthed by a human analyst
before any runs. Full text in `PROMPTS.md`. Ground-truth key includes:

- **Tier 1/2:** canonical value + unit + tolerance + citation spans.
  Verifiable facts; binary right/wrong.
- **Tier 3:** `evidentiary_anchors` — 4–6 specific material disclosures
  a sound analysis should engage with. Each anchor has a short summary,
  a `citation_span`, and a `source` (`10-K` or `earnings_call`). Anchors
  are *disclosures that exist*, not conclusions the analyst must reach.
  See `RUBRIC.md` for grading philosophy.
- `common_distractors`: specific numeric values from the peer corpus that
  could be mis-attributed to Microsoft (for programmatic cross-
  contamination detection).

---

## 7. Prompt assembly

```
[system prompt]                                  (cache breakpoint)
[noise block A]                                  (cache breakpoint, if present)
[target materials bundle: 10-K + earnings call]  (cache breakpoint)
[noise block B]                                  (cache breakpoint, if present)
[8-question block]                               (NOT cached — shuffled per rep)
```

Target position controls the A/B noise split:

- `start`:  A = 0, B = total_noise
- `middle`: A = B = total_noise / 2
- `end`:    A = total_noise, B = 0

Noise-block and target-block headers are explicit so the model has fair
notice of which document is the target. That's the realistic condition —
a user pasting multiple filings labels them.

---

## 8. Run harness (see `harness/`)

Per-run flow:

1. Resolve noise budget to hit target fill ± 500 tokens.
2. Assemble prompt with cache breakpoints.
3. Call Opus 4.7 with `thinking={type:enabled, budget_tokens: xhigh}`,
   `temperature=1.0`, `max_tokens=8192`.
4. Log request/response: realized tokens, cache-hit metadata, thinking
   tokens, latency, stop reason, full text.
5. Validate against pre-registered exclusion rules.
6. Persist + mark complete in manifest.

**Pre-registered exclusions:**

- **Over-target fill:** realized input tokens exceed target by > 500 tokens
  (we put in too much — programmer error).
- **Under-target fill NOT caused by pool exhaustion:** realized input short
  by > 500 tokens *when additional noise was available in the pool*. This is
  also a programmer error.
- Output addressing < 50% of questions.
- HTTP error not recovered by retry.

**Not exclusions (flagged instead):**

- **Pool-exhausted fill:** at high targets (typically 95%-target cells), the
  sampler packs the entire pool and still falls short. Recorded as
  `pool_exhausted=true` and the realized fill is honestly logged. Analysis
  uses `realized_fill_pct` as a continuous covariate.
- Malformed JSON and partial answers — dependent variables, not exclusions.

---

## 9. Evaluation

### 9.1 Structured extraction

Short-context Haiku 4.5 pass normalizes each response into per-question
JSON. Decouples grading from temperature=1 phrasing variance.

### 9.2 Tier 1 / Tier 2 — auto-graded

- Numeric: within tolerance (abs or rel).
- Citation match: partial credit 0.5 if answer correct but citation wrong.
- **Cross-contamination flag:** answer matches any `common_distractor`
  value (attributed peer data to MSFT).

### 9.3 Tier 3 — judge-graded (process, not verdict)

**v0.3 change (2026-04-24):** primary judge flipped from Sonnet 4.6
triple-pass median to Opus 4.7 single-pass at `effort=max`. Justification:
adaptive max-effort thinking collapses per-call variance enough that
single-pass replaces triple-pass aggregation; Sonnet remains in the
design as the cross-model reliability anchor on a 20% subsample.
Within-model judging is acceptable here because this is a within-model
*drift* study (judge runs at fill=0, no context pressure) — same-model
judging is not the bias source the original design feared.

- **Primary judge:** Opus 4.7, adaptive thinking `effort=max`, single
  pass per response. Output schema includes the five 1–5 dimensions plus
  `reasoning_quality` (0–10 holistic) and (for MSFT-S-03 only) the
  three Q8 structural diagnostics: `units_decomposed`,
  `frameworks_applied`, `synthesis_consistent`.
- **Secondary judge:** Sonnet 4.6, `effort=high`, on a 20% deterministic
  subsample of (run, q_id) pairs, for cross-model inter-rater reliability
  (ICC and Lin's CCC per dimension). Not a correctness check; a
  rubric-application consistency check.
- **Pairwise vs baseline:** Opus 4.7 max-effort, 25% deterministic
  subsample of non-baseline (run, q_id) pairs. A/B randomized; baseline
  is matched by `rep_idx` and `q_id`.
- **Dimensions (5 × Likert 1–5):** groundedness, evidentiary_breadth,
  scope_adherence, clarity, citation_accuracy. Plus programmatic counts:
  `unsupported_claims`, `cross_contamination`.
- Judge is given the question + evidentiary anchors + candidate response
  **and the full target materials block (cached)**. The v0.2 doctrine
  of "anchors only, never the source" was reversed in v0.3 because
  PROMPTS.md §6 added a cached system block carrying the full 10-K +
  earnings call as the source-of-truth for groundedness; anchors became
  the *breadth guide* (what the analysis ought to engage with), not the
  *only* reference.
- **Verdicts are not graded.** A response reaching any conclusion grounded
  in cited evidence scores high; a response fabricating evidence scores
  low regardless of conclusion.

See `RUBRIC.md` for anchors, the grading-philosophy preamble, and the
ICC/CCC aggregation rules.

### 9.4 Consistency metrics

Per cell, across the 7 reps:

- Tier 1/2: share of reps producing the same extracted answer; CV of numeric.
- Tier 3: mean pairwise cosine similarity of responses; mean pairwise judge
  preference rate.

---

## 10. Statistical analysis

### 10.1 Primary model

```
quality_score ~ fill_pct * position * tier
              + (1 | question_id) + (1 | run_id)
```

Mixed-effects via `lme4::lmer` (Gaussian for Likert composites) /
`glmer` binomial (tier 1/2 correctness). `report` is fixed (single
company, no random effect). `fill_pct` is the **realized** fill (continuous),
not the nominal target — honest about the pool-exhaustion case at 95%-target
cells.

### 10.2 Pre-registered tests

- H1: fill main effect on quality (negative, significant).
- H2: fill × position interaction; middle < {start, end} at ≥50%.
- H3: fill × tier interaction; Tier-2 slope more negative than Tier-1.
- H4 (two-sided): regression of thinking_tokens on fill_pct; slope ≠ 0.
  Direction matters but is not pre-specified:
    - positive slope ⇒ compensatory allocation
    - negative slope ⇒ reasoning withdrawal
    - null ⇒ allocation is fill-invariant; H1 effects are pure context drift
- H5: within-cell variance on tier 2 increases with fill.

Secondary: quadrant classification (§5.1). Report the quality × thinking
2×2 per tier as the headline interpretive output. Each cell in the grid
is populated by mean shift from baseline + CI.

Holm-Bonferroni across the 5 primary tests.

### 10.3 Sensitivity

- Include `cache_hit` as covariate; re-fit. If `cache_hit` coefficient is
  significant, report separately.
- Judge-model effect on the 20% dual-judged sample.
- Analysis with vs without excluded runs.
- **thinking_tokens_source:** if mixed provenance across runs (some `sdk`,
  some `estimated_char_per_4`), re-fit H4 restricted to each provenance
  class. If slopes differ in sign or significance, flag as measurement
  artifact and default to the `sdk` subset for H4 conclusions.

---

## 11. Pilot

**Purpose:** validate pipeline end-to-end at a small cost before full run.

**Pilot cells (3 cells × 7 reps = 21 runs):**

1. Baseline (0% fill).
2. 50% fill / middle position.
3. 95% fill / middle position.

Go/no-go criteria:

- Structured-output parse rate ≥ 98%.
- Judge ICC ≥ 0.70 on pilot tier-3 scoring.
- Realized fill within ±500 tokens of target.
- Pilot cost within 2× projection.

If any fails, iterate on design before full run. Pilot cost estimate: ~$50.

---

## 12. Risks and mitigations

| Risk                                                  | Mitigation                                                                                         |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| MSFT materials memorized from training                | Baseline performance will be inflated. Drift = Δ from baseline; memorization actually strengthens the drift finding ("model knows it, but context noise breaks the answer anyway"). |
| Single company → limited generalization               | Explicitly scoped. Follow-up study can extend to other companies / noise types.                    |
| Judge self-preference (Opus judging Opus)             | Primary judge is Opus 4.7 (max effort, low per-call variance) but the **judge runs at fill=0** — the bias the original design feared was *judges drifting under context pressure too*, which is structurally avoided here. Sonnet 4.6 cross-model ICC/CCC on 20% subsample acts as the external check; if a dimension's ICC < 0.70, fall back to pairwise comparison. |
| Prompt-cache behavioral artifacts                     | Log cache status; include as covariate in sensitivity analysis.                                   |
| API non-determinism beyond temp=1                     | 7 reps per cell + run_id random effect.                                                           |
| Budget overrun                                        | CostTracker enforces hard-stop at $850; pilot locks envelope before full run.                     |
| Noise contains MSFT-compatible figures                | Noise corpus hand-screened against ground-truth key during material prep.                          |
| Model update mid-study                                | Pin model snapshot ID; re-run from scratch on snapshot change.                                    |

---

## 13. Cost estimate

Per-rep cost model (Opus 4.7, with prompt cache):

- First rep in cell: `fill × 1M × $18.75/M` (cache write) + `~34K × $75/M`
  output ≈ thinking + answer.
- Subsequent reps: `fill × 1M × $1.50/M` (cache read) + same output.

| Component        | At N=7           |
| ---------------- | ---------------- |
| Collect (analyst runs) | ~$445     |
| Extractor (Haiku)      | ~$1       |
| Judge absolute (Sonnet, 3 passes) | ~$62 |
| Judge dual (20% Opus)  | ~$61      |
| Judge pairwise (25% subsample) | ~$7 |
| **Total**              | **~$575** |
| Budget                 | $700      |
| Hard stop              | $850      |

Margin of ~$125 covers cache-miss re-writes, retry cost, and a handful of
materials-prep sanity runs.

---

## 14. Deliverables

1. This pre-registration document (frozen before pilot).
2. Frozen materials (10-K, earnings call, competitor noise, questions,
   ground-truth JSON) with `materials.lock.json`.
3. Run harness code (`harness/`) at a pinned commit.
4. Raw data: JSONL dump of 91 runs (full prompts, responses, usage).
5. Analysis notebook (R, mixed-effects models).
6. Final report: all 5 hypothesis tests, effect sizes, decomposed drift
   diagnosis, practical guidance.

---

## 15. Open items (lock before pilot)

- [ ] xhigh thinking-token value (current estimate 32K).
- [ ] Opus 4.7 exact snapshot ID.
- [ ] MSFT 10-K fiscal year (FY2025 current best pick).
- [ ] Earnings call quarter (Q2 FY2026 current best pick).
- [ ] Final competitor list (current candidates: GOOGL, AMZN, ORCL, CRM,
      SAP, META).
- [ ] Question text finalized and ground-truthed.

---

## File map

- `DESIGN.md` — this document.
- `PROMPTS.md` — system prompt, question block, extractor, judge prompts.
- `RUBRIC.md` — judge rubric with 1–5 anchors.
- `harness/` — run harness (config, src, scripts).
- `materials/` — created during material-prep phase.
- `analysis/` — R notebooks (created post-collection).
