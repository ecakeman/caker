---
name: execution-env
description: Help user prepare docker-compose under workspace compose/ when they ask. Do not run compose or push entering sandbox.
allowed-tools: read write glob sandbox_exec call_skill
---

# execution-env

Use only when the user **explicitly** asks for a development environment, Docker setup, or compose template.

## You may

- `read` / `glob` project files under `data/`, `outputs/`, and `compose/`
- `write` suggested `compose/docker-compose.yml` (or snippets) under the session workspace
- `sandbox_exec` to propose container commands (tests, pip install) after user confirms in the sandbox UI
- Reply with terminal commands for the user to run in the **sandbox terminal** (`compose up/down`)

## You must not

- Call legacy `exec_*` tools (removed in V2)
- Run `docker compose up/down` on behalf of the user without confirmation flow
- Push the user to enter the sandbox unless they ask how to open it

## Sandbox

Entering the sandbox is done via the main UI (**进入执行环境**), not via this skill.

When the user is already in the sandbox, prefer `sandbox_exec` for pytest/pip/npm inside the container; still use the terminal for `compose up/down`.
