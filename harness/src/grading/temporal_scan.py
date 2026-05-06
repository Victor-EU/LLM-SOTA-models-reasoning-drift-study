"""
Programmatic temporal_contamination detector.

TEMPORAL_NOISE_ADDENDUM.md §5.1 specifies:

    temporal_contamination(run, q_id) :=
      count of distinct distractor values from the temporal-noise distractor
      list that appear in the answer or citation, attributed to the wrong
      MSFT period.

    "Programmatic detection is identical in shape to v1/v2's
     cross_contamination detector (DESIGN.md §9.2): regex/numeric match
     against the answer's answer_normalized field and the citation span,
     incrementing on each distinct hit."

This module is that detector. Pure functions; no API calls. Pinned via
grading_module SHA in pre_registration.v3.lock alongside scope_cap.py so
its bytes are part of the v3 methodology surface — edits change the
grading_module hash and invalidate any v3 arm that pinned the prior SHA.

Behavior on peer arms (no temporal distractors file): the detector is gated
upstream in judge.py — peer arms never load distractors, so this module is
inert for them. v1/v2 byte-equivalence preserved.

Hit-counting rule: each distractor (uniquely identified by period +
source_doc) counts AT MOST ONCE per record, even if the value appears
multiple times in the text. So `count = number of distinct distractors hit`,
not `number of textual matches`. Matches §5.1's "distinct hit" wording.

Tier 3 caveat: §4.2 explicitly permits longitudinal references in
synthesis answers IF the period is stated. This detector is faithful to
§5.1's literal spec — it counts numeric matches without checking whether
the period was correctly attributed. The per-hit log preserves the matched
substring + ~80 chars of context so analysis can post-filter explicitly
attributed mentions. If pilot reveals systematic over-counting on Tier 3,
add a period-mention nearby check (commented helper below).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# ---- dataclasses --------------------------------------------------------

@dataclass(frozen=True)
class Distractor:
    """One temporal distractor — a prior-period MSFT value that, if surfaced
    in the answer, indicates a mis-attribution."""
    q_id: str
    value: float
    unit: str                       # "USD_millions" | "USD_per_share" | "percent"
    period: str
    source_doc: str
    tolerance_abs: float | None
    tolerance_rel: float | None
    restatement_version: str
    notes: str = ""


@dataclass(frozen=True)
class TemporalHit:
    """One distractor matched in the candidate text."""
    distractor_value: float
    period: str
    source_doc: str
    restatement_version: str
    matched_string: str             # the literal substring that matched
    context: str                    # ±40 chars of surrounding text


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning one (run, q_id) record against its distractor list."""
    count: int
    hits: tuple[TemporalHit, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"count": self.count, "hits": [asdict(h) for h in self.hits]}


# ---- loader -------------------------------------------------------------

def load_distractors(path: Path) -> dict[str, list[Distractor]]:
    """Load MSFT_temporal_distractors.json and normalize per q_id.

    The file's per-q_id `values` field uses unit-specific key names
    (`value_usd_m` / `value_usd_per_share` / `value_percent`); the loader
    flattens these to a single `value` + `unit` pair.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[Distractor]] = {}
    for entry in raw.get("distractors", []):
        qid = entry["q_id"]
        tol_abs = entry.get("tolerance_abs_for_match")
        tol_rel = entry.get("tolerance_rel_for_match")
        ds: list[Distractor] = []
        for v in entry.get("values", []):
            value: float | None = None
            unit: str = ""
            if "value_usd_m" in v:
                value, unit = float(v["value_usd_m"]), "USD_millions"
            elif "value_usd_per_share" in v:
                value, unit = float(v["value_usd_per_share"]), "USD_per_share"
            elif "value_percent" in v:
                value, unit = float(v["value_percent"]), "percent"
            if value is None:
                continue
            ds.append(Distractor(
                q_id=qid,
                value=value,
                unit=unit,
                period=v["period"],
                source_doc=v["source_doc"],
                tolerance_abs=tol_abs,
                tolerance_rel=tol_rel,
                restatement_version=v.get("restatement_version", "?"),
                notes=v.get("notes", ""),
            ))
        out[qid] = ds
    return out


# ---- scanner ------------------------------------------------------------

# Match optional $ prefix, number with comma thousand-separators OR plain
# decimal, optional scale qualifier, optional trailing % sign.
# Group 1 = $ (or None); Group 2 = numeric token;
# Group 3 = scale word (or None); Group 4 = % (or None).
_NUM_RE = re.compile(
    r"(\$)?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(trillion|billion|million|thousand|T|B|M|K)\b)?"
    r"\s*(%)?",
    re.IGNORECASE,
)

# Scale qualifiers expressed in MILLIONS (the canonical unit for the
# revenue / op-income distractors). thousand/K is rare for our targets and
# would shrink the value; we don't transform on it.
_SCALE_TO_MILLIONS: dict[str, float] = {
    "trillion": 1_000_000.0, "t": 1_000_000.0,
    "billion":      1_000.0, "b":      1_000.0,
    "million":          1.0, "m":          1.0,
}

# Citation-context blacklist. Filings emit phrases like "Part II, Item 7"
# or "Note 13" where a bare integer follows a structural keyword. These are
# document-structure references, not financial values; the bare integer must
# never count as a temporal distractor hit. Pilot (2026-05-05) confirmed all
# 5 observed hits were of the form "Item 7" matching the 6.88% YoY-growth
# distractor within rel_tol — pure false positives. The lookback window is
# 15 chars (handles "Part II, Item " before the digit).
_CITATION_PRECEDER = re.compile(
    r"\b(?:Item|Part|Page|Note|Section|Table|Exhibit|Appendix|Schedule|Figure)"
    r"\s+(?:[IVX]+,?\s+)?$",
    re.IGNORECASE,
)


def _within_tolerance(
    v: float, target: float, abs_tol: float | None, rel_tol: float | None,
) -> bool:
    if abs_tol is not None and abs(v - target) <= abs_tol:
        return True
    if rel_tol is not None and target != 0.0 and abs(v - target) / abs(target) <= rel_tol:
        return True
    if abs_tol is None and rel_tol is None:
        return v == target
    return False


def _is_specific_enough(
    num_str: str, scale: str, has_pct: bool, has_dollar: bool,
) -> bool:
    """Reject numeric tokens that lack any specificity marker.

    Without this guard, a bare "7" in 'Part II, Item 7' falsely matches
    distractors like 6.88% (within ±5% rel tol) — observed in pilot
    (2026-05-05). Specificity markers, any one is sufficient:

      - decimal point in the numeric token   (e.g. "6.88", "245.1")
      - comma thousand-separator in the token (e.g. "245,122")
      - explicit "$" prefix
      - explicit "%" suffix
      - scale qualifier word                 (billion / million / etc.)
      - ≥3 contiguous digits                 (e.g. "245122" — covers JSON-emitted
                                              bare integers in answer fields)

    Single- and two-digit bare integers (no markers) cannot reach distractor
    magnitudes meaningful at our tolerance and are universally rejected.
    """
    if "." in num_str or "," in num_str:
        return True
    if scale or has_pct or has_dollar:
        return True
    return len(num_str) >= 3


def _in_citation_context(text: str, match_start: int) -> bool:
    """True when the numeric match is preceded by a citation/structure keyword
    (Item N, Part II, Page 13, Note 8, etc.). Filters document-structure
    references that share digit shapes with financial values.
    """
    look = text[max(0, match_start - 20):match_start]
    return _CITATION_PRECEDER.search(look) is not None


def scan_text(text: str, distractors: list[Distractor]) -> ScanResult:
    """Scan free-form text for distractor matches.

    Each distractor (period + source_doc) is counted AT MOST ONCE per record
    regardless of how many times its value appears. Returns a ScanResult
    whose `count` is the number of distinct distractors hit.

    For USD_millions distractors, prose mentions like "$245.1 billion" are
    converted to millions (245.1 * 1000 = 245,100) before tolerance check.
    For USD_per_share and percent distractors, scale qualifiers are not
    applied (units don't make sense — "$13.64 billion EPS" doesn't parse
    sensibly under our rules and won't match the EPS distractor).

    Two pre-filters drop ambiguous mentions BEFORE distractor testing:
      1. _is_specific_enough — bare 1-2 digit integers without $/%/scale/.
         markers can land within rel_tol of small distractors by chance.
      2. _in_citation_context — "Item 7", "Note 13", "Part II, Item 7"
         are document-structure references, never temporal values.
    Both guards added 2026-05-05 after pilot revealed 5 false positives
    (all "Item 7" → 6.88% distractor). See module docstring.
    """
    if not text or not distractors:
        return ScanResult(count=0)

    # Pre-extract every numeric mention with its scale + position.
    mentions: list[tuple[str, float, str, bool, int]] = []
    for m in _NUM_RE.finditer(text):
        raw = m.group(0).strip()
        has_dollar = bool(m.group(1))
        num_str = m.group(2)
        scale = (m.group(3) or "").strip().lower()
        is_pct = bool(m.group(4))
        try:
            v = float(num_str.replace(",", ""))
        except ValueError:
            continue
        # Use the DIGIT-token start (group 2), not m.start() — the latter
        # includes any leading "$" / whitespace eaten by `(\$)?\s*`, which
        # would push the citation-context lookback off the trailing space
        # after a keyword like "Item ". The downstream context window also
        # reads more naturally from the digit position.
        digit_start = m.start(2)
        # Specificity + context guards (see module docstring).
        if not _is_specific_enough(num_str, scale, is_pct, has_dollar):
            continue
        if _in_citation_context(text, digit_start):
            continue
        mentions.append((raw, v, scale, is_pct, digit_start))

    # Hit accounting:
    # - matched_keys dedupes the per-hit log so the SAME (period, source_doc)
    #   distractor isn't logged twice when its value appears more than once.
    # - matched_values is the COUNT key: per §5.1 the metric is "distinct
    #   distractor values." Per §3.1b "a hit on either restatement counts" —
    #   so two distractors with the same numeric value (e.g., FY24 as filed
    #   vs FY24 as restated) collapse to one distinct count, while their
    #   per-hit log entries are kept separately for §5.3 period diagnostics.
    matched_keys: set[tuple[str, str]] = set()
    matched_values: set[float] = set()
    hits: list[TemporalHit] = []

    for d in distractors:
        key = (d.period, d.source_doc)
        if key in matched_keys:
            continue
        target_is_money_in_millions = d.unit == "USD_millions"
        target_is_percent = d.unit == "percent"
        target_is_eps = d.unit == "USD_per_share"

        for raw, v, scale, is_pct, pos in mentions:
            # Build candidate values to test against the distractor.
            candidates: list[float] = []
            if target_is_money_in_millions:
                if scale and scale in _SCALE_TO_MILLIONS:
                    # "$X billion" → X * 1000 = X millions. Try it.
                    candidates.append(v * _SCALE_TO_MILLIONS[scale])
                # Bare number — could be millions already (clean numeric form).
                # Don't append the bare number when a scale word is present —
                # "$245.1 billion" should not also test 245.1 against 245122.
                if not scale:
                    candidates.append(v)
            elif target_is_percent:
                # Bare numbers + numbers with % both candidate at face value.
                # Reject if the prose carries a money-scale word (scale
                # mismatch — "$14.9 billion" is not "14.9 percent").
                if not scale:
                    candidates.append(v)
            elif target_is_eps:
                # Per-share dollars. Bare decimal acceptable; reject prose
                # money scales (an EPS isn't quoted as "$13.64 billion").
                if not scale:
                    candidates.append(v)
            else:
                if not scale:
                    candidates.append(v)

            matched = False
            for cv in candidates:
                if _within_tolerance(cv, d.value, d.tolerance_abs, d.tolerance_rel):
                    matched = True
                    break
            if matched:
                # Capture context window for §5.3 diagnostic.
                ctx_start = max(0, pos - 40)
                ctx_end = min(len(text), pos + len(raw) + 40)
                ctx = text[ctx_start:ctx_end].replace("\n", " ").strip()
                hits.append(TemporalHit(
                    distractor_value=d.value,
                    period=d.period,
                    source_doc=d.source_doc,
                    restatement_version=d.restatement_version,
                    matched_string=raw,
                    context=ctx,
                ))
                matched_keys.add(key)
                matched_values.add(round(d.value, 6))
                break  # done with this distractor; move to next

    return ScanResult(count=len(matched_values), hits=tuple(hits))


def scan_record(
    record: dict[str, Any],
    distractors_by_qid: dict[str, list[Distractor]],
) -> ScanResult:
    """Convenience wrapper: pick the right text fields off an extracted record
    based on tier and scan against the q_id's distractor list.

    Tier 1/2: scan answer_normalized (numeric) + citation (string). The
        answer_raw is also included to catch values mentioned in passing.
    Tier 3 (any tier with no autograder): scan answer_raw (the prose body).
    """
    qid = record.get("q_id")
    if not qid:
        return ScanResult(count=0)
    ds = distractors_by_qid.get(qid, [])
    if not ds:
        return ScanResult(count=0)
    parts = [
        str(record.get("answer_normalized") or ""),
        str(record.get("answer_raw") or ""),
        str(record.get("citation") or ""),
    ]
    return scan_text("\n".join(p for p in parts if p), ds)


# ---- module SHA (pinned in pre_registration.v3.lock) -------------------

def temporal_scan_module_sha256() -> str:
    """SHA-256 of this module's source bytes."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


if __name__ == "__main__":
    print(temporal_scan_module_sha256())
