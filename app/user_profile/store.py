from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.config import settings
from app.workspace.manager import manager

logger = logging.getLogger(__name__)

_PROFILE_DIRNAME = "profile"
_PROFILE_FILENAME = "user_profile.jsonl"
_SESSION_LINK = f"logs/{_PROFILE_FILENAME}"

_REFLECT_PROMPT = (
    "根据本轮对话，提取 0-2 条可跨会话复用的「用户偏好或纠正」。\n"
    "只记录用户明确表达或强烈暗示的习惯（如输出格式、工具选择、禁止行为），"
    "不要记录任务具体内容或一次性事实。\n"
    "若无新偏好，只回复 JSON：{{\"preferences\": []}}\n"
    "否则回复 JSON：{{\"preferences\": [\"用户偏好：…\", …]}}\n"
    "每条不超过 80 字，中文。\n\n"
    "对话：\n{dialog}"
)

_MAX_DIALOG = 1200


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def user_profile_path(user_id: str) -> Path:
    root = manager.root / user_id / _PROFILE_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root / _PROFILE_FILENAME


def ensure_profile_link(user_id: str, session_id: str) -> Path:
    """Symlink session logs/user_profile.jsonl -> user-level profile (read-only via read tool)."""
    ws = manager.session_dir(user_id, session_id)
    link = ws / _SESSION_LINK
    target = Path("..") / ".." / _PROFILE_DIRNAME / _PROFILE_FILENAME
    profile_file = user_profile_path(user_id)
    profile_file.parent.mkdir(parents=True, exist_ok=True)
    if not profile_file.is_file():
        profile_file.write_text("", encoding="utf-8")
    if link.is_symlink():
        return profile_file
    if link.exists():
        return profile_file
    link.symlink_to(target)
    return profile_file


def _read_entries(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def append_preference(user_id: str, text: str, *, source_session: str | None = None) -> None:
    t = (text or "").strip()
    if not t:
        return
    path = user_profile_path(user_id)
    rec = {
        "ts": _utc_iso(),
        "preference": t,
    }
    if source_session:
        rec["source_session"] = source_session
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _trim_profile(path)


def _trim_profile(path: Path) -> None:
    entries = _read_entries(path)
    max_n = max(1, settings.user_profile_max_entries)
    if len(entries) <= max_n:
        return
    kept = entries[-max_n:]
    with path.open("w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_profile_for_prompt(user_id: str, *, max_lines: int = 20) -> str:
    path = user_profile_path(user_id)
    entries = _read_entries(path)
    if not entries:
        return ""
    lines: list[str] = []
    for rec in entries[-max_lines:]:
        pref = str(rec.get("preference") or "").strip()
        if pref:
            lines.append(f"- {pref}")
    return "\n".join(lines)


def build_user_profile_context(user_id: str) -> str:
    body = load_profile_for_prompt(user_id)
    if not body:
        return ""
    return (
        "[USER_PROFILE]\n"
        "以下为跨会话积累的用户偏好，默认遵守；若本轮用户另有明确要求，以本轮为准。\n"
        f"{body}"
    )


def _format_dialog(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for msg in messages[-8:]:
        if isinstance(msg, HumanMessage):
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()[:400]
            if text:
                lines.append(f"用户: {text}")
        elif isinstance(msg, AIMessage):
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            text = text.strip()[:400]
            if text:
                lines.append(f"助手: {text}")
    dialog = "\n".join(lines)
    return dialog[:_MAX_DIALOG]


def _parse_preferences(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    prefs = data.get("preferences") if isinstance(data, dict) else None
    if not isinstance(prefs, list):
        return []
    out: list[str] = []
    for p in prefs:
        s = str(p).strip()
        if s:
            out.append(s)
    return out[:2]


def reflect_from_messages(
    user_id: str,
    session_id: str,
    messages: list[BaseMessage],
) -> None:
    if not settings.user_profile_enabled:
        return
    ensure_profile_link(user_id, session_id)
    dialog = _format_dialog(messages)
    if not dialog:
        return
    from app.runtime.llm import get_llm

    try:
        out = get_llm(user_id).invoke(
            [HumanMessage(content=_REFLECT_PROMPT.format(dialog=dialog))]
        )
        text = out.content if isinstance(out.content, str) else str(out.content)
    except Exception:
        logger.exception("user profile reflect LLM failed")
        return
    prefs = _parse_preferences(text)
    if not prefs:
        return
    existing = {str(r.get("preference") or "").strip() for r in _read_entries(user_profile_path(user_id))}
    for pref in prefs:
        if pref in existing:
            continue
        append_preference(user_id, pref, source_session=session_id)
