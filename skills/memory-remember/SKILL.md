---
name: memory-remember
description: Stores user-provided facts in long-term vector memory (Chroma) scoped by user_id. Use when the user explicitly asks to remember something for future sessions.
allowed-tools: chroma_in call_skill
---

# memory-remember

## When to use

User says to remember, save for later, or store a preference/fact across conversations.

## Instructions

1. Extract the exact fact or preference to store (one concise sentence when possible).
2. Call `chroma_in` with that text.
3. Confirm `ok: true` and `memory_id` to the user.
4. Do not store secrets the user did not intend to persist unless they clearly asked.

## Notes

- Memory is per **user_id**, not per session.
- Prefer `chroma_out` or automatic recall when answering later questions.
