from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage
from langgraph.prebuilt import ToolNode

from app.config import settings
from app.mempalace.injector import build_bootstrap, should_inject
from app.runtime.llm import get_llm_with_tools, get_tools_for_state
from app.runtime.state import GraphState
from app.skills.manager import skills_manager
from app.summary.handler import build_compact_messages, sanitize_messages_for_llm
from app.tools.base import build_default_tools

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


async def mempalace_inject_node(state: GraphState, config) -> dict:
    if not settings.mempalace_auto_inject:
        return {}
    messages = state.get("messages") or []
    if not should_inject(messages):
        return {}
    user_id = "local"
    if config and isinstance(config, dict):
        configurable = config.get("configurable") or {}
        if isinstance(configurable, dict):
            user_id = str(configurable.get("user_id") or "local")
    boot = build_bootstrap(state["input"], user_id)
    if boot is None:
        return {}
    return {"messages": [boot]}


async def llm_node(state: GraphState) -> dict:
    tools = get_tools_for_state(streaming=state.get("streaming", False))
    llm = get_llm_with_tools(tools)
    messages = sanitize_messages_for_llm(state["messages"])
    ai = await llm.ainvoke(messages)
    return {"messages": [ai]}


def apply_result_set_node(state: GraphState, config) -> dict:
    if not state.get("messages"):
        return {}
    last = state["messages"][-1]
    if isinstance(last, ToolMessage) and last.name == "result_set":
        text = last.content if isinstance(last.content, str) else str(last.content)
        return {"result": text, "result_set_handled": True}
    return {}


async def compact_node(state: GraphState, config) -> dict:
    messages = state.get("messages") or []
    compacted = build_compact_messages(messages, state["input"])
    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *compacted,
        ]
    }


async def end_node(state: GraphState, config) -> dict:
    if state.get("result_set_handled") and state.get("result"):
        result_text = state["result"]
    else:
        result_text = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage):
                content = msg.content
                result_text = content if isinstance(content, str) else str(content)
                break

    return {"result": result_text}


tools_node = ToolNode(_TOOLS_FOR_NODE)

# Legacy alias for docs/tests referencing summary_node
summary_node = compact_node
