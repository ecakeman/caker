from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.config import settings
from app.execution.sandbox_context import build_prompt_context
from app.observability.llm_meta import reset_run_token_totals
from app.observability.session_log import append_engine, log_for_ids
from app.runtime.graph import get_graph, iter_graph_stream_events
from app.runtime.llm import get_llm
from app.runtime.sse import sse_pack


def _graph_config(session_id: str | None, user_id: str | None = None) -> dict:
    sid = (session_id or "demo").strip() or "demo"
    uid = (user_id or "local").strip() or "local"
    return {
        "configurable": {"session_id": sid, "thread_id": sid, "user_id": uid},
        "recursion_limit": settings.graph_recursion_limit,
    }


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
    sandbox_context: str = "",
    regenerate: bool = False,
) -> dict:
    return {
        "messages": [],
        "input": _format_user_input(message, attachments),
        "result": "",
        "skip_inject_system": regenerate,
        "skip_inject_user": regenerate,
        "result_set_handled": False,
        "streaming": streaming,
        "sandbox_context": sandbox_context,
    }


def _prompt_context(user_id: str, session_id: str, x_sandbox: str | None) -> str:
    include_sandbox = (x_sandbox or "").strip() == "1"
    return build_prompt_context(user_id, session_id, include_sandbox=include_sandbox)


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
logger = logging.getLogger(__name__)


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
    regenerate: bool = False


class ChatGraphOut(BaseModel):
    reply: str


@router.post("/echo", response_model=EchoOut)
async def echo(body: EchoIn) -> EchoOut:
    return EchoOut(reply=f"you said {body.message}")


@router.post("/chat-once", response_model=ChatOnceOut)
async def chat_once(
    body: ChatOnceIn,
    x_user_id: str | None = Header(default=None, alias="x-user-id"),
) -> ChatOnceOut:
    llm = get_llm(x_user_id)
    try:
        ai_msg = llm.invoke([HumanMessage(content=body.message)])
    except Exception as e:
        raise HTTPException(status_code=502, detail="LLM upstream request failed") from e
    return ChatOnceOut(reply=str(ai_msg.content))


@router.post("/chat-graph", response_model=ChatGraphOut)
async def chat_graph(
    body: ChatGraphIn,
    x_user_id: str | None = Header(default=None, alias="x-user-id"),
    x_sandbox: str | None = Header(default=None, alias="x-sandbox"),
) -> ChatGraphOut:
    uid = (x_user_id or "local").strip() or "local"
    sid = (body.session_id or "demo").strip() or "demo"
    sandbox_ctx = _prompt_context(uid, sid, x_sandbox)
    config = _graph_config(body.session_id, x_user_id)
    reset_run_token_totals(uid, sid)
    try:
        out = await get_graph().ainvoke(
            _graph_inputs(
                body.message,
                streaming=False,
                attachments=body.attachments,
                sandbox_context=sandbox_ctx,
                regenerate=body.regenerate,
            ),
            config=config,
        )
    except Exception as e:
        append_engine(
            log_for_ids(uid, sid),
            "graph_error",
            "chat-graph failed",
            level="ERROR",
            meta={"error": str(e)},
        )
        raise HTTPException(status_code=502, detail="Graph upstream request failed") from e
    from app.user_profile.reflect_task import schedule_profile_reflect

    await schedule_profile_reflect(uid, sid, config)
    return ChatGraphOut(reply=str(out.get("result", "")))


@router.post("/stream")
async def stream_chat(
    body: ChatGraphIn,
    x_user_id: str | None = Header(default=None, alias="x-user-id"),
    x_sandbox: str | None = Header(default=None, alias="x-sandbox"),
) -> StreamingResponse:
    uid = (x_user_id or "local").strip() or "local"
    sid = (body.session_id or "demo").strip() or "demo"
    sandbox_ctx = _prompt_context(uid, sid, x_sandbox)

    async def gen():
        inputs = _graph_inputs(
            body.message,
            streaming=True,
            attachments=body.attachments,
            sandbox_context=sandbox_ctx,
            regenerate=body.regenerate,
        )
        config = _graph_config(body.session_id, x_user_id)
        emit_status = settings.stream_emit_tool_status
        log_ctx = log_for_ids(uid, sid)
        reset_run_token_totals(uid, sid)
        delta_batches = 0
        delta_chars = 0
        try:
            async for ev in iter_graph_stream_events(inputs, config=config):
                event = ev.get("event")
                node = _langgraph_node(ev)

                if event == "on_chat_model_end" and node in (None, "llm"):
                    output = ev.get("data", {})
                    if isinstance(output, dict):
                        ai_msg = output.get("output")
                        if ai_msg is not None and settings.session_agent_log_enabled:
                            from app.observability.llm_meta import extract_token_usage

                            usage = extract_token_usage(ai_msg)
                            if usage:
                                from app.observability.session_log import append_agent

                                append_agent(
                                    log_ctx,
                                    "llm_stream_end",
                                    "completed",
                                    meta=usage,
                                )
                    continue

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
                    label = _tool_label_from_event(ev) or "tool"
                    yield sse_pack(
                        "status",
                        {
                            "phase": "tool_done",
                            "tool": label,
                            "detail": "工具执行完成",
                        },
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
                    delta_batches += 1
                    delta_chars += len(content)
                    if settings.session_agent_log_enabled and delta_batches % 20 == 0:
                        from app.observability.session_log import append_agent

                        append_agent(
                            log_ctx,
                            "stream_delta",
                            "batch",
                            meta={"batches": delta_batches, "chars": delta_chars},
                        )
                    yield sse_pack("delta", {"text": content})

            if settings.session_agent_log_enabled and delta_batches:
                from app.observability.session_log import append_agent

                append_agent(
                    log_ctx,
                    "stream_done",
                    "completed",
                    meta={"batches": delta_batches, "chars": delta_chars},
                )
            yield sse_pack("done", {})
            from app.user_profile.reflect_task import schedule_profile_reflect

            await schedule_profile_reflect(uid, sid, config)
        except Exception as e:
            logger.exception("stream chat failed")
            append_engine(
                log_ctx,
                "graph_error",
                "stream failed",
                level="ERROR",
                meta={"error": str(e)},
            )
            detail = str(e).strip() or "stream upstream request failed"
            if len(detail) > 240:
                detail = detail[:240] + "…"
            yield sse_pack("error", {"detail": detail})

    return StreamingResponse(gen(), media_type="text/event-stream")
