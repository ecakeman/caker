from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.runtime.graph import GRAPH
from app.runtime.llm import get_llm

from fastapi.responses import StreamingResponse

from app.runtime.graph import iter_graph_stream_events
from app.runtime.sse import sse_pack


def _graph_config(session_id: str | None) -> dict:
    sid = (session_id or "demo").strip() or "demo"
    return {"configurable": {"session_id": sid}}

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
    message: str
    session_id: str | None = None

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
        # 上游（DashScope / PAI-EAS 等）鉴权、模型名、路径错误时，避免只返回 500
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ChatOnceOut(reply=str(ai_msg.content))


@router.post("/chat-graph", response_model=ChatGraphOut)
async def chat_graph(body: ChatGraphIn) -> ChatGraphOut:
    try:
        out = await GRAPH.ainvoke(
            {
                "messages": [],
                "input": body.message,
                "result": "",
                "skip_inject_system": False,
            },
            config=_graph_config(body.session_id),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ChatGraphOut(reply=str(out.get("result", "")))

@router.post("/stream")
async def stream_chat(body: ChatGraphIn) -> StreamingResponse:
    async def gen():
        inputs={
            "messages": [],
            "input": body.message,
            "result": "",
            "skip_inject_system": False,
        }
        config = _graph_config(body.session_id)
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
        except Exception as e:
            yield sse_pack("error", {"detail": str(e)})

    return StreamingResponse(gen(),media_type="text/event-stream")