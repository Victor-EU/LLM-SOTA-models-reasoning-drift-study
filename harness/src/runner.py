"""
Orchestrator for the COLLECT stage.

Design principle: run replicates within a cell back-to-back (serially) so the
Anthropic prompt cache stays warm across all reps_per_cell reps. Different
cells run in parallel up to `cfg.execution.max_concurrent_cells`.

    ┌────── cell A ──────┐     ┌────── cell B ──────┐
    │ rep0 → rep1 → rep6 │     │ rep0 → rep1 → rep6 │     (in parallel)
    └────────────────────┘     └────────────────────┘

Each cell writes reps_per_cell records to `data/raw/{cell_id}.jsonl` and the
same number of runs to the manifest. On resume, a cell skips any rep already
marked completed/excluded.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from anthropic import AsyncAnthropic

from .api import CallResult, run_analyst
from .cells import CellSpec, runs_for_cell
from .config import ExperimentConfig
from .cost import BudgetExceeded, CostTracker
from .manifest import Manifest, RunStatus, Stage
from .materials import Materials
from .persistence import WriterCache
from .tokens import BudgetError, resolve_budget
from .validation import validate_run

log = logging.getLogger(__name__)


async def run_collect_stage(
    client: AsyncAnthropic,
    cells: list[CellSpec],
    materials: Materials,
    cfg: ExperimentConfig,
    manifest: Manifest,
    cost_tracker: CostTracker,
    writers: WriterCache,
) -> None:
    """Run the collect stage for a list of cells."""
    # Pre-register all runs so `status` reports accurate denominators.
    for cell in cells:
        for run in runs_for_cell(cell, cfg.design.reps_per_cell):
            manifest.ensure_pending(
                run_id=run.run_id,
                cell_id=cell.cell_id,
                rep_idx=run.rep_idx,
                stage=Stage.COLLECT,
            )

    sem = asyncio.Semaphore(cfg.execution.max_concurrent_cells)

    async def run_one_cell(cell: CellSpec) -> None:
        async with sem:
            try:
                await _run_cell_serially(
                    cell=cell,
                    client=client,
                    materials=materials,
                    cfg=cfg,
                    manifest=manifest,
                    cost_tracker=cost_tracker,
                    writers=writers,
                )
            except BudgetExceeded:
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("cell %s failed: %s", cell.cell_id, e)

    try:
        await asyncio.gather(*(run_one_cell(c) for c in cells))
    except BudgetExceeded as e:
        log.error("BUDGET HARD STOP: %s", e)
        raise


async def _run_cell_serially(
    *,
    cell: CellSpec,
    client: AsyncAnthropic,
    materials: Materials,
    cfg: ExperimentConfig,
    manifest: Manifest,
    cost_tracker: CostTracker,
    writers: WriterCache,
) -> None:
    """Serial reps within one cell to preserve prompt-cache locality."""
    runs = runs_for_cell(cell, cfg.design.reps_per_cell)

    raw_writer = writers.for_cell(cfg.paths.raw_dir, cell.cell_id)

    log.info("starting cell %s (%s)", cell.cell_id, cell.describe())

    for run in runs:
        if manifest.is_done(run.run_id, Stage.COLLECT):
            log.debug("skip %s (already done)", run.run_id)
            continue

        cost_tracker.check_budget()
        manifest.mark_in_progress(run.run_id, Stage.COLLECT, started_at=time.time())

        try:
            record = await _run_single(
                run=run,
                client=client,
                materials=materials,
                cfg=cfg,
                cost_tracker=cost_tracker,
            )
        except BudgetError as e:
            log.warning("%s excluded at budget resolution: %s", run.run_id, e)
            manifest.mark_excluded(run.run_id, Stage.COLLECT, reason=str(e))
            raw_writer.append({
                "run_id": run.run_id,
                "cell_id": cell.cell_id,
                "rep_idx": run.rep_idx,
                "status": RunStatus.EXCLUDED.value,
                "error": str(e),
            })
            continue
        except Exception as e:  # noqa: BLE001
            log.warning("%s failed: %s", run.run_id, e)
            manifest.mark_failed(run.run_id, Stage.COLLECT, error=repr(e))
            raw_writer.append({
                "run_id": run.run_id,
                "cell_id": cell.cell_id,
                "rep_idx": run.rep_idx,
                "status": RunStatus.FAILED.value,
                "error": repr(e),
            })
            continue

        # Persist before marking complete, so the audit log is authoritative.
        raw_writer.append(record["raw_payload"])

        manifest.mark_completed(
            run_id=run.run_id,
            stage=Stage.COLLECT,
            completed_at=time.time(),
            realized_input_tokens=record["realized_input_tokens"],
            cache_read_input_tokens=record["cache_read_input_tokens"],
            cache_creation_input_tokens=record["cache_creation_input_tokens"],
            output_tokens=record["output_tokens"],
            thinking_tokens=record["thinking_tokens"],
            stop_reason=record["stop_reason"],
            meta=record["meta"],
        )


async def _run_single(
    *,
    run: Any,
    client: AsyncAnthropic,
    materials: Materials,
    cfg: ExperimentConfig,
    cost_tracker: CostTracker,
) -> dict[str, Any]:
    """Assemble, call, validate, and return a JSONL-ready record."""
    # 1) Token budget resolution.
    budget = await resolve_budget(client=client, run=run, materials=materials, cfg=cfg)

    # 2) Analyst call.
    result: CallResult = await run_analyst(client=client, prompt=budget.prompt, cfg=cfg)

    # 3) Cost.
    cost = cost_tracker.record(
        usage=result.usage,
        component="analyst",
        model=result.model or cfg.models.analyst.snapshot,
        run_id=run.run_id,
        stage=Stage.COLLECT,
    )

    # 4) Pre-registered validation (DESIGN §7.5).
    expected_qids = [q.q_id for q in materials.questions[run.cell.report_id]]
    validation = validate_run(
        result=result,
        realized_input_tokens=budget.realized_input_tokens,
        target_input_tokens=budget.target_input_tokens,
        expected_question_ids=expected_qids,
        cfg=cfg,
        pool_exhausted=budget.pool_exhausted,
        is_baseline=budget.is_baseline,
    )

    # 5) Build payload for JSONL persistence.
    payload: dict[str, Any] = {
        "run_id": run.run_id,
        "cell_id": run.cell.cell_id,
        "rep_idx": run.rep_idx,
        "report_id": run.cell.report_id,
        "fill_pct": run.cell.fill_pct,
        "position": run.cell.position,
        "noise_type": run.cell.noise_type,
        "model": result.model,
        "stop_reason": result.stop_reason,
        "latency_seconds": result.latency_seconds,
        "attempts": result.attempts,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cache_creation_input_tokens": result.usage.cache_creation_input_tokens,
            "cache_read_input_tokens": result.usage.cache_read_input_tokens,
            "thinking_tokens": result.usage.thinking_tokens,
            "thinking_tokens_source": result.usage.thinking_tokens_source,
        },
        "cost_usd": {
            "input": cost.input_usd,
            "cache_read": cost.cache_read_usd,
            "cache_write": cost.cache_write_usd,
            "output": cost.output_usd,
            "total": cost.total_usd,
        },
        "token_budget": {
            "target_input_tokens": budget.target_input_tokens,
            "realized_input_tokens": budget.realized_input_tokens,
            "realized_fill_pct": budget.realized_input_tokens / cfg.tokens.total_context_target,
            "iterations": budget.iterations,
            "pool_exhausted": budget.pool_exhausted,
        },
        "validation": {
            "exclude": validation.exclude,
            "reason": validation.reason,
            "flags": validation.flags,
        },
        "response_text": result.text,
        "noise_doc_ids": list(budget.prompt.noise_doc_ids),
    }
    if cfg.observability.persist_thinking_blocks:
        payload["thinking_text"] = result.thinking_text

    # If validation said exclude, surface as excluded (but still persisted).
    if validation.exclude:
        payload["status"] = RunStatus.EXCLUDED.value

    return {
        "raw_payload": payload,
        "realized_input_tokens": budget.realized_input_tokens,
        "cache_read_input_tokens": result.usage.cache_read_input_tokens,
        "cache_creation_input_tokens": result.usage.cache_creation_input_tokens,
        "output_tokens": result.usage.output_tokens,
        "thinking_tokens": result.usage.thinking_tokens,
        "stop_reason": result.stop_reason,
        "meta": {
            "latency_seconds": result.latency_seconds,
            "attempts": result.attempts,
            "validation_flags": validation.flags,
            "validation_reason": validation.reason,
        },
    }
