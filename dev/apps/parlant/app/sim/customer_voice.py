from __future__ import annotations

import os
import re
from typing import Any

from openai import OpenAI


def create_customer_client(timeout: float) -> OpenAI:
    import os

    api_key = (os.environ.get("LLM_API_KEY") or "").strip()
    base_url = (os.environ.get("LLM_BASE_URL") or "").strip()
    if not api_key or not base_url:
        raise RuntimeError("missing LLM_API_KEY or LLM_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)


BROKER_PHRASES = (
    "我是经纪人",
    "我是优选保",
    "咱们可以",
    "我来帮你",
    "方案做出来",
    "不站队某一家",
    "只看条款和性价比",
    "收到，",
)


def clean_customer_message(text: str) -> str:
    text = re.sub(r"^```(?:text)?|```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    text = text.strip().strip('"').strip("'")
    text = re.sub(r"\s+", " ", text)
    if not text:
        return "我再补充一下我的情况，你帮我继续分析下。"
    if text.upper() in {"END", "END_SESSION", "ROUND_END"}:
        return "我还有点没想明白，你再帮我接着分析一下。"
    lowered = text
    if any(p in lowered for p in BROKER_PHRASES):
        return "嗯，你刚说的我有点没听明白，能再通俗点说吗？"
    return text[:200]


def render_history(messages: list[dict[str, Any]], limit: int) -> str:
    tail = messages[-limit:] if limit > 0 else messages
    if not tail:
        return "（暂无历史，这是第一句）"
    return "\n".join(f"{m['role']}: {m['message']}" for m in tail)


def generate_customer_message(
    client: OpenAI,
    *,
    scenario: dict[str, Any],
    history: list[dict[str, Any]],
    turn: int,
    total_turns: int,
    history_messages: int = 8,
    real_customer_examples: list[str] | None = None,
) -> str:
    model = (os.environ.get("LLM_MODEL_NAME") or "gpt-4").removeprefix("openai/")
    examples = real_customer_examples or []
    system = (
        "你在微信里扮演一个真实保险咨询顾客。你不是保险从业者，表达要口语、自然、可带犹豫。"
        "每轮只发一个微信气泡，可以是半句话、追问或补充信息。"
        "每次只输出一条客户消息，不要 Markdown，不要编号，不要解释扮演策略。"
        "严禁复述、照抄或改写经纪人上一条原话；严禁使用经纪人口吻（如「我是经纪人」「咱们给您配方案」）。"
    )
    user = f"""
【场景主题】{scenario.get('topic')}
【目标 Journey】{scenario.get('target_journey') or '未指定'}
【顾客画像】{scenario.get('customer_profile')}
【开场意图】{scenario.get('opening_intent')}
【需要贴近触发的条件】{'; '.join(scenario.get('trigger_conditions') or [])}
【本场必须自然覆盖的问题】{'; '.join(scenario.get('must_cover') or [])}
【真实异议与情绪】{'; '.join(scenario.get('realistic_objections') or [])}
【可能被经纪人调用的素材线索】{'; '.join(scenario.get('material_cues') or [])}
【本场推进节奏】{'; '.join(scenario.get('customer_arc') or [])}
【避免事项】{'; '.join(scenario.get('avoid') or [])}
【真实客户原话样本】{'; '.join(examples) if examples else '（无）'}
【当前轮次】第 {turn}/{total_turns} 次客户发言（本场）
【历史对话】
{render_history(history, history_messages)}

请生成第 {turn} 次客户发言：
- 像真实微信消息，一条气泡；多数 15-80 字。
- 口语、碎片化，可带「嗯」「那」「我怕」等迟疑。
- 必须承接经纪人上一条，用顾客视角追问或补充，不要复述经纪人句子。
- 不要像测试脚本，不要说「触发 guideline/journey」。
- 按「本场推进节奏」逐步推进；前 {max(total_turns - 1, 1)} 轮不要结束会话。
""".strip()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.85,
        max_tokens=150,
    )
    content = response.choices[0].message.content or ""
    return clean_customer_message(content)
