# Temporal-Noise Addendum (second addendum, methodology v3)

**Version:** 0.2 (post-acquisition; pre-pilot)
**Date:** 2026-05-05
**v0.1→v0.2 change summary:** §3.1 table updated to reflect the *attainable*
corpus from indexed transcript sources (34 files, 991K tokens, 86.2%
utilization at the 95-cell — still passes the §6.4 ≤90% gate). New §3.1c
documents the source-availability ceiling discovered during acquisition
(FY2016+FY2017 transcripts unavailable from any indexed source; 9 modern
spotty quarters where AlphaStreet has only earnings-preview placeholders;
1 paywalled stub). §13 lock recipe + §14 open items adjusted accordingly.
v0.1 history entry recorded in `methodology_hash_history`.
**Supersedes:** none — extends `pre_registration.v2.lock` (v2) without
modifying it. Hashed into a new `pre_registration.v3.lock` alongside the
unchanged DESIGN.md, PROMPTS.md, RUBRIC.md, and MULTI_VENDOR_ADDENDUM.md.
**Scope:** authorizes a second noise type — `temporal_msft`, drawn from
Microsoft's *own* prior-period filings — and the disambiguating prompt
suffix and metric extension that test requires. Does not change the
existing `peer_materials` design grid, the locked v1/v2 arms, the locked
materials, the question bank, the rubric, the extractor, or the judge
configuration.

**Critical isolation guarantee:** every byte of v1 and v2 data
(`arms/{opus-4-7,sonnet-4-6,gpt-5-5,gemini-3-1-pro,deepseek-v4-pro}/data/**`,
`materials/materials.lock.json`, both `.lock` files, all reports) remains
untouched by anything in this addendum. v3 adds a parallel surface; it does
not edit the existing one. See §7 for the file-by-file map.

---

## 1. Why a v3 lock instead of editing v2

The v2 lock (`pre_registration.v2.lock`, methodology hash `3433f4a6…`) was
authored on the assumption that "noise" means cross-company peer 10-Ks.
DESIGN.md §6.2 explicitly excludes prior-period MSFT filings from the
noise pool, with the stated reason that mixing same-company time-series
with the cross-company scope test "conflates" the two effects.

That exclusion was the right call for v1/v2 — the cross-company test is
clean, the slope is interpretable, and the cross-arm comparison ranks
arms on a single dimension. But the v2 results are now in, and they
expose a structural blind spot:

| arm              | cross_contamination at 95% fill |
| ---------------- | ------------------------------- |
| Opus 4.7         | 0.095 / response                |
| Sonnet 4.6       | 0.020 / response                |
| GPT-5.5          | 0.000                           |
| Gemini 3.1 Pro   | 0.000                           |
| DeepSeek V4 Pro  | 0.000                           |

Three of five arms sit at the metric's floor. That is not a finding that
those three arms have "solved" misattribution; it is a finding that the
metric tests the *easy* version of scope — peer-noise gives the model a
free anchor (the company name is a hard string-level differentiator). The
hard version — same company, different period — is unmeasured. v3 adds
that measurement as an additive lock so the existing five arms remain
valid evidence on the cross-company question they were designed to test,
and a new noise condition opens a complementary, harder question without
disturbing the first.

Editing DESIGN.md §6.2 (or PROMPTS.md, where the questions hard-code "the
most recent completed fiscal year") would invalidate every locked arm.
v3 is therefore strictly additive, exactly as v2 was strictly additive
over v1.

### v2→v3 inheritance rule

The v1 arms (Opus 4.7, Sonnet 4.6) and v2 arms (GPT-5.5, Gemini 3.1 Pro,
DeepSeek V4 Pro) remain **valid evidence under v3**. Justification: this
addendum only *adds scope* (admits a second noise type, a new metric, a
question-disambiguation suffix used **only** when that noise type is
active, and one new arm-naming convention). It does not change the v1/v2
task, materials, prompts, rubric, design grid, extractor, or judge
configuration. Every claim a v1 or v2 arm makes about
peer-noise-attributable drift is still true under v3.

`compare_arms.py` therefore accepts an arm whose
`arm.lock.json.pre_registration.hash` equals **v1 OR v2 OR v3**, and refuses
any other value. Cross-arm tables that mix arms from more than one
methodology version footnote each arm's version, and tables that mix arms
from more than one **noise type** carry the §10 disclosure (cross-noise
comparison is not apples-to-apples).

---

## 2. What this addendum permits

A second noise type is admitted into the design grid:

```
noise_types: [peer_materials, temporal_msft]
```

For each existing analyst snapshot, a **parallel `-temporal` arm** may be
locked alongside the existing peer-noise arm. Naming convention:

```
arms/opus-4-7-temporal/
arms/sonnet-4-6-temporal/
arms/gpt-5-5-temporal/
arms/gemini-3-1-pro-temporal/
arms/deepseek-v4-pro-temporal/
```

Each `-temporal` arm:

- Uses the same analyst snapshot, the same vendor SDK, the same thinking
  config, the same temperature, and the same `max_output_tokens` as its
  base arm (the analyst is held constant — what changes is the noise).
- Uses the same extractor and judges as v1/v2 (held constant across the
  entire study; see `pre_registration.v2.lock §instruments_held_constant`).
- Uses the **temporal noise pool** (§3) instead of `peer_materials`.
- Uses the **disambiguated question block** (§4) — base question text
  unchanged; a noise-type-conditional period-anchoring suffix is appended
  to each Tier-1 and Tier-2 question and a scope reminder is appended to
  Tier-3.
- Reports the **new misattribution metric** `temporal_contamination` (§5)
  alongside (not replacing) the existing `cross_contamination` metric.
  `cross_contamination` is reported as 0 by construction — there is no
  peer material in the temporal arm's noise.
- Pilots on a **reduced cell grid** (§6) rather than the full 13 cells,
  because the v1/v2 cells already establish that drift exists; the
  question for v3 is only whether the temporal noise type changes the
  shape.

A `-temporal` arm is not required for any base arm. Locking the GPT-5.5
and Opus 4.7 temporal arms first is recommended (§6 rationale).

---

## 3. New noise corpus: `temporal_msft`

### 3.1 Sourcing rule

Microsoft's own prior-period public, first-party disclosures across three
document types — annual 10-Ks, interim 10-Qs, and earnings-call
transcripts — drawn from periods **strictly before the latest target
document** (the Q2 FY2026 earnings call, held 2026-01-28). The pool
therefore admits the Q1 FY2026 call (held Oct 2025), which postdates the
FY2025 10-K target but predates the Q2 FY2026 target — a clean
"intervening-period" distractor. All three types are SEC- or IR-public;
the corpus is reproducible from EDGAR plus Microsoft's IR archive (with
Motley Fool as a transcript fallback for older calls).

The pool is sized to enable the **full 0–95% drift sweep** the v1/v2
study uses, so the temporal arm produces a comparable five-point curve
rather than a truncated three-point one.

**Spec'd corpus (v0.1 — aspirational target):**

| Subpool                              | Files | Per-file tokens (Anthropic, est.) | Subtotal |
| ------------------------------------ | ----- | --------------------------------- | -------- |
| Prior MSFT 10-Ks (FY2024, FY2023)    | 2     | ~75K each                         | ~150K    |
| Prior MSFT 10-Qs (FY2025 Q1–Q3, FY2024 Q1–Q3, FY2023 Q1–Q3) | 9 | ~28K each | ~250K |
| Prior MSFT earnings-call transcripts: Q1 FY2026 + Q1–Q4 of FY2016 through FY2025 (10 fiscal years × 4 quarters = 41 calls) | 41 | ~14K each | ~580K |
|                                      | **52** | | **~980K** |

**Attainable corpus (v0.2 — measured 2026-05-05 after acquisition):**

| Subpool                              | Files acquired | Measured tokens | Per-file avg |
| ------------------------------------ | -------------- | --------------- | ------------ |
| Prior MSFT 10-Ks (FY2024, FY2023) — all from EDGAR | 2 | **175,369** | 87,684 |
| Prior MSFT 10-Qs (FY2025 Q1–Q3, FY2024 Q1–Q3, FY2023 Q1–Q3) — all from EDGAR | 9 | **463,827** | 51,536 |
| Prior MSFT earnings-call transcripts (23 of 41 spec'd) — Motley Fool live + Wayback Machine snapshots of Fool + Wayback snapshots of AlphaStreet | 23 | **352,184** | 15,312 |
|                                      | **34** | **991,380** | |

The 10-Qs come in materially larger than the v0.1 estimate (51K avg vs
the assumed 28K), which more than compensates for the call-subpool
shortfall. The pool size is therefore **above** the §6.4 threshold:

- 95% cell noise budget: ~855K
- Pool: 991K
- Utilization at 95-cell: **86.2%** ≤ 90% gate → **PASS**
- Headroom above the gate: ~41K tokens

The shape of the pool — small earnings calls plus mid-sized 10-Qs plus
two large 10-Ks — is preserved (deliberate per v0.1):

- Many small files give the FFD sampler fine-grained packing freedom at
  every fill level (the v1/v2 peer pool's seven large 10-Ks are clumsy
  to pack at 25–50% fill; the temporal pool packs cleanly).
- The 10-K subpool is the closest topical match to the target document
  itself (same disclosure structure, same MD&A organization, restated
  comparators of the very figures the questions ask about).
- The 10-Q subpool injects the highest-density distractor risk —
  quarterly revenue figures sit numerically close to "FY annual revenue
  / 4," and a model that fuzzy-matches periods will pick up a 10-Q line
  expecting it to be an annual disclosure.
- The earnings-call subpool (now 23 calls, FY2018-FY2026 sparse) is the
  closest stylistic match to the target's own Q2 FY2026 call.

The §3.4 deep-history extension is **not** triggered — pool already
clears the gate. If pilot reveals `pool_utilization_pct > 0.90` after
all (e.g., due to per-cell sampling variance), the deep-history fallback
is still available as designed.

### 3.1a Considered and rejected: third-party commentary as pool extender

The Stratechery archive at `/Users/vz/Stratechery scrapping/output/` (1,620
articles, ~25.7M chars, including 100+ titled MSFT pieces) was considered
as a pool extender and rejected. The rejection is part of the addendum's
explicit record so future reviewers can re-evaluate.

| Property                       | Prior MSFT calls/filings (chosen)              | Stratechery commentary (rejected)              |
| ------------------------------ | ---------------------------------------------- | ---------------------------------------------- |
| Document type vs target bundle | **Identical** — same speakers, same format     | Different — narrative essay style              |
| Source status                  | First-party disclosure                         | Third-party commentary                         |
| New confound introduced        | None — same content kind as the target itself  | **Frame leakage** — Thompson's analytical framing ("Aggregation Theory", "Strategy Credit", "Microsoft's Refoundation") becomes a misattribution vector the rubric does not measure and §5's distractor-list approach cannot detect |
| Copyright                      | SEC public + IR public + Motley Fool reprint   | Paid subscription content                      |
| Discriminability for the model | **Hard** — adjacent in style and vocabulary; only the period differs | Easy — prose style alone reveals it's not the 10-K source |
| Test cleanliness               | Same noise type as the target's own document type — measures what we want to measure (period drift) | Mixes period drift with style drift with frame-leakage drift — three things at once, none cleanly attributable |

The principle: pool extension should *strengthen* the test (more of the
same hard signal), not *broaden* it (more kinds of confusion at once). A
follow-up study (`commentary_msft` as a fourth noise type) is a clean way
to add the third-party-commentary axis later, with its own metric for
frame leakage; mixing it into v3 would corrupt the temporal-drift
endpoint.

### 3.1b The restated-comparator wrinkle

Each MSFT 10-K restates the prior-year figures for comparability. The
FY24 10-K's "FY23" comparator may differ slightly from the FY23 10-K's
own "FY23" disclosure (e.g., due to segment reorganization). Both
versions land in the temporal pool. The §3.3 hand-screen treats this as
*two distinct distractors* per ground-truth value — a hit on either
counts. Pilot results that reveal the model preferentially picks the
"as restated" version vs the "as originally filed" version are reported
as a §5.3 diagnostic (period-mismatch direction) sub-finding.

### 3.1c Source-availability ceiling (empirical, recorded v0.2)

Acquisition (2026-05-05) revealed a hard ceiling on indexed transcript
sources for prior MSFT calls. The v0.1 spec assumed Motley Fool (with MS
IR as theoretical backup) could supply all 41 calls; reality is more
constrained:

- **Microsoft IR** does not host transcript text — only press releases,
  slide decks, and webcast media. Verified by inspecting the FY2026 Q1
  IR landing page and earnings-archive index. (The v0.1 wording "EDGAR
  plus Microsoft's IR archive" is therefore aspirational for the call
  subpool; the addendum did not validate this before locking.)

- **Motley Fool** has full coverage from FY2018 onward but its IP-level
  rate-limit on the acquisition session imposed a sustained 24-hr 429
  block after a brief probe sweep. Wayback Machine's snapshot index of
  Fool covers ~12 (fy, fq) pairs (heavily Q2-biased — Wayback's January
  crawls hit MSFT Q2 calls reliably; other quarters spotty).

- **AlphaStreet** has full transcript coverage from FY2020 onward;
  partial FY2018–FY2019; **none for FY2016 or FY2017** (AlphaStreet's
  founding predates MSFT coverage by ~2 years). Their CloudFront WAF
  rate-limits aggressive HEAD-probing; acquisition session triggered a
  ~10-min block after ~50 HEADs. Wayback Machine has ~19 (fy, fq) AS
  captures; some are JS-shell pages that Wayback rendered before the
  transcript content loaded (q3/q4 FY2021 v1 captures), correctable by
  using a later Wayback timestamp.

- **Combined coverage achievable**: 23 of 41 specs. Missing 18:
  - **8 calls FY2016 + FY2017** — Wayback CDX prefix-search confirms
    *zero* MSFT captures of `fool.com/earnings/call-transcripts/2015*`
    or `2016*`. AlphaStreet has none. These transcripts are unavailable
    from any source we tested.
  - **9 spotty modern quarters** (Q1 FY2018, Q4 FY2018, Q1/Q3/Q4 FY2019,
    Q1 FY2020, Q4 FY2023, Q4 FY2024, Q1 FY2025) — AlphaStreet has only
    `microsoft-q<N>-<YYYY>-earnings-stay-tuned-for-the-live-earnings-call-and-real-time-transcript`
    placeholder pages, never replaced with real transcripts.
  - **1 paywalled call** (Q3 FY2025) — AlphaStreet served a 488-token
    speaker-list stub; Wayback never captured the full body.

The acquisition catalogue (`harness/scripts/_wayback_known_captures.json`
+ `harness/scripts/fetch_temporal_sources.py:_KNOWN_CALL_DATES`) is a
complete record of what was tried; the missing-list above is reproducible
from those two files plus the live-source state at acquisition time.

**Methodological consequences:**

1. **The §3.1 attainable table is the load-bearing record;** the v0.1
   aspirational table is preserved above for diff-clarity but is not
   what the v3 lock pins.
2. **Pool sizing still passes §6.4** because the 10-Q subpool is larger
   than v0.1 estimated. No deep-history extension required.
3. **Cell-by-cell stylistic match weakens slightly** — the call subpool
   shrinks from 41 to 23, so the FFD sampler has 56% as many call-style
   files to draw from. At the 95% cell, where ~855K of noise is packed,
   the call subpool contributes at most ~352K, meaning the marginal
   cells will lean more on 10-K/10-Q content. This is a real change in
   the noise composition the temporal arm sees vs the v0.1 design and
   is reported in the v3 final report's methodology section.
4. **Reproducibility**: a future re-run with Fool unblocked could fill
   the 9 spotty quarters and possibly the 8 ancient ones. If acquired,
   they extend the pool but do **not** invalidate the v0.2 lock —
   they'd produce a v0.3 lock with strictly larger coverage.

### 3.2 Materials lock — additive, separate file

The existing `materials/materials.lock.json` is **byte-unchanged**.
Adding new entries to that file would re-hash it and silently invalidate
every v1/v2 arm (their `arm.lock.json.materials_lock_hash` would no
longer match).

A second lock file is introduced:

```
materials/materials_temporal.lock.json
```

Same JSON schema as the original (`{"files": {<path>: {"sha256":…, "token_count":…}}}`),
but covering only the temporal-noise files plus a re-listing of the
target files (which the temporal arm shares with v1/v2 — re-listing makes
the lock self-contained). The v3 pre-registration lock references
**both** lock files (§13).

The directory layout that backs the new lock:

```
materials/noise/temporal_msft/MSFT/
  msft_10k_fy2024.txt
  msft_10k_fy2024.meta.json
  msft_10k_fy2023.txt
  msft_10k_fy2023.meta.json
  msft_q1fy26_call.txt
  ...
```

`materials/noise/peer_materials/MSFT/` is untouched. `materials/target/MSFT/`
is untouched. The `_source/` raw HTML dir gets the new HTM/HTML originals
appended; build_materials.py grows a `--noise-type temporal_msft` flag
that produces the new `.txt` + `.meta.json` pair (existing peer-pool
extraction unchanged).

### 3.3 Hand-screen rule (mirrors v1 §6.2 noise-screening)

Before locking the temporal pool, every prior-period file is hand-screened
for **forward-looking statements that match a Tier-1 or Tier-2 ground-truth
value within ±0.5%**. Two failure modes to catch:

1. **Forward guidance hits.** Q1 FY2026 call may have given Q2 FY2026
   guidance whose midpoint lands within tolerance of an FY2025 actual; if
   the model cites the guidance number as the FY2025 actual, that is a
   genuine misattribution but it inflates `temporal_contamination` for a
   reason orthogonal to drift.
2. **Restated comparators.** Each MSFT 10-K restates the prior year for
   comparability; FY2024 numbers as restated in the FY2025 10-K may
   differ slightly from FY2024 numbers as originally filed. The
   `common_distractors` list is widened to cover both originals and the
   most recent restatement, so a hit on either is counted.

Findings are recorded as a `noise_screening_log.md` next to the temporal
lock file. The lock includes the screening-log SHA-256 — changes to the
log are part of the methodology surface.

### 3.4 Future extension (not in v0.1 scope)

The §3.1 pool already supports the full 13-cell grid through 95% fill
with ~87% utilization at the 95-cell. Two future extensions are noted:

1. **Deep-history extension** — pre-FY2016 earnings calls and pre-FY2023
   10-Ks (FY2022 10-K, FY2021 10-K, FY2020 10-K). Bumps the pool toward
   ~1.3M tokens. Triggered if pilot reveals `pool_utilization_pct > 0.90`
   at the 95-cell on either priority arm, or if a separate "deep
   history" arm is later commissioned to test whether ten-years-prior
   content drifts differently than three-years-prior content.
2. **`commentary_msft` follow-up noise type** (third-party analyst
   commentary, e.g., the Stratechery archive considered and rejected in
   §3.1a). A separate addendum, separate metric (frame-leakage), separate
   arms — not v3 scope.

---

## 4. Question disambiguation under temporal noise

### 4.1 The problem

PROMPTS.md §3 phrases every question with "the most recent completed
fiscal year." Under peer noise that phrasing is unambiguous: there is
exactly one set of MSFT figures in context. Under temporal noise the
phrase is genuinely ambiguous — multiple "most recent completed fiscal
year" values for MSFT now coexist in the prompt (FY2024 most-recent at
the time of the FY2024 10-K, FY2025 most-recent at the time of the
FY2025 10-K). A model that answers "FY24 actuals" is not necessarily
drifting; the question allowed both readings.

To convert that ambiguity into a precise scope test, the addendum
specifies a **noise-type-conditional disambiguation suffix** that the
harness appends to each question id when assembling a temporal-arm
prompt. Base PROMPTS.md is untouched.

### 4.2 The suffix (frozen text — part of the v3 hash)

All three suffixes are written self-conditionally so the same sentence is
valid at the temporal-arm baseline (fill = 0, no other Microsoft filings
present) as at fill > 0 (other filings present). At baseline the
"if … appear" clause is vacuously satisfied; at fill > 0 it binds.

For Tier 1 (`F-01`, `F-02`, `F-03`), the literal sentence appended after
each question's existing text:

> *Use the figure as disclosed in Microsoft's FY2025 10-K specifically
> (the document inside `<<< TARGET MATERIALS >>>`); if any other
> Microsoft filings or earnings-call transcripts appear elsewhere in
> this prompt, treat them as scenario realism only.*

For Tier 2 (`C-01`, `C-02`), the literal sentence appended:

> *Compute the figure from values disclosed in Microsoft's FY2025 10-K
> specifically (the document inside `<<< TARGET MATERIALS >>>`); if any
> other Microsoft filings or earnings-call transcripts appear elsewhere
> in this prompt, do not mix in figures from them.*

For Tier 3 (`S-01`, `S-02`, `S-03`), the literal sentence appended:

> *Ground all claims in Microsoft's FY2025 10-K and Q2 FY2026 earnings
> call (the documents inside `<<< TARGET MATERIALS >>>`). If
> prior-period Microsoft filings or earnings-call transcripts appear
> elsewhere in this prompt, you may reference them only for explicit
> longitudinal context (e.g., "revenue grew from $X in FY2024 to $Y in
> FY2025") and only when the period of each cited figure is stated
> explicitly.*

These three sentences are pinned in this section by exact byte content.
Edits change the v3 methodology hash, which is correct behavior.

### 4.3 Why a suffix instead of editing PROMPTS.md

Editing PROMPTS.md would invalidate every locked v1/v2 arm. The suffix
is conditional on `noise_type == "temporal_msft"` — at peer-noise cells
the suffix is not applied and the prompt is byte-identical to v2. The
harness implements this as one branch in `assemble_prompt` (§7 file
map). The base PROMPTS.md remains the authoritative source for the
question text; the addendum supplies the suffix text and the rule for
when to apply it.

### 4.4 Effect on the cross-arm comparison

Cross-arm comparison **within** the temporal noise type is apples-to-apples
(every `-temporal` arm sees the same suffixed prompt). Cross-noise-type
comparison (peer vs temporal at the same arm) is not apples-to-apples —
the prompts differ by exactly the §4.2 suffixes — and §10 specifies how
the report flags this.

---

## 5. New misattribution metric: `temporal_contamination`

### 5.1 Definition

A per-(run, q_id) integer, parallel to the existing `cross_contamination`:

```
temporal_contamination(run, q_id) :=
  count of distinct distractor values from the temporal-noise distractor
  list that appear in the answer or citation, attributed to the wrong
  MSFT period.
```

The temporal distractor list is built during ground-truth preparation:
for each Tier-1 and Tier-2 ground-truth value V (e.g., FY2025 total
revenue = $X), the analyst lists the same line item from each
prior-period file in the temporal pool (FY2024 total revenue = $X', Q1
FY2026-guidance midpoint = $X'', etc.). Each prior-period value becomes
a `temporal_distractor` entry tagged with its source period. Hand-screen
(§3.3) ensures no temporal distractor lies within Tier-1/2 tolerance of
the FY2025 ground-truth.

Programmatic detection is identical in shape to v1/v2's
`cross_contamination` detector (DESIGN.md §9.2): regex/numeric match
against the answer's `answer_normalized` field and the citation span,
incrementing on each distinct hit.

### 5.2 Hard-fail integration with `scope_adherence`

`RUBRIC.md §scope_adherence` already caps the dimension at 3 when
`cross_contamination ≥ 1`. v3 extends the cap symmetrically: when
`cross_contamination + temporal_contamination ≥ 1`, the rubric still
caps `scope_adherence` at 3. RUBRIC.md is **not edited** — the cap is
implemented in the grading code and documented here in §5.2 as part of
the methodology surface (the grading code's behavior is part of the v3
hash via `harness/src/grading/scope_cap.py`'s SHA, recorded in each
arm.lock.json's `judge_secondary` block under a new
`grading_module_hash` field).

### 5.3 New diagnostic: period-mismatch direction

For each `temporal_contamination` hit, log the source period of the
matched distractor (`FY2024`, `Q4_FY2025`, `Q1_FY2026_guidance`, …).
This produces a per-arm distribution of "when the model picks the wrong
period, *which* wrong period does it pick?" The pre-registered
expectation (H9, §8) is that the closest adjacent period dominates; a
finding of "errors are uniform across the temporal pool" would be a
surprise worth reporting.

---

## 6. Cell grid for the temporal arm

### 6.1 The grid (full 13 cells, matching v1/v2)

The §3 pool extension to ~980K tokens makes the full v1/v2 grid
achievable under temporal noise. The grid is **byte-identical in shape
to v1/v2** so cross-noise comparison at every fill level and every
position is apples-to-apples (modulo the §10 disclosure on the §4.2
suffix-induced prompt difference).

```
Cells (13 total):
  C0:           fill=0.00, position=null,                         noise=temporal_msft   (baseline)
  C1–C12:       fill ∈ {0.25, 0.50, 0.75, 0.95}                                          (4 levels)
              × position ∈ {start, middle, end}                                          (3 positions)
              × noise = temporal_msft                                                    (1 type)

reps_per_cell: 7
total runs per temporal arm: 91
```

### 6.2 Why the full grid is the right choice

1. **Pool exhaustion is no longer the limiting factor.** The original
   ~239K filings-only pool exhausted at 50%; the §3.1 pool (~980K)
   carries the noise budget cleanly through 95%. The 95% cell logs
   `pool_utilization_pct ≈ 87%` in expectation; if pilot exceeds 90%,
   the pool is extended (§3.1) before the cell is locked, so high-fill
   cells are not pool-bound.
2. **Cross-noise comparison at every cell becomes the headline output.**
   The interesting v3 finding is not "drift exists under temporal noise"
   (it must) but "how does the *shape* of the temporal drift curve differ
   from the peer drift curve at each fill level." That is only answerable
   at matching fill levels and positions — i.e., the same 13 cells.
3. **Position interaction is a load-bearing v1/v2 finding** ("lost in
   the middle") and the most plausible mechanism for temporal
   misattribution to be position-sensitive: a prior 10-K dropped in the
   middle competes spatially with the target 10-K block, while a prior
   10-K at the start or end is positionally distinct. Truncating to one
   position would dodge the most diagnostic prediction.
4. **The full grid is what makes H6–H9 testable per-cell** rather than
   only at the aggregate level (§8 hypothesis specifications).

### 6.3 Recommended priority arms (still GPT-5.5 + Opus 4.7 first)

The same priority ordering applies even at the full grid:

- **GPT-5.5-temporal** first. Its v2 peer-noise `cross_contamination = 0`
  across all 91 runs is the most distinctive cross-arm finding in the
  dataset; whether that floor survives temporal noise is the single
  most informative result v3 can produce.
- **Opus 4.7-temporal** second. Its v2 `cross_contamination = 0.095`
  sets the upper-bound expectation for temporal performance; if its
  temporal rate is materially higher, the cross-arm gap that the v2
  report makes a headline of either compresses or grows on a different
  axis.

The remaining three arms (Sonnet 4.6, Gemini 3.1 Pro, DeepSeek V4 Pro)
are explicit follow-ups, gated on the GPT/Opus result. Each adds 91
runs at full-grid scale (§12 totals).

### 6.4 Pilot-within-the-arm (go/no-go before committing the full grid)

Before running the full 91-run grid for either priority arm, run the v3
pilot subset first — three cells, mirroring DESIGN.md §11:

```
pilot_temporal:
  cells:
    - {fill: 0.00, position: null,   noise: temporal_msft}
    - {fill: 0.50, position: middle, noise: temporal_msft}
    - {fill: 0.95, position: middle, noise: temporal_msft}
  reps_per_cell: 7
```

Same go/no-go criteria as DESIGN.md §11 (parse rate ≥ 98%, ICC ≥ 0.70,
realized fill within ±500 tokens of target, pool_utilization_pct ≤ 90%
at 95-cell, pilot cost within 2× projection). If any fail, the pool
shape or §4.2 suffix wording is iterated *before* the full grid is
funded. Pilot cost per arm: ~$45 (§12). Pilot data is kept on success
and folded into the full-grid dataset (cells re-run only if the pilot
exposed a methodology issue requiring a re-spec).

---

## 7. Data isolation — file-by-file map

This is the §7 the user explicitly demanded: previous data is unchanged.
Every byte that v1/v2 produced lives in one of the locations on the LEFT
side of the table below; every byte v3 produces lives on the RIGHT side.
There is no overlap.

| Untouched (v1/v2)                              | Added by v3                                              |
| ---------------------------------------------- | -------------------------------------------------------- |
| `DESIGN.md`                                    | (read-only)                                              |
| `PROMPTS.md`                                   | (read-only — base questions; suffix lives in §4.2)       |
| `RUBRIC.md`                                    | (read-only — cap rule extended in code, documented §5.2) |
| `MULTI_VENDOR_ADDENDUM.md`                     | (read-only)                                              |
| `pre_registration.lock`                        | (read-only — v1)                                         |
| `pre_registration.v2.lock`                     | (read-only — v2)                                         |
| `materials/materials.lock.json`                | (read-only — v1/v2 lock; bytes unchanged)                |
| `materials/noise/peer_materials/MSFT/*`        | (read-only)                                              |
| `materials/target/MSFT/*`                      | (read-only — also re-listed in v3 lock for self-containment) |
| `materials/ground_truth/MSFT.json`             | (read-only — temporal distractors live in a separate file, §5.1) |
| `materials/questions/MSFT.json`                | (read-only)                                              |
| `arms/{opus-4-7,sonnet-4-6,gpt-5-5,gemini-3-1-pro,deepseek-v4-pro}/**` | (read-only — every existing arm's lock, manifest, raw, extracted, graded, reports) |
| `cross_arm/COMPARATIVE_REPORT.md`              | (read-only — auto-generated; v3 may produce a *new* file `cross_arm/COMPARATIVE_REPORT_temporal.md` but does not edit this one) |
| `cross_arm/CROSS_ARM_REPORT.md`                | (read-only)                                              |
| `cross_arm/SOBER_STATE_*.md`                   | (read-only)                                              |
|                                                | `TEMPORAL_NOISE_ADDENDUM.md` *(this file)*               |
|                                                | `pre_registration.v3.lock`                               |
|                                                | `materials/materials_temporal.lock.json`                 |
|                                                | `materials/noise/temporal_msft/MSFT/*` (52 .txt + .meta.json) |
|                                                | `materials/ground_truth/MSFT_temporal_distractors.json`  |
|                                                | `materials/noise_screening_log.md`                       |
|                                                | `arms/{base}-temporal/` (one new directory per locked temporal arm) |
|                                                | `harness/config/arms/{base}-temporal.yaml`               |
|                                                | `harness/src/grading/scope_cap.py` (extracted from existing grading; no behavior change for peer arms) |
|                                                | `cross_arm/CROSS_ARM_REPORT_temporal.md` (new file, post-collection) |

`verify_arm_integrity.py` continues to refuse any change to a locked arm's
data manifest; running it against any v1/v2 arm after v3 lands must still
print `OK`. CI should add a smoke check that does exactly that.

---

## 8. Hypotheses for the temporal arm (pre-registered)

Numbered to continue the v1/v2 hypothesis list (RQ1–RQ5 in DESIGN.md §5).
Holm-Bonferroni across H6–H10. Hypotheses are defined per-cell where the
full-grid design supports it; aggregate forms are noted explicitly.

- **H6 — Floor breaks (one-sided, primary).** At fill ≥ 0.25 (any cell)
  with `temporal_msft` noise, mean per-response `temporal_contamination`
  exceeds 0 for at least one of the three arms (GPT-5.5, Gemini, DeepSeek)
  whose v2 peer-noise `cross_contamination` was identically 0 across all
  91 runs. Tested at every non-baseline cell; rejection requires
  significance after Holm-Bonferroni within H6's 12 cell-tests.

- **H7 — Cross-arm spread compresses.** The cross-arm spread on
  `temporal_contamination` at fill ∈ {0.50, 0.75, 0.95} is *narrower*
  than the spread on `cross_contamination` at the matching v2 peer cells,
  measured by max-minus-min across the arm set. Operationalized
  per-(fill, position) pair; H7 holds if it holds in ≥ 2 of the 9 paired
  cells. Prediction: same-company anchors collapse the vendor
  differentiation seen on cross-company anchors. (At full grid the
  comparison is per-cell; the v0.1 reduced-grid version of H7 is
  superseded.)

- **H8 — Tier-3 decoupling (two-sided, exploratory).** At every fill
  level ≥ 0.50, Tier-3 `reasoning_quality` under temporal noise is *not
  lower* than under peer noise (matched cell), while Tier-1+Tier-2
  accuracy under temporal *is* lower. Multi-period MSFT context is
  informational, not adversarial, for synthesis tasks; it is adversarial
  for retrieval and derivation. A confirming finding decomposes the
  failure-mode taxonomy in DESIGN.md §3.1 along the noise-type axis.

- **H9 — Period-proximity bias.** Conditional on a
  `temporal_contamination` hit, the source-period distribution across
  the §3.1 pool is *not uniform*: the periods closest to the target
  (FY2024 10-K, the FY2025 10-Qs, and the Q1 FY2026 / Q4 FY2025 calls)
  account for a disproportionate share of hits relative to their share of
  the pool's tokens. Confirming constrains the mechanism (recency-anchored
  attention); null rules out recency-bias as the explanation. Tested
  globally across all temporal-noise cells (per-cell power is
  insufficient).

- **H10 — Position × period-proximity interaction (full-grid only).**
  The "lost in the middle" v1/v2 effect (RQ2 / H2) interacts with
  period-proximity under temporal noise: when the target is in `middle`
  position at fill ≥ 0.50, the share of `temporal_contamination` hits
  attributable to the closest-adjacent period is *higher* than at
  `start` or `end`. Mechanism: the spatially-adjacent prior 10-K block
  and the target 10-K block compete most directly when both sit
  centrally. Rejection requires a significant interaction term in the
  per-hit logistic regression on `position × source_period_proximity`.

H6 is the load-bearing primary test. H7–H10 are characterization
hypotheses that shape the cross-noise interpretation. Per-cell tests
remain feasible because the §3.1 pool supports the full 13-cell grid
without truncation.

---

## 9. arm.lock.json schema additions (v3)

v1/v2 arms validate against v3 by treating missing fields as their v2
defaults (`noise_type: peer_materials`, `disambiguation_suffix: null`,
`materials_temporal_lock_hash: null`, `temporal_distractors_hash: null`).
v3 arms (`*-temporal`) must populate the new fields explicitly.

```json
{
  "analyst": { /* unchanged from v2 */ },
  "design_used": {
    "noise_types": ["temporal_msft"],            // NEW value (v2 allowed only "peer_materials")
    "noise_pool_path": "materials/noise/temporal_msft/MSFT",   // NEW
    "noise_pool_subpools": ["10k", "10q", "earnings_call"],    // NEW (per §3.1)
    "fill_levels_target":    [0.00, 0.25, 0.50, 0.75, 0.95],  // FULL v1/v2 grid restored
    "fill_levels_supported": [0.00, 0.25, 0.50, 0.75, 0.95],
    "positions": ["start", "middle", "end"],     // FULL v1/v2 grid restored
    "reports": ["MSFT"],
    "reps_per_cell": 7,
    "pool_utilization_pct_per_cell": { /* logged at run time, e.g., "0.95-middle": 0.87 */ }, // NEW
    "tokens_total_context_target": 1000000,
    "tokens_report_token_cap": 130000,
    "tokenizer_note": "<vendor tokenizer disclosure>"
  },
  "prompt_assembly": {
    "disambiguation_suffix_applied": true,        // NEW
    "disambiguation_suffix_source": "TEMPORAL_NOISE_ADDENDUM.md §4.2",
    "disambiguation_suffix_hash": "<sha256 of the three §4.2 sentences concatenated>"  // NEW
  },
  "materials": {
    "materials_lock_hash":          "c13b5514…",  // unchanged — v1/v2 lock, target+peer
    "materials_temporal_lock_hash": "<sha256>",   // NEW — temporal lock
    "temporal_distractors_hash":    "<sha256 of MSFT_temporal_distractors.json>",  // NEW
    "noise_screening_log_hash":     "<sha256 of noise_screening_log.md>"           // NEW
  },
  "judge_secondary": {
    /* unchanged from v2 — same snapshot, max_output_tokens, effort, subsample_pct */
    "grading_module_hash": "<sha256 of harness/src/grading/scope_cap.py>"  // NEW (rule extends to temporal_contamination)
  },
  "execution_results": {
    /* unchanged shape from v2; cross_contamination AND temporal_contamination both reported */
  }
}
```

Schema version bumps to **3.0** for `*-temporal` arms. v1/v2 arms remain at
2.0 (or 1.0 for the original Anthropic arms).

---

## 10. compare_arms.py changes (v3)

1. **Pre-registration acceptance:** an arm passes the gate if its
   `pre_registration.hash` matches **v1 OR v2 OR v3**. Other values refuse
   comparison.

2. **Cross-noise-type tables are explicitly opt-in.** The default cross-arm
   table uses arms of one noise type only. A `--include-temporal` flag is
   required to mix `peer_materials` and `temporal_msft` arms in the same
   table; tables produced under that flag carry a top-of-file disclosure:

   > *Cross-noise-type comparison. Prompts differ between rows by the
   > noise-type-conditional disambiguation suffix specified in
   > TEMPORAL_NOISE_ADDENDUM.md §4.2. Per-cell fill labels refer to the
   > noise-type-specific pool, not a shared budget. Treat differences as
   > directional, not as effect-size estimates against a common baseline.*

3. **`temporal_contamination` is a new column** in the cross-arm metric
   block, parallel to `cross_contamination`. For peer arms it renders as
   `0 (n/a — no temporal noise in pool)`; for temporal arms
   `cross_contamination` renders the same way symmetrically.

4. **Fill-level intersection** still applies, now per noise type. A
   cross-arm temporal table at fill={0, 0.25, 0.50} compares all temporal
   arms supporting those levels.

5. **A separate report file.** Cross-arm temporal output goes to
   `cross_arm/COMPARATIVE_REPORT_temporal.md` and (if narrative is added)
   `cross_arm/CROSS_ARM_REPORT_temporal.md`. The existing
   `COMPARATIVE_REPORT.md` and `CROSS_ARM_REPORT.md` are not edited or
   regenerated.

The strict per-cell apples-to-apples gate (identical assembled prompts
within a noise type, across the analyst arms of that noise type) is
preserved. The noise seeding scheme `sha256(report|fill|position|rep)`
gains `noise_type` as a fifth input — but only the temporal seeds use the
new key; peer seeds are unchanged because the seed function returns the
v1/v2 result when `noise_type == "peer_materials"`. (Equivalent to making
"peer_materials" the unsalted default; v1/v2 arm seeds remain valid.)

---

## 11. What still must not vary across arms (reaffirmed)

Unchanged from v1/v2:

- DESIGN.md, PROMPTS.md, RUBRIC.md (frozen by v1 hash, inherited by v2/v3)
- MULTI_VENDOR_ADDENDUM.md (frozen by v2 hash, inherited by v3)
- `materials/materials.lock.json` (frozen by v1/v2 hash, inherited by v3)
- v1/v2 arm data directories (frozen by each arm's data manifest)
- Extractor configuration (`claude-haiku-4-5-20251001`, `temperature=1.0`, `max_output_tokens=16384`, no thinking)
- Judge primary configuration (`claude-opus-4-7`, `effort=max`, `max_output_tokens=16384`)
- Judge secondary configuration (`claude-sonnet-4-6`, `effort=high`, `max_output_tokens=8192`, 20% deterministic subsample)
- Within-arm noise seeding scheme: `sha256(report|fill|position|rep)` for peer arms; `sha256(report|fill|position|rep|noise_type)` for temporal arms — peer arms are unaffected because the v1/v2 seed function is unchanged for them.

Within a noise type, prompts remain byte-identical across analyst arms at
the same `(cell, rep)` coordinate. Across noise types, prompts differ by
the §4.2 suffix only.

---

## 12. Cost estimate (full grid, two priority arms)

Two `*-temporal` arms (GPT-5.5-temporal + Opus 4.7-temporal), 91 runs
each, full v1/v2 grid (13 cells × 7 reps). The §3.1 pool extension makes
this feasible. Per-arm cost is anchored on the v1/v2 actual spend
(`arms/*/arm.lock.json.execution_results.cost_usd`) — the temporal arm's
prompt is identical in shape and within ±3% of the v1/v2 prompt's token
count at every fill level (the pool's tokenizer ratio is dominated by
the same English+tabular blend as the peer pool).

### Per-arm cost (extrapolated from v1/v2 actuals)

| Component                           | GPT-5.5-temporal | Opus 4.7-temporal |
| ----------------------------------- | ---------------- | ----------------- |
| Analyst (91 runs, full grid)        | ~$60             | ~$320             |
| Extractor (Haiku, 91 × 8 q)         | $1               | $1                |
| Judge primary (Opus max, 91 × 3 Tier-3 + Tier-1/2 sanity) | shared | ~$80 |
| Judge secondary (Sonnet, 20% subsample)                   | shared | ~$15 |
| Pairwise vs baseline (Opus, 25% subsample)                | shared | ~$10 |
| **Per-arm subtotal**                | **~$135**        | **~$425**         |

### Two-arm pilot (recommended v3 minimum)

| Stage                                       | Cost   |
| ------------------------------------------- | ------ |
| Pilot subset (3 cells × 7 reps × 2 arms — §6.4) | ~$90   |
| Full grid completion (10 remaining cells × 7 reps × 2 arms) | ~$470  |
| Materials prep + EDGAR/IR scrape automation + hand-screen | ~$20  |
| **Two-arm full-grid total**                 | **~$580** |
| Budget                                      | $700   |
| Hard stop                                   | $850   |

Sized to the same envelope as the v1/v2 single-arm budget (DESIGN.md §13:
$700 budget, $850 hard stop). Pilot is gated as in §6.4: pilot cost (~$90)
runs first; full grid only triggers if go/no-go criteria pass.

### Optional follow-on (5 arms, full grid)

If H6 lands and the cross-arm finding warrants extending to all five
arms (Sonnet 4.6, Gemini 3.1 Pro, DeepSeek V4 Pro added):

| Component                           | Estimate |
| ----------------------------------- | -------- |
| Sonnet 4.6-temporal (91 runs)       | ~$140    |
| Gemini 3.1 Pro-temporal (91 runs)   | ~$45     |
| DeepSeek V4 Pro-temporal (91 runs)  | ~$50     |
| Judge passes for the three new arms | ~$240    |
| **Follow-on total**                 | **~$475** |

Cumulative v3 spend at full five-arm grid: ~$1,055 — comparable to a
single-arm v1/v2 budget cycle, because the temporal arm reuses the same
extractor and judge configuration. Each extension is a separate
explicit-funding decision.

---

## 13. v3 lock recipe

```
pre_registration.v3.lock.methodology_hash =
    sha256(
        DESIGN.md
      + PROMPTS.md
      + RUBRIC.md
      + MULTI_VENDOR_ADDENDUM.md
      + TEMPORAL_NOISE_ADDENDUM.md
    )

Reproducible:
    python3 -c "import hashlib; print(hashlib.sha256(b''.join(
        open(f, 'rb').read()
        for f in [
            'DESIGN.md','PROMPTS.md','RUBRIC.md',
            'MULTI_VENDOR_ADDENDUM.md','TEMPORAL_NOISE_ADDENDUM.md'
        ]
    )).hexdigest())"
```

`materials_lock_hash` is unchanged from v1/v2
(`c13b5514279c9d8dbc5118ec9b3b1325a0cff56c4fb1cee8d66992a98cd25199`) — same
peer/target materials, no rehash. `materials_temporal_lock_hash` is **new**
and pins the temporal pool plus the temporal distractor file plus the
noise-screening log:

```
materials_temporal_lock_hash =
    sha256(materials/materials_temporal.lock.json file bytes)

with materials_temporal.lock.json containing:
  - all files under materials/noise/temporal_msft/MSFT/ (34 .txt files,
    attainable corpus per §3.1c: 2 prior 10-Ks, 9 prior 10-Qs,
    23 prior earnings-call transcripts; 991,380 tokens total)
  - materials/ground_truth/MSFT_temporal_distractors.json (added once
    authored — §14)
  - materials/noise_screening_log.md (added once authored — §14)
  - re-listing of materials/target/MSFT/{10k.txt, earnings_call.txt}
    (sha + token_count, identical to materials.lock.json — included for
    self-containment so the temporal lock is independently verifiable)
```

**v0.2 lock state (2026-05-05):** materials_temporal.lock.json written
with the 34-file noise pool + the target re-listing (36 entries total).
Distractor file and screening log are §14 open items; their addition
will produce a v0.3 of the temporal lock (the methodology hash is
unaffected — they're materials, not methodology).

The v3 pre-registration lock JSON references both lock files explicitly:

```json
{
  "$schema_version": "3.0",
  "version_lineage": {
    "supersedes": null,
    "extends": "pre_registration.v2.lock",
    "extends_hash": "3433f4a67cde4b24b92a1b41a78271aa5dbb4572beb2ee23e1d8c2c31d189e8e",
    "rule": "v3 = v2 + TEMPORAL_NOISE_ADDENDUM.md. v1 and v2 lock files are unchanged. v1 and v2 arms remain valid evidence under v3 by inheritance — the addendum only ADDS scope (admits a second noise type and a noise-type-conditional question disambiguation suffix), it does not change the v1/v2 task, materials, prompts, rubric, design grid, extractor, or judge configuration."
  },
  "methodology_files": [
    "DESIGN.md","PROMPTS.md","RUBRIC.md",
    "MULTI_VENDOR_ADDENDUM.md","TEMPORAL_NOISE_ADDENDUM.md"
  ],
  "methodology_hash": "<computed at lock time>",
  "materials_lock_path": "materials/materials.lock.json",
  "materials_lock_hash": "c13b5514279c9d8dbc5118ec9b3b1325a0cff56c4fb1cee8d66992a98cd25199",
  "materials_temporal_lock_path": "materials/materials_temporal.lock.json",
  "materials_temporal_lock_hash": "<computed at lock time>",
  "v1_arms_inheritance": { /* same as v2 lock */ },
  "v2_arms_inheritance": {
    "rule": "Arms locked under v2 (pre_registration.hash = 3433f4a6…) are valid evidence under v3 without re-locking.",
    "arms_grandfathered_under_v2": ["gpt-5-5","gemini-3-1-pro","deepseek-v4-pro"]
  }
}
```

---

## 14. Open items (lock before pilot)

**Material acquisition (all SEC- or IR-public; no copyright friction):**

- [x] FY2024 and FY2023 MSFT 10-Ks retrieved from EDGAR; SHA-256s recorded in `materials_temporal.lock.json`.
- [x] Nine prior MSFT 10-Qs retrieved from EDGAR (FY2025 Q1–Q3, FY2024 Q1–Q3, FY2023 Q1–Q3); SHA-256s recorded.
- [x] 23 of 41 prior MSFT earnings-call transcripts retrieved (see §3.1c for the source-availability ceiling). 18 specs unobtainable from any indexed transcript source; the spec'd 41-call target is documented for diff-clarity but not reachable without first-party Microsoft transcript publication.
- [x] `build_materials.py` extended with `--noise-type temporal_msft` flag (and `--allow-partial`) producing the `.txt + .meta.json` pairs under `materials/noise/temporal_msft/MSFT/`.

**Methodology surface:**

- [ ] Hand-screen of all 34 temporal-pool files against MSFT FY2025 ground-truth values (§3.3, including the §3.1b restated-comparator wrinkle); `noise_screening_log.md` written and SHA recorded.
- [ ] `MSFT_temporal_distractors.json` authored with per-period source tags (period, source-doc, line item, value, restatement-version-if-applicable).
- [ ] §4.2 disambiguation suffix wired into `assemble_prompt` behind the `noise_type == "temporal_msft"` branch. Smoke-verify by re-assembling a v2 cell (peer noise) and SHA-comparing the prompt against the on-disk v2 raw record — must match byte-for-byte.
- [ ] `scope_cap.py` extracted from existing grading code (current behavior preserved); §5.2 extended cap rule added; `grading_module_hash` recorded.
- [ ] Noise sampler updated to draw across the three subpools (10-K / 10-Q / call) at the §3.1 ratios; deterministic seed extended with `noise_type` (peer seed unchanged, see §10).

**Lock and verification:**

- [ ] `harness/config/arms/{gpt-5-5,opus-4-7}-temporal.yaml` authored, `noise_type: temporal_msft` set, `pre_registration_hash` set to the v3 hash.
- [ ] `pre_registration.v3.lock` written; SHA reproducible per §13 recipe.
- [x] `verify_v3_isolation.py` (new in v0.2) confirms `materials.lock.json` bytes unchanged and all 11 v1/v2 files byte-identical to lock. Run it to validate v3 isolation against v1/v2.

**Pilot gating (per §6.4) before full grid:**

- [ ] 3-cell × 7-rep pilot run on each priority arm (~$90 total).
- [ ] Go/no-go criteria evaluated: parse rate ≥ 98%, ICC ≥ 0.70 on Tier-3, realized fill within ±500 tokens of target at all three pilot cells, `pool_utilization_pct ≤ 0.90` at the 95-cell, pilot cost within 2× projection.
- [ ] On no-go: iterate pool composition or §4.2 suffix wording, increment addendum minor version, re-hash, document in `methodology_hash_history`.

---

## File map

- `TEMPORAL_NOISE_ADDENDUM.md` — this document.
- `pre_registration.v3.lock` — v3 hash + materials lock pointers (created at lock time).
- `materials/materials_temporal.lock.json` — temporal corpus lock.
- `materials/noise/temporal_msft/MSFT/*` — 34 `.txt` + `.meta.json` pairs (2 prior 10-Ks, 9 prior 10-Qs, 23 prior earnings-call transcripts; v0.2 attainable corpus per §3.1c). The aspirational v0.1 spec was 52 files; the gap is documented.
- `harness/scripts/fetch_temporal_sources.py` — acquisition driver (EDGAR + Motley Fool live + AlphaStreet live + Wayback Machine).
- `harness/scripts/_wayback_known_captures.json` — manifest of Wayback snapshot timestamps used as fallback when live providers are rate-limited.
- `harness/scripts/verify_v3_isolation.py` — invariant checker: confirms v1/v2 lock + locked files are byte-identical post-v3.
- `materials/ground_truth/MSFT_temporal_distractors.json` — temporal distractor list per ground-truth value.
- `materials/noise_screening_log.md` — hand-screen findings.
- `arms/{base}-temporal/` — per-arm data directory (created when each temporal arm is locked).
- `harness/config/arms/{base}-temporal.yaml` — per-arm config override.
- `harness/src/grading/scope_cap.py` — extracted scope-adherence cap module (extended for temporal).
