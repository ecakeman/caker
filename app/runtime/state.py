from typing import Annotated,TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    messages : Annotated[list[BaseMessage], add_messages]
    result : str
    skip_inject_system: bool 