---
name: deepresearch-lite
description: Lightweight multi-step research: gather files, optional web fetch, and draft a Markdown research note in outputs/. Use for structured investigation without enterprise search APIs.
allowed-tools: read write glob download call_skill
---

# deepresearch-lite

## When to use

User wants a research memo combining local files and optional public URLs.

## Instructions

1. Clarify scope; list sources (files in `data/`, URLs).
2. Use `glob`/`read` for local sources; `download` for URLs into `data/`.
3. Take notes; write `outputs/research-draft.md` with sections: Question, Sources, Findings, Open questions.
4. Do not claim access to paywalled or enterprise databases.

## Quality

- Cite file paths or URLs for each finding.
