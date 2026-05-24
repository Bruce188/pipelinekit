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
| `wenyan-ultra` | Extreme compression, classical-Chinese feel + three-zone split (see below). Maximum terse. **Default.** |

## Three-zone content split

Beyond the level system, subagent responses partition into three content zones by kind. The split is defined in the snippet contract at `~/.claude/snippets/caveman-subagent.md` (repo source: `claude/snippets/caveman-subagent.md`).

**Propagation protocol.** The Claude Code harness does NOT auto-inject this contract. When you dispatch a subagent via the `Agent` tool while caveman is active, you MUST prepend the contract — wrapped in `<caveman-inherited level="…">` … `</caveman-inherited>` — to the `prompt` parameter. The same rule applies recursively: a subagent that dispatches further subagents prepends the contract too. The PreToolUse gate `agent-caveman-gate.sh` enforces this: any Agent dispatch under caveman mode whose prompt lacks the contract is blocked with `exit 2` and the dispatching agent retries with the header prepended.

| Zone | Content kind | Style |
|------|--------------|-------|
| Zone 1 | Code, paths, commits, error strings, markdown structure | Normal English, exact strings, no transformation |
| Zone 2 | Narrative prose, reasoning, summaries | Real classical Chinese 文言, Han characters mandatory (U+4E00–U+9FFF) |
| Zone 3 | Fragments, status updates, beacons, bullet items | Ultra English (drop articles / filler / hedging) |

Zone 2 example (canonical): `文档新增, 验证通过. 下一步: 推送 PR.` Zone 3 example: `Build pass. Tests pass. Ready merge.` Zone 1 example: `feat: add three-zone caveman split` — preserved verbatim.

Smoke test for the snippet shape: `bash claude/skills/caveman-mode/tests/test_three_zone_split.sh`.

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
/caveman wenyan
/caveman wenyan-ultra
/caveman off
```

Shortcuts (additive — pre-existing levels unchanged):
- `/caveman wenyan` — alias for `wenyan-ultra`. Activates Zone 2 (real Han characters in narrative prose).
- `/caveman ultra` — keeps existing English-fragment semantics (Zone 3 only; no Han characters required).

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
