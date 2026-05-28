---
name: file-extract
description: Extracts relevant lines or sections from large text files in data/ or outputs/ based on a natural-language query. Use when the user wants snippets from logs, exports, or long documents.
allowed-tools: read glob
compatibility: Requires text files in session workspace
---

# file-extract

## When to use

- User points to a large file and asks for specific parts (errors, dates, keywords).
- Output from a prior command was saved and needs filtering.

## Instructions

1. Use `glob` to locate candidate files if path is unclear.
2. Use `read` with `offset`/`limit` to page through the file; avoid loading entire huge files in one reply.
3. Collect lines matching the user's criteria; quote with line numbers from `read` output.
4. Optionally write a summary to `outputs/extract-summary.md` via `write`.

## Edge cases

- If file is binary, state that text extraction is not supported.
- If no matches, say so and suggest broader keywords.
