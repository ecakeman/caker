from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.telemetry.collector import TurnCollector

_current_collector: ContextVar[TurnCollector | None] = ContextVar("turn_collector", default=None)


def get_collector() -> TurnCollector | None:
    return _current_collector.get()


def set_collector(collector: TurnCollector | None) -> None:
    _current_collector.set(collector)
