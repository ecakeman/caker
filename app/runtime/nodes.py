from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from app.runtime.llm import get_llm_with_tools, get_tools_for_state
from app.runtime.state import GraphState
from app.skills.manager import skills_manager
from app.tools.base import build_default_tools

from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage

from app.summary.handler import summarize
_TOOLS_FOR_NODE = build_default_tools(include_result_set=True)


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
    tools = get_tools_for_state(streaming=state.get("streaming", False))
    llm = get_llm_with_tools(tools)
    ai = await llm.ainvoke(state["messages"])
    return {"messages": [ai]}


def apply_result_set_node(state: GraphState, config) -> dict:
    if not state.get("messages"):
        return {}
    last = state["messages"][-1]
    if isinstance(last, ToolMessage) and last.name == "result_set":
        text = last.content if isinstance(last.content, str) else str(last.content)
        return {"result": text, "result_set_handled": True}
    return {}


async def end_node(state: GraphState) -> dict:
    if state.get("result_set_handled") and state.get("result"):
        return {}
    result_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            content = msg.content
            result_text = content if isinstance(content, str) else str(content)
            break
    return {"result": result_text}


tools_node = ToolNode(_TOOLS_FOR_NODE)


async def summary_node(state: GraphState, config) -> dict:
    summary_msg = summarize(state["messages"])
    last_user = HumanMessage(content=state["input"])
    return {
        "messages":[
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            summary_msg,
            last_user,
        ]
    }