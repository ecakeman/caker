from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage
from langgraph.prebuilt import ToolNode

from app.config import settings
from app.mempalace.compact_memory import persist_compact_summary
from app.mempalace.injector import build_bootstrap, should_inject
from app.observability.llm_meta import build_llm_invoke_meta
from app.observability.session_log import append_engine, log_for_ids
from app.runtime.llm import (
    get_llm_with_tools,
    get_tools_for_state,
    session_id_from_config,
    user_id_from_config,
)
from app.web.llm_settings import resolve_llm_credentials
from app.runtime.state import GraphState
from app.skills.manager import skills_manager
from app.summary.handler import build_compact_result, sanitize_messages_for_llm
from app.tools.base import build_default_tools

_TOOLS_FOR_NODE = build_default_tools(include_result_set=True)


async def start_node(state: GraphState) -> dict:
    if state.get("messages"):
        return {"skip_inject_system": True}
    return {"skip_inject_system": False}


def inject_system_node(state: GraphState) -> dict:
    if state.get("skip_inject_system", False):
        return {}
    sandbox_context = state.get("sandbox_context") or ""
    return {
        "messages": [
            SystemMessage(
                content=skills_manager.render_system_prompt(
                    sandbox_context=sandbox_context,
                )
            )
        ]
    }


def inject_user_node(state: GraphState) -> dict:
    if state.get("skip_inject_user"):
        return {}
    return {"messages": [HumanMessage(content=state["input"])]}


async def mempalace_inject_node(state: GraphState, config) -> dict:
    if not settings.mempalace_auto_inject:
        return {}
    messages = state.get("messages") or []
    if not should_inject(messages):
        return {}
    user_id = "local"
    session_id = "demo"
    if config and isinstance(config, dict):
        configurable = config.get("configurable") or {}
        if isinstance(configurable, dict):
            user_id = str(configurable.get("user_id") or "local")
            session_id = str(configurable.get("session_id") or configurable.get("thread_id") or "demo")
    boot = build_bootstrap(state["input"], user_id)
    log_ctx = log_for_ids(user_id, session_id)
    if boot is None:
        append_engine(log_ctx, "mempalace_inject", "no hits", meta={"hits": 0})
        return {}
    append_engine(log_ctx, "mempalace_inject", "injected bootstrap", meta={"hits": 1})
    return {"messages": [boot]}


async def llm_node(state: GraphState, config) -> dict:
    import time

    tools = get_tools_for_state(streaming=state.get("streaming", False))
    llm = get_llm_with_tools(tools, user_id=user_id_from_config(config))
    messages = sanitize_messages_for_llm(state["messages"])
    uid = user_id_from_config(config)
    sid = session_id_from_config(config)
    log_ctx = log_for_ids(uid, sid).with_run_id()
    t0 = time.perf_counter()
    ai = await llm.ainvoke(messages)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    creds = resolve_llm_credentials(uid)
    llm_meta = build_llm_invoke_meta(
        log_ctx,
        messages=messages,
        ai=ai,
        elapsed_ms=elapsed_ms,
        model=creds.model,
    )
    append_engine(
        log_ctx,
        "llm_invoke",
        "completed",
        meta=llm_meta,
    )
    if settings.session_agent_log_enabled:
        from app.observability.session_log import append_agent

        append_agent(
            log_ctx,
            "llm_invoke",
            "completed",
            meta={k: v for k, v in llm_meta.items() if k != "prompt_preview"},
        )
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
    uid = user_id_from_config(config)
    sid = session_id_from_config(config)
    log_ctx = log_for_ids(uid, sid)
    built = build_compact_result(
        messages,
        state["input"],
        user_id=uid,
    )
    from app.summary.handler import estimate_tokens

    append_engine(
        log_ctx,
        "context_compact",
        "compressed middle history",
        meta={
            "summary_len": len(built.summary_text or ""),
            "token_estimate": estimate_tokens(messages),
            "rebuilt_count": len(built.messages),
        },
    )
    persist_compact_summary(
        built.summary_text,
        user_id=uid,
        session_id=sid,
    )
    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *built.messages,
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
