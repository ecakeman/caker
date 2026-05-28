---
name: online-search-web
description: Fetches public web pages and summarizes content into outputs/. Use for general web references; does not include enterprise registry or paywalled search APIs.
allowed-tools: download write read
---

# online-search-web

## When to use

User provides a URL or asks to summarize a public web page.

## Instructions

1. Download the page to `data/fetched-page.html` (or appropriate extension) via `download`.
2. Use `read` on the saved file; extract main text (ignore boilerplate when possible).
3. Write summary to `outputs/web-summary.md` with `write`.
4. State limitations (JS-rendered sites may be incomplete).

## Not in scope

- Enterprise credit/search APIs (e.g. Qichacha).
- Authenticated or paywalled content.
