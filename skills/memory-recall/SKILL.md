---
name: memory-recall
description: Searches long-term vector memory (Chroma) for facts the user asked to remember earlier. Use when the user asks what was saved or refers to past remembered information.
allowed-tools: chroma_out call_skill read
---

# memory-recall

## When to use

User asks to recall, retrieve, or check what was remembered; or a question clearly depends on prior stored facts.

## Instructions

1. Form a short query from the user's question.
2. Call `chroma_out` with that query text.
3. If `count` is 0, say no matching memory was found.
4. Otherwise summarize relevant `hits` and cite that they came from long-term memory.
5. Optionally use `read` on workspace files if the user also attached local files.

## Quality

- Do not invent memories not present in `hits`.
- If hits conflict, mention uncertainty and ask the user to clarify.
