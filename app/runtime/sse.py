import json
from typing import Any


def sse_pack(event: str,data: dict[str,Any])->bytes:
    return (
        f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    ).encode("utf-8")

def sse_comment(text: str = "")->bytes:
    return (
        f": {text}\n\n"
    ).encode("utf-8")