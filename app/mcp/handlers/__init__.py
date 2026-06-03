from __future__ import annotations

from app.mcp.handlers import (
    caker_mirror,
    call_skill,
    chroma_in,
    chroma_out,
    daemon_tools,
    download,
    edit,
    file_watch_tools,
    glob,
    read,
    result_set,
    run_py_script,
    sandbox_exec,
    time_tool,
    write,
)

ALL_HANDLERS = [
    read,
    write,
    glob,
    edit,
    download,
    time_tool,
    run_py_script,
    sandbox_exec,
    caker_mirror,
    daemon_tools,
    file_watch_tools,
    call_skill,
    chroma_in,
    chroma_out,
    result_set,
]

__all__ = ["ALL_HANDLERS"]
