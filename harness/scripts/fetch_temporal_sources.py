"""
Acquire the 52-file `temporal_msft` noise corpus.

Downloads:
  - 2 prior MSFT 10-Ks  (FY2024, FY2023)              from SEC EDGAR
  - 9 prior MSFT 10-Qs  (FY2023 Q1-Q3, FY2024 Q1-Q3,  from SEC EDGAR
                         FY2025 Q1-Q3)
  - 41 prior MSFT earnings-call transcripts:           from Motley Fool
        Q1 FY2026 + Q1-Q4 of FY2016 through FY2025 (10 fiscal years × 4)

Outputs raw HTM/HTML into materials/_source/temporal/.

Per TEMPORAL_NOISE_ADDENDUM.md §3.1 + §14. Re-runnable: skips files that
already exist on disk with non-trivial size.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

HARNESS_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR_DEFAULT = HARNESS_ROOT.parent / "materials" / "_source" / "temporal"

SEC_UA = "LLM-Reasoning-Drift-Study victor.zhang.eu@gmail.com"
FOOL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
SEC_DELAY_S = 0.2   # SEC fair-use is 10 req/sec — keep well under
FOOL_DELAY_S = 4.0  # be polite to fool.com (returns 429 quickly otherwise)
FOOL_HEAD_DELAY_S = 0.6
FOOL_RATE_LIMIT_BACKOFF_S = 180  # if we see 429, sleep before giving up on this spec


# ------------------------------------------------------------------
# EDGAR catalogue (resolved 2026-05-04 from
#   https://data.sec.gov/submissions/CIK0000789019.json)
# Each entry → final URL: https://www.sec.gov/Archives/edgar/data/789019/{accn}/{doc}
# ------------------------------------------------------------------

@dataclass(frozen=True)
class EdgarFiling:
    out_name: str           # final file name in _source/temporal/
    form: str               # "10-K" | "10-Q"
    period_end: str         # YYYY-MM-DD
    filing_date: str
    accn: str               # accession with dashes
    primary_doc: str

EDGAR_FILINGS: list[EdgarFiling] = [
    # --- 10-Ks (2) ---
    EdgarFiling("msft_10k_fy2024.htm", "10-K", "2024-06-30", "2024-07-30",
                "0000950170-24-087843", "msft-20240630.htm"),
    EdgarFiling("msft_10k_fy2023.htm", "10-K", "2023-06-30", "2023-07-27",
                "0000950170-23-035122", "msft-20230630.htm"),

    # --- 10-Qs FY2025 (3) ---
    EdgarFiling("msft_10q_fy2025_q1.htm", "10-Q", "2024-09-30", "2024-10-30",
                "0000950170-24-118967", "msft-20240930.htm"),
    EdgarFiling("msft_10q_fy2025_q2.htm", "10-Q", "2024-12-31", "2025-01-29",
                "0000950170-25-010491", "msft-20241231.htm"),
    EdgarFiling("msft_10q_fy2025_q3.htm", "10-Q", "2025-03-31", "2025-04-30",
                "0000950170-25-061046", "msft-20250331.htm"),

    # --- 10-Qs FY2024 (3) ---
    EdgarFiling("msft_10q_fy2024_q1.htm", "10-Q", "2023-09-30", "2023-10-24",
                "0000950170-23-054855", "msft-20230930.htm"),
    EdgarFiling("msft_10q_fy2024_q2.htm", "10-Q", "2023-12-31", "2024-01-30",
                "0000950170-24-008814", "msft-20231231.htm"),
    EdgarFiling("msft_10q_fy2024_q3.htm", "10-Q", "2024-03-31", "2024-04-25",
                "0000950170-24-048288", "msft-20240331.htm"),

    # --- 10-Qs FY2023 (3) ---
    EdgarFiling("msft_10q_fy2023_q1.htm", "10-Q", "2022-09-30", "2022-10-25",
                "0001564590-22-035087", "msft-10q_20220930.htm"),
    EdgarFiling("msft_10q_fy2023_q2.htm", "10-Q", "2022-12-31", "2023-01-24",
                "0001564590-23-000733", "msft-10q_20221231.htm"),
    EdgarFiling("msft_10q_fy2023_q3.htm", "10-Q", "2023-03-31", "2023-04-25",
                "0000950170-23-014423", "msft-20230331.htm"),
]


def edgar_url(f: EdgarFiling) -> str:
    accn_compact = f.accn.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/789019/{accn_compact}/{f.primary_doc}"


# ------------------------------------------------------------------
# Motley Fool transcript catalogue
# ------------------------------------------------------------------
# Fool URL format:
#   https://www.fool.com/earnings/call-transcripts/<YYYY>/<MM>/<DD>/microsoft-msft-q<N>-<YYYY>-earnings-call-transcript/
# where:
#   - <YYYY>/<MM>/<DD> is the *publication* date (= day after the call most often)
#   - q<N> is the *calendar quarter* of the period covered by the call
#       (NOT the fiscal quarter — Fool labels MSFT calls by calendar Q)
#   - the trailing -<YYYY>- is the calendar year of the period
#
# To avoid having to discover every URL by hand, we discover exact URLs by
# hitting Fool's site search for each (fiscal_quarter, fiscal_year) combo
# and filtering for the matching microsoft transcript URL pattern.

@dataclass(frozen=True)
class CallSpec:
    out_name: str           # msft_q<N>fy<YY>_call.html  (matches existing convention)
    fiscal_quarter: int     # 1..4
    fiscal_year: int        # MSFT FY: ends June 30 of that calendar year
    # canonical call date (approx — verified from MS IR archives by quarter end + ~3 weeks)
    expected_call_date: str  # YYYY-MM-DD or YYYY-MM (a hint for searching)


def fy_to_call_specs() -> list[CallSpec]:
    """All 41 prior earnings-call transcripts we want."""
    out: list[CallSpec] = []
    # Q1 FY2026 — the only FY2026 call OTHER than the Q2 FY2026 target
    out.append(CallSpec("msft_q1fy26_call.html", 1, 2026, "2025-10"))
    # FY2016 .. FY2025: each Q1, Q2, Q3, Q4
    for fy in range(2016, 2026):
        # MSFT quarter -> approx calendar month of call
        # Q1 (period ends Sept 30 of FY-1) — call held in late October FY-1
        out.append(CallSpec(f"msft_q1fy{fy%100:02d}_call.html", 1, fy, f"{fy-1}-10"))
        # Q2 (period ends Dec 31 of FY-1) — call held in late January FY
        out.append(CallSpec(f"msft_q2fy{fy%100:02d}_call.html", 2, fy, f"{fy}-01"))
        # Q3 (period ends Mar 31 of FY) — call held in late April FY
        out.append(CallSpec(f"msft_q3fy{fy%100:02d}_call.html", 3, fy, f"{fy}-04"))
        # Q4 (period ends Jun 30 of FY) — call held in late July FY
        out.append(CallSpec(f"msft_q4fy{fy%100:02d}_call.html", 4, fy, f"{fy}-07"))
    return out


_KNOWN_CALL_DATES: dict[tuple[int, int], str] = {
    # (fiscal_year, fiscal_quarter): YYYY-MM-DD (call date — Fool publication
    # date matches in 95%+ of cases). Sourced from Microsoft IR press releases.
    (2026, 1): "2025-10-29",
    (2025, 4): "2025-07-30",
    (2025, 3): "2025-04-30",
    (2025, 2): "2025-01-29",
    (2025, 1): "2024-10-30",
    (2024, 4): "2024-07-30",
    (2024, 3): "2024-04-25",
    (2024, 2): "2024-01-30",
    (2024, 1): "2023-10-24",
    (2023, 4): "2023-07-25",
    (2023, 3): "2023-04-25",
    (2023, 2): "2023-01-24",
    (2023, 1): "2022-10-25",
    (2022, 4): "2022-07-26",
    (2022, 3): "2022-04-26",
    (2022, 2): "2022-01-25",
    (2022, 1): "2021-10-26",
    (2021, 4): "2021-07-27",
    (2021, 3): "2021-04-27",
    (2021, 2): "2021-01-26",
    (2021, 1): "2020-10-27",
    (2020, 4): "2020-07-22",
    (2020, 3): "2020-04-29",
    (2020, 2): "2020-01-29",
    (2020, 1): "2019-10-23",
    (2019, 4): "2019-07-18",
    (2019, 3): "2019-04-24",
    (2019, 2): "2019-01-30",
    (2019, 1): "2018-10-24",
    (2018, 4): "2018-07-19",
    (2018, 3): "2018-04-26",
    (2018, 2): "2018-01-31",
    (2018, 1): "2017-10-26",
    (2017, 4): "2017-07-20",
    (2017, 3): "2017-04-27",
    (2017, 2): "2017-01-26",
    (2017, 1): "2016-10-20",
    (2016, 4): "2016-07-19",
    (2016, 3): "2016-04-21",
    (2016, 2): "2016-01-28",
    (2016, 1): "2015-10-22",
}


def fool_url_candidates(spec: CallSpec) -> list[str]:
    """
    Generate plausible Fool URLs (HEAD-checked before downloading).

    Fool labels MSFT calls by FISCAL quarter/year (verified from the existing
    Q2 FY2026 target — slug "microsoft-msft-q2-2026-earnings-call-transcript",
    publication 2026-01-28). For each (fy, fq) we have a known canonical call
    date in `_KNOWN_CALL_DATES`; Fool's publication date is the call date in
    95%+ of cases, with ±2 day variance for late-night calls.
    """
    fq, fy = spec.fiscal_quarter, spec.fiscal_year
    if fq == 1:
        # period ends Sep 30 of calendar year (fy-1); call: late Oct
        month_candidates = [(fy - 1, 10), (fy - 1, 11)]
    elif fq == 2:
        # period ends Dec 31 of (fy-1); call: late Jan of fy
        month_candidates = [(fy, 1), (fy, 2)]
    elif fq == 3:
        # period ends Mar 31 of fy; call: late Apr of fy
        month_candidates = [(fy, 4), (fy, 5)]
    elif fq == 4:
        # period ends Jun 30 of fy; call: late Jul of fy
        month_candidates = [(fy, 7), (fy, 8)]
    else:
        raise ValueError(fq)

    # Slug forms seen in Fool's archive for MSFT, in priority order. Fool's
    # older slugs are truncated to ~50 chars so the longer suffixes appear
    # cropped (verified against historic transcripts).
    slug_forms = [
        # modern (~2018+)
        f"microsoft-msft-q{fq}-{fy}-earnings-call-transcript",
        # variant with full corporation name
        f"microsoft-corporation-msft-q{fq}-{fy}-earnings-call-trans",
        f"microsoft-corporation-msft-q{fq}-{fy}-earnings-call-transc",
        f"microsoft-corporation-msft-q{fq}-{fy}-earnings-call-transcr",
        f"microsoft-corp-msft-q{fq}-{fy}-earnings-call-transcript",
        # older Fool slug formats
        f"microsoft-msft-q{fq}-{fy}-earnings-conference-call-tra",
        f"microsoft-corp-msft-q{fq}-{fy}-earnings-conference-cal",
        f"microsoft-corporation-msft-q{fq}-{fy}-earnings-confere",
        f"microsoft-corporation-msft-q{fq}-{fy}-earnings-conf-ca",
        f"microsoft-q{fq}-{fy}-earnings-call-transcript",
        f"microsoft-corp-msft-fiscal-q{fq}-{fy}-earnings-call",
        f"microsoft-msft-fiscal-q{fq}-{fy}-earnings-conference-c",
    ]

    # Use the known canonical call date when we have it; fall back to a
    # bounded sweep otherwise. The known date typically nails the URL on
    # the first HEAD; the sweep handles edge cases (early-morning calls
    # where Fool publishes the next day).
    cands: list[str] = []
    known = _KNOWN_CALL_DATES.get((fy, fq))
    if known:
        ky, km, kd = (int(p) for p in known.split("-"))
        # ± 2 day window around the known date
        date_order = [(ky, km, kd)] + [
            (ky, km, kd + delta) for delta in (1, -1, 2, -2)
            if 1 <= kd + delta <= 31
        ]
    else:
        date_order = []
    day_order = [25, 26, 27, 28, 29, 24, 30, 23, 22, 21, 31, 20, 19, 18]
    for (yr, mo) in month_candidates:
        for day in day_order:
            t = (yr, mo, day)
            if t not in date_order:
                date_order.append(t)

    # Order by SLUG outermost so we exhaust the most-likely slug across
    # all candidate dates before trying alternate slugs.
    for slug in slug_forms:
        for (yr, mo, day) in date_order:
            cands.append(
                f"https://www.fool.com/earnings/call-transcripts/{yr:04d}/{mo:02d}/{day:02d}/{slug}/"
            )
    return cands


def is_microsoft_transcript_page_fiscal(html: str, spec: CallSpec) -> bool:
    """The page must mention Microsoft and the right FISCAL quarter+year."""
    fq, fy = spec.fiscal_quarter, spec.fiscal_year
    h_lower = html.lower()
    if "microsoft" not in h_lower:
        return False
    needles = [f"q{fq} {fy}", f"q{fq} fy{fy}", f"q{fq} fy{fy%100:02d}",
               f"first quarter {fy}", f"second quarter {fy}",
               f"third quarter {fy}", f"fourth quarter {fy}"]
    needles_for_q = {
        1: ["first quarter", "1q", f"q1 {fy}", f"q1 fiscal {fy}", "q1-2"],
        2: ["second quarter", "2q", f"q2 {fy}", f"q2 fiscal {fy}", "q2-2"],
        3: ["third quarter", "3q", f"q3 {fy}", f"q3 fiscal {fy}", "q3-2"],
        4: ["fourth quarter", "4q", f"q4 {fy}", f"q4 fiscal {fy}", "q4-2"],
    }[fq]
    has_q = any(n in h_lower for n in needles_for_q + needles)
    has_year = (str(fy) in html) or (str(fy)[-2:] in html)
    return has_q and has_year


# ------------------------------------------------------------------
# Downloaders
# ------------------------------------------------------------------

def fetch(url: str, ua: str, *, retries: int = 4, timeout: int = 60) -> requests.Response | None:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }, timeout=timeout, allow_redirects=True)
            return r
        except requests.RequestException as e:
            last_err = e
            time.sleep(2 * attempt)
    print(f"  fetch failed after {retries} retries: {url}  ({last_err})", file=sys.stderr)
    return None


def head(url: str, ua: str) -> int | None:
    """Return status code of HEAD; None on error."""
    try:
        r = requests.head(url, headers={"User-Agent": ua}, timeout=20, allow_redirects=True)
        return r.status_code
    except requests.RequestException:
        return None


def download_edgar(out_dir: Path, *, force: bool) -> int:
    n_ok = 0
    for f in EDGAR_FILINGS:
        out = out_dir / f.out_name
        if out.exists() and out.stat().st_size > 50_000 and not force:
            print(f"  skip   {f.out_name}  ({out.stat().st_size:,} bytes already on disk)")
            n_ok += 1
            continue
        url = edgar_url(f)
        print(f"  fetch  {f.out_name}  <- {url}")
        r = fetch(url, SEC_UA)
        if r is None or r.status_code != 200:
            print(f"  FAIL   {f.out_name}  status={getattr(r,'status_code',None)}")
            continue
        out.write_bytes(r.content)
        print(f"         {out.stat().st_size:,} bytes  saved")
        n_ok += 1
        time.sleep(SEC_DELAY_S)
    return n_ok


# ---- Fool article body extraction ---------------------------------
#
# Fool transcript pages share a stable structure (verified 2026-05-05 against
# msft_q1fy26 + the existing msft_q2fy26 target):
#   ...nav/header/sidebar...
#   <h2 id="date">Date</h2><p>...</p>
#   <h2 id="call-participants">...</h2>...
#   <h2 id="risks">...</h2>...
#   <h2 id="takeaways">...</h2>...
#   <h2 id="summary">...</h2>...                     ← article body
#   <h2 id="prepared-remarks">...</h2>...
#   <h2 id="questions-and-answers">...</h2>...
#   ...closing </div>...
#   <article ...>  ← FIRST <article> after the date marker = related-articles strip
# So the carve is [date_marker_start, next_article_after_date_marker).

_DATE_MARKER = re.compile(r"<h2[^>]*\bid\s*=\s*[\"']date[\"'][^>]*>", re.IGNORECASE)
_ARTICLE_OPEN = re.compile(r"<article\b[^>]*>", re.IGNORECASE)


# ---- AlphaStreet article body extraction --------------------------
#
# AlphaStreet transcript pages have an `<article>` or `<div class="entry-content">`
# main container. We carve from the first <h1>/<h2>/<article> through the next
# `<div class="related"...>` or footer.

_AS_ARTICLE_OPEN = re.compile(r'<article\b[^>]*class="[^"]*(?:single-transcript|transcript)[^"]*"[^>]*>', re.IGNORECASE)
_AS_ARTICLE_OPEN_FALLBACK = re.compile(r'<article\b[^>]*>', re.IGNORECASE)


def carve_alphastreet_article(html: str) -> str:
    """
    AlphaStreet wraps each transcript in a single <article class="single-transcript ...">
    block; we carve from the article opener to its </article> close. There are
    nested <footer>/<aside> elements WITHIN the article (related-posts strips,
    sharing widgets) — we keep them; html_to_text scrubs them downstream.
    """
    m = _AS_ARTICLE_OPEN.search(html) or _AS_ARTICLE_OPEN_FALLBACK.search(html)
    if not m:
        return html
    start = m.end()
    # Find the matching </article>. AS doesn't nest articles, so first close wins.
    m_end = re.search(r'</article\s*>', html[start:], re.IGNORECASE)
    end = (start + m_end.start()) if m_end else len(html)
    return html[start:end]


def is_alphastreet_msft_transcript_page(html: str, fy: int, fq: int) -> bool:
    h_lower = html.lower()
    if "microsoft" not in h_lower:
        return False
    return f"q{fq}" in h_lower and (str(fy) in html or str(fy)[-2:] in html)


def carve_fool_article(html: str) -> str:
    m_date = _DATE_MARKER.search(html)
    if not m_date:
        # Older Fool template (pre-2018ish) lacks the `id="date"` h2.
        # Fall back: take the largest <article>...</article> block.
        articles = []
        for m in _ARTICLE_OPEN.finditer(html):
            close = re.search(r"</article\s*>", html[m.end():], re.IGNORECASE)
            if close:
                end = m.end() + close.start()
                articles.append((end - m.end(), m.end(), end))
        if not articles:
            return html
        articles.sort(reverse=True)
        _, s, e = articles[0]
        return html[s:e]
    start = m_date.start()
    m_next_article = _ARTICLE_OPEN.search(html, pos=m_date.end())
    end = m_next_article.start() if m_next_article else len(html)
    return html[start:end]


def is_microsoft_transcript_page(html: str, spec: CallSpec) -> bool:
    return is_microsoft_transcript_page_fiscal(html, spec)


# ---- Wayback Machine downloader (primary fallback for Fool block) -

# Strategy: for each (fy, fq), construct the canonical Fool URL using known
# call dates, then ask Wayback for the closest snapshot. If a capture exists,
# Wayback returns a 200 with the original transcript HTML inline. Wayback's
# IP block is independent of Fool's, so this works even when live Fool returns
# 429.

WAYBACK_DELAY_S = 1.0


def fool_canonical_url(fy: int, fq: int) -> str | None:
    """The canonical Fool URL for (fy, fq) using known call dates."""
    known = _KNOWN_CALL_DATES.get((fy, fq))
    if not known:
        return None
    return (
        f"https://www.fool.com/earnings/call-transcripts/"
        f"{known.replace('-', '/')}/microsoft-msft-q{fq}-{fy}-earnings-call-transcript/"
    )


def wayback_url_for(fool_url: str) -> str:
    """Wayback redirect URL — finds closest snapshot to 'now'."""
    # The 2* timestamp pattern asks for the closest snapshot in the 2000s.
    # Wayback redirects (302) to the actual captured snapshot URL.
    return f"https://web.archive.org/web/2*/{fool_url}"


def download_wayback_calls(out_dir: Path, *, force: bool, max_calls: int | None = None) -> int:
    """
    Downloads via Wayback's id_/ raw-content endpoint using a known-captures
    manifest (enumerated from CDX once and stored in _wayback_known_captures.json
    so we can run even when CDX itself is offline).
    """
    captures_file = HARNESS_ROOT / "scripts" / "_wayback_known_captures.json"
    if not captures_file.exists():
        print(f"  no known-captures manifest at {captures_file}", file=sys.stderr)
        return 0
    import json as _json
    captures = _json.loads(captures_file.read_text())["captures"]

    # Map (fy, fq) -> (orig_url, ts)
    cap_by_key = {(fy, fq): (orig, ts) for (fy, fq, orig, ts) in captures}

    n_ok = 0
    specs = fy_to_call_specs()
    if max_calls is not None:
        specs = specs[:max_calls]

    for spec in specs:
        out = out_dir / spec.out_name
        if out.exists() and out.stat().st_size > 5_000 and not force:
            print(f"  skip   {spec.out_name}  ({out.stat().st_size:,} bytes already on disk)")
            n_ok += 1
            continue

        cap = cap_by_key.get((spec.fiscal_year, spec.fiscal_quarter))
        if cap is None:
            print(f"  MISS   {spec.out_name}  (no Wayback capture in manifest)")
            continue
        orig_url, ts = cap
        # id_/ modifier returns the raw archived content without Wayback chrome
        snap_url = f"https://web.archive.org/web/{ts}id_/{orig_url}"
        r = fetch(snap_url, FOOL_UA)
        if r is None or r.status_code != 200:
            print(f"  FAIL   {spec.out_name}  status={getattr(r, 'status_code', None)}  {snap_url}")
            time.sleep(WAYBACK_DELAY_S)
            continue
        # Pick carving fn based on origin; AS pages have <article class="single-transcript">,
        # Fool pages have <h2 id="date"> markers.
        if "alphastreet" in orig_url.lower():
            check = is_alphastreet_msft_transcript_page(r.text, spec.fiscal_year, spec.fiscal_quarter)
            carved = carve_alphastreet_article(r.text)
        else:
            check = is_microsoft_transcript_page(r.text, spec)
            carved = carve_fool_article(r.text)
        if not check:
            print(f"  reject {spec.out_name}  (page didn't match microsoft + q{spec.fiscal_quarter} fy{spec.fiscal_year})")
            time.sleep(WAYBACK_DELAY_S)
            continue
        if len(carved) < 5000:
            print(f"  reject {spec.out_name}  (carve too small: {len(carved)} bytes; likely a stub/preview)")
            time.sleep(WAYBACK_DELAY_S)
            continue
        out.write_text(carved, encoding="utf-8")
        (out_dir / (spec.out_name + ".url")).write_text(
            f"# Sourced via Wayback Machine snapshot:\n# original: {orig_url}\n# snapshot: {snap_url}\n",
            encoding="utf-8",
        )
        origin = "alphastreet" if "alphastreet" in orig_url.lower() else "fool"
        print(f"  ok     {spec.out_name}  carved={len(carved):,} bytes  via {origin} {ts}")
        n_ok += 1
        time.sleep(WAYBACK_DELAY_S)
    return n_ok


# ---- AlphaStreet downloader (Fool fallback) -----------------------

_AS_SLUG_FORMS = [
    "microsoft-corporation-msft-q{q}-{y}-earnings-call-transcript",
    "microsoft-corp-msft-q{q}-{y}-earnings-call-transcript",
    "microsoft-msft-q{q}-{y}-earnings-call-transcript",
    "microsoft-q{q}-{y}-earnings-call-transcript",
]


def alphastreet_url_for(fy: int, fq: int) -> str | None:
    """Return the first AS URL that 200s for (fy, fq), or None."""
    for sf in _AS_SLUG_FORMS:
        url = f"https://news.alphastreet.com/{sf.format(q=fq, y=fy)}/"
        sc = head(url, FOOL_UA)
        if sc == 200:
            return url
        time.sleep(0.3)
    return None


def download_alphastreet_calls(out_dir: Path, *, force: bool, max_calls: int | None = None) -> int:
    """Walk the same call specs and try AlphaStreet for each."""
    n_ok = 0
    specs = fy_to_call_specs()
    if max_calls is not None:
        specs = specs[:max_calls]

    for spec in specs:
        out = out_dir / spec.out_name
        if out.exists() and out.stat().st_size > 5_000 and not force:
            print(f"  skip   {spec.out_name}  ({out.stat().st_size:,} bytes already on disk)")
            n_ok += 1
            continue

        url = alphastreet_url_for(spec.fiscal_year, spec.fiscal_quarter)
        if url is None:
            print(f"  MISS   {spec.out_name}  (AS has no transcript at the standard slug forms)")
            continue
        r = fetch(url, FOOL_UA)
        if r is None or r.status_code != 200:
            print(f"  FAIL   {spec.out_name}  fetch failed")
            continue
        if not is_alphastreet_msft_transcript_page(r.text, spec.fiscal_year, spec.fiscal_quarter):
            print(f"  reject {url}  (page didn't match microsoft + q<n> <year>)")
            continue
        carved = carve_alphastreet_article(r.text)
        out.write_text(carved, encoding="utf-8")
        (out_dir / (spec.out_name + ".url")).write_text(url + "\n", encoding="utf-8")
        print(f"  ok     {spec.out_name}  <- {url}  carved={len(carved):,} bytes")
        n_ok += 1
        time.sleep(1.5)
    return n_ok


def download_fool_calls(out_dir: Path, *, force: bool, max_calls: int | None = None) -> int:
    n_ok = 0
    specs = fy_to_call_specs()
    if max_calls is not None:
        specs = specs[:max_calls]

    for spec in specs:
        out = out_dir / spec.out_name
        if out.exists() and out.stat().st_size > 30_000 and not force:
            print(f"  skip   {spec.out_name}  ({out.stat().st_size:,} bytes already on disk)")
            n_ok += 1
            continue

        # Try candidate URLs by HEAD until one returns 200.
        # On 429 (rate limit) we back off and retry once; if still 429, abort
        # the whole sweep — banging on fool.com after a 429 just deepens the
        # block. The user can re-run later.
        cands = fool_url_candidates(spec)
        chosen_url = None
        chosen_html = None
        rate_limited_twice = False
        for url in cands:
            sc = head(url, FOOL_UA)
            if sc == 429:
                print(f"  429 hit — backing off {FOOL_RATE_LIMIT_BACKOFF_S}s before retry")
                time.sleep(FOOL_RATE_LIMIT_BACKOFF_S)
                sc = head(url, FOOL_UA)
                if sc == 429:
                    rate_limited_twice = True
                    break
            if sc == 200:
                r = fetch(url, FOOL_UA)
                if r is None or r.status_code != 200:
                    continue
                if not is_microsoft_transcript_page(r.text, spec):
                    print(f"  reject {url}  (page doesn't match microsoft + qN <year>)")
                    continue
                chosen_url, chosen_html = url, r.text
                break
            time.sleep(FOOL_HEAD_DELAY_S)

        if rate_limited_twice:
            print(f"  ABORT  fool.com is rate-limiting; stopping sweep at {spec.out_name}")
            return n_ok

        if chosen_html is None:
            print(f"  MISS   {spec.out_name}  (no candidate URL returned 200; will need manual lookup)")
            continue

        carved = carve_fool_article(chosen_html)
        out.write_text(carved, encoding="utf-8")
        # Persist the source URL alongside as <out>.url for traceability
        (out_dir / (spec.out_name + ".url")).write_text(chosen_url + "\n", encoding="utf-8")
        print(f"  ok     {spec.out_name}  <- {chosen_url}  carved={len(carved):,} bytes")
        n_ok += 1
        time.sleep(FOOL_DELAY_S)
    return n_ok


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default=str(SOURCE_DIR_DEFAULT))
    p.add_argument("--force", action="store_true")
    p.add_argument("--edgar-only", action="store_true")
    p.add_argument("--fool-only", action="store_true")
    p.add_argument("--alphastreet-only", action="store_true",
                   help="only run the AlphaStreet fallback downloader")
    p.add_argument("--wayback-only", action="store_true",
                   help="only run the Wayback Machine downloader (uses canonical Fool URLs)")
    p.add_argument("--max-calls", type=int, default=None,
                   help="cap on number of transcripts (debug)")
    args = p.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    n_edgar = 0
    n_fool = 0
    n_as = 0
    if args.alphastreet_only:
        print(f"--- AlphaStreet earnings transcripts (target: 41) ---")
        n_as = download_alphastreet_calls(out_dir, force=args.force, max_calls=args.max_calls)
        print(f"\nDone. AlphaStreet ok={n_as}/41")
        return 0 if n_as == 41 else 1

    if args.wayback_only:
        print(f"--- Wayback Machine snapshots of Fool transcripts (target: 41) ---")
        n_wb = download_wayback_calls(out_dir, force=args.force, max_calls=args.max_calls)
        print(f"\nDone. Wayback ok={n_wb}/41")
        return 0 if n_wb == 41 else 1

    if not args.fool_only:
        print(f"--- EDGAR ({len(EDGAR_FILINGS)} filings) ---")
        n_edgar = download_edgar(out_dir, force=args.force)
    if not args.edgar_only:
        print(f"\n--- Motley Fool earnings transcripts (target: 41) ---")
        n_fool = download_fool_calls(out_dir, force=args.force, max_calls=args.max_calls)

    print(f"\nDone. EDGAR ok={n_edgar}/{len(EDGAR_FILINGS)}, Fool ok={n_fool}/41")
    return 0 if (n_edgar == len(EDGAR_FILINGS) or args.fool_only) and \
                (n_fool == 41 or args.edgar_only) else 1


if __name__ == "__main__":
    raise SystemExit(main())
