from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def turn_pipeline_path(root: Path) -> Path:
    return root / "var" / "turn_pipeline.jsonl"


def content_record_path(root: Path) -> Path:
    return root / "var" / "content_record.jsonl"


def append_turn_record(record: dict[str, Any], *, root: Path) -> Path:
    path = turn_pipeline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return path


def append_content_record(record: dict[str, Any], *, root: Path) -> Path:
    path = content_record_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return path


def read_turn_records(
    path: Path,
    *,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session_id and str(row.get("session_id") or "") != session_id:
            continue
        rows.append(row)
    return rows
