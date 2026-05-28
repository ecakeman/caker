---
name: report-html
description: Builds self-contained HTML reports with optional ECharts charts under outputs/. Use when the user wants a browser-viewable dashboard or visual report.
allowed-tools: write read
---

# report-html

## When to use

User wants charts, HTML preview, or a shareable single-file report.

## Instructions

1. Create `outputs/report.html` with `write`.
2. Include ECharts from CDN only if network is available in the user's browser; prefer inline data in the page.
3. Keep paths relative; assets stay under `outputs/`.
4. Summarize what the HTML contains and how to open it (local file or via static server).

## Template

- Title, summary section, one chart or table as needed, footer with generation time (`get_current_time` optional).
