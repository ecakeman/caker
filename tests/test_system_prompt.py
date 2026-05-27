"""system_prompt.md 加载与注入校验。"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import SystemMessage

from app.runtime.nodes import inject_system_node
from app.skills.manager import skills_manager


def test_load_system_prompt_has_required_sections():
    text = skills_manager.load_system_prompt()
    assert "身份与角色" in text
    assert "行为准则" in text
    assert "工作区" in text
    assert "路径规范" in text
    assert "工具" in text
    assert "技能" in text
    assert "{skills_meta}" in text
    assert "部署位置" not in text
    assert "inject_system_node" not in text


def test_render_system_prompt_replaces_skills_meta():
    meta = json.dumps([{"name": "hello_skill", "description": "demo", "version": ""}])
    rendered = skills_manager.render_system_prompt(skills_meta=meta)
    assert "{skills_meta}" not in rendered
    assert "hello_skill" in rendered
    assert "使用流程" in rendered
    assert "部署位置" not in rendered


def test_render_system_prompt_missing_placeholder_raises(monkeypatch):
    monkeypatch.setattr(
        skills_manager,
        "load_system_prompt",
        lambda: "no placeholder here",
    )
    with pytest.raises(ValueError, match="skills_meta"):
        skills_manager.render_system_prompt(skills_meta="[]")


def test_inject_system_node_returns_system_message():
    out = inject_system_node(
        {
            "messages": [],
            "input": "",
            "result": "",
            "skip_inject_system": False,
        }
    )
    assert "messages" in out
    msg = out["messages"][0]
    assert isinstance(msg, SystemMessage)
    assert "Caker" in msg.content
    assert "hello_skill" in msg.content or "[]" in msg.content


def test_inject_system_node_skips_when_flagged():
    assert inject_system_node(
        {
            "messages": [],
            "input": "",
            "result": "",
            "skip_inject_system": True,
        }
    ) == {}
