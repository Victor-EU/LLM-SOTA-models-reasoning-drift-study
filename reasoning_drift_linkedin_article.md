# Five frontier reasoning models. Five different ways to fail under context pressure.

Every frontier reasoning model on the market right now ships with roughly a one-million-token context window. Anthropic's Opus 4.7 and Sonnet 4.6, OpenAI's GPT-5.5, Google's Gemini 3.1 Pro, and DeepSeek V4 Pro all advertise it. The marketing pitch is consistent across vendors: stop worrying about what to put in your prompt, dump in every document that might be relevant, let the model figure out what matters.

The unstated assumption underneath that pitch is that filling the window is free — that the model uses the millionth token as well as it uses the first. Over the last few months I ran a controlled experiment across the five models above to test that assumption. 455 total runs, byte-identical inputs at every coordinate, held-constant judges, only the analyst model varying across arms. About $1,860 in spend. The short answer: filling the window is not free, the costs are real and measurable, they vary by roughly an order of magnitude across vendors, and they don't take the shape you'd intuit. The longer answer is the rest of this article.

## 1. The short version

The conventional wisdom on long context goes something like this: as the window fills with adjacent material, all reasoning models degrade in roughly the same shape. Performance falls. Hallucinations rise. The bigger model holds up better. Throw more thinking at the problem and most of the drift goes away.

That picture didn't survive contact with the data.

The five models produced five qualitatively distinct drift signatures. Identical inputs. The largest Anthropic model expanded its thinking by 87% under load and lost ground anyway. The smaller Anthropic model used five to ten times more thinking and was the only one in the panel whose quality actually *recovered* at 95% fill. OpenAI's GPT-5.5 contracted its thinking under pressure and stayed essentially hallucination-free across every fill level. Google's Gemini held a flat line at a lower ceiling but ran fifteen times faster than Sonnet. DeepSeek looked rock-solid on absolute scoring and turned out to be the steepest pairwise loser in the study.

There is no single "long-context degradation curve" to plan around. Each vendor has its own. The right deployment question isn't "which model wins?" — it's "which failure mode can my product absorb?" The headline number on the vendor spec sheet — "1M context window" — tells you what fits. It tells you almost nothing about what each model does with the back half of that window once you actually fill it. That gap, between advertised context and usable context, is the risk this study measured.

## 2. What each model does, and what to do about it

**Claude Opus 4.7.** Top of the panel on baseline reasoning quality (8.05 out of 10). Also the steepest absolute decline in the Anthropic family by 95% fill (−1.03), and the worst pairwise loser other than DeepSeek (loses 18 of 20 head-to-head against its own baseline). The defining failure is what I'd call evidentiary erosion. The structure of the answer holds together — sections, frameworks, decomposition all stay intact — but the actual claims start losing their grounding. Unsupported claims rise sevenfold. It's the only model in the panel with non-trivial cross-contamination — peer-company financials attributed to the target company at roughly 5× the next-worst arm (Sonnet) and infinitely more than the other three (which sit at zero). The strangest finding here: Opus expands its thinking budget by 87% under load and gets worse anyway. More work, weaker answer.

1. **Trust factual extraction at any fill.** If your task is "find a specific number, quote, or fact in a long document corpus," Opus 4.7 with max thinking is robust. Zero factual errors and zero Tier-1/2 cross-contamination across 455 records spanning 13–92% context fill.

2. **Keep context tight for evidence-heavy synthesis.** The drop from baseline to 25% fill alone costs about 0.7 points of reasoning quality and doubles unsupported claims. If your task requires the model to *reason from* the source (financial analysis, legal interpretation, policy synthesis), pulling in extra "potentially relevant" material is a measurable quality hit.

3. **Position the target last when possible.** The `end` position (target after noise) outperformed `start` and `middle` at every fill level. If you have to include peripheral material, append the target *after* it.

4. **Max thinking is not a defense against context drift on synthesis.** The model thought about 2× more at 95% fill than at baseline and still scored about 1 point lower. More thinking compensates partially but not fully.

5. **Variance is a leading indicator of drift.** At 47% fill, sd doubled (0.58 → 2.25) before the mean stabilized — the model becomes *unpredictable* before it becomes consistently worse. Monitor variance across reps if you're pushing context limits.

6. **Form is not content.** The model will faithfully follow your prompt scaffolding (decompose, apply frameworks, structure output) under pressure. That can mask declining evidence quality. If you rely on structural compliance as a quality signal, you'll miss this drift.

**Claude Sonnet 4.6.** The only model in the panel that wins pairwise against its own baseline at 95% fill (+2.3 mean delta, 13 of 20 wins). Quality follows an inverted-U: starts at 7.43, climbs to 8.00 at 25% fill, dips through the middle, recovers to 7.60 at 95%. The price you pay is wall clock. Sonnet at max thinking uses 18.6K reasoning tokens per call at baseline, five to ten times what Opus uses at the same setting, and runs 12 to 15 minutes per call. The full 91-run sweep took about seven hours even with four cells running in parallel. The recovery is bought with the thinking budget. If you trim the budget to make latency tolerable, you trim the property that makes the model valuable.

1. **Sonnet is the value pick on this workload.** Same Tier-1/2 perfection as Opus, comparable Tier-3 quality (mean RQ 7.19–8.00 across all fills), 10% lower total arm cost ($522.96 vs $582.33), and a flatter drift curve. Analyst spend alone was 35% lower ($217 vs $334).

2. **Don't fear high fill — Sonnet may actually improve with it.** At 95% context fill, Sonnet won 65% of pairwise comparisons against its own baseline (13 wins, 7 losses, 0 ties on the 25% subsample). The "1M context degrades reasoning" rule of thumb is empirically inverted here.

3. **Budget tokens for thinking — Sonnet at max is verbose.** Mean thinking allocation is 13.8K–18.6K tokens per call (5–10× Opus on the same prompts), pushing total output near 45K. Set `max_output_tokens` to 65,536 or higher; the default 32K caused `stop_reason=max_tokens` truncations during baseline smoke tests.

4. **Trust Sonnet for grounding under noise.** Cross-contamination at 95% fill is 0.02/response (vs Opus's ~0.10, a 5× gap), and unsupported claims at 95% are 1.06 (vs Opus's 1.68). Sonnet anchors more tightly to whatever you mark as the explicit target block in your prompt.

5. **The drift curve is an inverted-U, not monotonic.** RQ peaks at 25–50% fill (8.00 / 7.94), dips at 75% (7.19), recovers at 95% (7.60). Total swing is only 0.81 points — smaller than within-cell sd of 1.2–2.2. The robust finding is the *absence* of monotonic decline, not specific per-cell magnitudes.

6. **Plan for long wall-clock latency and streaming-error handling.** Sonnet at max effort runs 5–15 minutes per call and surfaced a streaming-retry bug (`httpx.RemoteProtocolError` after 5.7 minutes) that earlier retry classifiers didn't catch. Long-running synthesis pipelines need explicit streaming-error recovery, not just request-level retries.

**GPT-5.5.** Baseline reasoning quality 7.05 falling to 6.27 by 95% fill, in a flat-then-cliff shape: stable through about 70% fill, then drops. What makes this model different from everything else in the panel is hallucination behavior. Unsupported claims stay essentially zero across all five fill levels (0.00 to 0.05 per response). Cross-contamination — peer-company data attributed to the target — is exactly zero across all 91 runs. GPT-5.5 also contracts its thinking under load on three signals at once: reasoning tokens down 35%, output volume down, latency down 33%. The model is doing measurably less work as the window fills, and the work it does stays disciplined to the evidence. Forty-two percent cheaper than Opus for the same task.

1. **Trust citation-anchored synthesis at any fill — this is the no-hallucination model.** Unsupported claims rise from 0.00 to only 0.05 per response across the 13–92% fill range (about 33× lower than Opus's 1.68 at 95% fill). Cross-contamination is exactly zero across all 91 runs at every fill level.

2. **Position the target *after* the noise — the same direction as Opus, but with a sharper penalty for the wrong choice.** At 95% fill, the `start` position drops a full point (5.48 vs 6.67 for both middle and end). GPT-5.5 weights recent context more heavily during response generation.

3. **Expect *less* reasoning under load, not more.** xhigh thinking allocation contracts 35% as fill grows (9,669 → 6,289 tokens), latency drops 33% (168s → 113s), and output volume falls — three signals moving the same direction. If your workload pushes context, set lower expectations on reasoning depth and consider explicit step-by-step prompting to compensate.

4. **The drift profile is flat-then-cliff.** RQ holds within 0.16 points of baseline through 72% fill, then drops 0.62 points between 72% and 92% (variance also doubles from sd 0.79 to 1.67 at the cliff). Operate freely below 75% fill; budget for a step-change above it.

5. **Don't assume "less context is always better."** At 75% fill, GPT-5.5 *won* 11 of 18 pairwise comparisons against its own baseline (+0.8 mean delta), while Opus lost 17 of 18 at the same fill. Moderate noise can supply useful comparative anchors for some synthesis tasks.

6. **Accept lower absolute reasoning depth in exchange for discipline.** GPT-5.5's Tier-3 RQ ceiling is about 7.05 at baseline vs Opus's 8.05 — you're choosing roughly 1 point less depth in exchange for ~30× fewer fabrications. For most production agents that's the right trade.

**Gemini 3.1 Pro.** Lowest absolute drift in the panel (−0.30), but the explanation isn't flattering. Baseline reasoning quality is only 5.86, meaningfully below Anthropic and OpenAI at every fill level. The drift is small because the ceiling is low. Where Gemini dominates is latency: about 56 seconds per call at vendor-max thinking, three times faster than Opus, GPT-5.5, and DeepSeek, and roughly fifteen times faster than Sonnet. The full 91-run sweep finished in 28 minutes. Hallucinations are flat-elevated. Cross-contamination is zero. Position effects don't follow a clean rule, so the standard "put the target last" heuristic doesn't transfer.

1. **Latency is the dominant deployment factor.** Gemini runs 51–62 seconds per call across all fills — 3× faster than Opus / GPT-5.5 / DeepSeek (~142–200s) and roughly 15× faster than Sonnet (~822s). Latency only grows from 53s to 57s across an 8× input expansion (sub-linear scaling).

2. **The drift curve is the flattest of any arm — context fill is not your main quality concern.** RQ moves only 0.35 points across the 13–92% fill range (5.86 baseline → 5.51 bottom at 75%). Variance stays tight (sd ≤ 0.93 except for a 75%-fill spike to 1.38).

3. **The baseline ceiling matters more than the drift.** Gemini's baseline RQ (5.86) sits a full point below GPT-5.5 and over two points below Opus. Gemini under no noise is still meaningfully below Opus under heavy noise — pick the model whose baseline matches your task, because the gap doesn't close.

4. **Force granular decomposition explicitly in the prompt.** Q8 decompositions averaged only 4.5–5.0 units per response (vs Opus's 8.6–9.4 and GPT-5.5's 7.2–8.6). Gemini defaults to top-level segmentations rather than drilling into product lines. Explicit instructions like "decompose by product line, not segment" are required to get parity with the other arms.

5. **Citation accuracy is the lowest of the v2 arms.** Mean citation accuracy ranges 3.65–4.00 (vs GPT-5.5's 4.37–4.95). Prompt explicitly for quote-precision ("Quote the exact phrase you're citing"). Unsupported claims also peak higher than peers, hitting 0.79 at 75% fill.

6. **Log the API-returned `model_version`, not the requested string.** Requested `gemini-3-pro-preview` was server-resolved to `gemini-3.1-pro-preview` on every call. Always capture observed aliases in your run records — the alias can change underneath you between sessions.

**DeepSeek V4 Pro.** The most methodologically interesting arm and the cheapest at $2.14 per call. Absolute reasoning quality drift is essentially zero (−0.09), which on its own would lead you to conclude DeepSeek is the most context-robust model in the panel. Pairwise comparison tells the opposite story: −4.1 mean delta at 95% fill, 16 losses out of 17 — the steepest in the study. Same 91 runs, opposite conclusion, depending on which evaluation methodology you use. The reconciliation is variance. DeepSeek's per-rep responses have very high spread, so absolute means stay stable across reps while pairwise judgments cleanly separate the two responses being compared. Single-shot calls are much less informative than for any other arm in the panel.

1. **Parse analyst output deterministically — never chain a second LLM as a normalizer.** DeepSeek's analyst-side Tier-1 hit rate is 100%, but Haiku 4.5 deterministically failed to reformat 7 of 91 reps (7.7% measurement loss) despite valid analyst JSON. Use regex, pydantic, or structured-output mode directly. (Compare extractor failure rates: Opus 1.1%, Sonnet 1.2%, GPT-5.5 0%, Gemini 0%, DeepSeek 7.7%.)

2. **Don't trust absolute Likert scoring for this model — use pairwise.** DeepSeek shows the flattest absolute drift in the study (RQ 5.33 → 5.24, Δ = −0.09) but the steepest pairwise loss (−4.1 mean delta at 95% fill, 1 win / 16 losses / 0 ties out of 17 pairs). Absolute scoring averages out within-rep noise; pairwise exposes it. If you only run absolute Likerts, you'll silently miss the drift.

3. **Run more reps — within-cell variance is the highest of any arm.** Baseline sd is 2.31 on a 0–10 RQ scale (vs Opus 0.58, GPT-5.5 0.74). A single DeepSeek response is much less informative than a single response from any other arm; aggregate at least five calls and take the median or majority vote for production decisions.

4. **The position rule flips with fill: `start` for ≤50%, `end` for ≥75%.** At 25% fill, `start` scores 6.24 vs `end` 4.38 (a 1.9-point gap); at 95% fill, `end` scores 5.67 vs `start` 4.81. The within-cell start/end gap at 25% is larger than the entire RQ drop seen across all fills in any other arm.

5. **Cost is the headline.** Analyst-stage spend was $14.47 vs Opus's $334 (96% reduction). Total arm cost was $194.54 at *list* pricing; actual paid was about $50 during the 75%-off promo window. Latency (160–199s) is comparable to Opus and GPT-5.5.

6. **Cross-contamination isn't the failure mode here — internal inconsistency is.** Zero cross-contamination across all 91 runs. But DeepSeek is the only arm where baseline `synthesis_consistent` falls below 100% (86% at baseline; only 6 of 7 baseline reps had internally consistent multi-step syntheses). Frameworks-applied scores average 3.4–3.8 out of 4 (vs Opus and GPT-5.5 holding at 4.0). Validate output structure, not just citations.

## 3. Practical takeaways for agent builders

**Pick the failure mode you can absorb, not the leaderboard winner.** Each of these five models occupies a distinct point on the cost-quality-latency-reliability frontier. No model is dominated. No model is universally best. The honest decision criterion for production deployment is which of these five failure shapes your product can tolerate, and which one would break it.

**"Max thinking" is not a portable knob across vendors.** When you flip the same flag on different vendors, you get wildly different reasoning-token budgets. Sonnet at max uses 18.6K. Opus at max uses 2.4K. Same vendor, same flag, 7.7× spread. If you're A/B testing across vendors and keeping "thinking on" as the constant, you are not running a controlled comparison. Normalize on reasoning-token budget if you want fair numbers.

**Don't reflexively throw more context at the problem.** GPT-5.5 contracts its thinking by 35% as your context fills. Opus expands its thinking by 87% and gets worse anyway. The pattern of "stuff more documents in, get a better answer" is wrong for reasoning models. Context engineering — what you put in, what you leave out — matters more than tuning the thinking budget.

**Evaluate with pairwise comparisons, not just absolute scores.** This is the single most important methodological lesson from the study. If you only score outputs on a 0–10 scale and take the mean across reps, you will miss real drift on high-variance models. DeepSeek looks rock-solid on absolute scoring and falls off a cliff on pairwise. Same data, opposite conclusion. Use both metrics, and be skeptical of any vendor benchmark that only publishes one.

**Keep LLMs out of your extractor layer when you can.** Seven percent of DeepSeek's "Tier-1 failures" in this study turned out to be Haiku-the-extractor failing to reformat valid JSON from the analyst. Pydantic, structured output mode, deterministic regex — anywhere the contract allows. Putting an LLM in your normalization pipeline adds a silent failure surface that's hard to debug after the fact.

**Same vendor does not mean same behavior.** Two Anthropic models, same training family, same `effort=max` flag, opposite responses to context pressure. Opus expands thinking. Sonnet contracts. There is no vendor-coherent "thinking strategy" you can reason about at the family level. Don't generalize from one model in a vendor's lineup to its siblings.

## 4. The data and methodology

Five arms, one analyst model per arm. 91 runs per arm. 455 total runs. Held constant across every arm: the source materials (Microsoft's FY2025 10-K plus the Q2 FY2026 earnings call as the target, seven peer 10-Ks from Apple, Google, Amazon, Meta, Nvidia, Oracle, and Salesforce as the noise corpus), the eight-question stimulus (three factual lookups, two calculations, three open-ended synthesis), the extractor (Claude Haiku 4.5), the primary judge (Claude Opus 4.7 at max thinking), the secondary judge (Claude Sonnet 4.6 at high thinking), the design grid (one baseline plus five fill levels times three positions times seven repetitions per cell), and the per-cell seeds.

The choice of materials was deliberate, against the alternative many academic long-context studies prefer: a sterile adversarial design like a math problem buried in art-history paragraphs, or a needle-in-a-haystack with random Wikipedia sentences as filler. Those designs maximize internal control, but they test the wrong distribution. Production agents almost never see radically off-topic noise. A financial analyst agent reads peer filings. A legal research agent reads adjacent case law. A medical agent reads similar studies. The noise that matters in deployment is near-domain noise — material that shares vocabulary, narrative structure, and the kinds of numbers the target uses, and that therefore plausibly competes for the model's attention rather than being trivially ignored. Peer 10-Ks against an MSFT 10-K hit that property exactly. They share terminology, format conventions, and actual numerical values that a model could mistakenly attribute to Microsoft. That last property is what makes the cross-contamination finding diagnostic in the first place. Opus pulling peer financials and presenting them as MSFT's would never surface in a math-plus-art-history setup, because no one would ever attribute Caravaggio dates to a calculus problem. The 10-K choice also exercises factual retrieval, numeric calculation, evidence-grounded reasoning, and forward-looking synthesis in a single document genre, so one corpus produces the blended workload that production agents actually run. The tradeoff is more measurement ambiguity than a pristine adversarial setup would give. The gain is findings you can deploy against.

Realized fill levels were 13%, 24%, 47%, 72%, and 92% by Anthropic's tokenizer count. Cross-arm prompts are byte-identical at every (cell, rep) coordinate, proven via SHA-256 of the materials lockfile. Vendor-actual token counts differ from the labeled fill percentages because the four vendors use different tokenizers — that's a known caveat, not a confound, since the bytes are identical going in.

Vendor-max thinking knobs were Anthropic `effort=max`, OpenAI `reasoning.effort=xhigh`, Google `thinking_level=HIGH`, DeepSeek `reasoning_effort=max`. The actual reasoning-token allocation under those flags varied from 2.4K (Opus) to 18.6K (Sonnet) — a 7.7× spread. "Vendor-max" is not a comparable compute setting across vendors, and any cross-arm comparison should be read as "each model at its own top setting" rather than "matched compute."

Three layered integrity gates back the comparison. A pre-registration lock pins the methodology hash. An arm lock per model pins the analyst snapshot, the extractor, both judges, and a SHA-256 manifest of every output file. The cross-arm comparison script refuses to run unless every arm declares the same methodology hash, the same materials hash, and the same extractor and judge configuration. All five arms currently pass.

Total spend: $1,859.66. Opus 4.7 was the most expensive arm at $582. DeepSeek was the cheapest at $194 using list pricing — actual paid was lower under a 75%-off promo that closed in early May 2026. Per-call costs ranged from $2.14 (DeepSeek) to $6.40 (Opus) at constant 91 runs, constant judges, constant materials.

Honest limitations: single target company, single noise corpus, both judges from the Anthropic family (cross-vendor judging is the obvious follow-up), and seven repetitions per cell — adequate for direction but tight for variance estimation, especially on the high-variance arms. The pairwise-vs-absolute gap analysis is qualitatively robust but a tighter quantification would want more reps. None of the limitations changes the headline finding that the five arms produce five qualitatively distinct drift profiles. They do constrain how confidently you should generalize each per-model finding to your own deployment domain.

If you've gotten this far and you're building agents on top of these models, the practical lesson worth internalizing is the methodological one: stop letting absolute Likert scores be the final word on long-context behavior. Pairwise comparisons, hallucination-specific metrics, and per-position breakouts will all tell you things that single-number quality scores hide.
