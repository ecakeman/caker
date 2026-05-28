from __future__ import annotations

from app.mcp.handlers import (
    call_skill,
    chroma_in,
    chroma_out,
    download,
    edit,
    glob,
    read,
    result_set,
    run_py_script,
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
    call_skill,
    chroma_in,
    chroma_out,
    result_set,
]

__all__ = ["ALL_HANDLERS"]
