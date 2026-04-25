"""
Extractor stage — normalize each analyst response into per-question JSON.

Runs on short context (just the raw response + expected question ids), so it
is not affected by long-context drift. Output: one line per
(run_id × question_id) into data/extracted/{cell_id}.jsonl.

Uses Haiku 4.5 for cost. Output schema: see PROMPTS.md §4 and rubric §8.1.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from .api import call_messages
from .config import ExperimentConfig
from .cost import CostTracker
from .manifest import Manifest, Stage
from .materials import Materials
from .persistence import WriterCache
from .prompts import EXTRACTOR_SYSTEM_PROMPT

log = logging.getLogger(__name__)


async def run_extract_stage(
    client: AsyncAnthropic,
    materials: Materials,
    cfg: ExperimentConfig,
    manifest: Manifest,
    cost_tracker: CostTracker,
    writers: WriterCache,
) -> None:
    """Process every completed COLLECT run that has not yet been extracted."""
    raw_files = sorted(Path(cfg.paths.raw_dir).glob("*.jsonl"))
    sem = asyncio.Semaphore(cfg.execution.max_concurrent_extract)

    async def handle_file(raw_path: Path) -> None:
        cell_id = raw_path.stem
        extracted_writer = writers.for_cell(cfg.paths.extracted_dir, cell_id)
        with raw_path.open("r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                run_id = rec.get("run_id")
                if not run_id:
                    continue
                if rec.get("status") in ("excluded", "failed"):
                    continue
                if manifest.is_done(run_id, Stage.EXTRACT):
                    continue
                async with sem:
                    await _extract_one(
                        raw_record=rec,
                        materials=materials,
                        cfg=cfg,
                        manifest=manifest,
                        cost_tracker=cost_tracker,
                        client=client,
                        writer=extracted_writer,
                    )

    await asyncio.gather(*(handle_file(p) for p in raw_files))


async def _extract_one(
    *,
    raw_record: dict[str, Any],
    materials: Materials,
    cfg: ExperimentConfig,
    manifest: Manifest,
    cost_tracker: CostTracker,
    client: AsyncAnthropic,
    writer: Any,
) -> None:
    run_id = raw_record["run_id"]
    cell_id = raw_record["cell_id"]
    report_id = raw_record["report_id"]
    manifest.ensure_pending(run_id, cell_id, raw_record["rep_idx"], Stage.EXTRACT)
    manifest.mark_in_progress(run_id, Stage.EXTRACT, started_at=time.time())

    expected_qids = [q.q_id for q in materials.questions[report_id]]

    user_text = (
        f"EXPECTED_QIDS: {json.dumps(expected_qids)}\n\n"
        f"RAW_RESPONSE:\n```\n{raw_record.get('response_text', '')}\n```\n\n"
        f"Return the JSON array now."
    )

    try:
        result = await call_messages(
            client=client,
            model=cfg.models.extractor.snapshot,
            system=[{"type": "text", "text": EXTRACTOR_SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
            max_tokens=cfg.models.extractor.max_output_tokens,
            temperature=cfg.models.extractor.temperature,
            thinking_effort=None,
            extra_headers=None,
            retry=cfg.execution.retry,
            per_call_timeout_seconds=300,
        )
    except Exception as e:  # noqa: BLE001
        manifest.mark_failed(run_id, Stage.EXTRACT, error=repr(e))
        return

    cost_tracker.record(
        usage=result.usage,
        component="extractor",
        model=result.model or cfg.models.extractor.snapshot,
        run_id=run_id,
        stage=Stage.EXTRACT,
    )

    items = _safe_parse_items(result.text, expected_qids)
    for item in items:
        writer.append({
            "run_id": run_id,
            "cell_id": cell_id,
            "report_id": report_id,
            "fill_pct": raw_record["fill_pct"],
            "position": raw_record["position"],
            "noise_type": raw_record["noise_type"],
            "rep_idx": raw_record["rep_idx"],
            **item,
        })

    manifest.mark_completed(
        run_id=run_id,
        stage=Stage.EXTRACT,
        completed_at=time.time(),
        realized_input_tokens=result.usage.input_tokens,
        cache_read_input_tokens=result.usage.cache_read_input_tokens,
        cache_creation_input_tokens=result.usage.cache_creation_input_tokens,
        output_tokens=result.usage.output_tokens,
        stop_reason=result.stop_reason,
        meta={"n_extracted": len(items)},
    )


def _safe_parse_items(text: str, expected_qids: list[str]) -> list[dict[str, Any]]:
    """Return one record per expected qid; fall back to placeholders on parse failure."""
    stripped = text.strip()
    # Strip ```json or ``` opening fence even when the closing fence is absent
    # (Haiku occasionally truncates the trailing ``` when output approaches
    # max_tokens but the JSON itself is still complete).
    open_fence = re.match(r"^```(?:json)?\s*\n", stripped)
    if open_fence:
        stripped = stripped[open_fence.end():]
    if stripped.endswith("```"):
        stripped = stripped[:-3].rstrip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    # Last-ditch: extract first balanced [...] block from within surrounding prose.
    match = re.search(r"\[.*\]", stripped, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return [
        {"q_id": qid, "parsed_ok": False, "parse_notes": "extractor_output_unparseable"}
        for qid in expected_qids
    ]
