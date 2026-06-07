from __future__ import annotations

import logging
import sys
from pathlib import Path

import parlant.sdk as p

from app.artifacts import load_artifacts
from app.config import AppSettings
from app.governance.manifest_fingerprint import manifest_fingerprint
from app.loaders.glossary import install_glossary
from app.loaders.guidelines import install_guidelines
from app.loaders.journeys import install_journeys

# Register @p.tool handlers at import time (material + customer_facts).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tools.material_tools  # noqa: E402, F401

from tools.customer_facts import (  # noqa: E402
    CUSTOMER_FACTS_VARIABLE_DESCRIPTION,
    CUSTOMER_FACTS_VARIABLE_NAME,
    set_variable_id as _set_customer_facts_variable_id,
)
from tools.material_tools import TOOLS, init_registry  # noqa: E402

_logger = logging.getLogger(__name__)


async def _ensure_customer_facts_variable(agent: p.Agent) -> None:
    try:
        existing = await agent.find_variable(name=CUSTOMER_FACTS_VARIABLE_NAME)
    except Exception:
        existing = None
    if existing is not None:
        _set_customer_facts_variable_id(existing.id)
        return
    try:
        variable = await agent.create_variable(
            name=CUSTOMER_FACTS_VARIABLE_NAME,
            description=CUSTOMER_FACTS_VARIABLE_DESCRIPTION,
        )
        _set_customer_facts_variable_id(variable.id)
    except Exception as exc:
        _logger.warning("customer_facts variable setup failed: %r", exc)


async def bootstrap_agent(agent: p.Agent, settings: AppSettings) -> dict:
    registry_path = settings.root / "data" / "materials" / "registry.json"
    init_registry(registry_path)
    await _ensure_customer_facts_variable(agent)

    bundle = load_artifacts(settings.artifacts_root)
    manifest_fp = manifest_fingerprint(settings.artifacts_root / "manifest.json")
    glossary_stats = await install_glossary(agent, settings.root, glossary_doc=bundle.glossary)
    j_stats, journeys_by_id = await install_journeys(agent, bundle.journeys)
    g_stats = await install_guidelines(
        agent,
        bundle.guidelines,
        bundle.scope_map,
        journeys_by_id,
    )
    return {
        "glossary": glossary_stats,
        "guidelines": g_stats,
        "journeys": j_stats,
        "tools_registered": sorted(TOOLS.keys()),
        "material_registry": str(registry_path),
        "manifest_version": bundle.manifest.get("pipeline_version") or bundle.manifest.get("version"),
        "manifest_sha256": manifest_fp.get("manifest_sha256"),
        "manifest_missing_required_artifacts": manifest_fp.get("missing_required_artifacts"),
        "variables_count": (bundle.variables.get("stats") or {}).get("total"),
        "canned_count": (bundle.canned_responses.get("stats") or {}).get("count"),
        "artifact_stats": bundle.manifest.get("stats"),
    }
