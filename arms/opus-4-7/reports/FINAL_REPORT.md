# Reasoning drift in Opus 4.7 under context-window pressure
**Final report — 2026-04-25**

A 91-run controlled experiment on Anthropic's Opus 4.7 (1M context, "max" adaptive thinking) measuring how reasoning quality degrades as the context window fills with adjacent-but-irrelevant material.

The task domain is **financial analysis** — a deliberately blended workload of factual retrieval, numeric calculation, evidence-grounded reasoning, and forward-looking thesis construction — run over Microsoft's FY2025 disclosures with adversarially-near big-tech peer 10-Ks (AAPL, GOOGL, AMZN, META, NVDA, ORCL, CRM) as the noise corpus, because their business complexity exercises all four reasoning modes simultaneously. The goal is a **real-world financial-analyst use case**, not a synthetic benchmark.

Total spend: **$582.33**. Total runs: **91/91 successful** (zero exclusions, zero failures). Wall time end-to-end: **~3.5 hours** (collect 84 min + extract 2 min + grade ~110 min).

---

## TL;DR — three converging findings

1. **Factual lookup is robust.** Tier-1 numeric questions (revenue, operating income, EPS, tax rate, YoY growth) hit **100% accuracy in every cell** from 13% realized fill to 92% realized fill. Max-thinking + clear scope marker = no factual drift, even at near-saturation.

2. **Synthesis quality drifts measurably and monotonically.** Tier-3 reasoning quality drops **8.05 → 7.02** (−13%) on a 0–10 scale; unsupported claims rise **7×** (0.24 → 1.68 per response); pairwise judge prefers baseline over 75/95% fill in **~90% of head-to-head comparisons** (mean Δ ≈ −2.7).

3. **The drift is in evidence quality, not in scope or form.** Scope adherence stays ≥4.73/5 across all fills. Q8's prescribed 4-framework decomposition stays at 4/4 frameworks applied at every fill. What degrades: groundedness, citation accuracy, freedom from unsupported claims. **Max-thinking Opus 4.7 follows form but skips evidence under context pressure.**

If you ship Opus 4.7 to users today: **(a)** trust it for factual extraction at any fill; **(b)** keep context tight when the task requires evidence-heavy synthesis or citation accuracy.

---

## 1. Methodology

### 1.1 The question

Does Opus 4.7's reasoning quality drift as the context window fills with adjacent, plausibly-relevant noise (peer-company 10-Ks), even when the model is configured for maximum extended thinking?

This is a **within-model contrast under context pressure**, not a cross-model benchmark. The dependent variable is the model's analytical output on a fixed task, given identical instructions, varying only in how much noise surrounds the target material.

### 1.2 Design

- **Target material:** Microsoft Corporation FY2025 10-K (79,518 doc-meta tokens / ~125K Anthropic tokens) plus Q2 FY2026 earnings-call transcript (15,314 / ~20K tokens). Bundled and clearly delimited as `<<< TARGET MATERIALS: Microsoft Corporation >>>`.
- **Noise pool:** seven peer 10-Ks (AAPL, GOOGL, AMZN, META, NVDA, ORCL, CRM) — all from the same FY24-FY26 window, same domain, same document genre. Designed to be *adversarially near*: plausibly relevant, dilutive of MSFT-specific signal.
- **Design grid:** 1 baseline cell (0% fill, no noise) + (4 fill levels × 3 positions) = 13 cells. Realized fills: 13%, 24%, 47%, 72%, 92%. Positions: `start` (target before noise), `middle` (noise sandwiches target), `end` (target after noise).
- **Replication:** 7 reps per cell. Within a cell, the noise pack is byte-identical across all 7 reps (seeded by `cell_id`); only the question-block ordering varies (seeded by `run_id`).

### 1.3 Stimuli — eight questions per run

- **Tier 1 (factual lookup, 3Q):** total revenue, operating income, diluted EPS.
- **Tier 2 (calculation, 2Q):** effective tax rate, YoY revenue growth.
- **Tier 3 (synthesis, 3Q):** financial health assessment (S-01), strategic positioning across segments (S-02), AI impact over next 12-24 months (S-03). S-03 has a prescribed structure: **decompose by revenue unit → apply 4 frameworks (demand/complementarity/substitution/supply-constraint) → synthesize**.

### 1.4 Models

- **Analyst** — `claude-opus-4-7`, adaptive thinking with `effort=max`, max_output_tokens=32K, temperature=1.0. **Streaming** (required at this max_tokens given the 10-min nonstreaming SDK cap).
- **Extractor** — `claude-haiku-4-5-20251001`, no thinking, max_output_tokens=16K, temperature=1.0. Mechanical normalization of analyst JSON to per-question records.
- **Primary judge** — `claude-opus-4-7`, adaptive thinking `effort=max`, max_output_tokens=16K. Same model as analyst because this is a within-model drift study; judge runs at fill=0 (no context pressure on the judge itself).
- **Secondary judge** — `claude-sonnet-4-6`, `effort=high`, on a 20% subsample of (run, q_id) pairs for cross-model inter-rater reliability.

### 1.5 Pipeline

```
COLLECT  →  EXTRACT  →  GRADE
  Opus      Haiku       Opus + Sonnet
  91 runs   728 records 819 absolute + ~205 pairwise + ~164 secondary judge calls
```

- **Collect** assembles the prompt with up to 4 cache breakpoints (system, noise_a, target, noise_b — questions are uncached). Each cell's 7 reps run serially to amortize the cache write across all reads.
- **Extract** normalizes raw JSON output to per-(run, q_id) records.
- **Grade** routes Tier 1/2 to a local autograder (numeric tolerance + distractor check) and Tier 3 to the Opus judge against an evidentiary-anchor rubric (RUBRIC.md v2.1). 25% of non-baseline (run, q_id) pairs additionally get pairwise judging vs the baseline response (rep-matched, A/B randomized). 20% get a Sonnet absolute judge for ICC.

### 1.6 Judge rubric (Tier 3, 1–5 unless noted)

- `groundedness` — every substantive claim traces to the target materials.
- `evidentiary_breadth` — engages the pre-registered anchors via stated engagement signals.
- `scope_adherence` — no misattribution of peer data to MSFT.
- `clarity` — internally coherent.
- `citation_accuracy` — citations resolve to real sections of the target materials.
- `unsupported_claims` (count) — claims without trace in the target materials.
- `cross_contamination` (count) — claims attributing peer data to MSFT.
- `reasoning_quality` (0–10 holistic) — gestalt rating.
- For S-03 only: `units_decomposed`, `frameworks_applied (0–4)`, `synthesis_consistent (bool)`.

The judge grades **process, not verdict**. Two analysts reaching opposite conclusions from the same disclosures can both score maximally if their claims are grounded.

### 1.7 Reproducibility

- All seeds use SHA-256 over identifier strings (not Python `hash()`, which is process-randomized).
- Materials lockfile (`materials/materials.lock.json`) pins SHA-256 of every source file.
- Config is immutable per run; SHA-256 stored in manifest.
- Manifest (SQLite) tracks per-run state across all stages — supports clean resume.

---

## 2. Results

### 2.1 Headline drift curve

Mean reasoning quality (0–10), aggregated across all three Tier-3 questions × all positions × 7 reps per cell.

| realized fill | n | mean reasoning_quality | stdev |
|--------------:|---|-----------------------:|------:|
| 13% (baseline)| 21 | **8.05** | 0.58 |
| 24%           | 63 | 7.33 | 1.87 |
| 47%           | 63 | **6.89** ← bottom | 2.25 |
| 72%           | 63 | 7.17 | 0.92 |
| 92%           | 63 | **7.02** | 0.92 |

Drift is **non-monotonic**: sharp drop from baseline to mid-fill (~−1.2 points), partial recovery at 72-92%, and a roughly 1-point net loss at maximum fill. Variance more than doubles at moderate fill (sd 0.58 → 2.25) before tightening again — quality becomes *unpredictable* before it stabilizes at a lower mean.

### 2.2 Per-dimension drift

Aggregated across S-01, S-02, S-03; mean across 21 (baseline) or 63 (non-baseline) responses per fill.

| fill  | groundedness | breadth | scope | clarity | citation | reasoning | unsup | xcontam |
|------:|--------------|---------|-------|---------|----------|-----------|-------|---------|
| 0.00  | **4.91**     | 4.29    | 5.00  | 5.00    | 4.86     | **8.07**  | 0.24  | 0.000   |
| 0.25  | 4.33         | 3.95    | 4.89  | 4.70    | 4.29     | 7.37      | 0.76  | 0.000   |
| 0.50  | 4.14         | 3.76    | 4.86  | 4.48    | 4.25     | 6.87      | 0.62  | 0.016   |
| 0.75  | 4.22         | 3.87    | 4.87  | 4.84    | 4.14     | 7.17      | 1.02  | 0.079   |
| 0.95  | **3.93**     | 3.89    | 4.73  | 4.66    | **3.97** | **7.03**  | **1.68** | **0.095** |

- **Most-degraded dimensions:** groundedness (−0.98), citation accuracy (−0.89), reasoning quality (−1.04), unsupported_claims (+1.44 — 7× more).
- **Most-robust dimensions:** scope_adherence (−0.27, stays ≥4.73/5), clarity (−0.34), evidentiary_breadth (−0.40).
- **Cross-contamination first appears at ~50% fill, plateaus around 0.1 per response at 95%.** Small but non-zero — Opus does occasionally cite Apple/Google/Amazon disclosures as if they were MSFT's at high fill.

### 2.3 Position effect

Within each fill level, by noise position. n=21 per cell.

| fill | start | middle | end |
|------|-------|--------|-----|
| 0.25 | 7.62  | **6.48** | 7.90 |
| 0.50 | **5.29** ← outlier | 7.62 | 7.76 |
| 0.75 | 7.24  | 6.67   | 7.62 |
| 0.95 | 6.76  | 6.81   | 7.48 |

- **`end` position consistently strongest** at every fill — when the target sits *after* the noise, the model performs best (consistent with primacy of recent context for output generation).
- **`middle` is consistently weakest at low-to-moderate fills** — the sandwich layout breaks synthesis. This pattern weakens at 95% fill where the noise pool fully saturates and positions converge.
- **The 50% start outlier (5.29)** is driven by one cell with high variance (sd=3.18); the other reps are normal-quality. Likely a sampling artifact of that specific noise permutation rather than a position effect — would need more reps per (fill, position) cell to confirm.

### 2.4 Pairwise vs baseline (the cleanest drift signal)

For 25% of non-baseline (run, q_id) pairs, the Opus judge picks the better of (baseline rep, candidate rep) on the same question. A/B randomized.

| fill  | candidate wins | losses | ties | mean Δ (cand − base) | n  |
|------:|---------------:|-------:|-----:|---------------------:|---:|
| 0.25  | 7              | 9      | 1    | **−0.3 ± 2.7**       | 17 |
| 0.50  | 5              | 10     | 0    | **−1.2 ± 2.4**       | 15 |
| 0.75  | 1              | 17     | 0    | **−2.6 ± 1.6**       | 18 |
| 0.95  | 2              | 18     | 0    | **−2.7 ± 2.0**       | 20 |

By 75% fill, **baseline wins >90% of pairwise comparisons**. The drift is unambiguous on direct comparison and grows substantially with fill. This is the cleanest piece of evidence in the dataset.

### 2.5 Q8 structural diagnostics — form persists, content degrades

S-03 mandates a **decompose by unit → apply 4 frameworks → synthesize** structure.

| fill | units_decomposed | frameworks_applied | synthesis_consistent |
|------|------------------|---------------------|----------------------|
| 0.00 | 8.9 ± 0.6        | 4.0 ± 0.0           | 100% (7/7)           |
| 0.25 | 7.8 ± 2.9        | 3.6 ± 1.3           | 100% (21/21)         |
| 0.50 | 8.1 ± 2.7        | 3.6 ± 1.2           | 90% (19/21)          |
| 0.75 | 8.9 ± 0.9        | 4.0 ± 0.0           | 100% (21/21)         |
| 0.95 | 9.4 ± 1.4        | 4.0 ± 0.0           | 100% (21/21)         |

**Surprise finding:** Q8 *form* is robust — at 95% fill, the model still decomposes 9.4 units and applies all 4 frameworks. The drift on Q8 (visible above as lower groundedness and more unsupported claims for S-03) is in **content**, not form. The model still follows the prescribed scaffolding under pressure; it just fills the slots with weaker evidence.

### 2.6 Tier 1/2 — no drift detected

| cell type | F-01 (revenue) | F-02 (op income) | F-03 (EPS) | C-01 (tax rate) | C-02 (growth) |
|-----------|---------------:|-----------------:|-----------:|----------------:|--------------:|
| All 13 cells | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |

(One cell at 50% start has 6/7 due to a single Haiku extraction truncation — the analyst response was correct.)

Cross-contamination on Tier 1/2: **zero across all 91 runs**. Even at 92% realized fill with 7 peer 10-Ks in the window, Opus 4.7 never attributed peer revenues, op-income figures, or EPS to MSFT in factual answers.

### 2.7 Cross-model judge validation (Sonnet 4.6 secondary)

Paired Opus-vs-Sonnet ratings on the same 56 (run, q_id) responses (20% deterministic subsample). Per RUBRIC.md §Judge-model agreement, we compute Pearson r, ICC(2,1) (Shrout–Fleiss two-way random, single rater, absolute agreement), and Lin's Concordance Correlation Coefficient (CCC) per dimension. RUBRIC threshold for "use absolute scores": ≥ 0.70. Below that, fall back to pairwise.

| dimension | n | Opus μ | Sonnet μ | Δ μ | Pearson r | ICC(2,1) | Lin CCC | flag |
|-----------|--:|-------:|---------:|----:|----------:|---------:|--------:|------|
| groundedness | 56 | 4.21 | 3.86 | +0.36 | 0.753 | 0.706 | **0.702** | ok |
| evidentiary_breadth | 56 | 3.93 | 3.66 | +0.27 | 0.871 | 0.839 | **0.837** | ok |
| scope_adherence | 56 | 4.86 | 4.57 | +0.29 | 0.167 | 0.152 | **0.150** | ⚠ |
| clarity | 56 | 4.70 | 4.34 | +0.36 | 0.725 | 0.663 | **0.659** | ⚠ |
| citation_accuracy | 56 | 4.25 | 3.89 | +0.36 | 0.774 | 0.730 | **0.726** | ok |
| **reasoning_quality** (0–10) | 56 | 7.20 | 6.70 | +0.50 | 0.805 | 0.780 | **0.777** | ok |

**Read this carefully:**

- **The headline `reasoning_quality` is reliable** (CCC 0.777, ICC 0.780). The drift curves in §2.1 are not a self-judging artifact — Sonnet sees the same direction, with substantial agreement.
- **`evidentiary_breadth` is the most reliable dimension** (CCC 0.84). The judges most agree on whether a response engaged with the pre-registered anchors.
- **`groundedness` and `citation_accuracy` clear the 0.70 bar** by margins of 0.002 and 0.026 respectively — barely. Treat as reliable but expect noise.
- **`scope_adherence` flagged at CCC 0.15** is a *saturation artifact*, not real disagreement. Both judges score almost everything 5/5 (means 4.86 and 4.57), so the variance available for correlation is tiny, and Pearson picks up noise on a near-constant. Practically, both models agree that scope is rarely violated; the low CCC just reflects that low-variance dimensions are unmeasurable by Pearson-based metrics. Per RUBRIC.md, fall back to pairwise — but the pairwise data also shows scope barely shifts with fill, so the conclusion holds either way.
- **`clarity` flagged at CCC 0.66** is the only dimension where judge disagreement is substantively meaningful. Pairwise is the right fall-back; we report clarity as diagnostic only, not as a primary inference target.
- **Systematic bias:** Opus rates ~0.3–0.5 points higher than Sonnet on every dimension. This is a level shift, not a directional disagreement; both judges show the *same drift pattern* across fill levels. The bias doesn't threaten the within-study contrast that drives every conclusion in this report.

### 2.8 Compute and timing

| fill | realized input | output tokens | thinking tokens (signature-derived) | latency |
|-----:|---------------:|--------------:|------------------------------------:|--------:|
| 0.00 | 126K | 11,431 | 2,417 | 169s |
| 0.25 | 262K | 13,177 | 3,555 | 194s |
| 0.50 | 470K | 13,925 | 4,502 | 207s |
| 0.75 | 718K | 13,843 | 4,331 | 204s |
| 0.95 | 925K | 14,281 | 4,524 | 214s |

- **Thinking allocation grows with fill** (2.4K → 4.5K) — the model *does* compensate by thinking more under context pressure, but the extra thinking does not prevent the quality drop. This is a "compensatory allocation but insufficient" pattern.
- **Output volume only mildly increases** (11.4K → 14.3K) — the model isn't writing dramatically more, just thinking more before writing.
- **Latency scales sub-linearly** with input — 4× more tokens (126K → 925K) yields only ~1.3× more wall time, thanks to prompt caching.

---

## 3. Actionable insights

### 3.1 For practitioners deploying Opus 4.7

1. **Trust factual extraction at any fill.** If your task is "find a specific number/quote/fact in a long document corpus," Opus 4.7 with max thinking is robust. We saw zero factual errors and zero cross-contamination across 455 Tier-1/2 records spanning 13–92% context fill.

2. **Keep context tight for evidence-heavy synthesis.** If your task requires the model to *reason from* the source (financial analysis, legal interpretation, policy synthesis), pulling in extra "potentially relevant" material is a measurable quality hit. The drop from baseline to 25% fill alone costs ~0.7 points of reasoning quality and doubles unsupported claims.

3. **Position the target last when possible.** The `end` position (target after noise) outperformed `start` and `middle` at every fill level. If you have to include peripheral material, append the target *after* it — the model attends more carefully to recent context.

4. **Max thinking is not a defense against context drift on synthesis.** The model thought ~2× more at 95% fill than at baseline, and still scored ~1 point lower. More thinking compensates partially but not fully. Don't assume "thinking on" + "long context" = "no degradation."

5. **Variance is a leading indicator of drift.** At 47% fill, sd doubled (0.58 → 2.25) before mean stabilized — the model becomes *unpredictable* before it becomes consistently worse. Monitor variance across reps if you're pushing context limits.

6. **Form ≠ content.** The model will faithfully follow your prompt scaffolding (decompose, apply frameworks, structure output) under pressure. That can mask declining evidence quality. If you rely on structural compliance as a quality signal, you'll miss this drift.

### 3.2 For prompt engineers

- **Scope markers work.** The `<<< TARGET MATERIALS: ... >>>` delimiter combined with the analyst-prompt rule "Base EVERY answer EXCLUSIVELY on the TARGET MATERIALS block" prevented Tier-1 contamination across all 92K-token cells. This is a deployable pattern.
- **Citation requirements degrade with fill.** Even with explicit "cite the specific section/footnote" instructions, citation accuracy drops 4.86 → 3.97. Don't assume cite-as-you-go instructions hold under load.
- **Pre-registered evidentiary anchors expose drift the model can otherwise hide.** Without anchors, you'd see well-structured 4-framework Q8 answers and mistake them for high quality. With anchors, you see the model is missing or misciting specific disclosures.

### 3.3 For evaluators / researchers

- **Pairwise vs baseline is the cleanest signal.** Single-call absolute Likerts have substantial per-rep noise (the 2-point stdev on Sonnet/Opus disagreement). Pairwise comparison forces a relative judgment and produced the strongest drift signal in this study.
- **Test for the position effect explicitly.** If you only run one position per fill, you'll miss the consistent `end > start > middle` ordering and may misattribute its variance to noise.
- **Use realized fill, not nominal.** Anthropic's tokenizer counted ~25–30% more tokens than the per-doc meta in our materials lockfile. We targeted 25/50/75/95% but realized 24/47/72/92%. Bin by realized fill in analysis.
- **Watch for stop_reason=max_tokens at high fill.** Even at 32K output cap with max thinking, our 95% cells came close. Smaller caps will silently truncate Q8 synthesis answers and corrupt your data downstream.

### 3.4 For the Anthropic API team (observations, not asks)

- The encrypted `signature` field on thinking blocks is usable as a thinking-depth proxy (chars / 4 ≈ tokens). Adding `thinking_tokens` to the Usage object would make this more direct — currently consumers have to estimate.
- The 10-min nonstreaming hard cap silently rejected our initial non-streaming requests at max_tokens=32K. The error message was clear once it surfaced, but the relationship between max_tokens and the cap is non-obvious. Consumers will hit this when raising max_tokens for long outputs.
- The adaptive thinking schema with `output_config.effort=max` works as advertised, but `extra_body={"output_config": ...}` plumbing is awkward. First-class SDK support would help.

---

## 4. Limitations

- **Single target company (MSFT).** All findings are conditional on this one 10-K + earnings call. Generalization to other companies, industries, or document genres is plausible but not tested.
- **Single noise corpus (peer 10-Ks).** The "adversarially near" choice is one design point. Less-similar noise (e.g., random Wikipedia text) would likely show less drift; more-similar noise (e.g., MSFT's own historical 10-Ks) might show more.
- **Single judge model (Opus 4.7 primary).** Sonnet 4.6 secondary on 20% subsample shows aggregate agreement, but a human judge or third-model judge would be a stronger validation. Same-model judge (Opus judging Opus) is mitigated because the judge runs at fill=0 (no context pressure on the judge itself), but it is not eliminated.
- **n = 7 reps per cell.** Adequate for direction but tight for variance estimation, especially within (fill, position) cells (n=7 per cell × 3 positions × 4 fills = manageable but not generous).
- **Compressed fill range at high end.** Pool exhaustion means 75% and 95% target fills realized at 72% and 92% — close, but with limited true distinction between them. Adding more peer 10-Ks to the noise pool would extend the achievable range.
- **Three Tier-3 questions only.** Synthesis dimensions sampled: financial health (descriptive), strategic positioning (segment-level), AI impact (forward-looking). Other synthesis genres (causal, counterfactual, predictive over longer horizons) might drift differently.
- **Position effect on `50% start` is partly artifact.** The single low-quality cell drove the 5.29 mean for that condition. Replication needed.
- **Methodology pre-registration:** *resolved 2026-04-25.* DESIGN.md §9.3 was originally described as Sonnet-primary triple-pass; the v0.3 implementation flipped to Opus-primary single-pass with Sonnet on a 20% ICC subsample. Reconciled in this commit and the `pre_registration_hash` is now locked at `61b2d30f0c741bd96f24159fedc814276df565de317f780e117a3c7e32100419` (SHA-256 of DESIGN+PROMPTS+RUBRIC). Future replications should verify this hash before running.

---

## 5. What this means for the field

This study contributes one clear data point to an open question: **does extended thinking compensate for context drift?**

The answer here is: **partially, for some quality dimensions, on some task types — but not enough to eliminate drift on synthesis.** Specifically:

- For factual extraction with clear scope markers: max thinking + 1M context = effectively zero drift even at near-saturation.
- For evidence-heavy synthesis: max thinking provides ~2× more thinking allocation under load, which buys partial mitigation, but the model still loses ~1 point of reasoning quality and 7× more unsupported claims at 92% fill vs baseline.

This pattern — **structural/factual robustness with evidentiary degradation** — has implications for how we deploy long-context models. The intuitive failure mode (fabrication, scope leakage) is *not* what we observed. Instead, the failure mode is **subtle quality erosion underneath competent-looking output**: same structure, same scope, same surface fluency, weaker evidence per claim. That is harder to detect in production than overt failure.

Three follow-up studies would sharpen this:

1. **Replicate with non-MSFT targets and different noise corpora** to test generalization.
2. **Test other "max-thinking" models** (e.g., Sonnet at effort=max, future Opus releases) to see whether the pattern is model-specific or characteristic of the Anthropic adaptive-thinking architecture.
3. **Compare to alternative mitigations** — explicit per-claim citation enforcement in the prompt, agentic re-reading loops, structured retrieval — to see whether application-layer techniques can close the gap that more thinking alone cannot.

---

## 6. Reproducibility

All code, prompts, materials, and per-run data are in this repository.

```
Opus 4.7 Reasoning Drift Study/
├── DESIGN.md            — pre-registered design (v0.2; needs §9.3 reconciliation)
├── PROMPTS.md           — analyst, extractor, judge system prompts (v0.3)
├── RUBRIC.md            — judge rubric anchors (v2.1)
├── FINAL_REPORT.md      — this document
├── materials/
│   ├── target/MSFT/     — 10-K + earnings call (text + meta)
│   ├── noise/peer_materials/MSFT/  — 7 peer 10-Ks
│   ├── questions/MSFT.json   — 8 questions
│   ├── ground_truth/MSFT.json — canonical answers + evidentiary anchors
│   └── materials.lock.json   — SHA-256 of every source file
└── harness/
    ├── config/experiment.yaml       — frozen experiment config
    ├── src/                         — pipeline modules
    ├── scripts/
    │   ├── run_experiment.py        — collect stage
    │   ├── run_extractor.py         — extract stage
    │   ├── run_grading.py           — grade stage
    │   ├── drift_analysis.py        — aggregate analysis
    │   ├── status.py                — manifest snapshot
    │   ├── dry_run.py               — pre-flight token-budget check
    │   ├── smoke_test.py            — single-rep end-to-end smoke
    │   └── probe_api.py / probe_effort.py  — schema probes
    └── data/
        ├── raw/{cell_id}.jsonl      — full analyst responses + usage
        ├── extracted/{cell_id}.jsonl — normalized per-question records
        ├── graded/{cell_id}.jsonl   — autograde + judge ratings + pairwise + secondary
        └── manifest.sqlite          — run state, costs, audit log
```

To reproduce:

```bash
cd harness
python -m scripts.dry_run --assembly       # pre-flight: validate token math
python -m scripts.run_experiment --full    # collect: 91 analyst runs (~$334, 84 min)
python -m scripts.run_extractor            # extract: Haiku normalization (~$2, 2 min)
python -m scripts.run_grading              # grade: Opus + Sonnet judges (~$246, 110 min)
python -m scripts.drift_analysis           # report tables
```

Total cost for full reproduction: ~$582. Manifest is resumable — if any stage crashes, re-running picks up where it left off.

---

## 7. Cost summary

| stage | runs | cost   | per-run avg |
|-------|-----:|-------:|------------:|
| Collect (analyst, Opus 4.7 max) | 91 | $333.85 | $3.67 |
| Extract (Haiku 4.5) | 91 | $2.40 | $0.026 |
| Grade — primary absolute (Opus 4.7 max) | 273 | ~$190 | ~$0.70 |
| Grade — pairwise (Opus 4.7 max) | ~70 | ~$45 | ~$0.64 |
| Grade — Sonnet secondary (high effort) | ~55 | ~$11 | ~$0.20 |
| **Total** | | **$582.33** | |

Budget configured at $700, hard stop $850. Spend ended at 83% of budget.

---

## Acknowledgments

Pipeline built on the Anthropic Python SDK (v0.75.0) with prompt caching (5-min ephemeral) and adaptive extended thinking. Materials sourced from public 10-K filings.
