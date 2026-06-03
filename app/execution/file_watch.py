from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.workspace.manager import WorkspaceError, manager

_EVENTS_REL = "logs/watch_events.jsonl"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _events_path(user_id: str, session_id: str) -> Path:
    return manager.session_dir(user_id, session_id) / _EVENTS_REL


def append_watch_event(
    *,
    user_id: str,
    session_id: str,
    watch_id: str,
    event: str,
    path: str,
    meta: dict | None = None,
) -> None:
    rec = {
        "ts": _utc_iso(),
        "watch_id": watch_id,
        "event": event,
        "path": path,
    }
    if meta:
        rec["meta"] = meta
    p = _events_path(user_id, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


@dataclass
class _WatchState:
    watch_id: str
    user_id: str
    session_id: str
    paths: list[str]
    poll_interval: float
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    last_sig: dict[str, tuple[int, int]] = field(default_factory=dict)


_watches: dict[str, _WatchState] = {}
_lock = threading.Lock()


def _file_sig(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
        return int(st.st_mtime_ns), int(st.st_size)
    except OSError:
        return None


def _poll_loop(state: _WatchState) -> None:
    ws_root = manager.session_dir(state.user_id, state.session_id)
    while not state.stop_event.wait(state.poll_interval):
        for rel in state.paths:
            try:
                target = manager.resolve(state.user_id, state.session_id, rel)
            except WorkspaceError:
                continue
            sig = _file_sig(target)
            key = rel
            prev = state.last_sig.get(key)
            if sig is None:
                if prev is not None:
                    append_watch_event(
                        user_id=state.user_id,
                        session_id=state.session_id,
                        watch_id=state.watch_id,
                        event="deleted",
                        path=rel,
                    )
                    state.last_sig.pop(key, None)
                continue
            if prev is None:
                state.last_sig[key] = sig
                append_watch_event(
                    user_id=state.user_id,
                    session_id=state.session_id,
                    watch_id=state.watch_id,
                    event="watching",
                    path=rel,
                    meta={"size": sig[1]},
                )
                continue
            if sig != prev:
                state.last_sig[key] = sig
                append_watch_event(
                    user_id=state.user_id,
                    session_id=state.session_id,
                    watch_id=state.watch_id,
                    event="modify",
                    path=rel,
                    meta={"size": sig[1], "mtime_ns": sig[0]},
                )


def start_watch(
    *,
    user_id: str,
    session_id: str,
    paths: list[str],
    poll_interval_sec: float | None = None,
) -> dict:
    rel_paths = [p.strip().replace("\\", "/") for p in paths if p and p.strip()]
    if not rel_paths:
        raise WorkspaceError("paths must not be empty")
    for rel in rel_paths:
        manager.resolve(user_id, session_id, rel)

    interval = poll_interval_sec if poll_interval_sec is not None else settings.file_watch_poll_interval_default
    interval = max(0.5, min(float(interval), 60.0))

    watch_id = uuid.uuid4().hex[:12]
    state = _WatchState(
        watch_id=watch_id,
        user_id=user_id,
        session_id=session_id,
        paths=rel_paths,
        poll_interval=interval,
    )
    thread = threading.Thread(
        target=_poll_loop,
        args=(state,),
        name=f"file-watch-{watch_id}",
        daemon=True,
    )
    state.thread = thread

    with _lock:
        _watches[watch_id] = state
    thread.start()

    append_watch_event(
        user_id=user_id,
        session_id=session_id,
        watch_id=watch_id,
        event="watch_start",
        path=",".join(rel_paths),
        meta={"poll_interval_sec": interval},
    )
    return {
        "ok": True,
        "watch_id": watch_id,
        "paths": rel_paths,
        "poll_interval_sec": interval,
        "events_path": _EVENTS_REL,
    }


def stop_watch(*, user_id: str, session_id: str, watch_id: str) -> dict:
    wid = (watch_id or "").strip()
    if not wid:
        raise WorkspaceError("watch_id is required")
    with _lock:
        state = _watches.pop(wid, None)
    if state is None:
        raise WorkspaceError(f"watch {wid!r} not found")
    if state.user_id != user_id or state.session_id != session_id:
        raise WorkspaceError("watch session mismatch")
    state.stop_event.set()
    if state.thread is not None:
        state.thread.join(timeout=state.poll_interval + 2)

    append_watch_event(
        user_id=user_id,
        session_id=session_id,
        watch_id=wid,
        event="watch_stop",
        path=",".join(state.paths),
    )
    return {"ok": True, "watch_id": wid, "stopped": True}


def list_watches(*, user_id: str, session_id: str) -> dict:
    with _lock:
        items = [
            {
                "watch_id": s.watch_id,
                "paths": list(s.paths),
                "poll_interval_sec": s.poll_interval,
            }
            for s in _watches.values()
            if s.user_id == user_id and s.session_id == session_id
        ]
    return {"ok": True, "watches": items}
