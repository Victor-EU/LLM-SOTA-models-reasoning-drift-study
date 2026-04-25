"""
Append-only JSONL writers for raw/extracted/graded artifacts.

One file per cell per stage, e.g.:
    data/raw/{cell_id}.jsonl
    data/extracted/{cell_id}.jsonl
    data/graded/{cell_id}.jsonl

Each line is one record (one run for raw; one run × question for extracted/graded).
File writes are serialized per-file with a lock to avoid interleaved lines
when multiple coroutines within the same cell finish concurrently — though
by design (cell-serial execution) this is rare.

The manifest DB is the source of truth for status. These files are audit logs:
safe to truncate or re-derive from manifest + API responses.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        record = {"_ts": time.time(), **record}
        line = json.dumps(record, ensure_ascii=False, default=_default_serializer)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    @property
    def path(self) -> Path:
        return self._path


def _default_serializer(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


class WriterCache:
    """Lazy per-(stage,cell) writer cache so we open each file only once per process."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._cache: dict[Path, JsonlWriter] = {}
        self._lock = threading.Lock()

    def for_cell(self, stage_dir: Path, cell_id: str) -> JsonlWriter:
        path = stage_dir / f"{cell_id}.jsonl"
        with self._lock:
            w = self._cache.get(path)
            if w is None:
                w = JsonlWriter(path)
                self._cache[path] = w
        return w
