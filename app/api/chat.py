from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.runtime.graph import GRAPH
from app.runtime.llm import get_llm

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
            }
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ChatGraphOut(reply=str(out.get("result", "")))
