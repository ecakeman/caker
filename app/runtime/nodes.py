from __future__ import annotations
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from app.runtime.llm import get_llm_with_tools
from app.runtime.state import GraphState
from app.skills.manager import skills_manager
from app.tools.base import build_default_tools

_TOOLS = build_default_tools()

async def start_node(state: GraphState) -> dict:
    if state.get("messages"):
        return {"skip_inject_system": True}
    return {"skip_inject_system": False}



def inject_system_node(state: GraphState) -> dict:
    if state.get("skip_inject_system", False):
        return {}
    return {
        "messages": [
            SystemMessage(content=skills_manager.render_system_prompt())
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


tools_node = ToolNode(_TOOLS)