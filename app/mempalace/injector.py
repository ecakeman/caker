from __future__ import annotations

import json

from langchain_core.messages import BaseMessage, HumanMessage

from app.mempalace import chroma_store

WAKEUP = "下面是来自长期记忆的相关信息，仅供参考。请优先核对后再回答。"

def should_inject(messages: list[BaseMessage]) -> bool:
    if not messages:
        return False
    for m in messages:
        if isinstance(m, HumanMessage) and isinstance(m.content, str) and m.content.startswith('{"mempalace"'):
            return False
    return isinstance(messages[-1], HumanMessage)

def build_bootstrap(user_text: str, user_id: str) -> HumanMessage | None:
    hits = chroma_store.search(user_text, k=5, where={"user_id": user_id})
    if not hits:
        return None
    payload = {
        "mempalace": True,
        "wakeup": WAKEUP,
        "recall": [{"id": i, "text": t, "metadata": m} for i, t, m in hits],
    }
    return HumanMessage(content=json.dumps(payload, ensure_ascii=False))