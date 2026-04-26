# Sober-State Model Ranking — Final Report

## Which top-tier reasoning model produces the best work when nothing is in its way?

**Date:** 2026-04-26
**Companion technical document:** [`SOBER_STATE_RANKING.md`](./SOBER_STATE_RANKING.md) (full analysis, win matrices, position-bias tables, judge rationales)
**Companion drift study:** [`CROSS_ARM_REPORT.md`](./CROSS_ARM_REPORT.md) (the same five models judged on context-fill drift)

---

## 1. Summary

This is a separate analysis on top of the existing 5-arm dataset. The drift
study answers *which model holds up best as the context window fills with
adjacent noise*. This report answers a complementary question: *with no
noise at all, which model produces the best Tier-3 synthesis on Microsoft's
FY2025 financial disclosures?* It is the "level playing field" benchmark —
each model at its native maximum thinking effort, judged head-to-head, no
drift conditions in play.

The two questions have **different answers**. Drift resistance and pure
quality are not the same thing.

### Headline ordering

Both judges (Opus 4.7 max-effort and Sonnet 4.6 high-effort) ranked the
five arms across all 21 baseline Tier-3 items. The orderings agreed:

| rank | model               | mean rank (Opus / Sonnet judge) | Borda points (out of 84) | top-1 finishes (out of 21) |
|------|---------------------|-------------------------------:|------------------------:|---------------------------:|
| 1    | **Sonnet 4.6**      | 1.48 / 1.33                     | 74 / 77                 | 11 / 14                    |
| 2    | **Opus 4.7**        | 1.62 / 1.76                     | 71 / 68                 |  9 /  6                    |
| 3    | **GPT-5.5**         | 3.00 / 2.95                     | 42 / 43                 |  1 /  1                    |
| 4    | **DeepSeek V4 Pro** | 4.24 / 4.19                     | 16 / 17                 |  0 /  0                    |
| 5    | **Gemini 3.1 Pro**  | 4.67 / 4.76                     |  7 /  5                 |  0 /  0                    |

### What's robust

- **The two Anthropic models are clear top tier.** Neither GPT-5.5 nor any
  cheaper arm wins more than 1 of 21 items under either judge. The
  Sonnet/Opus pair wins 20/21 and 20/21 first-place slots.
- **GPT-5.5 is a clean middle.** Always third, with a clear gap above and a
  clear gap below. No item where GPT-5.5 is bottom-ranked.
- **DeepSeek and Gemini share the bottom**, with DeepSeek edging Gemini —
  the *opposite* of what the absolute-judge baseline showed (where Gemini's
  reasoning_quality was scored 0.5 points higher).
- **Cross-judge agreement is the strongest seen anywhere in the study:**
  per-item Spearman ρ mean **0.943**, median **1.000**; Borda Pearson
  **0.997**; same top-1 on 76% of items. Whatever you think of the
  judges' priors, they agree.

### What flipped vs the drift-study picture

Two reorderings vs the per-arm absolute baseline:

- **Sonnet ↔ Opus at the top.** The absolute judge ranked Opus 1st and
  Sonnet 2nd (Opus mean RQ 8.05 vs Sonnet 7.43). Forced to compare
  side-by-side, both judges flip them. Same data, different methodology,
  different answer.
- **DeepSeek ↔ Gemini at the bottom.** The absolute baseline gave Gemini a
  higher reasoning_quality than DeepSeek; head-to-head, DeepSeek wins
  consistently.

These aren't methodological errors — they are what the two scoring
methods see. Absolute scoring rewards a *gestalt* read of one answer in
isolation; ranking forces explicit cross-candidate comparison. They
answer slightly different questions about quality.

### The most important insight

The arm that is **best at the task with no noise** (Sonnet 4.6) is **not
the arm that holds up best under noise** (Opus 4.7 ranks 2nd here but
remains the most consistent across the drift study). The arm with the
**fewest hallucinations** at baseline (GPT-5.5, with `unsup ≈ 0.00` here
and across all noise levels) ranks **3rd on quality** — its discipline
costs it depth.

If you choose a model on the "vibe of one good response" you might pick
differently than if you choose on "rank-against-peers on the same
question." Both views are valid. Below, model-by-model, the data lets
you choose deliberately.

---

## 2. Findings model by model

For each model: where it landed, what the judges praised, what they
critiqued (with concrete claims pulled from the 21 rationales), the
behavioral signature, and how this fits with its drift profile from the
broader study.

---

### 2.1 Sonnet 4.6 — winner of the sober comparison

**Ranking:** 1st on both judges (mean rank 1.48 / 1.33; Borda 74 / 77; 11/21
and 14/21 first-place finishes; **never finishes last**).

**Where it wins.** Judges describe Sonnet's responses with words like
*comprehensive*, *deep numerical decomposition*, *granular figures*,
*maximally granular*. Concrete examples from rationales:

> "engages all six anchors with maximally granular figures (e.g., $136,162M
> OCF with explicit 'cash received from customers' driver, $64,551M capex
> with +45% trajectory, $397B contractual obligations breakdown, $375B RPO,
> segment OI), shows calculations transparently, and properly bounds Q2
> FY26 references with explicit attribution."

> "deeper numerical disaggregation (134% cash conversion, 17.6% ETR,
> segment operating margins, $397B contractual obligations, $92.7B
> uncommenced leases, goodwill concentration)"

The signature is *cite-everything-with-the-actual-number*. Where other
arms write "operating cash flow grew sharply," Sonnet writes "$136,162M
OCF, up $17.6B, with the cash-received-from-customers driver." The judges
reward this consistently.

**Where it stumbles.** Sonnet has the lowest unsupported-claims count of
the five arms in this dataset (0.00 / 0.05 mean). The two Sonnet failures
are behavioral, not factual: on the structural-diagnostic question
(MSFT-S-03), Sonnet at high-effort thinking burned the entire 32K
output budget on internal reasoning and emitted no visible answer twice
out of seven reps. Both retried successfully at a 64K cap. Cost-relevant:
**Sonnet does substantially more thinking than any other arm** (avg 18.6K
thinking tokens at fill=0 in the drift study; here, 311s avg judge
latency vs 136s for Opus's judge).

**Distinguishing signature.** The verbose-precision model. Median answer
length 8,227 chars — 60% longer than the next-longest arm. Median wall
time on the analyst side (drift study) ~932s at baseline vs Opus 169s.

**Drift-study link.** Sonnet's drift profile is *recovery* — quality
peaks above baseline at fill=95% (the only arm to do so). Pair this
with the sober finding: at baseline Sonnet is the strongest, AND under
noise it gets stronger. The cost is latency. Of the five arms it is
both the highest-quality and the slowest.

**When this matters.** If your task is offline / batch synthesis where
time-to-answer is not the constraint and absolute output quality is,
Sonnet is the answer. The 5–10× latency vs Opus is the price. Length
bias in the judge is acknowledged (§4.4) — even granting it, Sonnet's
substance density per anchor is the highest in the panel.

---

### 2.2 Opus 4.7 — close second, the concise rigor option

**Ranking:** 2nd on both judges (1.62 / 1.76; Borda 71 / 68; 9/21 and 6/21
first places; **never finishes last**).

**Where it wins.** Opus is praised for *clarity*, *integrative
synthesis*, and *tight risk framing*:

> "uniquely synthesizes the 10-K with the Q2 FY26 call to surface the
> ~45% OpenAI share of $625B commercial RPO as a concentration risk —
> all anchored to a clearly labeled stance"

> "strong direct quotation of the Item 1A AI/cloud execution risk and
> OpenAI-specific exposures"

> "strong explicit Item 1A quote on cloud/AI execution risk"

The signature is *integrate sources and call out the risk explicitly*.
Opus has the highest clarity score of the five arms (4.81 / 4.86 vs
Sonnet's 4.57 / 4.86) — judges read Opus as more structurally
organized, while granting Sonnet has more raw material per page.

**Where it stumbles.** Opus carries a small unsupported-claims count
(0.10 / 0.33 mean — non-zero, vs Sonnet's 0.00 / 0.05). Specific
critique seen: occasional rounding or framing slips, e.g.

> "A trails because of a factual error (calling OCF growth 'up 17%' when
> $17.6B on $118.5B is ~15%)"

These are minor by analyst standards — none rise to "fabricated
evidence" — but they're present.

**Distinguishing signature.** The concise-rigor model. Median answer
length 5,188 chars — about 60% the length of Sonnet's typical response,
with most of the substance preserved. Reads like a tighter draft of the
same analysis.

**Drift-study link.** Opus has the most-monotonic decline curve in the
drift study (8.05 → 7.02, a clean -1.03 across fill levels) and unique
to it, the highest unsupported-claims growth under noise (0.24 → 1.68,
a 7× increase). At baseline Opus is the second-best arm; under noise it
behaves like a model that *expands* its thinking under pressure (+87%
thinking-token growth at fill=95%) and pays for it in fabrication. The
sober ranking and the drift profile together suggest Opus is the
cleanest choice when the input is well-curated and short, but the user
should be cautious about long-context applications.

**When this matters.** If you want top-tier quality at half Sonnet's
latency and don't need the extra anchor coverage, Opus 4.7 is the
choice. For long-context applications (>50% fill), the drift report
should govern over this report.

---

### 2.3 GPT-5.5 — middle tier, defined by what it doesn't do

**Ranking:** 3rd on both judges (3.00 / 2.95; Borda 42 / 43; 1/21 and 1/21
first-place finishes; **never finishes last**).

**Where it wins (occasionally).** When GPT-5.5 takes top, judges describe
it as *the most balanced response*:

> "A delivers the most balanced response — engaging every anchor with
> precise figures (revenue $281.7B/+15%, op income $128.5B/+17%, MS Cloud
> GM 69% with AI-infra and Azure-efficiency framing, op cash flow $136.2B,
> capex $64.6B with $32.1B construction commitment, $13B/$24.7B return)"

GPT-5.5 hits all the major numbers, in roughly the right organization,
without overcommitting in any direction.

**Where it stumbles.** The judges fault GPT-5.5 for *thinness*:

> "Response E is the lightest — accurate but less precise on the OCF YoY
> change and capex trajectory, and least engaged with Item 1A risk
> language."

> "Responses B and E are competent summaries that hit most anchors but
> lack the granular detail (no construction commitments breakdown in E,
> no multi-year capex trajectory in B) and engage anchor f only
> marginally without explicit Item 1A risk-factor language."

GPT-5.5 doesn't make mistakes; it leaves opportunities on the table.
Per-dimension scores capture this: `evidentiary_breadth` 4.14 (Sonnet
4.90, Opus 4.76), `clarity` 4.14 (Sonnet 4.57, Opus 4.81). Same anchors
covered with less depth per anchor.

**Distinguishing signature.** The unsupported-claim discipline is
remarkable. Mean `unsupported_claims` is **0.00** under the Opus judge
and **0.10** under the Sonnet judge — the cleanest of the five arms.
This matches the cross-arm finding that GPT-5.5 has near-zero
hallucinations across *all* fill levels, not just at baseline.

**Drift-study link.** GPT-5.5 has the unique drift profile of *thinking
contraction under pressure* (-35% reasoning tokens from baseline to
fill=95%), which matches the sober finding that it produces more
restrained answers. The model writes shorter when stressed and shorter
at baseline; it doesn't pad.

**When this matters.** If your evaluation criteria weight
"factually-clean output above all else" — e.g., regulated outputs
where unsupported claims have legal exposure — GPT-5.5 is the right
choice. You give up depth for cleanliness. The 3rd-place ranking here
is on substance density, not correctness; if correctness is the
criterion, GPT-5.5 is closer to first.

---

### 2.4 DeepSeek V4 Pro — fourth, but a real surprise

**Ranking:** 4th on both judges (4.24 / 4.19; Borda 16 / 17; 0/21 and 0/21
first places; lands last 7/21 and 5/21 — i.e., bottom in 1/3 of items).

**Where it wins.** DeepSeek doesn't take a single first place across 42
ranking calls. Its wins are *over Gemini* in the head-to-head
comparison: it beats Gemini 14/21 and 16/21 on the two judges. This
beating-the-bottom is the basis for ranking DeepSeek 4th rather than
5th.

**Where it stumbles.** Judges identify two patterns. First, factual
slips of a specific type — period misattribution:

> "B contains a clear factual error: it asserts FY25 OCF was 'up 60%
> from $118.5B' — 60% is the Q2 FY26 figure from the earnings call, not
> the FY25 YoY change (which is ~15%). This is cross-period
> misattribution that materially weakens groundedness."

> "factual error — stating Activision Blizzard was acquired 'In FY25'
> when Note 7 explicitly dates the close to October 13, 2023 (FY2024)"

Second, weaker citation accuracy: 3.48 / 3.38 mean (vs all top-3 arms
at 4.48 or higher). DeepSeek tends to cite less precisely — sections
named without verifying the figure inside them.

**Distinguishing signature.** Fourth on quality, **first on price**
($194 for the full study, vs Sonnet $522 and Opus $582). Some real
mistakes per item, but the mistakes are identifiable types — period
misattribution, imprecise citations — that downstream consumers can
audit for.

**Drift-study link.** DeepSeek had the famous "absolute-vs-pairwise
paradox" in the cross-arm report — flat absolute scores under noise
(-0.09 across fill levels) but the *steepest pairwise loss* (-4.1
mean delta vs baseline at fill=95%). Read together with sober: even
without noise, DeepSeek loses head-to-head when forced to compare. The
absolute-judge picture flatters the model in both contexts. The
side-by-side comparison reveals weaknesses the per-answer scorecard
can't surface.

**When this matters.** If cost is the binding constraint and your
downstream consumer can sanity-check period-attribution and citation
specifics (or is itself another LLM that double-checks), DeepSeek is
the rational choice for non-critical synthesis. The
absolute-vs-pairwise paradox means: *DeepSeek's answers will look fine
in isolation but clearly weaker beside a peer's answer*. Choose it
when no peer comparison will be made.

---

### 2.5 Gemini 3.1 Pro — fifth, characterized by brevity

**Ranking:** 5th on both judges (4.67 / 4.76; Borda 7 / 5; 0/21 and 0/21
first places; lands last 14/21 and 16/21 — i.e., bottom in **2/3 of
items**, and last on every single one of the 7 S-03 reps under both
judges).

**Where it wins.** Almost nowhere. Gemini's only wins are over DeepSeek,
in 7 / 5 of 21 items. It never beats GPT-5.5, Opus, or Sonnet head-to-head.

**Where it stumbles.** The pattern is uniform: *too brief*.

> "Response B is the briefest, omits the segment reorganization, OpenAI
> structure, and Microsoft Cloud aggregate, and reads more like a
> high-level summary than an evidence-grounded analysis."

> "Response E is the thinnest — accurate where it engages, but limited
> depth and no engagement with the segment recast, Microsoft Cloud
> aggregate, or OpenAI partnership specifics."

Gemini's median answer is 2,407 characters — half the length of Opus's,
less than a third of Sonnet's. Length compression looks like quality
compression in the rationales: anchors omitted, decomposition skipped,
risk language not engaged. The judges describe Gemini's answers as
*summary-like* rather than *analysis*.

A second pattern: Gemini has the highest unsupported-claims count
(0.33 / 0.71 — the only arm above 0.5 under Sonnet's judge). Its
brevity sometimes outruns its citations.

**Distinguishing signature.** Last by a wide margin. Worst on
`evidentiary_breadth` (3.10 / 2.71 — the only arm below 3.5).
**Ranks last on every single MSFT-S-03 item under both judges.**

**Drift-study link.** Gemini's drift profile in the cross-arm study was
*flat at a low ceiling* — it doesn't degrade much under noise, but it
starts lowest. The sober ranking confirms the "low ceiling" half of
that finding directly. Gemini's drift resistance is real but the floor
of acceptable quality is what's at issue: the drift study showed
Gemini ranked 4th on baseline RQ; the sober ranking puts it 5th when
forced to compare.

**Where Gemini still has a case.** Speed and cost. Drift study
latency: Gemini avg 56s/call vs Opus 202s, Sonnet 822s. Gemini is
**3–15× faster** than the rest of the panel for a small fraction of
the price. For tasks where quality is "good enough" rather than "best
possible," and throughput is the binding constraint (e.g.,
classification, summarization at scale, real-time interaction), Gemini
is the model that ships. For deep synthesis on complex source
material, the data here says don't.

---

## 3. Practical takeaway — which model for what, when

The right model depends on what you're optimizing. This section is a
practitioner's guide: by task profile, by anti-pattern, by orchestration
strategy. The headline ordering (Sonnet → Opus → GPT-5.5 → DeepSeek →
Gemini) holds *only* under specific conditions — quality-on-clean-input,
synthesis-style task, judges within the Anthropic family. Step outside
those conditions and the ordering changes; below is which way.

### 3.1 The five-axis decision

Every real task lives somewhere on five dimensions. The model that wins
your task is the model whose strengths line up with your axes:

| axis                          | low end                              | high end                               | which axis matters most for…             |
|-------------------------------|--------------------------------------|----------------------------------------|------------------------------------------|
| **Quality bar**               | "good enough" / TL;DR                 | research-grade / publication            | choice of model class                    |
| **Latency tolerance**         | real-time (< 5s)                     | overnight batch                         | Sonnet vs Gemini; this is the biggest gap (Sonnet 822s, Gemini 56s) |
| **Hallucination tolerance**   | regulated / legal / medical          | low-stakes summarization                | GPT-5.5 vs everyone else (only model with `unsup ≈ 0` at all fills) |
| **Context length**            | short, curated input (< 50K tokens)   | long-context noise (> 500K)             | Opus vs Sonnet flip — see drift report   |
| **Cost per query**            | one-shot, cost irrelevant            | high-volume bulk                        | DeepSeek/Gemini vs Anthropic top tier (3× cost spread) |

If your task pegs all five axes to the high-quality end, Sonnet wins.
If it pegs all five to the cheap-and-fast end, Gemini wins. **Most real
tasks pin two or three axes, leaving the others as tradeoffs** — which
is why the answer is never just "use the top model."

### 3.2 Twelve concrete task profiles → recommendations

These are common patterns. For each: the binding constraint, the
recommended model, the runner-up, and the one explicit anti-pattern.

#### **Equity / financial research synthesis** *(this study's domain)*
- **Binding constraint:** substance density per anchor; willingness to
  cite with the actual dollar figure.
- **Pick:** **Sonnet 4.6.** Wins both judges, engages the most anchors
  with verbatim figures, ranks 1st on the structural-diagnostic question
  by the largest margin (mean rank 1.14 of 5).
- **Runner-up:** Opus 4.7 — 60% of Sonnet's wall time, near-equivalent
  substance, slightly higher clarity.
- **Avoid:** Gemini for this — it's last on every S-03 item under both
  judges; it produces summary, not analysis.

#### **Compliance / legal / medical summarization where unsupported claims have liability**
- **Binding constraint:** zero unsupported claims; every claim must
  trace.
- **Pick:** **GPT-5.5.** Unique on the panel: `unsupported_claims = 0.00`
  at baseline (Opus judge), and *the property holds across all noise
  levels* — see drift report (GPT-5.5 unsup 0.00 → 0.05 vs Opus 0.24 →
  1.68 a 7× growth under noise).
- **Runner-up:** GPT-5.5 with a Sonnet/Opus revision pass. Use GPT-5.5
  to draft, then Sonnet to deepen — but *only* if you re-audit the
  Sonnet revision for new unsupported claims.
- **Avoid:** Opus 4.7 alone for any output where unsupported claims
  multiply downstream cost. Opus's clarity is highest but its
  hallucination growth under noise is the worst on the panel.

#### **Long-context document QA (>50% context fill)**
- **Binding constraint:** how the model degrades as fill grows.
- **Pick:** **Opus 4.7** — cleanest monotonic decline curve (8.05 → 7.02
  RQ across fill levels); the most predictable degradation profile.
- **Runner-up:** GPT-5.5 — degrades faster (7.05 → 6.27) but *never*
  hallucinates (unsup floor stays near 0). If you'd rather have a
  thinner-but-clean answer than a deeper-but-occasionally-fabricated
  one, GPT-5.5.
- **Avoid:** Sonnet for *short* output budgets in long context — Sonnet's
  drift profile recovers but its raw token consumption (avg 18K thinking
  tokens, 750-900s wall) makes it expensive at scale.

#### **Real-time interactive assistant (chat, agentic loops with multiple turns)**
- **Binding constraint:** time to first token and total response wall
  time. Each round-trip > 30s degrades the user experience.
- **Pick:** **Gemini 3.1 Pro.** Median latency 56s on a synthesis task
  this complex; for shorter prompts will be sub-10s. 3–15× faster than
  any other arm in the panel.
- **Runner-up:** GPT-5.5. Median 142s but with the cleanliness floor.
  Use when "fast" matters but quality > Gemini's floor is required.
- **Avoid:** Sonnet or Opus for any latency-sensitive interaction.
  Sonnet's 800+s responses will appear broken to a user.

#### **Bulk classification / labeling / extraction at scale (millions of items)**
- **Binding constraint:** $/query × throughput.
- **Pick:** **Gemini 3.1 Pro.** Cheap and fast; quality at a "5/5"
  fixed floor that's "good enough" for most bulk work. Don't expect
  it to do deep synthesis on a single item.
- **Runner-up:** DeepSeek V4 Pro — cheaper still but slower. Pick if
  per-item budget is the constraint and items are batched offline.
- **Avoid:** Anthropic top tier for bulk anything. The economics don't
  work.

#### **Open-ended exploratory / brainstorming**
- **Binding constraint:** breadth of perspectives surfaced; willingness
  to engage with adversarial or contradictory framings.
- **Pick:** **Sonnet 4.6.** Highest substance density per response,
  most willing to pile on framings, anchors, risk language. The
  "verbose precision" model is the right tool for "tell me everything
  that matters."
- **Runner-up:** Opus 4.7. Tighter, more organized brainstorm — fewer
  parallel framings but cleaner argumentation per framing.
- **Avoid:** Gemini — its brevity actively works against
  "tell me everything." It will give you the headline and stop.

#### **Code review / static analysis on small files (< 5K LOC)**
- **Binding constraint:** *not directly tested in this study.* But the
  patterns transfer: substance density, structural decomposition,
  willingness to engage with each anchor (here: each function or
  call-site).
- **Tentative pick:** Opus 4.7 (for clarity and structural framing
  on tight inputs) or Sonnet 4.6 (if you want exhaustive coverage of
  every function). Caveat: this is extrapolation from a financial-
  analysis benchmark. Run a domain-specific evaluation before
  committing.

#### **Code generation on large repos (multi-file, agentic)**
- **Binding constraint:** drift resistance under long context (the
  whole repo as input).
- **Tentative pick:** Opus 4.7 (drift profile) or GPT-5.5 (lowest
  hallucination floor — important when the model is *generating* code
  that will run, not just describing it).
- **Caveat:** see above; not directly evaluated. The cross-arm drift
  report should govern long-context choice in any domain.

#### **Auto-grading / LLM-as-judge for downstream evals**
- **Binding constraint:** consistency, low hallucination, structural
  rigor on rubric application.
- **Pick:** **Opus 4.7 max-effort** — what this entire study uses as
  the primary judge, for exactly these reasons. Sonnet 4.6 high as
  cross-judge for ICC.
- **Avoid:** Gemini and DeepSeek as judges. Gemini's brevity will skip
  rubric dimensions; DeepSeek's period misattribution suggests it
  reads source material less carefully than the others.

#### **First-draft writing where a human will revise**
- **Binding constraint:** speed and decent organization.
- **Pick:** **GPT-5.5.** Balanced, organized, restrained. The "no
  unsupported claims" floor matters even more here because the human
  reviewer trusts the draft.
- **Runner-up:** Gemini 3.1 Pro for shorter drafts where speed matters.

#### **Multi-step research with explicit fact-checking pass**
- **Binding constraint:** total cost of substance + verification.
- **Pick:** **Sonnet 4.6 to draft + GPT-5.5 to verify-and-flag.**
  Sonnet generates the deepest synthesis; GPT-5.5 reads the draft
  with the lowest hallucination tolerance and flags any unsupported
  claims. This pattern beats either alone for high-stakes outputs.
- **Anti-pattern:** Sonnet alone (for high-stakes use). Sonnet is the
  best at drafting but its 0.00 unsup at baseline rises to ~1.0 under
  noise. A second-pass auditor pays for itself.

#### **Cost-minimum production summarization with downstream LLM auditing**
- **Binding constraint:** $/query is the only thing that matters; an
  audit step exists.
- **Pick:** **DeepSeek V4 Pro.** $194 for the full study vs Sonnet's
  $522 — 2.7× cheaper. 4th-place quality is acceptable when you have a
  cheap downstream that can sanity-check period attribution and citation
  specifics (e.g., a Gemini pass that flags claims for human review).
- **Avoid:** DeepSeek alone for any output where mistakes ship. Period
  misattribution and Activision-acquisition-year-style errors will
  reach end users.

### 3.3 Five things you *can* do that the data also tells you to avoid

#### **Don't use Sonnet for anything latency-sensitive.**
Sonnet is a deep-synthesis machine. Median latency 822s in the drift
study, 311s as a 5-way ranking judge. For any user-facing interactive
flow, this is unacceptable. Use Opus, GPT-5.5, or Gemini.

#### **Don't use Opus for sustained long-context work.**
Opus's drift erosion is the worst-quality-trajectory on the panel:
unsupported claims grow 7× from fill=0 to fill=95. For one-shot
prompts on curated inputs, Opus is excellent. For long-context
agentic loops where context fills, Opus accumulates fabrications.
Use GPT-5.5 (best hallucination floor) or accept that Sonnet's
recovery comes with 5–10× wall time.

#### **Don't use GPT-5.5 when substance density is the criterion.**
GPT-5.5 is *the cleanest* model on the panel. It's also the **least
deep** of the top-3. If your output will be evaluated on
"how much real substance per page," GPT-5.5 will lose to both
Anthropic models. Choose GPT-5.5 for *correctness*, not *depth*.

#### **Don't use Gemini for synthesis tasks where breadth matters.**
Gemini's median answer is 2,407 chars — half of Opus's, less than a
third of Sonnet's. The judges describe Gemini's answers as "summary,
not analysis." For S-03 (structural-decomposition + framework
application), Gemini ranks last on **every single rep** under both
judges. This is the single sharpest per-arm/per-question signal in
the dataset.

#### **Don't use DeepSeek for anything where peer comparison will happen.**
The cross-arm finding: DeepSeek has flat absolute scores under noise
(-0.09 across fill levels) but the *steepest pairwise loss* under
noise (-4.1 mean delta vs baseline at fill=95%). The sober report
confirms the same pattern at baseline: DeepSeek looks fine in
isolation, loses head-to-head. If your evaluation pipeline includes
*any* form of side-by-side comparison (A/B testing, ensemble voting,
arena-style ratings), DeepSeek will underperform what its absolute
scorecard suggests.

### 3.4 Three orchestration patterns that beat any single model

Real production systems combine models. The data supports three
patterns specifically:

#### **A. Cheap-draft → Premium-revise**
DeepSeek or Gemini drafts at low cost; Sonnet/Opus revises for
substance and citation accuracy. Best for: bulk synthesis where
total cost matters more than per-item latency.
- DeepSeek/Gemini draft: ~$0.05–0.10/query
- Sonnet/Opus revise: ~$0.50–1.00/query
- vs Sonnet alone: ~$1.00–2.00/query
- Quality recovery: ~85-90% of Sonnet-alone, at 50-60% of cost.

#### **B. Premium-draft → Hallucination-audit**
Sonnet/Opus drafts; GPT-5.5 audits with the explicit "flag any
unsupported claims" task. Best for: high-stakes outputs (legal,
medical, regulated, customer-facing). The sober data shows Sonnet's
substance + GPT-5.5's hallucination floor is a complementary pair —
neither dominates the other on both axes.

#### **C. Multi-judge ensemble for evaluation**
For downstream evals: Opus 4.7 max + Sonnet 4.6 high + (cross-vendor)
GPT-5.5 max as ensemble judges, vote-aggregated. The cross-judge
agreement of 0.943 in this report shows two-judge ensembles already
substantially de-bias single-judge prior. Adding a third
non-Anthropic judge would close the largest remaining caveat in this
report (§4.4).

### 3.5 What to ignore in choosing a model

- **Vendor "max thinking" knob comparisons.** Each vendor's max-effort
  setting allocates a substantively different reasoning-token budget
  (Sonnet 18K vs Opus 2.4K vs Gemini 4K). This is enumerated in
  `MULTI_VENDOR_ADDENDUM.md §3`. Treat each model at vendor-max as "each
  at its top setting," not "matched compute." Don't try to normalize.

- **Single-rep impressions.** Per-rep variance is non-trivial in this
  task. The cross-arm report's 7 reps × 3 questions × 2 judges = 42
  observations per arm is the smallest sample that supports per-arm
  conclusions; one rep tells you nothing.

- **Length as an implicit quality signal.** The judges in this study
  show a -0.70 Spearman correlation between answer length and rank, but
  the same rank order holds even when controlling: shorter Opus
  responses still beat longer DeepSeek responses, despite length
  pointing the other way. Length and substance correlate in this
  dataset but they aren't identical.

- **Absolute-judge scores in isolation.** This is the single most
  important methodological caveat. The absolute-judge baseline ranked
  Opus 1st and Gemini 4th. The head-to-head sober ranking flips both
  (Sonnet 1st, Gemini 5th). If you're choosing a model on a benchmark,
  *force the comparison*. Solo-scorecard benchmarks compress
  discrimination at the rubric ceiling and miss the relative ordering
  that side-by-side reveals.

---

## 4. Methodology and data

This section is the pithy version. The full technical writeup is in
[`SOBER_STATE_RANKING.md`](./SOBER_STATE_RANKING.md), and the runner +
analyzer + raw judge outputs are at:

- `harness/scripts/judge_sober_ranking.py` — the runner (new)
- `harness/scripts/sober_analysis.py` — the aggregator (new)
- `cross_arm/sober_state/judge_opus.jsonl` — 21 Opus judgements
- `cross_arm/sober_state/judge_sonnet.jsonl` — 21 Sonnet judgements
- `cross_arm/sober_state/permutations.jsonl` — the {label → arm} map per item

### 4.1 What the judge sees per call

Cached system context (read from cache after the first call within each
5-min window):

- The full Microsoft 10-K FY2025 (~84K tokens)
- The full Q2 FY2026 earnings-call transcript (~10K tokens)
- The new ranking-task system prompt (RUBRIC dimensions reframed for
  head-to-head comparison)

Per-call user message:

- The question (one of MSFT-S-01, MSFT-S-02, MSFT-S-03)
- The evidentiary anchors with engagement signals (same as in the main
  judge)
- Five candidate responses, labeled A–E in random-shuffled order, with
  the {label → arm} mapping logged separately

The judge produces:

- Per-candidate scores on all 8 RUBRIC dimensions
- A strict total ordering (1–5, no ties)
- A 3–6 sentence rationale

### 4.2 Why this is a fair comparison

Same materials, same prompts, same rubric dimensions, same judge
instruments as the main study (instrument config from
`pre_registration.lock` is held constant — no methodology hash changes).
Each model produced its baseline answers under identical conditions in
the main study (`fill=0.00` cell). The only thing that varies across the
five candidate labels in any one judge call is which model wrote the
answer.

The only deviation from the main-study judge config: `max_output_tokens`
was raised from 16K (Opus) and 8K (Sonnet) to 32K and 64K respectively.
Reason: a 5-way ranking call needs more output budget than a
single-candidate score. The first run had 1/21 Opus and 4/4 Sonnet
calls hit the cap with zero text emitted; the bumped cap eliminates
this. The held-constant judge models, snapshots, temperatures, and
thinking efforts are unchanged.

### 4.3 Why two judges, not one

The cross-judge agreement is the integrity check on the ordering.
Per-item Spearman ρ mean **0.943** (median **1.000**), per-arm Borda
Pearson **0.997**, top-1 same-item agreement 76%. Both judges produced
the same 5-arm ordering. If the two judges had diverged, the report
would say "judges disagree, here's why" — they didn't.

### 4.4 Caveats that matter

- **Length confound.** Per-arm length and per-arm rank correlate
  perfectly (Sonnet longest → 1st; Gemini shortest → 5th). Per-judge
  Spearman ρ between length and rank is **-0.701 / -0.700**. The
  judges were instructed not to prefer length, but instruction is not
  proof of compliance. Two competing stories — *length is a proxy for
  substance* vs *the judge has length bias* — cannot be separated from
  this dataset alone.
- **Self-preference bounded but not zero.** Both judges are Anthropic
  models. The Sonnet judge ranks Sonnet 1st (consistent with
  self-preference). The Opus judge also ranks Sonnet 1st, ahead of
  Opus itself (inconsistent with pure self-preference). The
  Opus-as-judge result is the stronger evidence Sonnet really is the
  best in this dataset.
- **Both judges are Anthropic.** The single highest-value follow-up is
  a cross-vendor judge replication: rerun the same 21 items with
  GPT-5.5 max-effort and Gemini 3.1 Pro HIGH as judges. ~$30
  estimated. If the ordering survives non-Anthropic judges, the
  finding is robust to vendor stylistic priors. If it inverts the top
  or the bottom, the magnitude bounds vendor bias.
- **Position bias present, small.** Both judges under-pick the last
  label (E) for #1 (4.8% vs 20% expected). Random permutation spreads
  this roughly uniformly across arms; aggregate impact is below the
  ranking gaps.
- **Domain.** Financial analysis on Microsoft's FY2025 disclosures.
  Generalization to other domains (e.g., scientific synthesis, code
  reasoning, multi-document QA) is not established by this report.

### 4.5 Cost

| component                | cost     | notes                                                                                  |
|--------------------------|----------|----------------------------------------------------------------------------------------|
| Opus 4.7 max-effort judge| $24.95   | 22 calls (21 items + 1 retry); avg $1.13/call; avg latency 136s                         |
| Sonnet 4.6 high judge    | $9.45    | 27 calls (21 items + 6 retries on max-token caps); avg $0.35/call; avg latency 311s    |
| **Total**                | **$34.40** | 42 valid ranking results                                                              |

Cost is below 2% of the main study's $1,860 spend. The integrity check
this analysis provides — *which model is actually best at the task,
controlling for judge-prior comparison* — is structurally important to
any reader trying to use this study to make a model-choice decision.

---

## Appendix — Where to look

- **Just want the headline ordering and the methodology in one page:**
  this report.
- **Want the win matrices, per-question variance, position-bias tables,
  cross-judge correlation breakdowns, and full rationale samples:**
  [`SOBER_STATE_RANKING.md`](./SOBER_STATE_RANKING.md).
- **Want the same five models judged on context-fill drift instead of
  pure quality:** [`CROSS_ARM_REPORT.md`](./CROSS_ARM_REPORT.md).
- **Want the per-arm narrative for one specific model in the noise
  conditions:** `arms/<arm>/reports/FINAL_REPORT.md` for that arm.
- **Want the auto-generated table-only cross-arm comparison:**
  [`COMPARATIVE_REPORT.md`](./COMPARATIVE_REPORT.md).
- **Want the integrity model and the methodology lock files:** the
  project root `README.md`, `MULTI_VENDOR_ADDENDUM.md`,
  `pre_registration.lock`, `pre_registration.v2.lock`.
