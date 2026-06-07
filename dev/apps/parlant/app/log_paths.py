"""Resolve ``var/`` layout for customer sim, gateway, and tests (parlant project)."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _strip(raw: str | None) -> str:
    return (raw or "").strip()


def _resolve_under(repo_root: Path, raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (repo_root / p).resolve()


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def var_root(repo_root: Path | None = None) -> Path:
    r = repo_root or project_root()
    raw = _strip(os.environ.get("VAR_ROOT")) or "var"
    return _resolve_under(r, raw)


def customer_sim_root(repo_root: Path | None = None) -> Path:
    r = repo_root or project_root()
    env = _strip(os.environ.get("CUSTOMER_SIM_RUN_ROOT"))
    if env:
        return _resolve_under(r, env)
    return (var_root(r) / "customer_sim").resolve()


def gateway_root(repo_root: Path | None = None) -> Path:
    r = repo_root or project_root()
    env = _strip(os.environ.get("GATEWAY_VAR_ROOT"))
    if env:
        return _resolve_under(r, env)
    return (var_root(r) / "gateway").resolve()


def gateway_process_root(repo_root: Path | None = None) -> Path:
    r = repo_root or project_root()
    env = _strip(os.environ.get("GATEWAY_LOG_DIR"))
    if env:
        return _resolve_under(r, env)
    return (gateway_root(r) / "process").resolve()


def gateway_messages_root(repo_root: Path | None = None) -> Path:
    r = repo_root or project_root()
    env = _strip(os.environ.get("GATEWAY_MESSAGE_LOG_ROOT"))
    if env:
        return _resolve_under(r, env)
    return (gateway_root(r) / "messages").resolve()


def safe_gateway_session_message_subdir(session_id: str) -> str:
    s = (session_id or "").strip()
    if not s:
        return "unknown_session"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", s)
    return (safe.strip("._-") or "unknown_session")[:240]


def gateway_session_messages_dir(session_id: str, repo_root: Path | None = None) -> Path:
    return (gateway_messages_root(repo_root) / safe_gateway_session_message_subdir(session_id)).resolve()


def parlant_home_resolved(repo_root: Path | None = None) -> Path:
    r = repo_root or project_root()
    env = _strip(os.environ.get("PARLANT_HOME"))
    if env:
        return _resolve_under(r, env)
    return (gateway_root(r) / "runtime").resolve()


def ensure_default_var_layout(repo_root: Path | None = None) -> Path:
    r = repo_root or project_root()
    vr = var_root(r)
    for rel in (
        "gateway/process",
        "gateway/runtime",
        "gateway/messages",
        "customer_sim",
        "tests/smoke",
        "telemetry",
    ):
        (vr / rel).mkdir(parents=True, exist_ok=True)
    return vr


def safe_session_subdir(session_id: str) -> str:
    s = (session_id or "").strip()
    if not s:
        return "unknown_session"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", s)
    return (safe.strip("._-") or "unknown_session")[:240]
