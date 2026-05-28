from __future__ import annotations

from pathlib import Path

import pytest

from app.web_store.workspace_info import (
    session_path_for_clipboard,
    session_path_for_file_manager,
)


def test_session_path_for_clipboard_falls_back_to_resolved(monkeypatch, tmp_path: Path):
    p = tmp_path / "local" / "s1"
    p.mkdir(parents=True)
    monkeypatch.setattr("app.web_store.workspace_info.linux_path_to_windows", lambda _: None)
    assert session_path_for_clipboard(str(p)) == str(p.resolve())


def test_session_path_for_file_manager_wsl_unc(monkeypatch, tmp_path: Path):
    p = tmp_path / "local" / "s1"
    p.mkdir(parents=True)
    unc = r"\\wsl.localhost\Ubuntu\home\user\ws"
    monkeypatch.setattr(
        "app.web_store.workspace_info.linux_path_to_windows",
        lambda _: unc,
    )
    assert session_path_for_file_manager(str(p)) == unc
