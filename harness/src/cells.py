"""
Cell-spec generation.

A "cell" is a cartesian combination of (report, fill_pct, position, noise_type).
Each cell is run `reps_per_cell` times. Within a cell, all reps share a cacheable
prefix — shuffling is done by run_id only on the question block.

Cell IDs are deterministic hashes so resumption across machines / restarts is safe.
"""
from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass
from typing import Iterable

from .config import ExperimentConfig, PilotCellOverride


@dataclass(frozen=True)
class CellSpec:
    cell_id: str
    report_id: str
    fill_pct: float          # 0.0 (baseline) up to max of cfg.design.fill_levels (e.g. 0.95)
    position: str | None     # 'start' | 'middle' | 'end' | None for baseline
    noise_type: str | None   # 'peer_materials' | ... | None for baseline

    @property
    def is_baseline(self) -> bool:
        return self.fill_pct == 0.0

    def describe(self) -> str:
        if self.is_baseline:
            return f"{self.report_id} baseline(0%)"
        return (
            f"{self.report_id} fill={int(self.fill_pct * 100)}% "
            f"pos={self.position} noise={self.noise_type}"
        )


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    cell: CellSpec
    rep_idx: int


# ---- id helpers ----------------------------------------------------------

def make_cell_id(report: str, fill: float, position: str | None, noise: str | None) -> str:
    payload = f"{report}|{fill:.2f}|{position or '-'}|{noise or '-'}"
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"c_{report}_{int(fill * 100):02d}_{position or 'X'}_{noise or 'X'}_{h}"


def make_run_id(cell_id: str, rep_idx: int) -> str:
    return f"{cell_id}__r{rep_idx:02d}"


# ---- generation ----------------------------------------------------------

def generate_cells(cfg: ExperimentConfig) -> list[CellSpec]:
    """Enumerate every cell in the full design grid."""
    cells: list[CellSpec] = []

    # Baseline: 0% fill, one per report (no position, no noise).
    for report in cfg.design.reports:
        cells.append(
            CellSpec(
                cell_id=make_cell_id(report, 0.0, None, None),
                report_id=report,
                fill_pct=0.0,
                position=None,
                noise_type=None,
            )
        )

    # Non-baseline: fill × position × noise × report.
    nonzero_fills = tuple(f for f in cfg.design.fill_levels if f > 0.0)
    for report, fill, position, noise in itertools.product(
        cfg.design.reports,
        nonzero_fills,
        cfg.design.positions,
        cfg.design.noise_types,
    ):
        cells.append(
            CellSpec(
                cell_id=make_cell_id(report, fill, position, noise),
                report_id=report,
                fill_pct=fill,
                position=position,
                noise_type=noise,
            )
        )

    return cells


def filter_to_pilot(all_cells: list[CellSpec], cfg: ExperimentConfig) -> list[CellSpec]:
    """Return only the cells listed in `pilot.cells` (DESIGN §10.2)."""
    wanted: set[str] = set()
    for override in cfg.pilot.cells:
        cid = make_cell_id(override.report, override.fill, override.position, override.noise)
        wanted.add(cid)

    result = [c for c in all_cells if c.cell_id in wanted]
    missing = wanted - {c.cell_id for c in result}
    if missing:
        raise ValueError(f"pilot cells not found in generated grid: {missing}")
    return result


def runs_for_cell(cell: CellSpec, reps: int) -> list[RunSpec]:
    return [RunSpec(run_id=make_run_id(cell.cell_id, i), cell=cell, rep_idx=i) for i in range(reps)]


# ---- summary -------------------------------------------------------------

def summarize(cells: Iterable[CellSpec], reps: int) -> dict[str, int]:
    cells = list(cells)
    baseline = [c for c in cells if c.is_baseline]
    non = [c for c in cells if not c.is_baseline]
    return {
        "total_cells": len(cells),
        "baseline_cells": len(baseline),
        "non_baseline_cells": len(non),
        "total_runs": len(cells) * reps,
    }
