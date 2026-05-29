from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.execution.compose_control import (
    ComposeError,
    _compose_error_detail,
    compose_down,
    compose_status,
    compose_up,
)
from app.workspace.manager import WorkspaceManager


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    mgr = WorkspaceManager(str(tmp_path))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.execution.compose_control.manager", mgr)
    mgr.session_dir("alice", "sess1")
    return mgr, tmp_path


def _write_compose(ws_root: Path) -> Path:
    compose_dir = ws_root / "alice" / "sess1" / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)
    compose_file = compose_dir / "docker-compose.yml"
    compose_file.write_text("services:\n  dev:\n    image: python:3.12-slim\n", encoding="utf-8")
    return compose_file


def test_compose_status_not_found(ws_env):
  _, tmp_path = ws_env
  with pytest.raises(ComposeError, match="not found"):
      compose_status("alice", "sess1")


def test_compose_status_running(ws_env, monkeypatch):
    _, tmp_path = ws_env
    _write_compose(tmp_path)
    monkeypatch.setattr("app.execution.compose_control.docker_available", lambda: True)
    monkeypatch.setattr(
        "app.execution.compose_control.compose_ps_has_running",
        lambda *_: True,
    )
    status = compose_status("alice", "sess1")
    assert status["running"] is True
    assert status["compose_file"] == "compose/docker-compose.yml"
    assert status["project"] == "caker-alice-sess1"


def test_compose_up_invokes_docker(ws_env, monkeypatch):
    _, tmp_path = ws_env
    _write_compose(tmp_path)
    monkeypatch.setattr("app.execution.compose_control.docker_available", lambda: True)

    calls: list[list[str]] = []

    def fake_docker(args, *, timeout=None):
        calls.append(args)
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "Started"
        proc.stderr = ""
        return proc

    monkeypatch.setattr("app.execution.docker_util._docker", fake_docker)
    monkeypatch.setattr(
        "app.execution.compose_control.compose_ps_has_running",
        lambda *_: True,
    )

    result = compose_up("alice", "sess1")
    assert result["ok"] is True
    assert result["running"] is True
    assert calls[0][:4] == ["compose", "-f", str(tmp_path / "alice" / "sess1" / "compose" / "docker-compose.yml"), "-p"]
    assert "up" in calls[0] and "-d" in calls[0]


def test_compose_down_failure(ws_env, monkeypatch):
    _, tmp_path = ws_env
    _write_compose(tmp_path)
    monkeypatch.setattr("app.execution.compose_control.docker_available", lambda: True)

    def fake_docker(args, *, timeout=None):
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "down failed"
        return proc

    monkeypatch.setattr("app.execution.docker_util._docker", fake_docker)

    with pytest.raises(ComposeError, match="down failed"):
        compose_down("alice", "sess1")


def test_compose_error_detail_filters_warnings():
    stderr = (
        'time="2026-05-29T19:28:58+08:00" level=warning msg="version is obsolete"\n'
        "45006ceeeea9 Pulling fs layer\n"
        "Error response from daemon: port is already allocated\n"
    )
    detail = _compose_error_detail(stderr, "")
    assert "obsolete" not in detail
    assert "Pulling fs layer" not in detail
    assert "port is already allocated" in detail
