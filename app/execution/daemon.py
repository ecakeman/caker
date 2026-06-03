from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.execution.exec_pending import validate_command
from app.execution.exec_runner import ExecError, build_exec_argv
from app.observability.session_log import _utc_ts, append_sandbox_log, log_for_ids
from app.workspace.manager import WorkspaceError, manager

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_REGISTRY_REL = "logs/daemons/registry.json"
_DAEMONS_DIR = "logs/daemons"


@dataclass
class DaemonRecord:
    name: str
    command: str
    started_at: str
    mode: str
    log_path: str
    status: str = "running"
    pid_file: str | None = None
    last_checked_at: str | None = None


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_name(name: str) -> str:
    n = (name or "").strip()
    if not _NAME_RE.fullmatch(n):
        raise ExecError("daemon name must be 1-64 chars of [A-Za-z0-9_-]")
    return n


def _registry_path(user_id: str, session_id: str) -> Path:
    return manager.session_dir(user_id, session_id) / _REGISTRY_REL


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"daemons": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ExecError(f"invalid daemon registry: {e}") from e
    if not isinstance(data, dict):
        raise ExecError("invalid daemon registry shape")
    daemons = data.get("daemons")
    if not isinstance(daemons, list):
        daemons = []
    return {"daemons": daemons}


def _save_registry(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_in_container(
    *,
    user_id: str,
    session_id: str,
    workspace_host: Path,
    command: str,
    timeout_sec: int = 30,
) -> subprocess.CompletedProcess[str]:
    argv = build_exec_argv(
        user_id=user_id,
        session_id=session_id,
        workspace_host=workspace_host,
        command=command,
        cwd=None,
    )
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ExecError(f"daemon control timeout after {timeout_sec}s") from e
    except OSError as e:
        raise ExecError(str(e)) from e


def _start_script(name: str, command: str) -> str:
    q_name = shlex.quote(name)
    q_cmd = shlex.quote(command)
    log = f"{_DAEMONS_DIR}/{name}.log"
    pid = f"{_DAEMONS_DIR}/{name}.pid"
    return (
        f"mkdir -p {_DAEMONS_DIR} && "
        f"if command -v tmux >/dev/null 2>&1; then "
        f"  if tmux has-session -t {q_name} 2>/dev/null; then echo 'daemon already running' >&2; exit 2; fi; "
        f"  tmux new-session -d -s {q_name} "
        f"    \"cd {settings.sandbox_venue_mount} && {command} >> {log} 2>&1; "
        f"echo '[daemon] exit:'\\$? >> {log}\"; "
        f"  echo tmux; "
        f"else "
        f"  if [ -f {shlex.quote(pid)} ] && kill -0 \"$(cat {shlex.quote(pid)})\" 2>/dev/null; then "
        f"echo 'daemon already running' >&2; exit 2; fi; "
        f"  nohup sh -c 'cd {settings.sandbox_venue_mount} && {q_cmd}' >> {shlex.quote(log)} 2>&1 & "
        f"  echo $! > {shlex.quote(pid)}; "
        f"  echo nohup; "
        f"fi"
    )


def _status_script(name: str, mode: str) -> str:
    q_name = shlex.quote(name)
    pid = f"{_DAEMONS_DIR}/{name}.pid"
    if mode == "tmux":
        return f"tmux has-session -t {q_name} 2>/dev/null && echo running || echo exited"
    q_pid = shlex.quote(pid)
    return f"if [ -f {q_pid} ] && kill -0 \"$(cat {q_pid})\" 2>/dev/null; then echo running; else echo exited; fi"


def _attach_script(name: str, mode: str, tail_lines: int) -> str:
    q_name = shlex.quote(name)
    log = f"{_DAEMONS_DIR}/{name}.log"
    if mode == "tmux":
        return (
            f"tmux capture-pane -p -t {q_name} -S -{max(1, tail_lines)} 2>/dev/null || "
            f"tail -n {tail_lines} {shlex.quote(log)}"
        )
    return f"tail -n {tail_lines} {shlex.quote(log)}"


def _stop_script(name: str, mode: str) -> str:
    q_name = shlex.quote(name)
    pid = f"{_DAEMONS_DIR}/{name}.pid"
    if mode == "tmux":
        return f"tmux kill-session -t {q_name} 2>/dev/null; rm -f {shlex.quote(pid)}; echo stopped"
    return f"if [ -f {shlex.quote(pid)} ]; then kill \"$(cat {shlex.quote(pid)})\" 2>/dev/null || true; fi; rm -f {shlex.quote(pid)}; echo stopped"


def _find_record(data: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in data.get("daemons") or []:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _refresh_statuses(
    *,
    user_id: str,
    session_id: str,
    workspace_host: Path,
    data: dict[str, Any],
) -> None:
    for item in data.get("daemons") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        mode = str(item.get("mode") or "nohup")
        if not name:
            continue
        proc = _run_in_container(
            user_id=user_id,
            session_id=session_id,
            workspace_host=workspace_host,
            command=_status_script(name, mode),
            timeout_sec=15,
        )
        status = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else "unknown"
        if status not in ("running", "exited"):
            status = "exited" if proc.returncode != 0 else "running"
        item["status"] = status
        item["last_checked_at"] = _utc_iso()


def start_daemon(
    *,
    user_id: str,
    session_id: str,
    name: str,
    command: str,
) -> dict[str, Any]:
    validate_command(command)
    daemon_name = _validate_name(name)
    try:
        ws = manager.session_dir(user_id, session_id)
    except WorkspaceError as e:
        raise ExecError(str(e)) from e

    reg_path = _registry_path(user_id, session_id)
    data = _load_registry(reg_path)
    daemons = [d for d in data.get("daemons") or [] if isinstance(d, dict)]
    if len(daemons) >= settings.daemon_max_per_session:
        raise ExecError(f"daemon limit reached ({settings.daemon_max_per_session})")
    if _find_record(data, daemon_name):
        raise ExecError(f"daemon {daemon_name!r} already registered; stop it first or pick another name")

    proc = _run_in_container(
        user_id=user_id,
        session_id=session_id,
        workspace_host=ws,
        command=_start_script(daemon_name, command.strip()),
        timeout_sec=30,
    )
    mode = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    if proc.returncode == 2:
        raise ExecError((proc.stderr or proc.stdout or "daemon already running").strip())
    if proc.returncode != 0 or mode not in ("tmux", "nohup"):
        err = (proc.stderr or proc.stdout or "failed to start daemon").strip()
        raise ExecError(err)

    log_path = f"{_DAEMONS_DIR}/{daemon_name}.log"
    record = DaemonRecord(
        name=daemon_name,
        command=command.strip(),
        started_at=_utc_iso(),
        mode=mode,
        log_path=log_path,
        status="running",
        pid_file=f"{_DAEMONS_DIR}/{daemon_name}.pid" if mode == "nohup" else None,
    )
    daemons.append(asdict(record))
    data["daemons"] = daemons
    _save_registry(reg_path, data)

    log_ctx = log_for_ids(user_id, session_id)
    append_sandbox_log(
        log_ctx,
        f"{_utc_ts()} [daemon_start] name={daemon_name} mode={mode} command={command.strip()}",
    )
    return {
        "ok": True,
        "name": daemon_name,
        "mode": mode,
        "log_path": log_path,
        "registry_path": _REGISTRY_REL,
        "message": "Daemon started in background. Use daemon_attach for live output.",
    }


def list_daemons(*, user_id: str, session_id: str) -> dict[str, Any]:
    try:
        ws = manager.session_dir(user_id, session_id)
    except WorkspaceError as e:
        raise ExecError(str(e)) from e
    reg_path = _registry_path(user_id, session_id)
    data = _load_registry(reg_path)
    if data.get("daemons"):
        _refresh_statuses(
            user_id=user_id,
            session_id=session_id,
            workspace_host=ws,
            data=data,
        )
        _save_registry(reg_path, data)
    return {"ok": True, "daemons": data.get("daemons") or []}


def attach_daemon(
    *,
    user_id: str,
    session_id: str,
    name: str,
    tail_lines: int = 200,
) -> dict[str, Any]:
    daemon_name = _validate_name(name)
    try:
        ws = manager.session_dir(user_id, session_id)
    except WorkspaceError as e:
        raise ExecError(str(e)) from e
    reg_path = _registry_path(user_id, session_id)
    data = _load_registry(reg_path)
    rec = _find_record(data, daemon_name)
    if rec is None:
        raise ExecError(f"daemon {daemon_name!r} not found")
    mode = str(rec.get("mode") or "nohup")
    _refresh_statuses(user_id=user_id, session_id=session_id, workspace_host=ws, data=data)
    _save_registry(reg_path, data)
    rec = _find_record(data, daemon_name) or rec

    proc = _run_in_container(
        user_id=user_id,
        session_id=session_id,
        workspace_host=ws,
        command=_attach_script(daemon_name, mode, tail_lines),
        timeout_sec=30,
    )
    output = (proc.stdout or "")[-8192:]
    if proc.returncode != 0 and not output:
        output = (proc.stderr or "")[-8192:]
    return {
        "ok": True,
        "name": daemon_name,
        "status": rec.get("status"),
        "mode": mode,
        "log_path": rec.get("log_path"),
        "output": output,
    }


def stop_daemon(*, user_id: str, session_id: str, name: str) -> dict[str, Any]:
    daemon_name = _validate_name(name)
    try:
        ws = manager.session_dir(user_id, session_id)
    except WorkspaceError as e:
        raise ExecError(str(e)) from e
    reg_path = _registry_path(user_id, session_id)
    data = _load_registry(reg_path)
    rec = _find_record(data, daemon_name)
    if rec is None:
        raise ExecError(f"daemon {daemon_name!r} not found")
    mode = str(rec.get("mode") or "nohup")

    proc = _run_in_container(
        user_id=user_id,
        session_id=session_id,
        workspace_host=ws,
        command=_stop_script(daemon_name, mode),
        timeout_sec=20,
    )
    remaining = [d for d in data.get("daemons") or [] if not (isinstance(d, dict) and d.get("name") == daemon_name)]
    data["daemons"] = remaining
    _save_registry(reg_path, data)

    log_ctx = log_for_ids(user_id, session_id)
    append_sandbox_log(log_ctx, f"{_utc_ts()} [daemon_stop] name={daemon_name}")
    return {
        "ok": True,
        "name": daemon_name,
        "stopped": True,
        "detail": (proc.stdout or proc.stderr or "stopped").strip(),
    }
