from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.runtime.graph import get_graph, iter_graph_stream_events
from app.runtime.llm import get_llm

from fastapi.responses import StreamingResponse

from app.runtime.sse import sse_pack
from fastapi import Header


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
    lines.append("（可用 read / glob 读取工作区文件；文本类可直接 read。）")
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
        # 不把上游错误原文返回客户端，避免泄露 URL、Key 片段等
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
        try:
            async for ev in iter_graph_stream_events(inputs, config=config):
                if ev.get("event") != "on_chat_model_stream":
                    continue
                chunk = ev.get("data",{}).get("chunk")
                if chunk is None:
                    continue
                content = getattr(chunk,"content",None)
                if isinstance(content,str) and content:
                    yield sse_pack("delta", {"text": content})
            yield sse_pack("done", {})
        except Exception:
            yield sse_pack("error", {"detail": "stream upstream request failed"})

    return StreamingResponse(gen(),media_type="text/event-stream")