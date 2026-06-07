from __future__ import annotations

from pathlib import Path

from tools.material_tools import TOOLS, init_registry, _lookup_precise, resolve_material


def test_tools_registry_has_material_and_facts() -> None:
    for name in (
        "send_image",
        "send_link",
        "send_quoted_chat",
        "send_shareuser",
        "record_customer_facts",
        "read_customer_facts",
    ):
        assert name in TOOLS


def test_material_registry_lookup() -> None:
    root = Path(__file__).resolve().parents[1]
    init_registry(root / "data" / "materials" / "registry.json")
    rids, meta = _lookup_precise("send_image", topic="保险经纪人身份/执业资质查询截图")
    assert rids, meta
    assert meta.get("mode") == "exact"


def test_material_resolver_alias_to_stable_id() -> None:
    root = Path(__file__).resolve().parents[1]
    init_registry(root / "data" / "materials" / "registry.json")
    resolved = resolve_material(topic="线上理赔流程与服务连续性说明", modality="image")
    assert resolved["resolved_id"] == "image59"
    assert resolved["material_slot_id"] == "image_slot_0372"
    assert resolved["confidence"] >= 0.9


def test_material_resolver_miss_requires_no_image_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    init_registry(root / "data" / "materials" / "registry.json")
    resolved = resolve_material(topic="不存在的图片素材", modality="image")
    assert resolved["resolved_id"] is None
    assert resolved["reason"] == "topic_miss"
