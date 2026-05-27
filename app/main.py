from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.api.chat import router as chat_router
from app.runtime.graph import compile_graph

DB_PATH = Path("var/state.db")

@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("var").mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
        await checkpointer.setup()
        compile_graph(checkpointer)
        yield

app = FastAPI(title="caker", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"ok": True}

# TODO: 你加 request_id 中间件、structlog 日志
