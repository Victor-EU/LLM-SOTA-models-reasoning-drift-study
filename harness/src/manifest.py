"""
Run state tracking — SQLite-backed for resumable execution.

Source of truth for "is this run done?" — raw JSONL files are append-only
audit logs; on conflict, manifest wins. Thread-safe: uses a per-process lock
on a single connection with WAL journaling.

Schema intentionally denormalized: one row per run, wide columns for the
fields we care about in status/resumption. Judge and extractor stages use
`stage` + `substage` columns on the same table.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


class RunStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXCLUDED = "excluded"   # e.g. realized fill out of tolerance


class Stage(str, Enum):
    COLLECT = "collect"
    EXTRACT = "extract"
    GRADE = "grade"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    cell_id: str
    rep_idx: int
    stage: Stage
    status: RunStatus
    attempts: int
    started_at: float | None
    completed_at: float | None
    realized_input_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None
    output_tokens: int | None
    thinking_tokens: int | None
    stop_reason: str | None
    error: str | None
    meta: dict[str, Any]


_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id                        TEXT NOT NULL,
    cell_id                       TEXT NOT NULL,
    rep_idx                       INTEGER NOT NULL,
    stage                         TEXT NOT NULL,
    status                        TEXT NOT NULL,
    attempts                      INTEGER NOT NULL DEFAULT 0,
    started_at                    REAL,
    completed_at                  REAL,
    realized_input_tokens         INTEGER,
    cache_read_input_tokens       INTEGER,
    cache_creation_input_tokens   INTEGER,
    output_tokens                 INTEGER,
    thinking_tokens               INTEGER,
    stop_reason                   TEXT,
    error                         TEXT,
    meta_json                     TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_runs_stage_status ON runs(stage, status);
CREATE INDEX IF NOT EXISTS idx_runs_cell ON runs(cell_id, stage);

CREATE TABLE IF NOT EXISTS costs (
    ts              REAL NOT NULL,
    component       TEXT NOT NULL,
    run_id          TEXT,
    stage           TEXT,
    model           TEXT,
    input_usd       REAL NOT NULL DEFAULT 0,
    cache_read_usd  REAL NOT NULL DEFAULT 0,
    cache_write_usd REAL NOT NULL DEFAULT 0,
    output_usd      REAL NOT NULL DEFAULT 0,
    total_usd       REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_costs_ts ON costs(ts);

CREATE TABLE IF NOT EXISTS experiment_meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""


class Manifest:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")
        self._conn.executescript(_DDL)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- transaction helper ---------------------------------------------

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ---- experiment meta -------------------------------------------------

    def set_meta(self, key: str, value: str) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO experiment_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM experiment_meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    # ---- run lifecycle ---------------------------------------------------

    def ensure_pending(self, run_id: str, cell_id: str, rep_idx: int, stage: Stage) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO runs(run_id, cell_id, rep_idx, stage, status) "
                "VALUES(?, ?, ?, ?, ?)",
                (run_id, cell_id, rep_idx, stage.value, RunStatus.PENDING.value),
            )

    def mark_in_progress(self, run_id: str, stage: Stage, started_at: float) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE runs SET status=?, started_at=?, attempts=attempts+1 "
                "WHERE run_id=? AND stage=?",
                (RunStatus.IN_PROGRESS.value, started_at, run_id, stage.value),
            )

    def mark_completed(
        self,
        run_id: str,
        stage: Stage,
        *,
        completed_at: float,
        realized_input_tokens: int | None = None,
        cache_read_input_tokens: int | None = None,
        cache_creation_input_tokens: int | None = None,
        output_tokens: int | None = None,
        thinking_tokens: int | None = None,
        stop_reason: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        with self._tx() as c:
            c.execute(
                """
                UPDATE runs SET
                    status = ?,
                    completed_at = ?,
                    realized_input_tokens = ?,
                    cache_read_input_tokens = ?,
                    cache_creation_input_tokens = ?,
                    output_tokens = ?,
                    thinking_tokens = ?,
                    stop_reason = ?,
                    error = NULL,
                    meta_json = ?
                WHERE run_id = ? AND stage = ?
                """,
                (
                    RunStatus.COMPLETED.value,
                    completed_at,
                    realized_input_tokens,
                    cache_read_input_tokens,
                    cache_creation_input_tokens,
                    output_tokens,
                    thinking_tokens,
                    stop_reason,
                    json.dumps(meta or {}),
                    run_id,
                    stage.value,
                ),
            )

    def mark_failed(self, run_id: str, stage: Stage, *, error: str) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE runs SET status=?, error=? WHERE run_id=? AND stage=?",
                (RunStatus.FAILED.value, error, run_id, stage.value),
            )

    def mark_excluded(self, run_id: str, stage: Stage, *, reason: str) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE runs SET status=?, error=? WHERE run_id=? AND stage=?",
                (RunStatus.EXCLUDED.value, reason, run_id, stage.value),
            )

    # ---- queries ---------------------------------------------------------

    def is_done(self, run_id: str, stage: Stage) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM runs WHERE run_id=? AND stage=?",
                (run_id, stage.value),
            ).fetchone()
        if row is None:
            return False
        return row["status"] in (RunStatus.COMPLETED.value, RunStatus.EXCLUDED.value)

    def pending_runs_for_cell(self, cell_id: str, stage: Stage) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT run_id FROM runs
                 WHERE cell_id=? AND stage=?
                   AND status NOT IN (?, ?)
                 ORDER BY rep_idx ASC
                """,
                (
                    cell_id,
                    stage.value,
                    RunStatus.COMPLETED.value,
                    RunStatus.EXCLUDED.value,
                ),
            ).fetchall()
        return [r["run_id"] for r in rows]

    def status_counts(self, stage: Stage) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM runs WHERE stage=? GROUP BY status",
                (stage.value,),
            ).fetchall()
        return {r["status"]: int(r["n"]) for r in rows}

    # ---- cost log --------------------------------------------------------

    def log_cost(
        self,
        *,
        ts: float,
        component: str,
        run_id: str | None,
        stage: Stage | None,
        model: str,
        input_usd: float,
        cache_read_usd: float,
        cache_write_usd: float,
        output_usd: float,
    ) -> None:
        total = input_usd + cache_read_usd + cache_write_usd + output_usd
        with self._tx() as c:
            c.execute(
                """
                INSERT INTO costs(
                    ts, component, run_id, stage, model,
                    input_usd, cache_read_usd, cache_write_usd, output_usd, total_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts, component, run_id,
                    stage.value if stage else None,
                    model, input_usd, cache_read_usd,
                    cache_write_usd, output_usd, total,
                ),
            )

    def cumulative_cost(self) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(total_usd), 0) AS total FROM costs"
            ).fetchone()
        return float(row["total"])
