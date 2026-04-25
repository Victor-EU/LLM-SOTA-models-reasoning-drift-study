"""
Materials loader — target bundle (10-K + earnings call), noise corpus,
questions, ground truth.

Materials are produced by a separate prep pipeline (DESIGN §6 and the
`scripts/build_materials.py` script, to be added during material-prep phase).
This module defines the on-disk schema and the in-memory dataclasses the
harness consumes.

On-disk layout (under cfg.paths.materials_dir):

    target/
        MSFT/
            10k.txt                     # normalized 10-K text
            10k.meta.json               # {company_name, fiscal_year, sha256, token_count}
            earnings_call.txt           # normalized earnings-call transcript
            earnings_call.meta.json     # {quarter, fiscal_year, call_date, sha256, token_count}
    noise/
        adversarial_near/
            MSFT/                       # paired-to-MSFT competitor 10-Ks
                alphabet.txt
                alphabet.meta.json
                amazon.txt / .meta.json
                oracle.txt / ...
                salesforce.txt / ...
                sap.txt / ...
                meta.txt / ...
    questions/
        MSFT.json                       # list[Question]
    ground_truth/
        MSFT.json                       # list[GroundTruth]; tier 3 entries
                                         # hold evidentiary_anchors (not
                                         # conclusions). See DESIGN §3.1.
    materials.lock.json                 # SHA-256 of every file above

`load_materials` reads the layout above. It will fail until prep runs.
`verify_lock` is the primary integrity check — `run_experiment.py` MUST call
it before any API calls.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---- dataclasses --------------------------------------------------------

@dataclass(frozen=True)
class TargetReport:
    report_id: str           # "MSFT"
    company_name: str        # "Microsoft Corporation"
    fiscal_year: int
    text: str
    sha256: str
    token_count: int


@dataclass(frozen=True)
class EarningsCall:
    report_id: str           # "MSFT"
    quarter: str             # e.g. "Q2"
    fiscal_year: int         # FY the quarter falls in
    call_date: str           # ISO date
    text: str
    sha256: str
    token_count: int


@dataclass(frozen=True)
class TargetBundle:
    """The full target materials for one company: 10-K + latest earnings call."""
    report_id: str
    company_name: str
    report: TargetReport
    earnings_call: EarningsCall

    @property
    def combined_token_count(self) -> int:
        return self.report.token_count + self.earnings_call.token_count


@dataclass(frozen=True)
class NoiseDoc:
    doc_id: str              # "alphabet_10k_fy24"
    noise_type: str          # "adversarial_near"
    title: str
    text: str
    sha256: str
    token_count: int
    # For adversarial_near, the target report this doc is paired with.
    pair_target: str | None


@dataclass(frozen=True)
class Question:
    q_id: str                # "MSFT-F-01"
    report_id: str           # "MSFT"
    tier: int                # 1 | 2 | 3
    prompt: str


@dataclass(frozen=True)
class EvidentiaryAnchor:
    """
    A specific material disclosure a sound Tier-3 analysis should engage with.

    Anchors describe disclosures that EXIST in the target materials — not
    conclusions the analyst must reach. See DESIGN §3.1 and RUBRIC.md for the
    process-not-verdict grading philosophy.

    `engagement_signals` — concrete, deterministic cues that mark a response
    as having engaged with the anchor. If the response surfaces ≥1 signal,
    it counts toward `evidentiary_breadth`. Added in rubric v2.1 to remove
    judge discretion on what "engaged" means.

    `not_engagement` — a short negative example (generic phrasing that does
    NOT count as engagement). Reinforces the signal list.
    """
    anchor_id: str              # e.g. "MSFT-S-01-a"
    summary: str                # 1-2 sentences describing the disclosure
    citation_span: str          # specific Item/section/footnote/speaker-turn
    source: str                 # "10-K" | "earnings_call"
    engagement_signals: tuple[str, ...] = ()
    not_engagement: str | None = None


@dataclass(frozen=True)
class GroundTruth:
    q_id: str
    tier: int
    # Tier 1/2: numeric or short string canonical answer. Tier 3: unused.
    canonical_answer: Any
    unit: str | None
    tolerance_abs: float | None
    tolerance_rel: float | None
    citation_spans: tuple[str, ...]
    # Peer-document values that could be mis-attributed to the target
    # (programmatic cross-contamination detection on Tier 1/2).
    common_distractors: tuple[Any, ...]
    # Tier 3 only: material disclosures the analyst should engage with.
    # NOT conclusions they must reach.
    evidentiary_anchors: tuple[EvidentiaryAnchor, ...] | None


@dataclass(frozen=True)
class Materials:
    target_bundles: dict[str, TargetBundle]       # keyed by report_id
    noise: dict[str, list[NoiseDoc]]               # keyed by noise_type
    questions: dict[str, list[Question]]           # keyed by report_id
    ground_truth: dict[str, GroundTruth]           # keyed by q_id
    lock_sha256: str

    # Backwards-compatible accessor for earlier harness code paths that
    # read `materials.reports[report_id]`. Returns the 10-K TargetReport.
    @property
    def reports(self) -> dict[str, TargetReport]:
        return {rid: b.report for rid, b in self.target_bundles.items()}


# ---- loader -------------------------------------------------------------

def load_materials(materials_dir: Path, lock_path: Path) -> Materials:
    if not lock_path.exists():
        raise FileNotFoundError(
            f"materials.lock.json not found at {lock_path}. "
            f"Run scripts/build_materials.py first."
        )
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_sha = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    verify_lock(materials_dir, lock)

    target_bundles = _load_target_bundles(materials_dir / "target")
    noise = _load_noise(materials_dir / "noise")
    questions = _load_questions(materials_dir / "questions", target_bundles.keys())
    ground_truth = _load_ground_truth(materials_dir / "ground_truth", questions)

    return Materials(
        target_bundles=target_bundles,
        noise=noise,
        questions=questions,
        ground_truth=ground_truth,
        lock_sha256=lock_sha,
    )


def verify_lock(materials_dir: Path, lock: dict[str, Any]) -> None:
    for rel_path, expected in lock.get("files", {}).items():
        full = materials_dir / rel_path
        if not full.exists():
            raise FileNotFoundError(f"locked material missing: {full}")
        actual = hashlib.sha256(full.read_bytes()).hexdigest()
        if actual != expected["sha256"]:
            raise ValueError(
                f"hash mismatch for {rel_path}: "
                f"expected {expected['sha256']}, got {actual}"
            )


# ---- loader helpers (stubs) ---------------------------------------------
# Implementation is intentionally minimal: prep pipeline defines the exact
# schema of each .meta.json file. These helpers will be fleshed out in the
# material-prep phase.

def _load_target_bundles(target_dir: Path) -> dict[str, TargetBundle]:
    """Each target/{report_id}/ → one TargetBundle (10-K + earnings call)."""
    out: dict[str, TargetBundle] = {}
    if not target_dir.exists():
        raise FileNotFoundError(f"target dir missing: {target_dir}")
    for report_dir in sorted(d for d in target_dir.iterdir() if d.is_dir()):
        rid = report_dir.name
        tenk_txt = (report_dir / "10k.txt").read_text(encoding="utf-8")
        tenk_meta = json.loads((report_dir / "10k.meta.json").read_text(encoding="utf-8"))
        call_txt = (report_dir / "earnings_call.txt").read_text(encoding="utf-8")
        call_meta = json.loads((report_dir / "earnings_call.meta.json").read_text(encoding="utf-8"))
        report = TargetReport(
            report_id=tenk_meta["report_id"],
            company_name=tenk_meta["company_name"],
            fiscal_year=int(tenk_meta["fiscal_year"]),
            text=tenk_txt,
            sha256=tenk_meta["sha256"],
            token_count=int(tenk_meta["token_count"]),
        )
        call = EarningsCall(
            report_id=call_meta["report_id"],
            quarter=call_meta["quarter"],
            fiscal_year=int(call_meta["fiscal_year"]),
            call_date=call_meta["call_date"],
            text=call_txt,
            sha256=call_meta["sha256"],
            token_count=int(call_meta["token_count"]),
        )
        out[rid] = TargetBundle(
            report_id=rid,
            company_name=report.company_name,
            report=report,
            earnings_call=call,
        )
    if not out:
        raise ValueError(f"no target bundles under {target_dir}")
    return out


def _load_noise(noise_dir: Path) -> dict[str, list[NoiseDoc]]:
    """Walk noise/{noise_type}/{pair_target}/*.txt (+ sibling .meta.json)."""
    out: dict[str, list[NoiseDoc]] = {}
    if not noise_dir.exists():
        return out
    for type_dir in sorted(d for d in noise_dir.iterdir() if d.is_dir()):
        noise_type = type_dir.name
        docs: list[NoiseDoc] = []
        for pair_dir in sorted(d for d in type_dir.iterdir() if d.is_dir()):
            pair_target = pair_dir.name
            for txt in sorted(pair_dir.glob("*.txt")):
                meta_path = txt.with_suffix(".meta.json")
                if not meta_path.exists():
                    raise FileNotFoundError(f"missing meta: {meta_path}")
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                docs.append(NoiseDoc(
                    doc_id=meta["doc_id"],
                    noise_type=meta["noise_type"],
                    title=meta["title"],
                    text=txt.read_text(encoding="utf-8"),
                    sha256=meta["sha256"],
                    token_count=int(meta["token_count"]),
                    pair_target=meta.get("pair_target"),
                ))
        out[noise_type] = docs
    return out


def _load_questions(
    questions_dir: Path, report_ids: Any
) -> dict[str, list[Question]]:
    """Load questions/{report_id}.json for each expected target bundle."""
    out: dict[str, list[Question]] = {}
    for rid in report_ids:
        path = questions_dir / f"{rid}.json"
        if not path.exists():
            raise FileNotFoundError(f"missing question bank: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"{path} must be a non-empty JSON list")
        out[rid] = [
            Question(
                q_id=q["q_id"],
                report_id=q["report_id"],
                tier=int(q["tier"]),
                prompt=q["prompt"],
            )
            for q in raw
        ]
    return out


def _load_ground_truth(
    gt_dir: Path, questions: dict[str, list[Question]]
) -> dict[str, GroundTruth]:
    """Load ground_truth/{report_id}.json; assert every question has a matching entry."""
    out: dict[str, GroundTruth] = {}
    expected_qids: set[str] = {q.q_id for qs in questions.values() for q in qs}

    for rid in questions.keys():
        path = gt_dir / f"{rid}.json"
        if not path.exists():
            raise FileNotFoundError(f"missing ground-truth file: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        for gt in raw:
            anchors = gt.get("evidentiary_anchors")
            anchor_tuple: tuple[EvidentiaryAnchor, ...] | None = None
            if anchors is not None:
                anchor_tuple = tuple(
                    EvidentiaryAnchor(
                        anchor_id=a["anchor_id"],
                        summary=a["summary"],
                        citation_span=a["citation_span"],
                        source=a["source"],
                        engagement_signals=tuple(a.get("engagement_signals", ())),
                        not_engagement=a.get("not_engagement"),
                    )
                    for a in anchors
                )
            out[gt["q_id"]] = GroundTruth(
                q_id=gt["q_id"],
                tier=int(gt["tier"]),
                canonical_answer=gt.get("canonical_answer"),
                unit=gt.get("unit"),
                tolerance_abs=gt.get("tolerance_abs"),
                tolerance_rel=gt.get("tolerance_rel"),
                citation_spans=tuple(gt.get("citation_spans", ())),
                common_distractors=tuple(gt.get("common_distractors", ())),
                evidentiary_anchors=anchor_tuple,
            )

    missing = expected_qids - set(out.keys())
    if missing:
        raise ValueError(f"ground-truth entries missing for q_ids: {sorted(missing)}")
    extra = set(out.keys()) - expected_qids
    if extra:
        raise ValueError(f"ground-truth entries for unknown q_ids: {sorted(extra)}")

    # Tier-specific schema checks.
    for qid, gt in out.items():
        if gt.tier in (1, 2):
            if gt.canonical_answer is None:
                raise ValueError(f"{qid}: tier {gt.tier} must have canonical_answer")
            if gt.evidentiary_anchors:
                raise ValueError(f"{qid}: tier {gt.tier} should not have evidentiary_anchors")
        elif gt.tier == 3:
            if not gt.evidentiary_anchors:
                raise ValueError(f"{qid}: tier 3 must have evidentiary_anchors")
        else:
            raise ValueError(f"{qid}: unknown tier {gt.tier}")

    return out
