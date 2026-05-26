from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.runtime import nodes
from app.runtime.state import GraphState

from collections.abc import AsyncIterator
from typing import Any

from app.runtime import routes


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("start", nodes.start_node)
    g.add_node("inject_system", nodes.inject_system_node)
    g.add_node("inject_user", nodes.inject_user_node)
    g.add_node("llm", nodes.llm_node)
    g.add_node("tools", nodes.tools_node)
    g.add_node("end", nodes.end_node)

    g.add_edge(START, "start")
    g.add_edge("start", "inject_system")
    g.add_edge("inject_system", "inject_user")
    g.add_edge("inject_user", "llm")
    g.add_conditional_edges(
        "llm", 
        routes.route_after_llm,
        {
            "tools": "tools",
            "end": "end"
        }
    )
    g.add_edge("tools", "llm")
    g.add_edge("end", END)
    return g


Path("var").mkdir(parents=True, exist_ok=True)
_sqlite_checkpointer_cm = SqliteSaver.from_conn_string("var/state.db")
CHECKPOINTER = _sqlite_checkpointer_cm.__enter__()

GRAPH = build_graph().compile(checkpointer=CHECKPOINTER)

async def iter_graph_stream_events(
    inputs: dict[str,Any],
    *,
    config: dict[str, Any] | None = None,
)->AsyncIterator[dict[str,Any]]:
    async for ev in GRAPH.astream_events(inputs, config=config, version="v2"):
        yield ev