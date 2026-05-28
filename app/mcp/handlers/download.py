from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.mcp.handlers._workspace import resolve_write
from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace.manager import WorkspaceError

MAX_BYTES = 10 * 1024 * 1024
TIMEOUT_SEC = 30


class DownloadArgs(BaseModel):
    url: str = Field(..., description="HTTP or HTTPS URL")
    rel_path: str = Field(
        ...,
        description="Destination path under data/, e.g. data/download.bin",
    )


def handle_download(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = DownloadArgs.model_validate(args)
    parsed_url = urlparse(parsed.url.strip())
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": "url must be http or https"}),
            is_error=True,
        )

    try:
        target = resolve_write(ctx, parsed.rel_path)
    except WorkspaceError as e:
        return ToolCallResult(text=json.dumps({"ok": False, "error": str(e)}), is_error=True)

    try:
        with httpx.Client(timeout=TIMEOUT_SEC, follow_redirects=True) as client:
            with client.stream("GET", parsed.url) as resp:
                resp.raise_for_status()
                total = 0
                chunks: list[bytes] = []
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        return ToolCallResult(
                            text=json.dumps({"ok": False, "error": "response too large"}),
                            is_error=True,
                        )
                    chunks.append(chunk)
    except httpx.HTTPError as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}),
            is_error=True,
        )

    data = b"".join(chunks)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return ToolCallResult(
        text=json.dumps(
            {
                "ok": True,
                "path": parsed.rel_path,
                "bytes": len(data),
                "filename": Path(parsed.rel_path).name,
            },
            ensure_ascii=False,
        )
    )


DEFINITION = McpToolDefinition(
    name="download",
    description="Download a file from HTTP(S) into data/ or outputs/ (size limit 10MB).",
    input_schema=pydantic_input_schema(DownloadArgs),
)
HANDLER: ToolHandler = handle_download
