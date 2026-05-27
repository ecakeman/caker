from langchain_core.messages import AIMessage
from app.runtime.state import GraphState

from app.summary.handler import need_summary

def route_after_llm(state : GraphState):
    last = state['messages'][-1]
    if isinstance(last,AIMessage) and getattr(last,"tool_calls",None):
        return "tools"
    return "end"

def route_after_start(state : GraphState):
    if state.get("skip_inject_system"):
        return "inject_user"
    return "inject_system"

def route_after_tools(state : GraphState):
    if state.get("result_set_handled"):
        return "end"
    if need_summary(state.get("messages") or []):
        return "summary"
    return "llm"
