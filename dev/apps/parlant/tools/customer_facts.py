"""Persist customer-facing facts into Parlant ``context_variables``.

The agent learns durable customer details over many turns - age, family
structure, health declarations, budget, concerns, materials already sent.
Once those facts roll out of the prompt history window they would otherwise
be lost.  We surface a single ``record_customer_facts`` tool the agent can
call to merge new facts into a per-customer ``customer_facts`` Variable, and a
``read_customer_facts`` helper to inspect what is currently remembered.

Both tools are intentionally schema-light: the agent supplies a JSON string
with arbitrary keys (we recommend a small, broker-defined namespace via the
guideline that triggers the call).  We always shallow-merge values to avoid
clobbering existing facts; ``null`` clears a key.

Note: ``from __future__ import annotations`` is intentionally NOT used here
because Parlant's ``@p.tool`` decorator validates the first parameter's
annotation by ``==`` against the runtime ``ToolContext`` class.
"""

import json
import logging
from typing import Any, Mapping, Optional, Union

import parlant.sdk as p
from parlant.core.context_variables import (
    ContextVariableId,
    ContextVariableStore,
)
from parlant.core.tools import ToolContext, ToolResult

_logger = logging.getLogger(__name__)

CUSTOMER_FACTS_VARIABLE_NAME = "customer_facts"
CUSTOMER_FACTS_VARIABLE_DESCRIPTION = (
    "Durable customer-facing facts the agent has gathered across the conversation. "
    "Includes basic profile (age/gender/family), health declarations, budget, "
    "preferences, concerns, open questions, and which materials have been shared. "
    "Use ``record_customer_facts`` to update; this object is always available to "
    "the agent at the top of each prompt as a CONTEXT_VARIABLES entry."
)

_VARIABLE_ID: Optional[ContextVariableId] = None
_MAX_KEYS = 64
_MAX_VALUE_CHARS = 600


def set_variable_id(variable_id: Union[ContextVariableId, str, None]) -> None:
    global _VARIABLE_ID
    _VARIABLE_ID = ContextVariableId(variable_id) if variable_id else None


def get_variable_id() -> Optional[ContextVariableId]:
    return _VARIABLE_ID


def _coerce_facts(payload: Any) -> Union[dict, str]:
    if isinstance(payload, dict):
        candidate = payload
    elif isinstance(payload, str):
        text = payload.strip()
        if not text:
            return "empty_payload"
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError as exc:
            return f"invalid_json: {exc.msg}"
    else:
        return "facts_must_be_object_or_json_string"

    if not isinstance(candidate, dict):
        return "facts_must_decode_to_object"
    return candidate


def _truncate_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_VALUE_CHARS:
        return value[:_MAX_VALUE_CHARS].rstrip() + "...[truncated]"
    if isinstance(value, list):
        return [_truncate_value(v) for v in value[:20]]
    if isinstance(value, dict):
        return {str(k): _truncate_value(v) for k, v in list(value.items())[:_MAX_KEYS]}
    return value


def _merge_facts(
    existing: Mapping[str, Any], updates: Mapping[str, Any]
) -> dict:
    merged: dict = dict(existing)
    for key, value in updates.items():
        clean_key = str(key).strip()
        if not clean_key:
            continue
        if value is None:
            merged.pop(clean_key, None)
            continue
        merged[clean_key] = _truncate_value(value)

    if len(merged) > _MAX_KEYS:
        truncated = dict(list(merged.items())[-_MAX_KEYS:])
        return truncated
    return merged


async def _read_value(
    store: ContextVariableStore,
    variable_id: ContextVariableId,
    customer_id: str,
) -> dict:
    value = await store.read_value(variable_id=variable_id, key=customer_id)
    if value and isinstance(value.data, dict):
        return dict(value.data)
    return {}


def _server_store() -> Optional[ContextVariableStore]:
    try:
        server = p.Server.current
    except RuntimeError:
        return None
    return server._container[ContextVariableStore]  # type: ignore[index]


@p.tool
async def record_customer_facts(context: ToolContext, facts: str) -> ToolResult:
    """Merge a JSON object of facts into the customer's ``customer_facts`` variable.

    Args:
        facts: JSON-encoded object with the new/updated keys. Pass ``null`` for a
            value to remove that key. Keys should be short, broker-defined names
            such as ``age``, ``family_status``, ``budget_yearly``, ``health_flags``,
            ``concerns``, ``materials_sent``.
    """
    if _VARIABLE_ID is None:
        return ToolResult(
            data={"ok": False, "reason": "customer_facts_variable_not_initialized"},
            control={"lifespan": "response"},
        )

    coerced = _coerce_facts(facts)
    if isinstance(coerced, str):
        return ToolResult(
            data={"ok": False, "reason": coerced},
            control={"lifespan": "response"},
        )

    store = _server_store()
    if store is None:
        return ToolResult(
            data={"ok": False, "reason": "server_unavailable"},
            control={"lifespan": "response"},
        )

    customer_id = context.customer_id
    existing = await _read_value(store, _VARIABLE_ID, customer_id)
    merged = _merge_facts(existing, coerced)
    await store.update_value(
        variable_id=_VARIABLE_ID,
        key=customer_id,
        data=merged,
    )

    return ToolResult(
        data={
            "ok": True,
            "updated_keys": list(coerced.keys()),
            "total_keys": len(merged),
        },
        metadata={"customer_facts": merged},
        control={"lifespan": "response"},
    )


@p.tool
async def read_customer_facts(context: ToolContext) -> ToolResult:
    """Return the current ``customer_facts`` snapshot for the active customer."""
    if _VARIABLE_ID is None:
        return ToolResult(
            data={"ok": False, "reason": "customer_facts_variable_not_initialized"},
            control={"lifespan": "response"},
        )

    store = _server_store()
    if store is None:
        return ToolResult(
            data={"ok": False, "reason": "server_unavailable"},
            control={"lifespan": "response"},
        )

    facts = await _read_value(store, _VARIABLE_ID, context.customer_id)
    return ToolResult(
        data={"ok": True, "facts": facts, "total_keys": len(facts)},
        control={"lifespan": "response"},
    )


CUSTOMER_FACTS_TOOLS = {
    "record_customer_facts": record_customer_facts,
    "read_customer_facts": read_customer_facts,
}
