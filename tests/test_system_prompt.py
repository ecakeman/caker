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
    assert "运行架构" in text
    assert "交互界面" in text
    assert "行为准则" in text
    assert "路径规范" in text
    assert "记忆与内部上下文" in text
    assert "已移除能力" in text
    assert "工具" in text
    assert "技能" in text
    assert "{skills_meta}" in text
    assert "{tools_meta}" in text
    assert "{sandbox_context}" in text
    assert "部署位置" not in text


def test_render_system_prompt_replaces_placeholders():
    skills = json.dumps([{"name": "demo-hello", "description": "demo", "version": ""}])
    rendered = skills_manager.render_system_prompt(skills_meta=skills)
    assert "{skills_meta}" not in rendered
    assert "{tools_meta}" not in rendered
    assert "demo-hello" in rendered
    assert "**read**" in rendered or "- **read**" in rendered
    assert "使用流程" in rendered


def test_render_system_prompt_missing_skills_placeholder_raises(monkeypatch):
    monkeypatch.setattr(
        skills_manager,
        "load_system_prompt",
        lambda: "no skills {tools_meta} only",
    )
    with pytest.raises(ValueError, match="skills_meta"):
        skills_manager.render_system_prompt(skills_meta="[]")


def test_inject_system_node_returns_system_message():
    skills_manager.reindex()
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
    assert "demo-hello" in msg.content or "file-extract" in msg.content


def test_inject_system_node_skips_when_flagged():
    assert inject_system_node(
        {
            "messages": [],
            "input": "",
            "result": "",
            "skip_inject_system": True,
        }
    ) == {}
