---
name: github-readonly
description: Clones or reads public GitHub repositories into data/ for inspection. Use when the user wants code from a public repo URL without modifying remotes.
allowed-tools: download read glob run_py_script write
compatibility: Requires git and network access
---

# github-readonly

## When to use

User shares a `https://github.com/owner/repo` URL and wants files read or summarized.

## Instructions

1. Clone shallow into `data/repos/<repo-name>/` using `run_py_script` with `skills/github-readonly/scripts/clone.py` and the repo URL.
2. Use `glob` and `read` to inspect files; do not push or modify git remotes.
3. Write notes to `outputs/github-summary.md` if the user wants a report.

## Safety

- Public repos only unless user supplies credentials (out of scope).
