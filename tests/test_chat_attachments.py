from __future__ import annotations

from app.api.chat import _format_user_input


def test_format_user_input_with_attachments():
    out = _format_user_input("分析", ["data/uploads/a.txt"])
    assert "分析" in out
    assert "data/uploads/a.txt" in out
    assert "[附件]" in out


def test_format_user_input_attachments_only():
    out = _format_user_input("", ["data/uploads/b.csv"])
    assert "data/uploads/b.csv" in out
