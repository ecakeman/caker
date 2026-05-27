from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.runtime import nodes, routes
from app.runtime.state import GraphState

_compiled: CompiledStateGraph | None = None


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("start", nodes.start_node)
    g.add_node("inject_system", nodes.inject_system_node)
    g.add_node("inject_user", nodes.inject_user_node)
    g.add_node("llm", nodes.llm_node)
    g.add_node("tools", nodes.tools_node)
    g.add_node("end", nodes.end_node)
    g.add_node("apply_result_set", nodes.apply_result_set_node)

    g.add_edge(START, "start")
    g.add_conditional_edges(
        "start",
        routes.route_after_start,
        {
            "inject_system": "inject_system",
            "inject_user": "inject_user",
        }
    )
    g.add_edge("inject_system", "inject_user")
    g.add_edge("inject_user", "llm")
    g.add_conditional_edges(
        "llm",
        routes.route_after_llm,
        {
            "tools": "tools",
            "end": "end",
        },
    )
    g.add_edge("tools", "apply_result_set")
    g.add_conditional_edges(
        "apply_result_set",
        routes.route_after_tools,
        {
            "end": "end",
            "llm": "llm",
        },
    )
    g.add_edge("end", END)
    return g


def compile_graph(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    global _compiled
    _compiled = build_graph().compile(checkpointer=checkpointer)
    return _compiled

def get_graph() -> CompiledStateGraph:
    if _compiled is None:
        raise RuntimeError(
            "Graph not compiled. Start uvicorn with app.main:app (lifespan initializes checkpointer)."
        )
    return _compiled

async def iter_graph_stream_events(
    inputs: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    async for ev in get_graph().astream_events(inputs, config=config, version="v2"):
        yield ev
