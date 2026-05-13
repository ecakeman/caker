from fastapi import FastAPI

from app.api.chat import router as chat_router

app = FastAPI(title="caker")
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"ok": True}

# TODO: 你加 request_id 中间件、structlog 日志
