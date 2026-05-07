# Reasoning Drift Study — Multi-Arm, Multi-Vendor, Multi-Noise

A controlled experiment measuring how top-tier reasoning models from four
vendors degrade as the context window fills with adjacent-but-irrelevant
material, even at each vendor's maximum extended-thinking setting. A v3
extension adds a second, harder noise type — Microsoft's *own* prior-period
filings — and a cross-vendor judge ablation that re-grades all 10 arms
under three independent judges (Anthropic, OpenAI, Google).

The task domain is **financial analysis** — a deliberately blended workload
of factual retrieval, numeric calculation, evidence-grounded reasoning, and
forward-looking thesis construction — run over Microsoft's FY2025
disclosures. Two noise corpora exercise different scope-confusion mechanisms:
the **peer-materials** corpus (AAPL, GOOGL, AMZN, META, NVDA, ORCL, CRM
10-Ks) is the *easy* scope test where the company name is a hard string-level
differentiator; the **temporal-MSFT** corpus (MSFT's own prior-period
10-Ks for FY2023 and FY2024, 10-Qs covering FY2023–FY2025, and 23
earnings-call transcripts back to FY2018 — 34 files, ~991K tokens) is the
*hard* scope test where every period attribution must be inferred from
context.

**Ten analyst arms are now locked** — five vendors × two noise types — plus
a baseline-only sober-state ranking and a cross-vendor judging ablation
that adds GPT-5.5 and Gemini 3.1 Pro as judges alongside the original
Anthropic stack. Only the analyst varies between arms within a noise type;
methodology, prompts, rubric, materials, judges, extractor, design grid,
and per-cell seeds are held constant — every arm sees byte-identical
prompts at the same `(cell, rep)` coordinate (with a noise-type-conditional
disambiguation suffix for temporal arms, per `TEMPORAL_NOISE_ADDENDUM.md
§4.2`). The integrity gate (`harness/scripts/verify_arm_integrity.py`)
enforces this at the SHA-256 level, and `compare_arms.py` refuses to
produce cross-arm output unless every arm declares an accepted methodology
hash (v1 OR v2 OR v3), the same materials hash, design grid, and extractor
+ judge configuration.

| Vendor    | Analyst snapshot   | Max-thinking knob          | Peer arm (v1/v2)         | Temporal arm (v3)              |
| --------- | ------------------ | -------------------------- | ------------------------ | ------------------------------ |
| Anthropic | **Opus 4.7**       | `effort=max`               | `opus-4-7` (v1)          | `opus-4-7-temporal`            |
| Anthropic | **Sonnet 4.6**     | `effort=max`               | `sonnet-4-6` (v1)        | `sonnet-4-6-temporal`          |
| OpenAI    | **GPT-5.5**        | `reasoning.effort=xhigh`   | `gpt-5-5` (v2)           | `gpt-5-5-temporal`             |
| Google    | **Gemini 3.1 Pro** | `thinking_level=HIGH`      | `gemini-3-1-pro` (v2)    | `gemini-3-1-pro-temporal`      |
| DeepSeek  | **DeepSeek V4 Pro**| `reasoning_effort=max`     | `deepseek-v4-pro` (v2)   | `deepseek-v4-pro-temporal`     |

Each arm runs 91 cells (1 baseline + 12 noise cells, 7 reps × 8 questions)
= 728 records, for **7,280 analyst records** across the 10 arms. Cross-vendor
re-judging on tier-3 synthesis adds **7,885 judge records** (Opus + GPT +
Gemini, of an 8,190 theoretical max — coverage gaps documented in
`UNIFIED_V2V3_REPORT.md §6.4`, concentrated in DeepSeek temporal where
25–30% of records dropped on analyst-side extractor failures).

The unified cross-noise × cross-judge synthesis lives at
[`cross_arm/UNIFIED_V2V3_REPORT.md`](cross_arm/UNIFIED_V2V3_REPORT.md)
(latest, May 6 2026 — covers all 10 arms × 3 judges, includes a
position-effects analysis in §9 and a per-model strength profile in §10).
The earlier v2-only Anthropic-judge synthesis remains at
[`cross_arm/CROSS_ARM_REPORT.md`](cross_arm/CROSS_ARM_REPORT.md); the
auto-generated table-only comparison at
[`cross_arm/COMPARATIVE_REPORT.md`](cross_arm/COMPARATIVE_REPORT.md).

A **third experiment**, layered on the same five baselines (Opus + Sonnet
under v1, GPT + Gemini + DeepSeek under v2), ranks the arms head-to-head
at zero noise — answering the question the drift study can't: *with no
noise at all, which arm produces the best Tier-3 synthesis?*
Headline ordering under both Anthropic judges:
**Sonnet 4.6 > Opus 4.7 > GPT-5.5 > DeepSeek V4 Pro > Gemini 3.1 Pro**
(cross-judge per-item Spearman ρ = 0.943). The top is *flipped* from the
absolute-judge baseline (which had Opus 1st at RQ 8.05, Sonnet 2nd at 7.43).
A **cross-vendor judge follow-up** (GPT-5.5 xhigh + Gemini 3.1 Pro HIGH on
the same 21 items, same permutations) confirmed the ordering for 3 of 4
judges and produced unanimous agreement on the bottom — Gemini last,
DeepSeek 4th, including under the Gemini judge itself. Reports:
[`cross_arm/SOBER_STATE_FINAL_REPORT.md`](cross_arm/SOBER_STATE_FINAL_REPORT.md)
(reader-facing),
[`cross_arm/SOBER_STATE_RANKING.md`](cross_arm/SOBER_STATE_RANKING.md)
(technical, with §10 covering the cross-vendor follow-up), and
[`cross_arm/sober_state/CROSS_VENDOR_JUDGE_FOLLOWUP.md`](cross_arm/sober_state/CROSS_VENDOR_JUDGE_FOLLOWUP.md)
(standalone follow-up summary). See
[The sober-state ranking](#the-sober-state-ranking--third-experiment) below.

Haiku 4.5 was considered but excluded — its 200K context window and
unverified `effort=max` thinking support would force two confounded changes
at once. See `ARMS.md` for the full rationale.

## Layout

```
.
├── DESIGN.md                        # methodology  ┐
├── PROMPTS.md                       # prompts      │  v1: hashed → pre_registration.lock
├── RUBRIC.md                        # rubric       ┘
├── MULTI_VENDOR_ADDENDUM.md         # v2: vendor-max mapping, tokenizer asymmetry, judge-bias acceptance
├── TEMPORAL_NOISE_ADDENDUM.md       # v3: temporal_msft noise type, §4.2 disambiguation suffix, §5 metrics
├── pre_registration.lock            # v1 hash (Anthropic-only arms)
├── pre_registration.v2.lock         # v2 hash (v1 + multi-vendor, additive — v1 arms inherit)
├── pre_registration.v3.lock         # v3 hash (v2 + temporal-noise, additive — v1/v2 arms inherit)
├── materials/                       # corpus
│   ├── materials.lock.json          # v1/v2 surface (MSFT 10-K, peer 10-Ks, ground truth) — byte-frozen across v3
│   ├── materials_temporal.lock.json # v3 surface (MSFT prior-period 10-Ks/10-Qs/earnings calls)
│   ├── target/                      # MSFT FY2025 10-K + Q2 FY2026 call (v1/v2/v3)
│   ├── ground_truth/                # canonical answers + temporal-distractor list (v3)
│   ├── questions/                   # 8-question bank (v1/v2/v3, byte-identical)
│   ├── noise/peer_materials/        # v1/v2 noise corpus (7 peer 10-Ks)
│   ├── noise/temporal_msft/         # v3 noise corpus (34 files: 2 prior 10-Ks + 9 prior 10-Qs + 23 earnings calls)
│   └── noise_screening_log.md       # v3 hand-screen + acquisition ceiling notes (§3.1c)
├── arms/
│   ├── opus-4-7/                  (v1, peer)       # Anthropic — original lock arm
│   ├── sonnet-4-6/                (v1, peer)       # Anthropic
│   ├── gpt-5-5/                   (v2, peer)       # OpenAI
│   ├── gemini-3-1-pro/            (v2, peer)       # Google
│   ├── deepseek-v4-pro/           (v2, peer)       # DeepSeek
│   ├── opus-4-7-temporal/         (v3, temporal)   # paired with opus-4-7
│   ├── sonnet-4-6-temporal/       (v3, temporal)   # paired with sonnet-4-6
│   ├── gpt-5-5-temporal/          (v3, temporal)   # paired with gpt-5-5
│   ├── gemini-3-1-pro-temporal/   (v3, temporal)   # paired with gemini-3-1-pro
│   └── deepseek-v4-pro-temporal/  (v3, temporal)   # paired with deepseek-v4-pro
│       ├── arm.lock.json            # arm config snapshot + run results (schema 1.0/2.0/3.0)
│       ├── data.manifest.sha256     # one line per file; integrity verifier reads this
│       ├── data/                    # raw, extracted, graded, cross_judged, manifest.sqlite, logs
│       └── reports/FINAL_REPORT.md  # arm-specific narrative
├── cross_arm/
│   ├── UNIFIED_V2V3_REPORT.md       # 4th experiment: cross-noise × cross-judge synthesis (all 10 arms × 3 judges)
│   ├── CROSS_ARM_REPORT.md          # v2-only drift synthesis — five drift signatures, Pareto frontier
│   ├── COMPARATIVE_REPORT.md        # auto-generated by compare_arms.py — tables only
│   ├── OPUS_VS_SONNET_FOR_AGENTS.md # spin-off: agent-builder picking guide (Opus vs Sonnet)
│   ├── SOBER_STATE_FINAL_REPORT.md  # 3rd experiment: sober-state ranking, reader-facing
│   ├── SOBER_STATE_RANKING.md       # 3rd experiment: sober-state ranking, technical writeup
│   ├── build_unified_report.py      # builds UNIFIED_V2V3_REPORT.md
│   ├── analyze_position_strength.py # §9 position effects + §10 per-model strength profile
│   ├── plot_unified_v2v3.py         # capability_matrix + noise_drift_by_model figures
│   └── sober_state/                 # raw judge outputs + per-item {label → arm} permutations
│       ├── judge_{opus,sonnet,gpt,gemini}.jsonl  # one row per (q_id, rep_idx, judge)
│       ├── permutations.jsonl                    # stable across all 4 judges
│       ├── cross_judge_4way.json                 # structured 4-way agreement dump
│       └── CROSS_VENDOR_JUDGE_FOLLOWUP.md        # standalone cross-vendor summary
├── figures/                         # capability_matrix.png, noise_drift_by_model.png, drift_signatures.png
├── QUALITATIVE_FINDINGS.md          # qualitative observations across arms
└── harness/
    ├── config/
    │   ├── base.yaml                # shared (extractor, judges, design grid, paths)
    │   └── arms/<arm>.yaml          # per-arm analyst override (vendor + thinking_config + noise_type)
    ├── src/
    │   ├── disambiguation.py        # v3: §4.2 noise-type-conditional question suffix (SHA-pinned in v3 lock)
    │   ├── grading/scope_cap.py     # v3: scope-cap rule from RUBRIC.md + §5.2 (SHA-pinned)
    │   ├── grading/temporal_scan.py # v3: programmatic temporal_contamination detector (SHA-pinned)
    │   └── ...                      # arm-agnostic pipeline modules + per-vendor adapters
    └── scripts/                     # all take --arm <arm-name>
```

## The integrity model

This study makes a strong claim: **observed differences across arms come
from the analyst, not from the methodology, the corpus, or the measuring
instruments.** A chain of additive locks backs that claim — each
subsequent version *adds scope* without modifying any prior surface, so
arms locked under earlier versions remain valid evidence by inheritance:

1. **`pre_registration.lock` (v1)** — sha256 of `DESIGN.md + PROMPTS.md +
   RUBRIC.md` plus the materials lock hash. Pins the original
   Anthropic-only methodology.
2. **`pre_registration.v2.lock`** — sha256 of `DESIGN.md + PROMPTS.md +
   RUBRIC.md + MULTI_VENDOR_ADDENDUM.md`. v1 files byte-unchanged; v2
   adds non-Anthropic vendors and codifies per-vendor footnotes
   (tokenizer ratios, max-thinking mapping, snapshot mutability).
3. **`pre_registration.v3.lock`** — sha256 of `DESIGN.md + PROMPTS.md +
   RUBRIC.md + MULTI_VENDOR_ADDENDUM.md + TEMPORAL_NOISE_ADDENDUM.md`.
   v1/v2 files byte-unchanged; v3 admits the `temporal_msft` noise type, a
   noise-type-conditional question disambiguation suffix (§4.2), a
   programmatic `temporal_contamination` detector and `scope_adherence`
   cap (§5), and parallel `materials_temporal.lock.json` materials. v1
   and v2 arms inherit because peer-arm prompt assembly is byte-identical
   to v2 — the v3 changes are gated on `noise_type=temporal_msft`.
4. **`arms/<arm>/arm.lock.json`** — pins the analyst snapshot, references
   the `pre_registration.hash` (v1 OR v2 OR v3 — accepted symmetrically),
   snapshots the extractor + both judges (held constant across all arms),
   and records actual cost + run counts. Schema 3.0 adds the temporal
   instrument SHAs (scope_cap.py, temporal_scan.py, disambiguation.py)
   and per-arm noise-type binding.
5. **`arms/<arm>/data.manifest.sha256`** — SHA-256 of every file in
   `arms/<arm>/data/` at the moment of lock.

Any of those can be re-verified offline:

```
python -m scripts.verify_arm_integrity --arm opus-4-7
python -m scripts.verify_arm_integrity --arm gpt-5-5
python -m scripts.verify_arm_integrity --arm sonnet-4-6-temporal
python -m scripts.verify_v3_isolation               # v3-only: confirms v1/v2 surface untouched
python -m scripts.compare_arms                      # refuses if hashes don't match across arms
```

`compare_arms.py` accepts an arm whose `arm.lock.json.pre_registration.hash`
equals **v1 OR v2 OR v3**, and refuses any other value. Tables that mix
arms from more than one **methodology version** footnote each arm's
version; tables that mix arms from more than one **noise type** carry the
`TEMPORAL_NOISE_ADDENDUM.md §10` disclosure (cross-noise comparison is not
apples-to-apples — prompts differ by §4.2 suffixes, fill labels refer to
noise-type-specific pools). That gating — plus the byte-identical materials
locks and the held-constant judge stack — is what makes the cross-arm
comparison meaningful even though five different vendors' models produced
the answers under two different noise corpora.

For the deeper rationale and the procedure for adding a new arm, see
[`ARMS.md`](ARMS.md). For the v2 inheritance rule, vendor-max thinking
mapping, tokenizer asymmetry, and the judge-bias acceptance argument, see
[`MULTI_VENDOR_ADDENDUM.md`](MULTI_VENDOR_ADDENDUM.md). For the v3 noise
admission, the temporal-distractor metric, the §4.2 disambiguation suffix,
and the v1/v2/v3 isolation invariant, see
[`TEMPORAL_NOISE_ADDENDUM.md`](TEMPORAL_NOISE_ADDENDUM.md).

## The sober-state ranking — third experiment

The drift study answers *which arm degrades least under noise.* The
sober-state ranking, layered on the same dataset, answers a complementary
question the drift study can't: *with no noise at all, which arm produces
the best Tier-3 synthesis?* It is layered on top of the existing dataset,
not a re-run of any arm — every analyst response was already collected
during the main study's `fill=0` baseline cell.

Each arm's 21 baseline Tier-3 responses (3 questions × 7 reps) were
re-judged in randomly-permuted 5-way A–E bundles by both Anthropic judges
(Opus 4.7 max + Sonnet 4.6 high). Same materials, same rubric, same judge
snapshots — only the judge's **task** changes: 5-way head-to-head ranking
instead of single-answer absolute Likert scoring.

| rank | model              | mean rank (Opus / Sonnet) | Borda (of 84) | top-1 (of 21) |
|------|--------------------|---------------------------|---------------|---------------|
| 1    | **Sonnet 4.6**     | 1.48 / 1.33               | 74 / 77       | 11 / 14       |
| 2    | **Opus 4.7**       | 1.62 / 1.76               | 71 / 68       |  9 /  6       |
| 3    | **GPT-5.5**        | 3.00 / 2.95               | 42 / 43       |  1 /  1       |
| 4    | **DeepSeek V4 Pro**| 4.24 / 4.19               | 16 / 17       |  0 /  0       |
| 5    | **Gemini 3.1 Pro** | 4.67 / 4.76               |  7 /  5       |  0 /  0       |

Cross-judge agreement is the strongest seen anywhere in the project:
per-item Spearman ρ mean **0.943** (median **1.000**), per-arm Borda
Pearson **0.997**, top-1 same-item agreement 76%. Two reorderings vs the
absolute-judge baseline:

- **Sonnet ↔ Opus at the top.** Absolute scoring ranked Opus 1st
  (RQ 8.05) and Sonnet 2nd (7.43). Forced to compare side-by-side, both
  judges flip them — Sonnet's verbose-precision style packs more
  per-anchor substance than Opus's tighter framing.
- **DeepSeek ↔ Gemini at the bottom.** Absolute scoring gave Gemini a
  higher RQ (5.86 vs 5.33). Head-to-head, DeepSeek wins consistently —
  judges describe Gemini's answers as *summary, not analysis* beside any
  peer.

Same methodological lesson as the drift study's absolute-vs-pairwise
paradox (`CROSS_ARM_REPORT.md §4`), reapplied to the no-noise condition:
side-by-side comparison and isolated Likert scoring answer different
questions about quality, and the ordering depends on which one you use.

Reproduce with:

```
python -m scripts.judge_sober_ranking    # 21 items × 2 judges
python -m scripts.sober_analysis         # rebuild rankings + diagnostics
```

The only deviation from the main-study judge config is `max_output_tokens`
(raised from 16K/8K to 32K/64K because 5-way ranking output exceeds
single-answer scoring budgets — first run had 1/21 Opus and 4/4 Sonnet
calls hit the cap with zero text emitted). All other integrity guarantees
inherited: same materials hash, same methodology hash, same per-arm
`fill=0` data files, same judge snapshots, same temperatures, same
thinking efforts.

The largest remaining caveat at first writing — that both judges were
Anthropic-family — was closed by a cross-vendor follow-up that added
GPT-5.5 (xhigh) and Gemini 3.1 Pro (HIGH) as judges on the same 21
items, same permutations. Three of four judges (Opus, Sonnet, Gemini)
returned the exact ordering above; the GPT judge alone moved itself
from #3 to a tie at #1 with Opus, displacing Sonnet to #3 — but the
top-3 set was unchanged. The bottom is unanimous: Gemini last on every
judge, including the Gemini judge itself (which puts Gemini behind
DeepSeek). Self-preference is bounded — GPT +1.11 rank steps in-house
(largest), Sonnet +0.38, Gemini +0.25, Opus +0.17 — and none invert
any pair. Per-arm Pearson r between judges ranges 0.84 – 1.00. Full
breakdown: `SOBER_STATE_RANKING.md §10` and the standalone
`cross_arm/sober_state/CROSS_VENDOR_JUDGE_FOLLOWUP.md`.

## The temporal-noise experiment — fourth experiment (v3)

The v1/v2 drift study answers *which arms degrade least under
cross-company peer noise*, where the company name itself is a hard
string-level differentiator. The v2 results then exposed a structural
blind spot: at 95% peer-noise fill, three of five arms (GPT, Gemini,
DeepSeek) sit at the `cross_contamination` floor of 0.000 — not because
they've solved scope adherence, but because the metric only tests the
*easy* version of it. The hard version — *same company, different
period* — is unmeasured.

**v3 adds that measurement.** Five `*-temporal` arms re-run every
analyst against a noise corpus drawn from MSFT's *own* prior-period
filings: 2 prior 10-Ks (FY2023, FY2024) + 9 prior 10-Qs (FY2023 Q1–Q3,
FY2024 Q1–Q3, FY2025 Q1–Q3) + 23 earnings-call transcripts back to FY2018,
totalling 991K tokens (86.2% utilization at the 95% cell). Same target document, same questions, same rubric, same
judge stack — only the noise type and a §4.2 question-disambiguation
suffix change. v1/v2 prompt assembly is byte-identical to before; v3
seeding adds `noise_type` as a fifth seed input *only* when
`noise_type != peer_materials`, so the existing five arms remain valid
evidence on the cross-company question without re-running.

Layered on top, a **cross-vendor judging ablation** re-judges every
tier-3 record from all 10 arms under three judges in parallel — Opus 4.7
(original), GPT-5.5 (xhigh), Gemini 3.1 Pro (HIGH) — so every finding
below carries a 3-judge robustness verdict. Reports:
[`cross_arm/UNIFIED_V2V3_REPORT.md`](cross_arm/UNIFIED_V2V3_REPORT.md)
(headline reader-facing synthesis with §9 position-effects and §10
per-model strength matrix).

### Headline findings

**1. The "models will confuse periods" hypothesis is empirically null.**
Across 5 frontier models × 95% temporal fill × 3 independent judges, the
judge-rated `temporal_contamination` count is **zero on every record**
(0/1,362 under Opus, 0/1,227 under GPT, 0/1,260 under Gemini). The
earlier rule-based scanner's 24 hits all turned out to be
correctly-formatted 3-year comparative income statements — the FY2024
number 245,122 appearing alongside FY2025 281,724 and FY2023 211,915 is
correct comparative reporting, not contamination. The metric is null
when the right metric is used.

**2. Sonnet 4.6 collapses at 95% temporal — confirmed by all three judges.**
Sonnet's reasoning_quality drops by **−1.5 to −3.8 points** on a 10-point
scale at 95% temporal fill, robust across the Anthropic, OpenAI, and
Google judges (Opus −2.47, GPT −1.57, Gemini −3.81). Under the Opus
judge the failure mode is *bimodal and detectable*: ~20% of responses
get rated 0–2/10 while ~23% are still rated 8+/10 (n=60), with the
failures showing as truncation (delivering Part 1 of a 3-part synthesis
and stopping). Groundedness drops from 4.30 → 2.91 — claims stop
tracing cleanly to the FY2025 source under heavy old-version noise.
This was *not* visible under peer noise (Sonnet's peer-95% blended
reasoning is 7.84 — the highest 95% cell in the v2 grid).

**3. DeepSeek V4 Pro shows multi-mode collapse — but only under one judge.**
Tier-1 retrieval drops 28% at 95% temporal fill (0.43 baseline → 0.31),
with the worst single cell at 50%/end position scoring 0.14 (a 67% drop
from DeepSeek's own baseline; the worst data point in the entire study).
Tier-2 calculation collapses identically. Tier-3 reasoning under the Opus judge
drops −1.78 at 95% temporal — but the GPT and Gemini judges show no
significant degradation. **Caveat:** 25–30% of DeepSeek temporal records
were dropped from cross-judging due to downstream extractor failures
(15K-char substantive raw responses that the haiku-extractor couldn't
parse into the 8-question schema). The cross-judge sample may be biased
toward DeepSeek's better-formed responses, so the surviving GPT/Gemini
agreement is weaker evidence than it looks.

**4. Opus 4.7 *recovers* at 95% temporal — also confirmed by all three judges.**
Opus's reasoning_quality at 95% temporal is 7.87 (blended), *higher* than
its 95% peer score of 7.07. All three independent judges agree (Opus
+0.65, GPT +0.45, Gemini +1.29). The most plausible mechanism is
context-pressure-mediated thinking budget — Opus invests more reasoning
tokens when it senses saturation and disambiguates periods correctly.
This is the only "noise makes the model better" cell in the entire
v2/v3 grid.

**5. GPT-5.5 and Gemini 3.1 Pro are temporal-noise invariant.** Neither
shows reasoning-quality degradation under temporal noise across any
judge at any fill level. GPT-5.5 holds at 7.6–7.9/10 (blended) from
baseline through every temporal cell with extremely tight confidence
intervals; Gemini sits in the mid-6s across the entire grid (lowest
baseline of the five, but the flattest shape).

### Cross-vendor judge ablation — second-order findings

The 3-judge re-grade of all 10 arms also surfaces measurement-instrument
findings independent of the temporal-noise question:

- **Gemini-as-judge has a +2.0-point level shift** vs Opus across all 10
  arms. On top of that level shift, Gemini also rates Gemini-3.1-Pro
  outputs **+2.7 vs Opus** — the largest self-favoritism observed in the
  study. Use Gemini in agent self-eval loops only with calibration.
- **GPT-as-judge has a +0.5-point level shift** vs Opus, with mild
  +0.7-point self-favoritism on GPT-5.5 outputs. Per-record agreement
  with Opus is r = 0.69–0.84 across all 10 arms — the most reliable
  cross-vendor judging pair tested.
- **No within-Anthropic favoritism observed.** When Opus judges Sonnet,
  Opus rates Sonnet *lower* than GPT or Gemini do (Sonnet temporal: Opus
  6.54 vs GPT 6.97 vs Gemini 7.80). Anthropic's own judge is the harshest
  on its own kind, not the most lenient — closing the "judge bias"
  caveat carried since v1.

### Position effects

`UNIFIED_V2V3_REPORT.md §9` decomposes drift by where the noise sits in
the prompt (target-at-start, target-sandwiched, target-adjacent-to-questions).
For most arms position is a small effect (≤ 0.6-point spread on the
10-point scale), but two outliers stand out:

- **Opus under peer noise** has a **1.12-point spread** — `end` layout
  (target adjacent to questions, 8.10) outperforms the `middle` layout
  (target sandwiched, 6.98). Position-tuning matters.
- **DeepSeek under temporal noise** has a **2.06-point spread** in the
  opposite direction — the `end` layout (noise anchored at the front of
  context) collapses to 4.65, vs `start` at 6.71. Same position label
  as Opus's win, opposite mechanism.

`§10` of the same report builds a per-model strength profile across all
8 cognitive dimensions and at every (fill, position) cell. One-line
signatures: Opus is the *reasoning generalist* (best baseline RQ + best
clarity), Sonnet is *capable but bimodal* under temporal stress, GPT is
the *groundedness specialist* (perfect 5.00 baseline groundedness, only
−7% worst-cell drop), Gemini is the *most resilient* (lowest baseline,
flattest worst-cell drops), DeepSeek is *cheap but with a cliff*
downstream of its extractor.

### Reproduce

```
# Run a single temporal arm end-to-end
python -m scripts.run_experiment --arm opus-4-7-temporal --full
python -m scripts.run_extractor  --arm opus-4-7-temporal
python -m scripts.run_grading    --arm opus-4-7-temporal

# Cross-vendor re-judge tier-3 records (multi-arm, multi-judge in one call)
python -m scripts.cross_judge \
    --arms opus-4-7-temporal,sonnet-4-6-temporal,gpt-5-5-temporal,gemini-3-1-pro-temporal,deepseek-v4-pro-temporal \
    --judges gpt-5.5,gemini-3.1-pro \
    --filter all_tier3

# Rebuild the unified report + figures from sidecars
python cross_arm/build_unified_report.py            # rebuilds UNIFIED_V2V3_REPORT.md tables
python cross_arm/analyze_position_strength.py       # rebuilds §9 + §10 addenda
python cross_arm/plot_unified_v2v3.py               # rebuilds capability_matrix + noise_drift figures
```

## Reproducing an arm

```
git clone <repo> && cd "Opus 4.7 Reasoning Drift Study"
cd harness
uv sync && cp .env.example .env                # add the vendor key(s) you need
python -m scripts.verify_arm_integrity --arm opus-4-7                  # v1 peer arm
python -m scripts.verify_arm_integrity --arm deepseek-v4-pro           # v2 peer arm
python -m scripts.verify_arm_integrity --arm sonnet-4-6-temporal       # v3 temporal arm
python -m scripts.verify_v3_isolation                                  # v1/v2 surface untouched by v3
python -m scripts.drift_analysis    --arm gpt-5-5                      # rebuilds drift profile
python -m scripts.compare_arms                                         # cross-arm comparison
```

Each arm's data directory is the integrity boundary; nothing inside it
should change post-lock. `verify_arm_integrity.py` recomputes SHA-256s
against `data.manifest.sha256` and confirms the methodology hash and
materials hash referenced by `arm.lock.json` still match the on-disk
files.

## Running a new arm

```
# 1. Edit harness/config/arms/<arm>.yaml — set vendor, analyst snapshot, thinking_config, noise_type.
#    pre_registration_hash:
#      - v1 hash (61b2d30f…) for Anthropic peer arms
#      - v2 hash (3433f4a6…) for non-Anthropic peer arms (per MULTI_VENDOR_ADDENDUM.md §1)
#      - v3 hash (10ebe9f1…) for any *-temporal arm (per TEMPORAL_NOISE_ADDENDUM.md §6)
# 2. Verify the model accepts the chosen thinking schema
python -m scripts.smoke_test --arm <arm> --cell-fill 0.0

# 3. Pilot then full
python -m scripts.run_experiment --arm <arm> --pilot
python -m scripts.run_experiment --arm <arm> --full
python -m scripts.run_extractor  --arm <arm>
python -m scripts.run_grading    --arm <arm>

# 4. Lock the arm
python -m scripts.write_arm_lock --arm <arm>
python -m scripts.verify_arm_integrity --arm <arm>

# 5. Compare
python -m scripts.compare_arms --write-report
```

