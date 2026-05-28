---
name: markdown-report
description: Produces structured Markdown reports in outputs/ from analysis or conversation. Use when the user wants a downloadable .md deliverable.
allowed-tools: write read glob
---

# markdown-report

## When to use

User asks for a report, summary document, or notes as Markdown.

## Instructions

1. Outline sections (title, summary, details, next steps).
2. Write the full document to `outputs/report.md` (or a user-specified name under `outputs/`) via `write`.
3. Tell the user the relative path; do not paste the entire long file in chat unless asked.

## Quality

- Use clear headings and lists; match the user's language (default Chinese if user writes in Chinese).
