# Reasoning Drift Study — Multi-Arm, Multi-Vendor

A controlled experiment measuring how top-tier reasoning models from four
vendors degrade as the context window fills with adjacent-but-irrelevant
material, even at each vendor's maximum extended-thinking setting.

The task domain is **financial analysis** — a deliberately blended workload
of factual retrieval, numeric calculation, evidence-grounded reasoning, and
forward-looking thesis construction — run over Microsoft's FY2025
disclosures with adversarially-near big-tech peer 10-Ks (AAPL, GOOGL, AMZN,
META, NVDA, ORCL, CRM) as the noise corpus, because their business
complexity exercises all four reasoning modes simultaneously.

Five analyst arms are now locked. Only the analyst varies between arms;
methodology, prompts, rubric, materials, judges, extractor, design grid,
and per-cell seeds are held constant — every arm sees byte-identical
prompts at the same `(cell, rep)` coordinate. The integrity gate
(`harness/scripts/verify_arm_integrity.py`) enforces this at the SHA-256
level, and `compare_arms.py` refuses to produce cross-arm output unless
every arm declares the same methodology hash, materials hash, design grid,
and extractor + judge configuration.

| Arm                                   | Vendor    | Max-thinking knob              | Lock | Spend    | Notes                                                                                                  |
| ------------------------------------- | --------- | ------------------------------ | ---- | -------- | ------------------------------------------------------------------------------------------------------ |
| **Opus 4.7** (max effort)             | Anthropic | `effort=max`                   | v1   | $582.33  | 91/91/91 runs. Original lock arm. Monotonic decline; unsupported-claim hallucinations 7× under load.   |
| **Sonnet 4.6** (max effort)           | Anthropic | `effort=max`                   | v1   | $522.96  | 91/91/91 runs. Drift profile *differs* from Opus — quality recovers at 95% fill. 5–10× longer latency. |
| **GPT-5.5** (xhigh)                   | OpenAI    | `reasoning.effort=xhigh`       | v2   | $338.83  | 91/91/91 runs. Flat-then-cliff at 92%. Hallucination floor across all fills (unsup ≈ 0).               |
| **Gemini 3.1 Pro** (HIGH)             | Google    | `thinking_level=HIGH`          | v2   | $221.00  | 91/91/91 runs. Flattest absolute drift, lowest baseline ceiling. 3–15× speed advantage.                |
| **DeepSeek V4 Pro** (max)             | DeepSeek  | `reasoning_effort=max`         | v2   | $194.54  | 91/91/91 runs. Absolute-vs-pairwise paradox: flat absolute, steepest pairwise. Highest cross-judge CCC.|

Total spend across the five arms: **$1,859.66** (Opus + Sonnet + judge spend
shared at v1; three new analyst arms added at v2). The cross-arm
interpretive synthesis lives at
[`cross_arm/CROSS_ARM_REPORT.md`](cross_arm/CROSS_ARM_REPORT.md); the
auto-generated table-only comparison at
[`cross_arm/COMPARATIVE_REPORT.md`](cross_arm/COMPARATIVE_REPORT.md).

A **third experiment**, layered on the same five baselines, ranks the arms
head-to-head at zero noise — answering the question the drift study can't:
*with no noise at all, which arm produces the best Tier-3 synthesis?*
Headline ordering under both Anthropic judges:
**Sonnet 4.6 > Opus 4.7 > GPT-5.5 > DeepSeek V4 Pro > Gemini 3.1 Pro**
(cross-judge per-item Spearman ρ = 0.943). The top is *flipped* from the
absolute-judge baseline (which had Opus 1st at RQ 8.05, Sonnet 2nd at 7.43).
Reports: [`cross_arm/SOBER_STATE_FINAL_REPORT.md`](cross_arm/SOBER_STATE_FINAL_REPORT.md)
(reader-facing) and
[`cross_arm/SOBER_STATE_RANKING.md`](cross_arm/SOBER_STATE_RANKING.md)
(technical). Incremental spend: **$34.40** (1.8% of the main study). See
[The sober-state ranking](#the-sober-state-ranking--third-experiment) below.

Haiku 4.5 was considered but excluded — its 200K context window and
unverified `effort=max` thinking support would force two confounded changes
at once. See `ARMS.md` for the full rationale.

(Estimate: the judge spend (~$246) is shared across arms since the judge is
held constant at Opus 4.7 max-effort. Analyst-side spend varies with the
vendor's pricing and reasoning-token allocation. Run
`python -m scripts.dry_run --arm <arm>` for a fresh estimate against
current pricing before kicking off a new arm.)

## Layout

```
.
├── DESIGN.md                        # methodology  ┐
├── PROMPTS.md                       # prompts      │  v1: hashed → pre_registration.lock
├── RUBRIC.md                        # rubric       ┘
├── MULTI_VENDOR_ADDENDUM.md         # v2: vendor-max mapping, tokenizer asymmetry, judge-bias acceptance
├── pre_registration.lock            # v1 hash (Anthropic-only arms)
├── pre_registration.v2.lock         # v2 hash (v1 + addendum, additive — v1 arms inherit)
├── materials/                       # corpus (MSFT 10-K, peer 10-Ks, ground truth) — shared, unchanged
├── arms/
│   ├── opus-4-7/         (v1)      # Anthropic — original lock arm
│   ├── sonnet-4-6/       (v1)      # Anthropic — drift profile differs from Opus
│   ├── gpt-5-5/          (v2)      # OpenAI
│   ├── gemini-3-1-pro/   (v2)      # Google
│   └── deepseek-v4-pro/  (v2)      # DeepSeek
│       ├── arm.lock.json            # arm config snapshot + run results (schema_version 1.0 or 2.0)
│       ├── data.manifest.sha256     # one line per file; integrity verifier reads this
│       ├── data/                    # raw, extracted, graded, manifest.sqlite, logs
│       └── reports/FINAL_REPORT.md  # arm-specific narrative
├── cross_arm/
│   ├── COMPARATIVE_REPORT.md        # auto-generated by compare_arms.py — tables only
│   ├── CROSS_ARM_REPORT.md          # drift study synthesis — five drift signatures, Pareto frontier
│   ├── SOBER_STATE_FINAL_REPORT.md  # 3rd experiment: sober-state ranking, reader-facing
│   ├── SOBER_STATE_RANKING.md       # 3rd experiment: sober-state ranking, technical writeup
│   └── sober_state/                 # raw judge outputs + per-item {label → arm} permutations
├── QUALITATIVE_FINDINGS.md          # qualitative observations across arms
└── harness/
    ├── config/
    │   ├── base.yaml                # shared (extractor, judges, design grid, paths)
    │   └── arms/<arm>.yaml          # per-arm analyst override (vendor + thinking_config)
    ├── src/                         # arm-agnostic pipeline modules + per-vendor adapters
    └── scripts/                     # all take --arm <arm-name>
```

## The integrity model

This study makes a strong claim: **observed differences across arms come
from the analyst, not from the methodology, the corpus, or the measuring
instruments.** Three layered guards back that claim, with v2 added as an
*additive* lock so v1 arms remain valid evidence by inheritance:

1. **`pre_registration.lock` (v1)** — sha256 of `DESIGN.md + PROMPTS.md +
   RUBRIC.md` plus the materials lock hash. Pins the original
   Anthropic-only methodology. Edit any of those files and the hash changes
   and every arm's lock becomes invalid.
2. **`pre_registration.v2.lock`** — sha256 of `DESIGN.md + PROMPTS.md +
   RUBRIC.md + MULTI_VENDOR_ADDENDUM.md`. v1 files are byte-unchanged; v2
   only *adds scope* (admitting non-Anthropic vendors and codifying
   per-vendor footnotes — tokenizer ratios, max-thinking mapping, snapshot
   mutability). v1 arms remain valid under v2 because the v1 methodology is
   a strict subset of the v2 methodology.
3. **`arms/<arm>/arm.lock.json`** — pins the analyst snapshot (and observed
   alias, when the snapshot is mutable), references the `pre_registration`
   hash (v1 OR v2 — accepted symmetrically), snapshots the extractor + both
   judges (held constant across all arms), and records actual cost + run
   counts for the locked arm. Schema 2.0 adds `analyst.vendor`,
   `analyst.thinking_config` (vendor-native shape),
   `analyst.snapshot_observed_aliases`, and per-vendor pricing snapshots.
4. **`arms/<arm>/data.manifest.sha256`** — SHA-256 of every file in
   `arms/<arm>/data/` at the moment of lock.

Any of those can be re-verified offline:

```
python -m scripts.verify_arm_integrity --arm opus-4-7
python -m scripts.verify_arm_integrity --arm gpt-5-5
python -m scripts.compare_arms                    # refuses if hashes don't match across arms
```

`compare_arms.py` accepts an arm whose `arm.lock.json.pre_registration.hash`
equals **either** the v1 hash or the v2 hash, and refuses any other value.
Mixed-version comparisons footnote each arm's version. That gating — plus
the byte-identical materials lock and the held-constant judge — is what
makes the cross-arm comparison meaningful even though five different
vendors' models produced the answers.

For the deeper rationale and the procedure for adding a new arm, see
[`ARMS.md`](ARMS.md). For the v2 inheritance rule, vendor-max thinking
mapping, tokenizer asymmetry, and the judge-bias acceptance argument, see
[`MULTI_VENDOR_ADDENDUM.md`](MULTI_VENDOR_ADDENDUM.md).

## The sober-state ranking — third experiment

The drift study answers *which arm degrades least under noise.* The
sober-state ranking, layered on the same dataset, answers a complementary
question the drift study can't: *with no noise at all, which arm produces
the best Tier-3 synthesis?* It is a separate analysis with separate spend,
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

Incremental spend: **$34.40** (1.8% of the main study) — 22 Opus
judgements + 27 Sonnet judgements over 21 items. Reproduce with:

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

The largest remaining caveat is that both judges are Anthropic-family. A
cross-vendor judge replication (~$30 estimated, GPT-5.5 max + Gemini 3.1
Pro HIGH as ranking judges) is enumerated as the highest-value follow-up
in `SOBER_STATE_FINAL_REPORT.md §4.4`.

## Reproducing an arm

```
git clone <repo> && cd "Opus 4.7 Reasoning Drift Study"
cd harness
uv sync && cp .env.example .env                # add the vendor key(s) you need
python -m scripts.verify_arm_integrity --arm opus-4-7        # confirms data byte-identical
python -m scripts.verify_arm_integrity --arm deepseek-v4-pro
python -m scripts.drift_analysis    --arm gpt-5-5            # rebuilds drift profile
python -m scripts.compare_arms                               # cross-arm comparison
```

Each arm's data directory is the integrity boundary; nothing inside it
should change post-lock. `verify_arm_integrity.py` recomputes SHA-256s
against `data.manifest.sha256` and confirms the methodology hash and
materials hash referenced by `arm.lock.json` still match the on-disk
files.

## Running a new arm

```
# 1. Edit harness/config/arms/<arm>.yaml — set vendor, analyst snapshot, thinking_config.
#    Override pre_registration_hash with the v2 hash if the arm is non-Anthropic
#    (per MULTI_VENDOR_ADDENDUM.md §1).
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

## Spend and budget

Per-arm budget guards live in `harness/config/base.yaml`:

```
budget_usd:    $700   (warning threshold)
hard_stop_usd: $850   (CostTracker aborts)
```

Pricing is snapshotted into each `arm.lock.json` so cost can be honestly
reconstructed even if API rates change after an arm closes. The five
locked arms span a 3× cost range ($194 → $582) at constant 91 runs,
constant judges, and constant materials — the spread reflects vendor
pricing + per-vendor reasoning-token allocation differences only.

The third experiment (sober-state ranking) added **$34.40 incremental
spend** — 1.8% of the main study, executed against the same baseline
data files without re-running any analyst. Project-wide total:
**$1,894.06**.
