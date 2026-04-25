"""
Material-prep pipeline (v0.2).

Converts raw source documents (SEC 10-K XBRL HTML + Motley Fool transcript HTML)
into the normalized-text layout the harness expects under cfg.paths.materials_dir.

Usage:
    python -m scripts.build_materials               # process all targets
    python -m scripts.build_materials --check       # dry-run, no writes

Output layout (per DESIGN §6 / materials.py):
    materials/
        target/MSFT/
            10k.txt           normalized plain text
            10k.meta.json     {company_name, fiscal_year, sha256, token_count, source_url}
            earnings_call.txt
            earnings_call.meta.json
        noise/adversarial_near/MSFT/
            alphabet.txt      (fetched separately via the same pipeline)
            alphabet.meta.json
            ...
        questions/MSFT.json
        ground_truth/MSFT.json
        materials.lock.json   {files: {path: {sha256, token_count}, ...}}

This script only handles the TARGET bundle for MSFT. Noise corpus, question
bank, and ground-truth JSONs are authored separately (noise: via the same
SEC-fetch pattern in a competitor loop; questions + GT: by the human analyst).

Source files expected in materials/_source/:
    msft_10k_fy2025.htm                (SEC EDGAR, filed 2025-07-30)
    msft_q2fy26_call_raw_body.html     (transcript body carved from Motley Fool)
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_mod
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))


# ---- HTML → text ---------------------------------------------------------

_SCRIPT_STYLE = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_TAGS = {
    "p", "div", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "tr", "br", "hr",
    "header", "footer",
}
_TAG = re.compile(r"<(/?)(\w+)([^>]*)>", re.IGNORECASE)


def html_to_text(html: str) -> str:
    """
    Deterministic HTML → plain text.

    - Drops <script>, <style>, <noscript> and HTML comments.
    - Block-level tags force a paragraph break.
    - Everything else is stripped; entities decoded; whitespace collapsed.
    """
    html = _COMMENT.sub("", html)
    html = _SCRIPT_STYLE.sub("", html)

    parts: list[str] = []
    pos = 0
    for m in _TAG.finditer(html):
        chunk = html[pos:m.start()]
        if chunk:
            parts.append(chunk)
        tag = m.group(2).lower()
        if tag in _BLOCK_TAGS:
            parts.append("\n\n")
        pos = m.end()
    chunk = html[pos:]
    if chunk:
        parts.append(chunk)

    text = "".join(parts)
    text = html_mod.unescape(text)
    text = text.replace("\xa0", " ").replace("​", "")
    # Collapse runs of whitespace within a line; preserve paragraph breaks.
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    # Collapse > 1 blank line into a single blank line.
    out: list[str] = []
    blank = False
    for ln in lines:
        if ln == "":
            if not blank:
                out.append("")
                blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip() + "\n"


# ---- 10-K-specific cleanup ----------------------------------------------

def strip_10k_html_header(html: str) -> str:
    """
    SEC inline-XBRL HTML prepends a huge XBRL fact dictionary (taxonomy IRIs,
    US-GAAP facts, schema references) to the document. It contains no narrative
    content and inflates token counts. We trim everything before the cover-page
    marker 'UNITED STATES\\nSECURITIES AND EXCHANGE COMMISSION'.

    If the marker isn't found, return the HTML unchanged (the caller will still
    get a usable document).
    """
    idx = html.find("UNITED STATES")
    if idx < 0:
        return html
    # Back up to the start of the enclosing opening tag so we keep clean HTML.
    tag_start = html.rfind("<", 0, idx)
    return html[tag_start if tag_start > 0 else idx:]


def strip_10k_artifacts(text: str) -> str:
    """
    Post-text-extraction cleanup of common 10-K artifacts:
      - Long runs of '.' used as table dots.
      - Underscore rulers.
      - Runaway blank lines.
    """
    text = re.sub(r"\.{3,}", "…", text)
    text = re.sub(r"_{3,}", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# ---- meta + token count --------------------------------------------------

@dataclass(frozen=True)
class PreparedDoc:
    text: str
    token_count: int
    sha256: str


def prepare_doc(text: str) -> PreparedDoc:
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    tokens = _count_tokens(text)
    return PreparedDoc(text=text, token_count=tokens, sha256=sha)


def _count_tokens(text: str) -> int:
    """
    Authoritative count via Anthropic tokenizer; falls back to char/4 heuristic
    if the SDK is not yet wired up or credentials missing.
    """
    try:
        from anthropic import Anthropic  # noqa: WPS433
        client = Anthropic()
        resp = client.messages.count_tokens(
            model="claude-opus-4-7-20250101",   # placeholder; any Opus snapshot works
            messages=[{"role": "user", "content": text}],
        )
        return int(resp.input_tokens)
    except Exception:
        return max(1, len(text) // 4)


# ---- writers -------------------------------------------------------------

def write_target_bundle(
    materials_dir: Path,
    report_id: str,
    company_name: str,
    fiscal_year: int,
    tenk: PreparedDoc,
    call: PreparedDoc,
    call_quarter: str,
    call_fiscal_year: int,
    call_date: str,
    tenk_source_url: str,
    call_source_url: str,
) -> dict[str, dict]:
    """Write target/<report_id>/10k.{txt,meta.json} and earnings_call.{txt,meta.json}."""
    target_dir = materials_dir / "target" / report_id
    target_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "10k.txt").write_text(tenk.text, encoding="utf-8")
    (target_dir / "10k.meta.json").write_text(json.dumps({
        "report_id": report_id,
        "company_name": company_name,
        "fiscal_year": fiscal_year,
        "sha256": tenk.sha256,
        "token_count": tenk.token_count,
        "source_url": tenk_source_url,
    }, indent=2), encoding="utf-8")

    (target_dir / "earnings_call.txt").write_text(call.text, encoding="utf-8")
    (target_dir / "earnings_call.meta.json").write_text(json.dumps({
        "report_id": report_id,
        "quarter": call_quarter,
        "fiscal_year": call_fiscal_year,
        "call_date": call_date,
        "sha256": call.sha256,
        "token_count": call.token_count,
        "source_url": call_source_url,
    }, indent=2), encoding="utf-8")

    return {
        f"target/{report_id}/10k.txt": {
            "sha256": tenk.sha256, "token_count": tenk.token_count,
        },
        f"target/{report_id}/earnings_call.txt": {
            "sha256": call.sha256, "token_count": call.token_count,
        },
    }


def update_lock(materials_dir: Path, additions: dict[str, dict]) -> None:
    lock_path = materials_dir / "materials.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else {"files": {}}
    lock.setdefault("files", {}).update(additions)
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True), encoding="utf-8")


# ---- main ----------------------------------------------------------------

MSFT = dict(
    report_id="MSFT",
    company_name="Microsoft Corporation",
    fiscal_year=2025,
    tenk_source_url="https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630.htm",
    call_quarter="Q2",
    call_fiscal_year=2026,
    call_date="2026-01-28",
    call_source_url="https://www.fool.com/earnings/call-transcripts/2026/01/28/microsoft-msft-q2-2026-earnings-call-transcript/",
)

# Peer 10-Ks — realistic adjacent context an analyst would paste alongside MSFT.
PEERS = [
    dict(
        doc_id="aapl_10k_fy2025",
        ticker="AAPL",
        title="Apple Inc. Form 10-K FY2025",
        source_file="aapl_10k_fy2025.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
        fiscal_period="fiscal year ended September 27, 2025",
    ),
    dict(
        doc_id="googl_10k_fy2025",
        ticker="GOOGL",
        title="Alphabet Inc. Form 10-K FY2025",
        source_file="googl_10k_fy2025.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/goog-20251231.htm",
        fiscal_period="fiscal year ended December 31, 2025",
    ),
    dict(
        doc_id="amzn_10k_fy2025",
        ticker="AMZN",
        title="Amazon.com Inc. Form 10-K FY2025",
        source_file="amzn_10k_fy2025.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/1018724/000101872426000004/amzn-20251231.htm",
        fiscal_period="fiscal year ended December 31, 2025",
    ),
    dict(
        doc_id="nvda_10k_fy2026",
        ticker="NVDA",
        title="NVIDIA Corp Form 10-K FY2026",
        source_file="nvda_10k_fy2026.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm",
        fiscal_period="fiscal year ended January 25, 2026",
    ),
    dict(
        doc_id="crm_10k_fy2026",
        ticker="CRM",
        title="Salesforce Inc. Form 10-K FY2026",
        source_file="crm_10k_fy2026.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/1108524/000110852426000060/crm-20260131.htm",
        fiscal_period="fiscal year ended January 31, 2026",
    ),
    dict(
        doc_id="meta_10k_fy2025",
        ticker="META",
        title="Meta Platforms Inc. Form 10-K FY2025",
        source_file="meta_10k_fy2025.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/1326801/000162828026003942/meta-20251231.htm",
        fiscal_period="fiscal year ended December 31, 2025",
    ),
    dict(
        doc_id="orcl_10k_fy2025",
        ticker="ORCL",
        title="Oracle Corporation Form 10-K FY2025",
        source_file="orcl_10k_fy2025.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/1341439/000095017025087926/orcl-20250531.htm",
        fiscal_period="fiscal year ended May 31, 2025",
    ),
]


def write_noise_doc(
    materials_dir: Path,
    pair_target: str,
    noise_type: str,
    doc_id: str,
    title: str,
    ticker: str,
    source_url: str,
    fiscal_period: str,
    doc: PreparedDoc,
) -> dict[str, dict]:
    out_dir = materials_dir / "noise" / noise_type / pair_target
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{doc_id}.txt").write_text(doc.text, encoding="utf-8")
    (out_dir / f"{doc_id}.meta.json").write_text(json.dumps({
        "doc_id": doc_id,
        "noise_type": noise_type,
        "title": title,
        "ticker": ticker,
        "fiscal_period": fiscal_period,
        "sha256": doc.sha256,
        "token_count": doc.token_count,
        "source_url": source_url,
        "pair_target": pair_target,
    }, indent=2), encoding="utf-8")
    return {
        f"noise/{noise_type}/{pair_target}/{doc_id}.txt": {
            "sha256": doc.sha256, "token_count": doc.token_count,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--materials-dir", default=str(HARNESS_ROOT.parent / "materials"))
    parser.add_argument("--source-dir", default=str(HARNESS_ROOT.parent / "materials" / "_source"))
    parser.add_argument("--check", action="store_true", help="process but don't write outputs")
    parser.add_argument("--skip-target", action="store_true")
    parser.add_argument("--skip-noise", action="store_true")
    args = parser.parse_args()

    materials_dir = Path(args.materials_dir).resolve()
    source_dir = Path(args.source_dir).resolve()
    if not source_dir.exists():
        print(f"source dir not found: {source_dir}", file=sys.stderr)
        return 2

    all_lock_entries: dict[str, dict] = {}

    # ---- target bundle (MSFT 10-K + earnings call) ---------------------
    if not args.skip_target:
        tenk_raw = (source_dir / "msft_10k_fy2025.htm").read_text(encoding="utf-8", errors="replace")
        call_raw = (source_dir / "msft_q2fy26_call_raw_body.html").read_text(encoding="utf-8", errors="replace")
        tenk_doc = prepare_doc(strip_10k_artifacts(html_to_text(strip_10k_html_header(tenk_raw))))
        call_doc = prepare_doc(html_to_text(call_raw))
        print(f"target MSFT 10-K:  {tenk_doc.token_count:>7} tokens  sha={tenk_doc.sha256[:12]}")
        print(f"target MSFT call:  {call_doc.token_count:>7} tokens  sha={call_doc.sha256[:12]}")
        print(f"target combined:   {tenk_doc.token_count + call_doc.token_count:>7}")
        if not args.check:
            all_lock_entries.update(write_target_bundle(
                materials_dir=materials_dir, tenk=tenk_doc, call=call_doc, **MSFT,
            ))

    # ---- peer_materials noise corpus (paired to MSFT) ------------------
    if not args.skip_noise:
        pool_total = 0
        print("\n--- peer_materials noise (paired to MSFT) ---")
        for peer in PEERS:
            src = source_dir / peer["source_file"]
            raw = src.read_text(encoding="utf-8", errors="replace")
            doc = prepare_doc(strip_10k_artifacts(html_to_text(strip_10k_html_header(raw))))
            pool_total += doc.token_count
            print(f"  {peer['ticker']:<6}  {doc.token_count:>7} tokens  sha={doc.sha256[:12]}  {peer['doc_id']}")
            if not args.check:
                all_lock_entries.update(write_noise_doc(
                    materials_dir=materials_dir,
                    pair_target="MSFT",
                    noise_type="peer_materials",
                    doc_id=peer["doc_id"],
                    title=peer["title"],
                    ticker=peer["ticker"],
                    source_url=peer["source_url"],
                    fiscal_period=peer["fiscal_period"],
                    doc=doc,
                ))
        print(f"  pool total: {pool_total:,} tokens across {len(PEERS)} peers")

    if args.check:
        print("\n(--check) not writing outputs")
        return 0

    update_lock(materials_dir, all_lock_entries)
    print(f"\nlock updated: {materials_dir}/materials.lock.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
