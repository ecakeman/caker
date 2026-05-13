from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.runtime.llm import get_llm_with_tools
from app.runtime.state import GraphState
from app.tools.base import build_default_tools

_TOOLS = build_default_tools()

async def start_node(state: GraphState) -> dict:
    return {}


def inject_system_node(state: GraphState) -> dict:
    if state.get("skip_inject_system", False):
        return {}
    return {
        "messages": [
            SystemMessage(
                content=(
                    "你叫Caker,是一个AI助手"
                    "你需要根据用户的提问回答相应问题"
                    "如果涉及到项目本身敏感信息，你要拒绝回答"
                )
            )
        ]
    }


def inject_user_node(state: GraphState) -> dict:
    return {"messages": [HumanMessage(content=state["input"])]}


async def llm_node(state: GraphState) -> dict:
    llm = get_llm_with_tools(_TOOLS)
    ai = await llm.ainvoke(state["messages"])
    return {"messages": [ai]}


async def end_node(state: GraphState) -> dict:
    result_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            result_text = msg.content
            break
    return {"result": result_text}


