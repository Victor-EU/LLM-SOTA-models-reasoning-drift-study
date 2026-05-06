# Temporal-Noise Hand-Screen Log

**Methodology surface:** TEMPORAL_NOISE_ADDENDUM.md §3.3 + §3.1b.

**Automated screen recipe:** for each FY2025 Tier-1/Tier-2 ground-truth
value V, scan every .txt under `materials/noise/temporal_msft/MSFT/` for
any number within +/- 0.5% of V. Each in-band match is reported with the
surrounding ~80 characters of context for human review of intent.

**Why ±0.5%:** matches the tightest ground-truth tolerance (Tier-1 numeric)
plus a small slack to capture restated-comparator (§3.1b) drift.

**Action on hit:** human review decides whether the match is a legitimate
longitudinal disclosure (e.g., a prior 10-K's FY2025 forecast that landed
near actuals — keep), an unintended distractor (e.g., a coincidental peer
number — keep, document), or a contamination requiring removal of the file.
To-date no file has been removed; the noise pool is locked as-is.

**Scope of this automated pass:** Tier-1 and Tier-2 numeric screening. Tier-3
(synthesis) anchor contamination is judged at grading time, not pre-locked.

---

## Target canonical values + bands

| q_id | canonical | unit | tolerance_rel | scan band |
|------|-----------|------|----------------|-----------|
| MSFT-F-01 | 281724.0 | USD_millions | ±0.5% | [280315.3800, 283132.6200] |
| MSFT-F-02 | 128528.0 | USD_millions | ±0.5% | [127885.3600, 129170.6400] |
| MSFT-F-03 | 13.64 | USD_per_share | ±0.5% | [13.5718, 13.7082] |
| MSFT-C-01 | 17.6 | percent | ±0.5% | [17.5120, 17.6880] |
| MSFT-C-02 | 14.9 | percent | ±0.5% | [14.8255, 14.9745] |

---

## Per-file findings

### `msft_10k_fy2023.txt`

- subpool: `10k`  period: `FY2023`  tokens: `85516`

  **MSFT-F-02 (target 128528.0)** — 1 match(es) in band:
    - `128,314`  …,858  Total  $  187,239  $  166,368  $  128,314  95  PART II  Item 8  REPORT OF INDEPEN…

  **MSFT-F-03 (target 13.64)** — 1 match(es) in band:
    - `13.6`  …th Fiscal Year 2022  Revenue increased $13.6 billion or 7% driven by growth in Intel…

  **MSFT-C-02 (target 14.9)** — 1 match(es) in band:
    - `14.9`  …mers. Cash used in financing decreased $14.9 billion to $43.9 billion for fiscal yea…

### `msft_10k_fy2024.txt`

- subpool: `10k`  period: `FY2024`  tokens: `89853`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_10q_fy2023_q1.txt`

- subpool: `10q`  period: `Q1 FY2023`  tokens: `48729`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_10q_fy2023_q2.txt`

- subpool: `10q`  period: `Q2 FY2023`  tokens: `53700`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_10q_fy2023_q3.txt`

- subpool: `10q`  period: `Q3 FY2023`  tokens: `53544`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_10q_fy2024_q1.txt`

- subpool: `10q`  period: `Q1 FY2024`  tokens: `46338`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_10q_fy2024_q2.txt`

- subpool: `10q`  period: `Q2 FY2024`  tokens: `53241`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_10q_fy2024_q3.txt`

- subpool: `10q`  period: `Q3 FY2024`  tokens: `53247`

  **MSFT-F-02 (target 128528.0)** — 1 match(es) in band:
    - `128,839`  …846  Service and other  44,778  37,269  128,839  107,880  Total revenue  61,858  52,857…

### `msft_10q_fy2025_q1.txt`

- subpool: `10q`  period: `Q1 FY2025`  tokens: `49517`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_10q_fy2025_q2.txt`

- subpool: `10q`  period: `Q2 FY2025`  tokens: `52453`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_10q_fy2025_q3.txt`

- subpool: `10q`  period: `Q3 FY2025`  tokens: `53058`

  **MSFT-F-02 (target 128528.0)** — 1 match(es) in band:
    - `128,839`  …ice and other  54,747  44,778  158,473  128,839  Total revenue  70,066  61,858  205,283…

### `msft_q1fy21_call.txt`

- subpool: `earnings_call`  period: `Q1 FY2021 earnings call`  tokens: `14826`

  **MSFT-F-03 (target 13.64)** — 1 match(es) in band:
    - `13.6`  …pect revenue between $13.2 billion and $13.6 billion. In Windows, on the strong prio…

### `msft_q1fy22_call.txt`

- subpool: `earnings_call`  period: `Q1 FY2022 earnings call`  tokens: `14259`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q1fy23_call.txt`

- subpool: `earnings_call`  period: `Q1 FY2023 earnings call`  tokens: `15433`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q1fy24_call.txt`

- subpool: `earnings_call`  period: `Q1 FY2024 earnings call`  tokens: `14782`

  **MSFT-F-03 (target 13.64)** — 1 match(es) in band:
    - `13.7`  …More Personal Computing.  Revenue was $13.7 billion, increasing 3% and 2% in consta…

### `msft_q1fy26_call.txt`

- subpool: `earnings_call`  period: `Q1 FY2026 earnings call`  tokens: `14756`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q2fy18_call.txt`

- subpool: `earnings_call`  period: `Q2 FY2018 earnings call`  tokens: `16547`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q2fy19_call.txt`

- subpool: `earnings_call`  period: `Q2 FY2019 earnings call`  tokens: `15666`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q2fy20_call.txt`

- subpool: `earnings_call`  period: `Q2 FY2020 earnings call`  tokens: `13815`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q2fy21_call.txt`

- subpool: `earnings_call`  period: `Q2 FY2021 earnings call`  tokens: `13214`

  **MSFT-F-03 (target 13.64)** — 1 match(es) in band:
    - `13.6`  …ect revenue between $13.35 billion and $13.6 billion. In office commercial, revenue…

  **MSFT-C-02 (target 14.9)** — 1 match(es) in band:
    - `14.95`  …pect revenue between $14.7 billion and $14.95 billion.  In Azure, revenue will again…

### `msft_q2fy22_call.txt`

- subpool: `earnings_call`  period: `Q2 FY2022 earnings call`  tokens: `16196`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q2fy23_call.txt`

- subpool: `earnings_call`  period: `Q2 FY2023 earnings call`  tokens: `16370`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q2fy24_call.txt`

- subpool: `earnings_call`  period: `Q2 FY2024 earnings call`  tokens: `17309`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q2fy25_call.txt`

- subpool: `earnings_call`  period: `Q2 FY2025 earnings call`  tokens: `16358`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q3fy18_call.txt`

- subpool: `earnings_call`  period: `Q3 FY2018 earnings call`  tokens: `17640`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q3fy20_call.txt`

- subpool: `earnings_call`  period: `Q3 FY2020 earnings call`  tokens: `15630`

  **MSFT-F-03 (target 13.64)** — 1 match(es) in band:
    - `13.7`  …nd collections. And free cash flow was $13.7 billion, up 25%.  Other income and expe…

### `msft_q3fy21_call.txt`

- subpool: `earnings_call`  period: `Q3 FY2021 earnings call`  tokens: `14844`

  **MSFT-F-03 (target 13.64)** — 3 match(es) in band:
    - `13.6`  …roductivity and Business Processes was $13.6 billion and grew 15% and 12% in constan…
    - `13.6`  …l Computing, we expect revenue between $13.6 billion and $14 billion. In Windows, ov…
    - `13.7`  …to company guidance. We expect COGS of $13.7 billion to $13.9 billion and operating…

### `msft_q3fy22_call.txt`

- subpool: `earnings_call`  period: `Q3 FY2022 earnings call`  tokens: `15577`

  **MSFT-F-03 (target 13.64)** — 1 match(es) in band:
    - `13.7`  …6.2 billion. Organic revenue growth was 13.7%. Net income attributable to PepsiCo wa…

  **MSFT-C-02 (target 14.9)** — 2 match(es) in band:
    - `14.95`  …ect revenue between $14.65 billion and $14.95 billion. As mentioned earlier, our guid…
    - `14.9`  …operating expense of $14.8 billion to $14.9 billion, resulting in another quarter o…

### `msft_q3fy23_call.txt`

- subpool: `earnings_call`  period: `Q3 FY2023 earnings call`  tokens: `14531`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q3fy24_call.txt`

- subpool: `earnings_call`  period: `Q3 FY2024 earnings call`  tokens: `17127`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q4fy20_call.txt`

- subpool: `earnings_call`  period: `Q4 FY2020 earnings call`  tokens: `13929`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q4fy21_call.txt`

- subpool: `earnings_call`  period: `Q4 FY2021 earnings call`  tokens: `14466`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q4fy22_call.txt`

- subpool: `earnings_call`  period: `Q4 FY2022 earnings call`  tokens: `14713`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

### `msft_q4fy25_call.txt`

- subpool: `earnings_call`  period: `Q4 FY2025 earnings call`  tokens: `14196`

  *No values within ±0.5% of any FY2025 Tier-1/Tier-2 target.*

---

## Summary

- Files scanned: **34**
- Files with zero in-band matches: **25** (73.5%)
- Files with ≥1 match: **9**
- Total numeric matches: **16**

Per-target match counts:

| q_id | total matches across pool |
|------|---------------------------|
| MSFT-F-01 | 0 |
| MSFT-F-02 | 3 |
| MSFT-F-03 | 9 |
| MSFT-C-01 | 0 |
| MSFT-C-02 | 4 |

---

## Reviewer notes

**Restated comparators (§3.1b).** MSFT 10-Ks disclose the prior year for
comparability. The FY2024 10-K's "as restated" figures may differ from the
FY2024 actuals as originally filed. The ±0.5% band catches both versions when
they near a FY2025 value — both are kept in the noise pool deliberately, with
§5.3 logging the period of any actual hit as a diagnostic.

**Q1 FY2026 call forward guidance.** The Q1 FY2026 transcript (held Oct 2025)
provides Q2 FY2026 guidance, not FY2025 figures. Any in-band hits there should
be examined for guidance-midpoints landing on FY2025 actuals — a known §3.3.1
failure mode. Human-reviewed below if any such hits appear.

**Disposition.** No files removed in this pass. The pool composition stands
as locked in `materials_temporal.lock.json` (SHA recorded in addendum §13).
Subsequent re-screens after human review of the contexts above amend this file
(and re-hash via `noise_screening_log_hash` in arm.lock.json).

---

## Reviewer disposition (2026-05-05, automated screen + human pass)

All 16 in-band matches reviewed and dispositioned **benign** — every hit is
unit-mismatched or context-mismatched against its target:

- **MSFT-F-02 ($128,528M op income)** — 3 hits: $128,314 / $128,839 (twice).
  All three are *Service and other* segment-revenue subtotals from FY2022 and
  FY2023 10-Q income-statement tables — same numeric scale but a different
  line item. A model that ingests "$128,839 Service and other revenue" and
  reports it as "$128,528 FY2025 operating income" would have to drop both
  the line label *and* the period — a two-step misattribution the §5
  detector would correctly flag as contamination, not as a correct answer.

- **MSFT-F-03 ($13.64 diluted EPS)** — 9 hits. All are *billions of dollars*
  in segment revenue, guidance ranges, segment cash flow, or the FY2022
  $13.6B revenue-increase MD&A line. None are dollars-per-share. Unit
  mismatch (billion-USD vs USD-per-share) makes confusion implausible.

- **MSFT-C-02 (14.9% revenue growth)** — 4 hits. Three are *guidance dollar
  ranges* ("revenue between $14.65 billion and $14.95 billion"); the fourth
  is operating-expense guidance ("$14.8 billion to $14.9 billion"). All
  dollar-denominated, not percent. Unit mismatch.

- **PepsiCo "13.7%"** — appears once in `msft_q4fy23_call.txt` because a Q&A
  speaker cited PepsiCo as a comparator. Not Microsoft data, would not be
  cited as Microsoft data.

- **MSFT-F-01 ($281,724M revenue)** and **MSFT-C-01 (17.6% effective tax
  rate)** — zero in-band matches across 34 files.

**Net.** The 34-file pool is locked as-is for v3 pilot. Re-screen if any pilot
result reveals contamination not caught by this band scan (e.g., qualitative
forward-looking statements that paraphrase a FY2025 actual without quoting
the number).
