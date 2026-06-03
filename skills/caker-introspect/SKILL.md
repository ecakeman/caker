---
name: caker-introspect
description: Read-only introspection of Caker's own published source on GitHub. Use when the user asks how Caker works, where a tool is defined, or why sandbox isolation blocks engine code in the workspace.
allowed-tools: caker_mirror_read caker_mirror_glob call_skill
---

# caker-introspect

## When to use

- User asks about **Caker itself** (runtime, MCP tools, sandbox, observability, web UI)
- User wants to know **where** a feature is implemented in the Caker repo
- Agent would otherwise guess paths under the session workspace for engine code

## Mirror

- Source of truth: **https://github.com/ecakeman/caker** (read-only)
- Tools: `caker_mirror_glob` then `caker_mirror_read` — **not** workspace `read`/`glob`
- Cannot modify Caker via these tools; changes belong in a local checkout / PR outside the session sandbox

## Instructions

1. `call_skill(skill_name="caker-introspect")` is optional if you already know the flow; otherwise load this skill first.
2. Use `caker_mirror_glob` to locate files (e.g. `app/mcp/handlers/*.py`, `system_prompt.md`).
3. Use `caker_mirror_read` with `offset`/`limit` for large files; negative offset for log-style tails.
4. Summarize for the user in plain language; cite repo paths (e.g. `app/mcp/registry.py`), not workspace paths.
5. If the user wants to **change** Caker, explain they must edit the GitHub repo / local clone — the mirror is view-only.

## Do not

- Clone the Caker repo into `data/` for self-introspection (use mirror tools instead)
- Use `write`/`edit` against engine paths — they are not in the session workspace
- Claim you modified Caker source after reading the mirror
