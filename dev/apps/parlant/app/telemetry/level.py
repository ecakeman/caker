from __future__ import annotations

import os


def telemetry_level() -> str:
    return (os.environ.get("TELEMETRY_LEVEL") or "default").strip().lower()


def is_debug_telemetry() -> bool:
    return telemetry_level() in {"debug", "full", "verbose"}
