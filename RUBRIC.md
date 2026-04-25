# Judge rubric — full anchors (v2.1)

Companion to `DESIGN.md` and `PROMPTS.md`. Canonical reference for the LLM
judge and anyone auditing the scoring.

**v2.1 changes** (see Versioning at bottom):
- Judge model = Opus 4.7 with xhigh extended thinking (was Sonnet 4.6).
  Justification: this is a within-model drift study, not a cross-model
  benchmark, so same-family judging does not introduce bias.
- Judge now has access to the FULL target materials (10-K + earnings call)
  via a cached system block. Anchors remain the breadth guide; materials are
  the groundedness source of truth.
- Aggregation: single pass per response (was median-of-3). xhigh thinking
  collapses per-call variance; Opus intelligence is the reliability
  substrate. Triple-pass was replaced by cross-model Sonnet subsample.
- New scoring surface: `reasoning_quality` (0-10 holistic gestalt).
- New Q8-only structural diagnostics: `units_decomposed`,
  `frameworks_applied`, `synthesis_consistent`.
- Anchor schema extended with `engagement_signals` and `not_engagement` —
  deterministic cues for what counts as "engaged."

---

## Grading philosophy (read this first)

Financial analysis contains two kinds of claims, graded differently:

**Verifiable facts** — disclosed figures, named events, segment attributions.
These have ground truth. Binary right/wrong. Tier 1 (factual) and Tier 2
(calculation) questions are entirely in this category and are graded
**automatically** against a ground-truth key, not by the judge.

**Grounded judgments** — forecasts, strategic assessments, causal claims,
competitive positioning. These are *conditional on belief-assumptions*;
reasonable analysts reach different conclusions from the same disclosures.
They have **no ground-truth verdict**. Tier 3 (synthesis) questions fall
here and are graded by the judge on **process**, not verdict.

### What the judge grades for Tier 3

- Did the analyst engage with the material disclosures a sound analysis
  would engage with? (evidentiary breadth)
- Are their factual claims traceable to real disclosures? (groundedness)
- Are evaluative claims supported by cited evidence, regardless of whether
  the verdict matches any reference view? (grounded judgment)
- Did they avoid misattributing peer company data to Microsoft? (scope)
- Is the analysis readable, coherent, internally consistent? (clarity)
- Do citations resolve to the correct sections? (citation accuracy)

### What the judge does NOT grade

- Whether the conclusion matches any predetermined "right answer."
- Whether the POV is assertive or hedged.
- Whether a different analyst might reach a different conclusion from the
  same evidence.

This distinction is what makes the drift measurement clean. A response that
says "MSFT's subscription business is well-positioned" and one that says
"MSFT's subscription business is vulnerable to agent-era disruption" both
score high on groundedness **if they cite real MSFT disclosures to support
their view**. What we penalize is: fabricated evidence, missed material
disclosures, misattribution of peer data.

---

## Evidentiary anchors (replaces "rubric points")

For each Tier 3 question, the ground-truth key contains a list of
**evidentiary anchors** — specific material disclosures a sound analysis
should engage with. Anchors are **disclosures that exist in the target
materials**, not conclusions the analyst must reach.

Each anchor is a tuple:

```json
{
  "anchor_id": "MSFT-S-01-a",
  "summary": "MD&A discussion of AI-infrastructure capex pressure on gross margin",
  "citation_span": "Item 7, MD&A, Cost of Revenue and Gross Margin",
  "source": "10-K" | "earnings_call"
}
```

A response **engages with** an anchor if it surfaces at least one of the
anchor's `engagement_signals` (v2.1). Signals are concrete, deterministic
cues specific to each anchor; they remove judge discretion about what
counts as engagement. Example:

```json
{
  "anchor_id": "MSFT-S-03-a",
  "summary": "DEMAND — cloud contracts. Commercial RPO $625B, ~45% OpenAI...",
  "citation_span": "Earnings call (Q2 FY2026), Amy Hood prepared remarks...",
  "source": "earnings_call",
  "engagement_signals": [
    "mentions commercial RPO or backlog figure in the $500-700B range",
    "mentions OpenAI share of Azure commitments (~45%) or non-OpenAI RPO growth (~28%)",
    "references multi-year commitment visibility / duration extension (~2.5y)"
  ],
  "not_engagement": "generic 'Azure is growing' statements with no contract-disclosure reference"
}
```

**Engagement does not require agreement.** A response saying "AI capex
pressures margins, which is bearish" engages the same anchor as one saying
"AI capex pressures margins, which is an acceptable cost for long-term
positioning." Both surface the same disclosure; both score on breadth.

---

## Scoring surface

Per Tier 3 candidate response, the judge produces:

- **Five Likert scores** (1–5), one per dimension (§3–§7).
- **Two programmatic counts** (integers): `unsupported_claims`,
  `cross_contamination`.
- **One overall reasoning-quality score** (0–10 integer, gestalt — §8).
- **Q8-only structural diagnostics** (only on `MSFT-S-03`; omitted for
  `MSFT-S-01` and `MSFT-S-02` — §9).
- **One short justification** (2–3 sentences).

Tier 1/2 are auto-graded; this rubric does not apply to them.

---

## Dimension 1 — Groundedness

*Every factual or evaluative claim is traceable to real evidence.*

For a factual claim ("operating income was $X"): traceable means the value
matches an anchor or a disclosure reasonably covered by the anchor set.

For an evaluative claim ("the company faces margin pressure from X"):
traceable means the supporting evidence is cited and real. The *verdict*
("this is bearish" vs "this is acceptable") does not affect groundedness —
only the evidence foundation does.

| Score | Anchor |
|-------|--------|
| 5 | Every substantive claim rests on cited evidence that maps to an anchor or a disclosure clearly inside the target materials. No fabrications. Evaluative claims surface the evidence behind them. |
| 4 | At most one substantive claim lacks a clear evidentiary trace, but is plausibly compatible with disclosed material. |
| 3 | Several substantive claims lack evidentiary grounding; the analysis mixes well-grounded observations with unsupported assertions. |
| 2 | The majority of substantive claims are ungrounded. Fabrication or pure speculation dominates. |
| 1 | The response appears to fabricate disclosures wholesale or reach conclusions with no evidentiary trace. |

**Counted as "unsupported":** specific numeric claims not in materials;
attributions to named executives / business decisions not disclosed;
period-over-period claims without disclosed data; competitive claims
sourced from outside the materials.

**NOT counted as "unsupported":** evaluative verdicts drawn from cited
disclosures; explicitly labeled assumptions ("assuming AI value accrues to
application layer..."); standard analytical framings.

---

## Dimension 2 — Evidentiary breadth

*The analysis engages with the material disclosures a sound analyst should notice.*

Let `A` = number of anchors in the ground-truth key (typically 4–6 per question).

| Score | Anchor |
|-------|--------|
| 5 | Engages ≥ 80% of anchors (A=4: all 4; A=5: 4 or 5; A=6: 5 or 6). |
| 4 | Engages 60–79% of anchors. |
| 3 | Engages 40–59% of anchors. |
| 2 | Engages 20–39% of anchors. |
| 1 | Engages 0–19% of anchors. |

"Engaged" = response surfaces the substance of the anchor's disclosure,
regardless of verdict reached.

An analyst who engaged 5 of 6 anchors and hedged their conclusion
out-scores one who engaged 2 anchors and reached a confident verdict.

---

## Dimension 3 — Scope adherence

*No misattribution of peer-company data to Microsoft.*

Reframed from v1.1: the bar is no longer "don't mention other companies."
Real analysis of Microsoft naturally references Alphabet (Gemini), Amazon
(AWS), Anthropic (Claude), etc. as competitive context. That's not a scope
failure; it's realism.

What is a scope failure: attributing facts, numbers, or disclosures from a
peer document to Microsoft. Example: citing Alphabet's $400B revenue or
Amazon's AWS capex as Microsoft's.

| Score | Anchor |
|-------|--------|
| 5 | All factual claims about Microsoft trace to Microsoft's materials. Peers may appear as competitive context but their data is never attributed to MSFT. |
| 4 | One borderline moment — an ambiguous phrasing where a peer figure is mentioned near a MSFT claim, but context makes attribution clear. |
| 3 | At least one peer fact is attributed to Microsoft, though the analysis is otherwise MSFT-focused. |
| 2 | Multiple peer facts are attributed to Microsoft, or the response uses peer data to support MSFT-specific conclusions. |
| 1 | A substantial portion of claims about Microsoft are actually sourced from peer documents. |

**Hard fail → `cross_contamination` count:** every specific peer figure
attributed to MSFT increments `cross_contamination` by 1. A
`cross_contamination ≥ 1` caps `scope_adherence` at 3.

Mentioning Anthropic's Claude as a competitor to Microsoft Copilot is NOT
a scope failure even though Anthropic isn't in the target materials — this
is legitimate competitive context. What would be a failure: citing
Claude's pricing as if it were Microsoft's.

---

## Dimension 4 — Clarity / coherence

*The analysis is readable and internally consistent.*

| Score | Anchor |
|-------|--------|
| 5 | Well-structured; the reasoning from evidence to conclusion is visible and logically consistent. Easy to extract the thesis and its support on first read. |
| 4 | Well-organized overall; minor structural awkwardness or mild redundancy. |
| 3 | Readable but disorganized. Claims and evidence are present but not clearly connected. |
| 2 | Structure is confusing; important claims are buried; reasoning is hard to follow. |
| 1 | Incoherent, self-contradictory, or not meaningfully readable. |

**Length-neutral.** A terse but complete answer can score 5; a long
rambling answer can score 2.

**Internal consistency matters.** A response that cites "revenue +15%" and
then concludes "revenue is declining" loses points here, not on
groundedness.

---

## Dimension 5 — Citation accuracy

*Citations resolve to real sections of the target materials.*

The judge DOES have access to the full 10-K and earnings call via the
cached TARGET MATERIALS system block (v2.1). Citations are verified by
locating the cited Item / section / footnote / speaker turn directly in the
materials, with the anchor `citation_span` list as a convenience index.

| Score | Anchor |
|-------|--------|
| 5 | All citations present and match anchor `citation_span` fields (correct Item, section, note, or speaker/turn). |
| 4 | All citations present; ≥ 80% match anchor spans. One may be partially right (correct section, wrong subsection). |
| 3 | Citations present but 40–80% match. Some point to wrong sections. |
| 2 | Citations present but < 40% match. Most point to wrong places. |
| 1 | Citations missing, fabricated, or point to locations that don't exist. |

No citations at all → score 1 (score range is 1–5).

---

## Programmatic counts

### Unsupported-claims count (integer ≥ 0)

Substantive factual claims not traceable to any anchor or disclosure
clearly inside the target materials. Substantive = specific values, named
events/decisions, attributions, period-over-period claims.

Evaluative verdicts that rest on cited evidence are NOT unsupported claims.
Explicitly-labeled assumptions ("if X holds...") are NOT unsupported.

### Cross-contamination count (integer ≥ 0)

Substantive claims that attribute peer-company data to Microsoft. Counted
even if the judge can't locate the exact peer source — if the value clearly
isn't MSFT's, it counts.

---

## Dimension 6 — Reasoning quality (0–10 holistic, v2.1)

*Gestalt judgment — counting on model intelligence.*

The five Likert dimensions decompose the response into diagnostic failure
modes. This sixth score is **holistic**: a single integer 0–10 that answers
"how good is the reasoning, overall?" It is NOT a mechanical composite —
the judge may weight dimensions differently based on the specific response.

Anchor points:

| Score | Meaning |
|-------|---------|
| 10 | Expert-level: senior-analyst output, nothing to fix. |
|  8 | Strong: minor weakness in one dimension. |
|  6 | Solid-but-gapped: material shortfall in rigor, breadth, or evidence. |
|  4 | Partial: meaningful gaps or superficial treatment. |
|  2 | Poor: fabrication, key evidence missed, framework absent. |
|  0 | Failed: refusal, off-topic, incoherent. |

The judge is explicitly directed to **use the full 0–10 range** and not
cluster at 7. Opus 4.7 with xhigh extended thinking is the reliability
substrate for this score (v2.1 philosophy: "we are counting on the model's
intelligence").

This is the **headline score** for drift measurement. The five Likerts
remain diagnostic (they tell us *where* drift appears); `reasoning_quality`
is the primary outcome variable.

---

## Dimension 7 — Q8 structural diagnostics (MSFT-S-03 only, v2.1)

Q8 explicitly mandates a **DECOMPOSE → APPLY 4 FRAMEWORKS → SYNTHESIZE**
structure. The judge reports three additional fields on MSFT-S-03 only
(omitted for MSFT-S-01 and MSFT-S-02). These are diagnostic, not part of
the headline composite; they let us see *which* part of the Q8 structure
drift breaks first.

### `units_decomposed` (int ≥ 0)

How many distinct revenue units the response treats as **economically
different**, not just name-dropped. Expected units pool: Azure cloud
services, Server products, Microsoft 365 Commercial cloud, LinkedIn,
Dynamics 365, Windows OEM, Gaming, Search and news advertising.

A unit counts when the response includes at least one per-unit economic
observation (demand shape, margin structure, competitive position, growth
driver). Superficial mentions ("MSFT has Gaming") do not count.

Target for a well-structured response: ≥ 5.

### `frameworks_applied` (int 0–4)

Of `{demand, complementarity, substitution, supply_constraint}`, how many
the response **explicitly applies** to at least one unit. A framework is
"applied" when the response:

1. Names the framework OR names its mechanism, AND
2. Connects it to a specific revenue unit.

Example — framework applied: "Azure benefits from complementarity with AI
agents: each agent call consumes inference on Azure, so agent deployment
drives Azure consumption." Example — framework NOT applied: "AI changes
everything for Microsoft."

Target: 4.

### `synthesis_consistent` (bool)

Does the final thesis resolve unit-level views without contradicting its
own per-unit analyses? Example of inconsistency: response argues M365 is
durable due to data-graph moat in unit-level section, then concludes
overall thesis that "AI-native productivity tools will replace M365" in
synthesis — without reconciling.

### Interaction with the five Likerts

- `units_decomposed < 3` or `frameworks_applied < 2` ⇒ `evidentiary_breadth`
  on Q8 drops by 1 (automatic; judge applies this in their scoring).
- `synthesis_consistent = false` ⇒ `clarity` on Q8 drops by 1.

These cross-links keep Q8 structural failures visible in the main
dimension scores without requiring a bespoke Q8 composite.

---

## Aggregation rules (v2.1)

### Per-response composite

For exploratory visualization only (primary analysis uses individual
dimensions plus `reasoning_quality`):

```
likert_composite = mean(groundedness, evidentiary_breadth, scope_adherence, clarity, citation_accuracy)
```

Primary hypothesis tests use **`reasoning_quality`** (0–10) as the headline
outcome variable, with individual dimensions as diagnostic decomposition.
The five Likerts tell us *where* drift appears; reasoning_quality tells us
*how much* drift there is.

### Per response

**One judge call per response** (v2.1 change from triple-median).
Justification:
- xhigh extended thinking collapses per-call stochasticity to near zero,
  so median-of-3 smoothing adds little information.
- Triple-pass would cost ~$1,150 for Opus-xhigh grading; single-pass is
  ~$380 and fits the pilot budget.
- Cross-model Sonnet subsample (below) replaces self-consistency as the
  reliability diagnostic.

If the pilot reveals high single-pass variance on a dimension, we re-judge
that dimension across all responses with 3 passes and take median. This is
a fallback, not the default.

### Judge-model agreement

On the 20% Opus+Sonnet dual-judged subsample:

- ICC (2,1) per dimension (including `reasoning_quality`).
- ICC < 0.70 on a dimension ⇒ that dimension is flagged as
  low-reliability; analysis relies on pairwise comparison rather than
  absolute scores.

Sonnet is the secondary not because it is better — it is cheaper and
structurally different. The point is cross-model rubric-application
consistency, not an appeal to higher authority.

---

## Edge cases

- **Empty or null response:** all dimensions = 1; both counts = 0.
- **Valid JSON but `"answer": "OUT_OF_SCOPE"` for a legitimate tier-3
  question:** instruction-following failure. Score: groundedness=1,
  evidentiary_breadth=1, scope_adherence=5, clarity=3, citation_accuracy=1.
  Flag `refused_in_scope_question=true`.
- **Answers a different question:** score as a complete miss (1s). Flag
  `off_topic=true`.
- **Quotes anchor language verbatim without having seen the anchor list:**
  treat as correct (anchors are not shown to the analyst). Convergent
  framing is evidence of genuine engagement.
- **Confident verdict grounded in cited evidence:** high groundedness,
  even if the verdict differs from a reference view. Analysts disagree;
  this is expected.
- **Hedged summary that engages all anchors but reaches no conclusion:**
  high evidentiary_breadth, high groundedness, possibly lower clarity if
  the hedging obscures the reasoning. Not penalized for stance.
- **Assumption-explicit argument:** ("if AI value accrues at the
  application layer, then MSFT's Copilot positioning is vulnerable")
  treated as maximally grounded on groundedness — the assumption is
  labeled, and the implication is traceable to the assumption plus cited
  evidence.

---

## Versioning

- `v1.0` (2026-04-24) — initial pre-registered rubric.
- `v1.1` (2026-04-24) — DESIGN v0.2 sync; AI-impact Q8 addendum.
- `v2.0` (2026-04-24) — process-not-verdict rubric. Q8 addendum
  generalized to all Tier 3 questions. `rubric_points` renamed to
  `evidentiary_anchors`. Scope-adherence loosened from "no peer mentions"
  to "no peer misattribution." Added Grading Philosophy preamble.
- `v2.1` (2026-04-24) — Opus 4.7 judge with xhigh thinking; judge sees
  full target materials via cached system block. Added `reasoning_quality`
  (0-10 holistic gestalt) as headline outcome. Added Q8-only structural
  diagnostics (`units_decomposed`, `frameworks_applied`,
  `synthesis_consistent`). Anchor schema extended with
  `engagement_signals` and `not_engagement`. Single-pass judging replaces
  triple-median (xhigh thinking supplies reliability).
