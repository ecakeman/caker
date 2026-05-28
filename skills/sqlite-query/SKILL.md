---
name: sqlite-query
description: Queries or inspects SQLite databases under data/*.db in the session workspace. Use for SQL lookups, schema inspection, or exporting query results.
allowed-tools: read write run_py_script glob
compatibility: Requires Python sqlite3; database file under data/
---

# sqlite-query

## When to use

User provides or references a `.db` file and wants SQL results or schema.

## Instructions

1. Confirm database path with `glob` (e.g. `data/**/*.db`).
2. Run `skills/sqlite-query/scripts/query.py` via `run_py_script` with args: db path, SQL statement (read-only preferred).
3. Save large results to `outputs/query-result.txt` with `write` if needed.
4. Summarize findings for the user in Markdown.

## Safety

- Prefer SELECT; avoid destructive SQL unless user explicitly requests and confirms.
