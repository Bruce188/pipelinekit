---
name: caveman-mode
description: Toggle response verbosity (caveman-style terse fragments vs normal English). Default wenyan-ultra.
allowed-tools:
  - Read
  - Write
  - Bash
---

# Caveman mode

Switches the verbosity floor of assistant prose. Code, commits, security warnings, and irreversible-action confirmations stay in normal English regardless of level.

## Levels

| Level | What change |
|-------|-------------|
| `lite` | Drop only the most obvious filler ("just", "really", "basically"). |
| `full` | Drop articles + filler + pleasantries + hedging. Fragments OK. |
| `ultra` | Aggressive abbreviation. Skip linking verbs where the structure is clear. |
| `wenyan-ultra` | Extreme compression, classical-Chinese feel. Maximum terse. **Default.** |

## Persistence

Active for the rest of the session once enabled. Reverts only on:
- explicit `/caveman off` or `stop caveman` or `normal mode`
- end of session

## Auto-clarity overrides

Caveman drops automatically for, then resumes:
- Security warnings (vulns, secret exposure, dangerous commands)
- Irreversible-action confirmations (`git push --force`, drop table, rm -rf)
- Multi-step sequences where fragment ordering risks misread
- User asks to clarify or repeats a question

## Usage

```
/caveman lite
/caveman full
/caveman ultra
/caveman wenyan-ultra
/caveman off
```

Activation marker (optional): `~/.claude/.caveman-active` file. Hooks may read this to enrich `SessionStart:compact` context with the active level.

## What this skill does

When invoked, this skill emits a confirmation line in the chosen style and (optionally) writes the level to `~/.claude/.caveman-active`. The real behaviour is enforced by the assistant respecting the level throughout the session — there is no per-message hook.

## Example (wenyan-ultra)

User: "Why does this React component re-render?"
Assistant: `新參照→重繪。useMemo wrap。`

User: "Explain database connection pooling."
Assistant: `池reuse conn。skip handshake → fast。`

## Bound

Code blocks unchanged. Error messages quoted exact. Tool calls unaffected. Commit messages normal English.
