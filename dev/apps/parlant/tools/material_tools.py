import json
import re
from pathlib import Path
import os
from typing import Any

import parlant.sdk as p
from parlant.core.tools import ToolContext, ToolResult

_REGISTRY: dict[str, Any] = {}
# 拓扑：{tool: [(topic_str, token_set, reuse_ids), ...]} —— 启动时一次性建立，lookup 时 fallback 用
_FUZZY_INDEX: dict[str, list[tuple[str, set[str], list[str]]]] = {}

# Overlap 阈值（Szymkiewicz–Simpson = inter / min(|q|, |c|)，对 topic 长度差不敏感）
# 低于此分数不返回——太牵强反而误导 LLM；
# 实测：完全无关 query 的 overlap=0；轻度复述/同义改写在 0.40-0.50；近义词替换约 0.85+
_FUZZY_THRESHOLD = 0.40
# Overlap 命中后，最多返回多少个 (tool, topic) 桶的 reuse_ids（合并去重）
_FUZZY_TOP_K = 3


def _tokens(s: str) -> set[str]:
    """中文 2/3-gram + 拉丁/数字保留：用于 topic 模糊匹配。"""
    s = re.sub(r"[^\u4e00-\u9fff a-zA-Z0-9]", "", s or "")
    out: set[str] = set()
    for n in (2, 3):
        for i in range(max(len(s) - n + 1, 0)):
            out.add(s[i:i+n])
    return out


def _build_fuzzy_index() -> None:
    """从 _REGISTRY['by_topic'] 拆出 (tool, topic) → token_set 索引。一次性，启动时调用。"""
    global _FUZZY_INDEX
    _FUZZY_INDEX = {}
    by_topic = _REGISTRY.get("by_topic") if isinstance(_REGISTRY, dict) else {}
    if not isinstance(by_topic, dict):
        return
    for compound_key, rids in by_topic.items():
        if "::" not in compound_key or not isinstance(rids, list):
            continue
        tool, _, topic = compound_key.partition("::")
        _FUZZY_INDEX.setdefault(tool, []).append((topic, _tokens(topic), list(rids)))


def init_registry(path: str | Path) -> None:
    global _REGISTRY
    registry_path = Path(path)
    _REGISTRY = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.is_file() else {}
    _build_fuzzy_index()


def _lookup_exact(tool: str, topic: str) -> list[str]:
    by_topic = _REGISTRY.get("by_topic") if isinstance(_REGISTRY, dict) else {}
    if not isinstance(by_topic, dict):
        return []
    return list(by_topic.get(f"{tool}::{topic}") or [])


def _material_type_for_tool(tool: str) -> str:
    return {
        "send_image": "image",
        "send_link": "link",
        "send_quoted_chat": "quoted_chat",
        "send_shareuser": "shareuser",
    }.get(tool, "")


def _tool_for_material_type(material_type: str) -> str:
    return {
        "image": "send_image",
        "link": "send_link",
        "quoted_chat": "send_quoted_chat",
        "shareuser": "send_shareuser",
    }.get(material_type, "")


def _resolve_alias(tool: str, topic: str) -> tuple[str | None, str | None, dict[str, Any]]:
    aliases = _REGISTRY.get("aliases") if isinstance(_REGISTRY, dict) else {}
    tool_aliases = aliases.get(tool) if isinstance(aliases, dict) else {}
    if not isinstance(tool_aliases, dict):
        return None, None, {"mode": "alias_miss"}
    alias = tool_aliases.get((topic or "").strip())
    if not isinstance(alias, dict):
        return None, None, {"mode": "alias_miss"}
    reuse_id = str(alias.get("reuse_id") or "").strip() or None
    material_slot_id = str(alias.get("material_slot_id") or "").strip() or None
    return reuse_id, material_slot_id, {
        "mode": "alias",
        "alias_topic": topic,
        "canonical_topic": alias.get("canonical_topic"),
        "confidence": float(alias.get("confidence") or 0.0),
    }


def resolve_material(
    *,
    topic: str = "",
    modality: str = "image",
    reuse_id: str | None = None,
    material_slot_id: str | None = None,
) -> dict[str, Any]:
    """Resolve free-form material intent to a stable registry id.

    This is intentionally internal: user-facing responses must not expose
    candidate lists. A miss means the dialogue should print [暂无可用图片].
    """
    tool = _tool_for_material_type(modality)
    if not tool:
        return {"resolved_id": None, "material_slot_id": None, "confidence": 0.0, "reason": "invalid_modality"}

    rids, meta = _lookup_precise(tool, topic, reuse_id=reuse_id, material_slot_id=material_slot_id)
    if rids:
        slot = material_slot_id
        by_reuse = _REGISTRY.get("by_reuse_id") if isinstance(_REGISTRY, dict) else {}
        if not slot and isinstance(by_reuse, dict):
            slot = (by_reuse.get(rids[0]) or {}).get("material_slot_id")
        confidence = 1.0 if meta.get("mode") in {"reuse_id", "material_slot", "exact"} else 0.95
        return {
            "resolved_id": rids[0],
            "material_slot_id": slot,
            "confidence": confidence,
            "reason": None,
            "lookup": meta,
        }

    if (topic or "").strip():
        alias_reuse_id, alias_slot, alias_meta = _resolve_alias(tool, topic)
        if alias_reuse_id or alias_slot:
            rids, meta = _lookup_precise(
                tool,
                "",
                reuse_id=alias_reuse_id,
                material_slot_id=alias_slot,
            )
            if rids:
                merged = {**alias_meta, "resolved_by": meta.get("mode")}
                return {
                    "resolved_id": rids[0],
                    "material_slot_id": alias_slot,
                    "confidence": float(alias_meta.get("confidence") or 0.9),
                    "reason": None,
                    "lookup": merged,
                }

    reason = "missing_params" if not (topic or reuse_id or material_slot_id) else "topic_miss"
    return {"resolved_id": None, "material_slot_id": None, "confidence": 0.0, "reason": reason}


def _lookup_fuzzy(tool: str, topic: str) -> tuple[list[str], list[dict]]:
    """精确未命中时的 fallback：在同 tool 内对所有 topic 做 2/3-gram overlap 召回 top-K 桶，合并去重。

    用 Szymkiewicz-Simpson overlap = |inter| / min(|q|, |c|) 而非 Jaccard，因为候选 topic
    通常带较长括号注释（"...（含 X 标注）"），Jaccard 的 union 会被膨胀拉低分数；
    overlap 仅看"query 中有多少比例的 token 在候选里出现"，对长度差不敏感。

    返回 (reuse_ids, debug_matches) —— debug_matches 给 _render 用于在响应里打印 fallback 信息。
    """
    qt = _tokens(topic)
    if not qt:
        return [], []
    candidates = _FUZZY_INDEX.get(tool) or []
    scored: list[tuple[float, str, list[str]]] = []
    for cand_topic, cand_tokens, cand_rids in candidates:
        if not cand_tokens:
            continue
        inter = len(qt & cand_tokens)
        if inter == 0:
            continue
        score = inter / min(len(qt), len(cand_tokens))
        if score >= _FUZZY_THRESHOLD:
            scored.append((score, cand_topic, cand_rids))
    scored.sort(reverse=True, key=lambda x: x[0])
    top = scored[:_FUZZY_TOP_K]

    seen: set[str] = set()
    merged: list[str] = []
    matches_dbg: list[dict] = []
    for score, cand_topic, cand_rids in top:
        matches_dbg.append({"score": round(score, 3), "matched_topic": cand_topic,
                            "n_reuse_ids": len(cand_rids)})
        for rid in cand_rids:
            if rid not in seen:
                seen.add(rid)
                merged.append(rid)
    return merged, matches_dbg


def _lookup(tool: str, topic: str) -> tuple[list[str], dict]:
    """主入口：只做精确 topic 命中。

    不做模糊降级；topic 未命中必须暴露为 miss，由上游修 production 数据。
    """
    rids = _lookup_exact(tool, topic)
    if rids:
        return rids, {"mode": "exact"}
    return [], {"mode": "miss"}


def _lookup_precise(
    tool: str,
    topic: str = "",
    reuse_id: str | None = None,
    material_slot_id: str | None = None,
) -> tuple[list[str], dict]:
    by_reuse = _REGISTRY.get("by_reuse_id") if isinstance(_REGISTRY, dict) else {}
    if reuse_id:
        item = by_reuse.get(reuse_id) if isinstance(by_reuse, dict) else None
        if not isinstance(item, dict):
            return [], {"mode": "miss_reuse_id", "reuse_id": reuse_id}
        if item.get("type") and _tool_for_material_type(str(item.get("type"))) != tool:
            return [], {"mode": "tool_mismatch", "reuse_id": reuse_id}
        return [reuse_id], {"mode": "reuse_id", "reuse_id": reuse_id}

    by_slot = _REGISTRY.get("by_slot") if isinstance(_REGISTRY, dict) else {}
    if material_slot_id and isinstance(by_slot, dict):
        slot = by_slot.get(material_slot_id)
        if not isinstance(slot, dict):
            return [], {"mode": "miss_material_slot", "material_slot_id": material_slot_id}
        rid = str(slot.get("representative_reuse_id") or "").strip()
        if slot.get("tool") != tool or not rid:
            return [], {"mode": "slot_tool_mismatch", "material_slot_id": material_slot_id}
        return [rid], {"mode": "material_slot", "material_slot_id": material_slot_id}

    return _lookup(tool, topic)


def _render(tool: str, topic: str, reuse_ids: list[str], lookup_meta: dict) -> dict[str, Any]:
    by_reuse = _REGISTRY.get("by_reuse_id") if isinstance(_REGISTRY, dict) else {}
    materials = []
    if isinstance(by_reuse, dict):
        for reuse_id in reuse_ids:
            item = by_reuse.get(reuse_id) or {}
            materials.append({"reuse_id": reuse_id, **item})
    return {
        "tool": tool, "topic": topic, "reuse_ids": reuse_ids,
        "materials": materials, "lookup": lookup_meta,
    }


def _compact_result(tool: str, topic: str, reuse_ids: list[str], lookup_meta: dict) -> dict[str, Any]:
    """Small model-visible payload; full material details belong in metadata."""
    compact_env = (
        os.environ.get("PARLANT_MATERIAL_TOOL_COMPACT_DATA")
        or os.environ.get("BROKER_MATERIAL_TOOL_COMPACT_DATA")
        or "0"
    )
    if compact_env.strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return {
            "tool": tool,
            "topic": topic,
            "reuse_ids": reuse_ids,
            "lookup": lookup_meta,
        }

    compact: dict[str, Any] = {
        "tool": tool,
        "topic": topic,
        "reuse_id": reuse_ids[0] if reuse_ids else None,
        "n_matches": len(reuse_ids),
    }
    if material_slot_id := lookup_meta.get("material_slot_id"):
        compact["material_slot_id"] = material_slot_id
    if mode := lookup_meta.get("mode"):
        compact["lookup_mode"] = mode
    return compact


def _tool_result(
    tool: str,
    topic: str = "",
    reuse_id: str | None = None,
    material_slot_id: str | None = None,
) -> ToolResult:
    material_type = _material_type_for_tool(tool)
    resolved = resolve_material(
        topic=topic,
        modality=material_type,
        reuse_id=reuse_id,
        material_slot_id=material_slot_id,
    )
    if not resolved.get("resolved_id"):
        reason = str(resolved.get("reason") or "missing_params")
        meta = {"mode": reason, "need": ["reuse_id", "material_slot_id"], "topic": topic}
        payload = {
            "ok": True,
            "reason": "no_image_fallback" if tool == "send_image" else "material_fallback",
            "need": ["reuse_id", "material_slot_id"],
            "lookup_mode": "no_image_fallback" if tool == "send_image" else "material_fallback",
            "fallback_no_image": tool == "send_image",
            "message": "素材未解析到稳定 reuse_id/material_slot_id，应降级输出 [暂无可用图片]，不要口头发图或列候选图名。",
        }
        return ToolResult(data=payload, metadata={"tool": tool, "lookup": meta}, control={"lifespan": "response"})

    resolved_reuse_id = str(resolved["resolved_id"])
    resolved_slot = resolved.get("material_slot_id") or material_slot_id
    rids, meta = _lookup_precise(
        tool,
        topic,
        reuse_id=resolved_reuse_id,
        material_slot_id=resolved_slot,
    )
    if resolved.get("lookup"):
        meta = {**meta, "resolver": resolved.get("lookup"), "confidence": resolved.get("confidence")}
    compact = _compact_result(tool, topic, rids, meta)
    if not rids and meta.get("mode", "").startswith("miss"):
        compact = {
            **compact,
            "ok": False,
            "reason": "topic_miss",
            "lookup_mode": "topic_miss",
            "fallback_no_image": tool == "send_image",
            "message": "未命中稳定素材 id，应降级输出 [暂无可用图片]，勿盲发。",
        }
    else:
        attachment_id = f"{material_type}:{rids[0]}" if material_type and rids else None
        compact = {
            **compact,
            "ok": True,
            "attachment_id": attachment_id,
            "output_url": None,
            "material_slot_id": resolved_slot,
        }
    return ToolResult(
        data=compact,
        metadata=_render(tool, topic, rids, meta),
        control={"lifespan": "response"},
    )


@p.tool
async def send_image(
    context: ToolContext,
    topic: str = "",
    reuse_id: str | None = None,
    material_slot_id: str | None = None,
) -> ToolResult:
    return _tool_result("send_image", topic, reuse_id=reuse_id, material_slot_id=material_slot_id)


@p.tool
async def send_link(
    context: ToolContext,
    topic: str = "",
    reuse_id: str | None = None,
    material_slot_id: str | None = None,
) -> ToolResult:
    return _tool_result("send_link", topic, reuse_id=reuse_id, material_slot_id=material_slot_id)


@p.tool
async def send_quoted_chat(
    context: ToolContext,
    topic: str = "",
    reuse_id: str | None = None,
    material_slot_id: str | None = None,
) -> ToolResult:
    return _tool_result("send_quoted_chat", topic, reuse_id=reuse_id, material_slot_id=material_slot_id)


@p.tool
async def send_shareuser(
    context: ToolContext,
    topic: str = "",
    reuse_id: str | None = None,
    material_slot_id: str | None = None,
) -> ToolResult:
    return _tool_result("send_shareuser", topic, reuse_id=reuse_id, material_slot_id=material_slot_id)


TOOLS = {
    "send_image": send_image,
    "send_link": send_link,
    "send_quoted_chat": send_quoted_chat,
    "send_shareuser": send_shareuser,
}

try:
    from tools.customer_facts import CUSTOMER_FACTS_TOOLS

    TOOLS.update(CUSTOMER_FACTS_TOOLS)
except Exception:  # pragma: no cover - defensive: keep material tools usable
    pass

VALID_TOOLS: frozenset[str] = frozenset(TOOLS)
