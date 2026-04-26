# Multi-Vendor Addendum (v2)

**Version:** 0.2 (post-smoke revision)
**Date:** 2026-04-25
**Supersedes:** none — extends `pre_registration.lock` (v1) without
modifying it. Hashed into `pre_registration.v2.lock` alongside the
unchanged DESIGN.md + PROMPTS.md + RUBRIC.md.
**Scope:** authorizes the experiment to admit non-Anthropic analyst arms
(Google Gemini 3.1 Pro, OpenAI GPT-5.5, DeepSeek V4 Pro) and codifies the
methodological footnotes those arms require.

**Revision note (v0.1 → v0.2):** Following the three vendor smoke runs on
2026-04-25 (MSFT baseline cell, one rep per arm), §3 (DeepSeek max-effort
acceptance), §4 (tokenizer asymmetry — empirical ratios replace the v0.1
±5% guess), §5 (per-vendor introspection details), and §6 (DeepSeek
system_fingerprint capture mechanism) are revised in place. The v2
methodology hash changes accordingly. No locked arms exist yet at the
v0.2 hash, so no arm.lock.json files are invalidated. v1 hash unchanged;
v1 arms (Opus 4.7, Sonnet 4.6) remain grandfathered.

---

## 1. Why a v2 lock instead of editing v1

The v1 pre-registration (`pre_registration.lock`, methodology hash
`61b2d30f…`) was authored when the only candidate analysts were Anthropic
models. DESIGN.md §4.2 names `claude-opus-4-7` as the model and discusses
"Anthropic prompt cache" and "thinking_effort" as if they were universal
knobs. They are not.

Editing DESIGN.md would silently invalidate the locked Opus 4.7 and
Sonnet 4.6 arms (their `arm.lock.json.pre_registration.hash` would no
longer match). v2 is therefore an **additive lock**: v1 files are untouched
and v2 = `sha256(DESIGN.md + PROMPTS.md + RUBRIC.md + MULTI_VENDOR_ADDENDUM.md)`.

### v1→v2 inheritance rule

The v1 arms (Opus 4.7, Sonnet 4.6) remain **valid evidence under v2**.
Justification: the addendum only *adds scope* (admitting more vendors
and documenting their footnotes). It does not change the task, the
materials, the question bank, the ground truth, the rubric, the design
grid, the extractor, or the judge configuration. Every claim a v1 arm
makes is still true under v2.

`compare_arms.py` therefore accepts an arm whose
`arm.lock.json.pre_registration.hash` equals **either** the v1 hash or the
v2 hash, and refuses any other value. Mixed-version comparison reports
must footnote the version of each arm.

---

## 2. What this addendum permits

Three new analyst vendors are admitted as legitimate arms:

| Vendor   | Reference snapshot (April 2026) | Native SDK            |
| -------- | ------------------------------- | --------------------- |
| Google   | `gemini-3-pro-preview` (mutable alias on Gemini API) | `google-genai` |
| OpenAI   | `gpt-5.5-2026-04-23` (dated)    | `openai`              |
| DeepSeek | `deepseek-v4-pro` (mutable alias) | `openai` against `api.deepseek.com` (no first-party SDK) |

Each new arm runs against the same materials, prompts, rubric, and design
grid as the v1 arms. Each new arm is graded by the same Opus 4.7
max-effort primary judge and Sonnet 4.6 high-effort secondary judge as the
v1 arms. **No instrument changes.**

---

## 3. "Max thinking" mapping across vendors

DESIGN.md §4.2 specifies "Extended thinking: xhigh" without defining what
that means in vendor-neutral terms. v2 formalizes the per-vendor mapping
of "Anthropic effort=max" to its closest analog:

| Vendor    | API knob                                  | Value used | Why this is "max"                                                                                          |
| --------- | ----------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------- |
| Anthropic | `thinking.effort`                         | `max`      | Top of {low, medium, high, max, xhigh}; v1 arms used `max` for Sonnet (which has no `xhigh`).               |
| Google    | `thinking_level`                          | `high`     | Top of {minimal, low, medium, high}. Gemini 3 deprecated the `thinking_budget` integer.                    |
| OpenAI    | `reasoning.effort`                        | `xhigh`    | Top of {none, low, medium, high, xhigh}.                                                                   |
| DeepSeek  | `reasoning_effort` (extra_body, openai-compat) | `max` | Confirmed accepted by `deepseek-v4-pro` at smoke 2026-04-25 (1 attempt, no 400). The v0.1 fallback to `high` is therefore not exercised. |

These are **not** equivalent in underlying reasoning-budget tokens. They
are vendor-honest interpretations of "spend the most reasoning the API
will let me spend on this call." Comparing thinking-token counts across
vendors is therefore meaningful **within a vendor** but **not directly
across vendors**. The cross-arm report acknowledges this by tabulating
thinking-token statistics per arm, not as a single comparable column.

**Empirical thinking-token spread observed at the baseline smoke**
(MSFT, fill=0%, single rep): Anthropic ~na (smoked separately under v1),
GPT-5.5 = 10,839, Gemini 3.1 Pro = 5,733, DeepSeek V4 Pro ≈ 8,550 (after
the SDK double-append fix in §5). The 1.9× spread between Gemini-low and
GPT-5.5-high illustrates why the cross-vendor thinking-token column is
descriptive only.

---

## 4. Tokenizer asymmetry

DESIGN.md uses Anthropic tokenizer counts throughout (target materials
~95K tokens, noise pool 628,609 tokens, fill levels expressed as fractions
of 1M context). The materials on disk are byte-identical regardless of
arm — what differs is how each vendor's tokenizer chunks them.

### Empirical per-vendor ratios (revised in v0.2)

The v0.1 estimate of "±5% divergence from Anthropic on English prose"
was a guess at lock authoring time. The 2026-04-25 baseline smoke (MSFT,
fill=0%, byte-identical assembled prompt across arms; Anthropic
`count_tokens` = 126,414) measured the following:

| Vendor   | Vendor input_tokens | Vendor / Anthropic | Implication for fill labels                              |
| -------- | ------------------- | ------------------ | -------------------------------------------------------- |
| OpenAI (o200k_base, GPT-5.5) | 78,608 | 0.622 | Cell labeled fill=0.95 (~950K Anthropic tokens) delivers ~590K of GPT-5.5's own tokens — well below 95% of its 1.05M context window. |
| Google (Gemini 3.1 Pro)      | 87,119 | 0.689 | Cell labeled fill=0.95 delivers ~655K of Gemini's own tokens — about 62% of its 1.048M context window. |
| DeepSeek (V4 Pro)            | 79,192 | 0.627 | Cell labeled fill=0.95 delivers ~595K of DeepSeek's own tokens — about 60% of its 1.0M context window. |

The divergence is **~30–38%, an order of magnitude larger than v0.1
anticipated**. This is consistent with Anthropic's tokenizer producing
substantially smaller chunks (more tokens per character) than the BPE/SP
families used by the other three vendors on dense financial English
mixed with tabular data.

### What this means for the experiment

1. **Within-arm drift slope (the primary endpoint) is unaffected.** Each
   arm sees a monotonically increasing token volume across fill levels
   {0, 0.25, 0.50, 0.75, 0.95}. The ranks are preserved; the slope of
   `quality_score` against `realized_input_tokens` is the headline.
2. **Cross-arm comparison at the same fill label is comparison of "same
   byte content delivered," not "same fraction of context window."** A
   non-Anthropic arm at fill=0.95 is not actually saturating its context
   window. We do not claim it is. The cross-arm report makes this
   explicit and tabulates *realized vendor input_tokens* alongside the
   Anthropic-labeled fill fraction.
3. **Cross-arm comparison of absolute drift onset (e.g., "where does
   quality crack?") must be expressed in vendor-native input_tokens, not
   in Anthropic-labeled fill fractions.** The per-arm
   DRIFT_ANALYSIS.txt already does this; the cross-arm summary will plot
   quality vs realized input_tokens on a shared x-axis.

### Why we do not re-grid per vendor

A per-vendor target adjustment (e.g., padding noise so each non-Anthropic
arm hits its own 95% context fill) would multiply the integrity surface:
per-vendor materials hashes, per-vendor noise seed schemes, per-vendor
ground-truth recomputation, per-vendor pre-registration locks. The
within-arm drift endpoint is the load-bearing endpoint and is unaffected
by the labeling choice. The cross-arm absolute-onset question is honestly
answerable by switching the x-axis from fill-label to realized-tokens,
which costs zero integrity surface and zero rerun spend.

`arm.lock.json.design_used.tokenizer_note` records the per-arm ratio
(populated from the smoke run, refined from the pilot run before the
arm.lock.json is finalized). The cross-arm report carries the same
disclosure as a per-arm row footnote and renders quality-vs-tokens plots
on a shared linear x-axis spanning the union of realized token ranges.

### Caveat: ratio measured at baseline only

The 0.62/0.69/0.63 ratios were measured on the baseline cell, where the
prompt content is purely target materials (MSFT 10-K + earnings call).
Higher-fill cells add peer 10-K text from the noise pool. Tokenizer
ratios on peer materials are expected to be similar but not identical
(different vocabulary distribution, different tabular density). Pilot
runs will record the realized vendor input_tokens at every fill level
into the raw record; the cross-arm report uses those measurements
directly rather than re-applying the baseline ratio.

---

## 5. Thinking introspection asymmetry

Each vendor exposes a different shape of reasoning evidence. v2 codifies
the four distinct cases and how the harness logs them. Confirmations
below are from the 2026-04-25 baseline smokes:

| Vendor / model        | Raw CoT text? | Encrypted blob? | Token counts | Logged into raw record as                          |
| --------------------- | ------------- | --------------- | ------------ | -------------------------------------------------- |
| Anthropic Opus 4.7    | redacted | `signature` (base64) | yes (sdk) | `signature_chars`, `thinking_tokens`             |
| Anthropic Sonnet 4.6  | yes      | n/a                  | yes (sdk) | `thinking_text`, `thinking_tokens`               |
| Google Gemini 3.1 Pro | no       | thought-signature blob (per-part, captured from `Part.thought_signature`; **confirmed populated at smoke**) | yes (sdk: `thoughts_token_count`) | `signature_chars`, `thinking_tokens` |
| OpenAI GPT-5.5        | no (summary only) | `encrypted_content` (per-item, **confirmed populated at smoke**; lengths captured) | yes (sdk: `output_tokens_details.reasoning_tokens`) | `signature_chars`, `thinking_tokens` |
| DeepSeek V4 Pro       | yes — `reasoning_content` field on the streaming delta; **confirmed present in V4 at smoke 2026-04-25** | n/a | derived (see below) | `thinking_text`, `thinking_tokens` (estimated)   |

### Adapter-side normalization (per-vendor harness rules)

Three vendor-specific implementation rules emerged from the smokes and
are pinned here as part of the methodology lock so reproducers get
identical accounting:

**Gemini (`_extract_gemini`).** The SDK reports `candidates_token_count`
(answer only) separately from `thoughts_token_count`. Anthropic and
OpenAI bundle reasoning into `output_tokens` in their billing. To keep
`cost.py` vendor-agnostic, the Gemini adapter sets
`output_tokens = candidates_token_count + thoughts_token_count`. Token
provenance for diagnostics is preserved via the separate
`thinking_tokens` field (sourced from `thoughts_token_count`). This is a
billing-semantics normalization, not a content change.

**OpenAI (`_extract_openai`).** The SDK reports `reasoning_tokens` inside
`output_tokens_details` and already includes them in `output_tokens`.
The adapter therefore takes `output_tokens` verbatim and reads
`thinking_tokens` from `output_tokens_details.reasoning_tokens`. No
normalization needed.

**DeepSeek (`_deepseek_stream_to_final` + `_extract_deepseek`).** The
openai-compatible SDK exposes `reasoning_content` via *both* the explicit
`delta.reasoning_content` attribute *and* the unknown-field bag
`delta.model_extra["reasoning_content"]`. The smoke run revealed that
naive concatenation from both sources doubles every CoT token (every
word appeared twice in the captured `thinking_text`). The adapter
deduplicates by preferring the explicit attribute and only consulting
`model_extra` when the attribute is empty. Separately, V4
`completion_tokens` does **not** bundle reasoning tokens (unlike
OpenAI's `output_tokens`); the adapter therefore estimates
`thinking_tokens` from `len(thinking_text) // 4` and tags
`thinking_tokens_source = "estimated_char_per_4"` so downstream
analysis can distinguish SDK-reported from adapter-estimated counts.
Cost.py uses `output_tokens` (= `completion_tokens` for DeepSeek,
covering only the answer); reasoning is not separately billed by
DeepSeek, so this matches the invoice.

Two columns in the cross-arm report depend on §5:

- **`thinking_tokens` (mean per response)** — comparable within an arm,
  qualitative across arms (see §3). Provenance flag distinguishes
  SDK-reported vs adapter-estimated.
- **`thinking_text` length** — Sonnet-and-DeepSeek-only column. The other
  three arms render `n/a`. Reported but never compared across arms.

---

## 6. Snapshot mutability disclosure

Anthropic and OpenAI publish dated snapshot strings (`claude-opus-4-7`,
`gpt-5.5-2026-04-23`). These pin a specific build that the API will
continue to serve indefinitely.

Google (`gemini-3-pro-preview`) exposes a versioned alias on Vertex AI
but a moving alias on the Gemini API. DeepSeek (`deepseek-v4-pro`) exposes
**only** a moving alias — there is no dated snapshot.

For arms whose snapshot string is mutable, the harness logs the API
response's `system_fingerprint` (or vendor equivalent) into every raw
record as a per-call build identifier:

- **OpenAI** — `system_fingerprint` from the Responses API response
  envelope (Anthropic-style snapshots are dated, so this is a redundant
  audit trail rather than the primary build pin).
- **Gemini** — the SDK does not expose a build fingerprint in the
  response. The captured `Part.thought_signature` blob (logged as
  `signature_chars`) plus the response's `model_version` field (when
  populated) serve as the closest equivalents.
- **DeepSeek** — `system_fingerprint` captured per stream chunk; the
  last-seen value is persisted to the raw record. Adapter mechanism is
  in place; per-call population was not visible in the smoke summary
  log (the smoke logger only prints text + thinking previews) — pilot
  raw records will show whether DeepSeek populates the field. If
  empty, the per-call audit trail falls back to `model` echo and
  request `id` (both confirmed populated at smoke).

`arm.lock.json.analyst.snapshot_note` documents the mutability and
points reproducers at the fingerprint trail and at
`arm.lock.json.execution_results.system_fingerprints_observed` (a
deduped list of build IDs the arm encountered during execution).
Future re-runs against the same model string may or may not reproduce
results bit-for-bit; the integrity claim remains "this is the build that
served these calls at this time," which the fingerprint preserves.

---

## 7. Judge bias acceptance

The primary judge stays `claude-opus-4-7` at `effort=max` across all five
arms (Opus 4.7, Sonnet 4.6, GPT-5.5, Gemini 3.1 Pro, DeepSeek V4 Pro). The
secondary 20% Sonnet 4.6 subsample stays as well. This is the v1 choice
inherited by v2 — codified here because going multi-vendor changes the
*shape* of the same-model-bias concern and reviewers should engage with
the actual decision rather than infer it.

### Two judging regimes across the five arms

| Arm                | Judge regime          | Same-model-bias risk                                    |
| ------------------ | --------------------- | ------------------------------------------------------- |
| opus-4-7           | in-family             | Direct self-favor possible.                             |
| sonnet-4-6         | in-family             | Same vendor, plausible affinity (different model size). |
| gpt-5-5            | cross-vendor          | None from same-model.                                   |
| gemini-3-1-pro     | cross-vendor          | None from same-model.                                   |
| deepseek-v4-pro    | cross-vendor          | None from same-model.                                   |

### Why the bias is bounded (not eliminated)

1. **Drift is the primary endpoint, not absolute score.** All headline
   results are within-arm Δ from each arm's own baseline (fill=0, same
   analyst). A judge that systematically rates Opus answers higher rates
   *both* baseline Opus and 95%-fill Opus higher — the slope is
   bias-cancelling. The same applies to Sonnet.
2. **The judge runs at fill=0.** The mechanism the original design feared
   ("judges drift under context pressure too, correlated with the analyst")
   is structurally absent here. The judge sees only the cached target
   materials + question + candidate response, never the noise context.
3. **Sonnet 4.6 secondary on 20% deterministic subsample** computes
   cross-model ICC/CCC per dimension. A dimension where Sonnet ranks
   responses materially differently from Opus surfaces as low ICC and
   gets flagged in the per-arm DRIFT_ANALYSIS.txt.
4. **Opus 4.7 pairwise on 25% subsample is A/B-randomized.** Self-favor
   would have to act consistently in both A and B slot orderings to bias
   the verdict — a much stronger bias mechanism than absolute-score lift.

### The bounded claim

- **Primary cross-arm endpoint:** within-arm drift slope (e.g., Δ
  reasoning_quality between baseline and 95% fill, per arm). Bias-cancelling.
- **Secondary cross-arm endpoint:** within-arm pairwise win rate vs own
  baseline (25% subsample, A/B randomized). Bias-cancelling.
- **Descriptive-only:** absolute Tier 3 mean scores in the cross-arm
  table. The Opus and Sonnet arms carry an unresolved same-vendor-pair
  confound here; the three cross-vendor arms do not. The cross-arm report
  flags this in the per-arm notes section.

### Alternatives considered and rejected

- **Per-vendor matched judges** (Opus judges Opus, GPT judges GPT, etc.):
  multiplies instrument differences across arms. We'd trade one named bias
  for five different unknown ones. Strictly worse.
- **A "neutral" smaller-vendor judge across all arms** (e.g., Llama
  3.3-Instruct): degrades the measuring instrument across the board.
  Cheaper but noisier, with no clear bias-elimination benefit since
  "neutral" judges have their own biases.
- **Three-judge ensemble** with one cross-vendor third judge (e.g.,
  GPT-5.5 high added as judge_tertiary on 20% subsample): would add
  ~$80/arm of judge spend and require new ICC math. Deferred to a future
  study — the existing two-judge design already provides cross-model
  rubric-application anchoring.

The principal-investigator decision (Victor Zhang, 2026-04-25): retain
the single Opus 4.7 max-effort primary judge across all arms, accept the
named bias, and frame results around the bias-cancelling endpoints.

---

## 8. arm.lock.json schema additions (v2)

v1 arms validate against v2 by treating missing fields as their v1
defaults (`vendor: anthropic`, `fill_levels_supported = fill_levels_target`).
v2 arms must populate the new fields explicitly.

```json
{
  "analyst": {
    "vendor": "anthropic | google | openai | deepseek",     // NEW
    "snapshot": "...",
    "snapshot_note": "<free text — mutability + 'why this is max thinking'>",  // NEW
    "context_window": 1000000,
    "thinking_config": { /* vendor-native shape */ },        // NEW (replaces thinking_effort for non-Anthropic)
    "thinking_effort": "...",                                 // KEPT for Anthropic backward compat
    "max_output_tokens": 65536,
    "temperature": 1.0
  },
  "design_used": {
    "fill_levels_target": [0.00, 0.25, 0.50, 0.75, 0.95],
    "fill_levels_supported": [0.00, 0.25, 0.50, 0.75, 0.95], // NEW (subset of target if context-limited)
    "positions": ["start", "middle", "end"],
    "noise_types": ["peer_materials"],
    "reports": ["MSFT"],
    "reps_per_cell": 7,
    "tokens_total_context_target": 1000000,
    "tokens_report_token_cap": 130000,
    "tokenizer_note": "<vendor tokenizer disclosure>"        // NEW
  }
}
```

All other arm.lock.json sections are unchanged.

---

## 9. compare_arms.py changes (v2)

1. **Pre-registration acceptance:** an arm passes the gate if its
   `pre_registration.hash` matches **either** v1 or v2 hash. Other values
   refuse comparison.
2. **Fill-level intersection:** the cross-arm tables are built over the
   intersection of `fill_levels_supported` across the arms being
   compared. Fill levels missing from any arm are listed in a footnote.
3. **Parser-failure rate per arm:** `grade_unparseable_pct` from
   `arm.lock.json.execution_results` becomes a separate column rather
   than being filtered out. JSON adherence is a real model property and
   varies across vendors; do not conflate it with instrument accuracy.
4. **Tokenizer-note + snapshot-note footnotes:** every per-arm row in the
   cross-arm report carries the arm's `tokenizer_note` and
   `snapshot_note` as table footnotes.

The strict per-cell apples-to-apples gate (identical assembled prompts
across arms for the same `(cell, rep)` coordinates) is preserved — the
noise seeding scheme `sha256(report|fill|position|rep)` does not include
analyst as an input, so all five arms see the same materials in the same
order at the same fill level. Tokenizer differences are downstream of
assembly.

---

## 10. What still must not vary across arms (reaffirmed)

Unchanged from v1:

- DESIGN.md, PROMPTS.md, RUBRIC.md (frozen by v1 hash, inherited by v2)
- `materials/*` (frozen by `materials.lock.json`, unchanged)
- Design grid: `fill_levels_target`, `positions`, `noise_types`,
  `reports`, `reps_per_cell`, `tiers`
- Extractor configuration (`claude-haiku-4-5-20251001`, `temperature=1.0`,
  `max_output_tokens=16384`, no thinking)
- Judge primary configuration (`claude-opus-4-7`, `effort=max`,
  `max_output_tokens=16384`)
- Judge secondary configuration (`claude-sonnet-4-6`, `effort=high`,
  `max_output_tokens=8192`, 20% deterministic subsample)
- Noise seeding scheme: `sha256(report|fill|position|rep)`

---

## 11. v2 lock recipe

```
pre_registration.v2.lock.methodology_hash =
    sha256(DESIGN.md + PROMPTS.md + RUBRIC.md + MULTI_VENDOR_ADDENDUM.md)

Reproducible:
    python3 -c "import hashlib; print(hashlib.sha256(b''.join(
        open(f, 'rb').read()
        for f in ['DESIGN.md','PROMPTS.md','RUBRIC.md','MULTI_VENDOR_ADDENDUM.md']
    )).hexdigest())"
```

`materials_lock_hash` is unchanged from v1
(`c13b5514279c9d8dbc5118ec9b3b1325a0cff56c4fb1cee8d66992a98cd25199`) —
same materials, no rehash.
