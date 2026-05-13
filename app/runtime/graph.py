from langgraph.graph import END, START, StateGraph

from app.runtime import nodes
from app.runtime.state import GraphState

from collections.abc import AsyncIterator
from typing import Any


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("start", nodes.start_node)
    g.add_node("inject_system", nodes.inject_system_node)
    g.add_node("inject_user", nodes.inject_user_node)
    g.add_node("llm", nodes.llm_node)
    g.add_node("end", nodes.end_node)
    g.add_edge(START, "start")
    g.add_edge("start", "inject_system")
    g.add_edge("inject_system", "inject_user")
    g.add_edge("inject_user", "llm")
    g.add_edge("llm", "end")
    g.add_edge("end", END)
    return g.compile()


GRAPH = build_graph()

async def iter_graph_stream_events(
    inputs: dict[str,Any]
)->AsyncIterator[dict[str,Any]]:
    async for ev in GRAPH.astream_events(inputs, version="v2"):
        yield ev