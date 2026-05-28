from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler


class GetCurrentTimeArgs(BaseModel):
    timezone: str = Field("UTC", description="IANA timezone name, e.g. Asia/Shanghai")


def handle_get_current_time(args: dict, ctx: ToolContext) -> ToolCallResult:
    _ = ctx
    parsed = GetCurrentTimeArgs.model_validate(args)
    try:
        tz = ZoneInfo(parsed.timezone)
    except ZoneInfoNotFoundError:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": f"unknown timezone: {parsed.timezone}"}),
            is_error=True,
        )
    now = datetime.now(tz=tz)
    return ToolCallResult(
        text=json.dumps(
            {
                "ok": True,
                "iso": now.isoformat(),
                "timezone": parsed.timezone,
            },
            ensure_ascii=False,
        )
    )


DEFINITION = McpToolDefinition(
    name="get_current_time",
    description="Return current date and time in the given IANA timezone.",
    input_schema=pydantic_input_schema(GetCurrentTimeArgs),
)
HANDLER: ToolHandler = handle_get_current_time
