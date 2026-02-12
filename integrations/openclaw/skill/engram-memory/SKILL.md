---
name: engram-memory
description: Local-first persistent memory. Remember facts, decisions, and preferences across sessions. Your data never leaves your machine.
metadata: {"openclaw": {"emoji": "🧠", "homepage": "https://github.com/engram-memory/engram"}}
---

# Engram Memory

You have access to **Engram**, a local-first persistent memory system. All memories are stored on the user's machine — nothing is sent to the cloud.

## When to use memory

- **Store** important facts, user preferences, decisions, error fixes, and workflow patterns
- **Search** your memories when the user references something from a previous session
- **Recall** high-priority memories when starting a new conversation or switching context

## Memory types

Use the appropriate type when storing:
- `fact` — General knowledge or information
- `preference` — User likes, dislikes, choices
- `decision` — Agreed-upon decisions or plans
- `error_fix` — Bug fixes, workarounds, solutions
- `pattern` — Recurring patterns, conventions, standards
- `workflow` — Processes, pipelines, step-by-step procedures

## Importance scale (1-10)

- **1-3**: Nice to know, can forget
- **4-6**: Useful, recall when relevant
- **7-8**: Important, recall often
- **9-10**: Critical, never forget (user identity, hard rules, key decisions)

## Guidelines

- Do NOT store trivial greetings or small talk
- Do NOT store information the user explicitly asks you to forget
- DO store corrections — when the user corrects you, store the correction as `error_fix` with importance 8+
- DO store user preferences immediately when stated
- When unsure if something is worth remembering, store it with importance 5 — the decay system will handle the rest
- Before answering questions about past sessions, search your memories first
- When the user says "remember this" or similar, store with importance 8+
