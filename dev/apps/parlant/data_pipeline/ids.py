from __future__ import annotations

import hashlib
import re


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:max_len] or "item")


def content_hash(*parts: str) -> str:
    payload = "\n---\n".join(p.strip() for p in parts if p)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def guideline_id(condition: str, action: str) -> str:
    return f"ag_{content_hash(condition, action)}"


def journey_id(title: str) -> str:
    return f"J_{_slug(title, 32)}_{content_hash(title)[:8]}"


def state_key(journey_id_val: str, state_id: str) -> str:
    return f"{journey_id_val}::{state_id}"
