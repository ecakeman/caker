"""Journey BFS loader with tool_state / fork_state support (ported from broker)."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

import parlant.sdk as p


async def build_journey(
    agent: Any,
    j: dict,
    send_tools_map: dict[str, Callable],
) -> tuple[Any, list[str]]:
    warnings: list[str] = []

    journey = await agent.create_journey(
        title=j["title"],
        conditions=list(j.get("activation_conditions") or j.get("conditions") or []),
        description=j.get("description", ""),
    )

    states_def: dict[str, dict] = {s["state_id"]: s for s in j.get("states", [])}
    transitions = list(j.get("transitions", []))

    out_degree = Counter(
        t["from_state"]
        for t in transitions
        if t.get("from_state") and t.get("to_state") and t.get("to_state") not in ("END", "END_JOURNEY")
    )

    fork_eligible: set[str] = set()
    for sid, sd in states_def.items():
        if sd.get("state_kind") != "fork_state":
            continue
        in_edges = [t for t in transitions if t.get("to_state") == sid]
        ok = True
        for ie in in_edges:
            src = ie.get("from_state")
            if src == "INITIAL":
                ok = False
                break
            if out_degree.get(src, 0) != 1:
                ok = False
                break
        if ok and in_edges:
            fork_eligible.add(sid)

    state_nodes: dict[str, Any] = {"INITIAL": journey.initial_state}
    pending = list(transitions)
    max_iters = max(1, len(pending) * 4)

    while pending and max_iters > 0:
        max_iters -= 1
        progress = False
        new_pending: list[dict] = []

        for t in pending:
            from_id = t.get("from_state")
            to_id = t.get("to_state")
            kind = t.get("transition_kind", "direct")
            cond_text = (t.get("condition_text") or "").strip()

            if not from_id or not to_id:
                warnings.append(f"transition missing from/to: {t}")
                continue

            if from_id not in state_nodes:
                new_pending.append(t)
                continue

            from_node = state_nodes[from_id]
            tr_kwargs: dict[str, Any] = {}

            if kind == "conditional" and cond_text and cond_text.lower() != "always":
                tr_kwargs["condition"] = cond_text
            elif out_degree.get(from_id, 0) > 1 and "condition" not in tr_kwargs:
                tr_kwargs["condition"] = f"(branch: {from_id} → {to_id})"

            if to_id in ("END", "END_JOURNEY"):
                tr_kwargs["state"] = p.END_JOURNEY
                await from_node.transition_to(**tr_kwargs)
                progress = True
                continue

            if to_id in state_nodes:
                tr_kwargs["state"] = state_nodes[to_id]
                await from_node.transition_to(**tr_kwargs)
                progress = True
                continue

            sd = states_def.get(to_id)
            if not sd:
                warnings.append(f"to_state={to_id!r} undefined, using chat placeholder")
                tr_kwargs["chat_state"] = f"(placeholder) {to_id}"
            else:
                tk = sd.get("state_kind", "chat_state")
                if tk == "fork_state":
                    tr = None
                    if to_id in fork_eligible and hasattr(from_node, "fork"):
                        try:
                            tr = await from_node.fork()
                        except Exception as exc:
                            warnings.append(f"fork_state {to_id!r} failed → chat_state: {exc!r}")
                            tr = None
                    if tr is None:
                        tr_kwargs["chat_state"] = sd.get("summary_cn") or "顺着客户最在意的那块自然往下聊"
                        tr = await from_node.transition_to(**tr_kwargs)
                    state_nodes[to_id] = tr.target
                    progress = True
                    continue
                if tk == "tool_state":
                    tool_name = sd.get("tool_name", "")
                    tool_func = send_tools_map.get(tool_name)
                    if tool_func is None:
                        warnings.append(f"tool_state {to_id!r} tool {tool_name!r} not registered → chat_state")
                        tr_kwargs["chat_state"] = sd.get("tool_instruction") or "调用工具"
                    else:
                        tr_kwargs["tool_state"] = tool_func
                        if sd.get("tool_instruction"):
                            tr_kwargs["tool_instruction"] = sd["tool_instruction"]
                else:
                    tr_kwargs["chat_state"] = (
                        sd.get("chat_instruction") or sd.get("tool_instruction") or f"Proceed to {to_id}"
                    )

            tr = await from_node.transition_to(**tr_kwargs)
            state_nodes[to_id] = tr.target
            progress = True

        if not progress:
            break
        pending = new_pending

    if pending:
        warnings.append(f"{len(pending)} transitions could not be installed")

    out_degree_built = Counter()
    for t in transitions:
        f = t.get("from_state")
        to = t.get("to_state")
        if not (f and to and f in state_nodes):
            continue
        if to in ("END", "END_JOURNEY") or to in state_nodes:
            out_degree_built[f] += 1

    for sid in state_nodes:
        if sid != "INITIAL" and out_degree_built.get(sid, 0) == 0:
            try:
                await state_nodes[sid].transition_to(state=p.END_JOURNEY)
            except Exception as exc:
                warnings.append(f"leaf {sid!r} → END_JOURNEY failed: {exc!r}")

    return journey, warnings
