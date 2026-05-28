from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.config import settings
from app.runtime.graph import get_graph, iter_graph_stream_events
from app.runtime.llm import get_llm
from app.runtime.sse import sse_pack


def _graph_config(session_id: str | None, user_id: str | None = None) -> dict:
    sid = (session_id or "demo").strip() or "demo"
    uid = (user_id or "local").strip() or "local"
    return {"configurable": {"session_id": sid, "thread_id": sid, "user_id": uid}}


def _format_user_input(message: str, attachments: list[str] | None = None) -> str:
    paths = [p.strip() for p in (attachments or []) if p and p.strip()]
    if not paths:
        return message
    lines: list[str] = []
    if message.strip():
        lines.append(message.strip())
    lines.append("[附件]")
    for p in paths:
        lines.append(f"- {p}")
    lines.append("（可用 read / glob 读取工作区文件；大文件请分页 read。）")
    return "\n".join(lines)


def _graph_inputs(
    message: str,
    *,
    streaming: bool = False,
    attachments: list[str] | None = None,
) -> dict:
    return {
        "messages": [],
        "input": _format_user_input(message, attachments),
        "result": "",
        "skip_inject_system": False,
        "result_set_handled": False,
        "streaming": streaming,
    }


def _langgraph_node(ev: dict) -> str | None:
    meta = ev.get("metadata")
    if isinstance(meta, dict):
        node = meta.get("langgraph_node")
        return str(node) if node else None
    return None


def _tool_label_from_event(ev: dict) -> str:
    data = ev.get("data")
    if not isinstance(data, dict):
        return ""
    name = data.get("name")
    if name:
        return str(name)
    inp = data.get("input")
    if isinstance(inp, dict) and inp.get("name"):
        return str(inp["name"])
    return str(ev.get("name") or "")


router = APIRouter(prefix="/api/v2")


class EchoIn(BaseModel):
    message: str
    session_id: str | None = None


class EchoOut(BaseModel):
    reply: str


class ChatOnceIn(BaseModel):
    message: str


class ChatOnceOut(BaseModel):
    reply: str


class ChatGraphIn(BaseModel):
    message: str = ""
    session_id: str | None = None
    attachments: list[str] = []


class ChatGraphOut(BaseModel):
    reply: str


@router.post("/echo", response_model=EchoOut)
async def echo(body: EchoIn) -> EchoOut:
    return EchoOut(reply=f"you said {body.message}")


@router.post("/chat-once", response_model=ChatOnceOut)
async def chat_once(body: ChatOnceIn) -> ChatOnceOut:
    llm = get_llm()
    try:
        ai_msg = llm.invoke([HumanMessage(content=body.message)])
    except Exception as e:
        raise HTTPException(status_code=502, detail="LLM upstream request failed") from e
    return ChatOnceOut(reply=str(ai_msg.content))


@router.post("/chat-graph", response_model=ChatGraphOut)
async def chat_graph(
    body: ChatGraphIn,
    x_user_id: str | None = Header(default=None, alias="x-user-id"),
) -> ChatGraphOut:
    try:
        out = await get_graph().ainvoke(
            _graph_inputs(
                body.message,
                streaming=False,
                attachments=body.attachments,
            ),
            config=_graph_config(body.session_id, x_user_id),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail="Graph upstream request failed") from e
    return ChatGraphOut(reply=str(out.get("result", "")))


@router.post("/stream")
async def stream_chat(
    body: ChatGraphIn,
    x_user_id: str | None = Header(default=None, alias="x-user-id"),
) -> StreamingResponse:
    async def gen():
        inputs = _graph_inputs(
            body.message,
            streaming=True,
            attachments=body.attachments,
        )
        config = _graph_config(body.session_id, x_user_id)
        emit_status = settings.stream_emit_tool_status
        try:
            async for ev in iter_graph_stream_events(inputs, config=config):
                event = ev.get("event")
                node = _langgraph_node(ev)

                if emit_status and event == "on_chain_start" and node == "compact":
                    yield sse_pack(
                        "status",
                        {"phase": "compact", "detail": "正在压缩较早对话…"},
                    )
                    continue

                if emit_status and event in ("on_tool_start", "on_chain_start"):
                    if node == "tools" or event == "on_tool_start":
                        label = _tool_label_from_event(ev) or "tool"
                        yield sse_pack(
                            "status",
                            {
                                "phase": "tool",
                                "tool": label,
                                "detail": f"执行 {label}…",
                            },
                        )
                        continue

                if emit_status and event == "on_tool_end":
                    yield sse_pack(
                        "status",
                        {"phase": "tool_done", "detail": "工具执行完成"},
                    )
                    continue

                if event != "on_chat_model_stream":
                    continue
                if node not in (None, "llm"):
                    continue

                chunk = ev.get("data", {})
                if not isinstance(chunk, dict):
                    continue
                chunk = chunk.get("chunk")
                if chunk is None:
                    continue

                tool_chunks = getattr(chunk, "tool_call_chunks", None)
                if tool_chunks:
                    if emit_status:
                        yield sse_pack(
                            "status",
                            {"phase": "planning", "detail": "正在选择工具…"},
                        )
                    continue

                content = getattr(chunk, "content", None)
                if isinstance(content, str) and content:
                    yield sse_pack("delta", {"text": content})

            yield sse_pack("done", {})
        except Exception:
            yield sse_pack("error", {"detail": "stream upstream request failed"})

    return StreamingResponse(gen(), media_type="text/event-stream")
