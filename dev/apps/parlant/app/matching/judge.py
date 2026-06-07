from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


def judge_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    llm_model: str,
    llm_base_url: str,
    llm_api_key: str,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    model = llm_model.removeprefix("openai/")
    client = OpenAI(api_key=llm_api_key, base_url=llm_base_url, timeout=90.0)
    payload = [
        {
            "guideline_id": c["guideline_id"],
            "condition": c["condition_text"],
            "action": c["action_text"][:400],
        }
        for c in candidates
    ]
    prompt = (
        "你是 guideline 匹配器。给定用户上下文与候选规则，判断哪些规则应触发。\n"
        f"用户上下文:\n{query}\n\n候选规则:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "返回 JSON: {\"matches\":[{\"guideline_id\":\"...\",\"matched\":true,\"rationale\":\"...\"}]}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )
        text = resp.choices[0].message.content or "{}"
        data = json.loads(text)
        by_id = {m["guideline_id"]: m for m in data.get("matches") or []}
        out = []
        for c in candidates:
            m = by_id.get(c["guideline_id"], {})
            if m.get("matched"):
                out.append({**c, "rationale": m.get("rationale", "")})
        return out
    except Exception as exc:
        return [{**c, "rationale": f"fallback_rrf:{exc}"} for c in candidates[:3]]
