from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass(frozen=True)
class QueryBundle:
    original: str
    rewritten: str | None


def build_query(
    user_message: str,
    *,
    session_summary: str = "",
    active_journey_id: str | None = None,
    active_state_id: str | None = None,
) -> str:
    parts = [user_message.strip()]
    if session_summary.strip():
        parts.append(f"会话摘要: {session_summary.strip()}")
    if active_journey_id:
        parts.append(f"当前旅程: {active_journey_id}")
    if active_state_id:
        parts.append(f"当前状态: {active_state_id}")
    return "\n".join(parts)


def maybe_rewrite_query(
    query: str,
    *,
    llm_model: str,
    llm_base_url: str,
    llm_api_key: str,
    enabled: bool = True,
) -> QueryBundle:
    if not enabled or len(query) < 8:
        return QueryBundle(original=query, rewritten=None)
    model = llm_model.removeprefix("openai/")
    client = OpenAI(api_key=llm_api_key, base_url=llm_base_url, timeout=60.0)
    prompt = (
        "将以下保险经纪对话上下文改写为 guideline 检索 query，保留关键意图词，"
        "不要添加不存在的信息。只返回 JSON: {\"rewrite\":\"...\"}\n\n"
        f"{query}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        rewrite = (data.get("rewrite") or "").strip()
        if rewrite and rewrite != query:
            return QueryBundle(original=query, rewritten=rewrite)
    except Exception:
        pass
    return QueryBundle(original=query, rewritten=None)
