from __future__ import annotations

from typing import Any

from pydantic import BaseModel

try:
    import jsonschema

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


def pydantic_input_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    if "$defs" in schema:
        schema = _inline_defs(schema)
    return schema


def _inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.pop("$defs", {})
    if not defs:
        return schema

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if ref.startswith("#/$defs/"):
                    key = ref.removeprefix("#/$defs/")
                    return resolve(defs.get(key, node))
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


def validate_input_schema(name: str, input_schema: dict[str, Any]) -> None:
    if input_schema.get("type") != "object":
        raise ValueError(f"tool {name}: inputSchema.type must be object")
    if not _HAS_JSONSCHEMA:
        return
    jsonschema.Draft202012Validator.check_schema(input_schema)
