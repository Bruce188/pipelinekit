---
name: incident
description: Triage a failing post-merge verification gate using @incident-responder. Gathers failure context from logs and dispatches the incident-responder agent with a structured prompt. Use when /post-merge reports a verification failure or any post-merge anomaly.
argument-hint: [path-to-log-file] (optional)
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Agent
---

# /incident — Triage post-merge verification failure

Dispatch `@incident-responder` against a structured failure brief built from local
signals. The skill is human-invoked — typically after `/post-merge` prints an
advisory line referencing `/incident`.

## Usage

```
/incident                       # collect signals from local logs and dispatch
/incident docs/.last-verify.json   # collect signals starting from the given file
```

## Steps

1. Collect failure context:
   - If `$ARGUMENTS` includes a path, read that file first.
   - Otherwise, look in this order (read what exists, skip what doesn't):
     - `docs/.last-verify.json` — verification gate output
     - `~/.claude/logs/*.log` — recent agent/skill logs (last 200 lines per file)
     - `git log -5 --oneline` and `git status --porcelain` for working-tree state
     - `gh run list --limit 3 --json name,status,conclusion,headBranch` if `gh` is available
   - Summarize what was checked and what is known. Keep the summary under 50 lines.

2. Dispatch the incident-responder agent via the Agent tool:
   - subagent_type: `incident-responder`
   - prompt: a structured brief containing:
     - The failure summary from Step 1.
     - Branch name, base branch, current SHA (`git rev-parse HEAD`).
     - Any deploy/cloud signals surfaced by `/post-merge` (Azure config, etc.).
     - Instruction: produce a triage report with severity, suspected root cause,
       and recommended next action.
   - Capture the agent's response.

3. Persist the triage report:
   - Write the agent's response to `docs/incident-$(date -u +%Y%m%d-%H%M%S).md`.
   - `docs/incident-*.md` files are workflow artifacts — never committed (matches
     the `docs/` convention; covered by `block-stage-sensitive.sh`).

4. Print a one-screen summary to stdout:
   - Severity (extracted from the triage report).
   - Suspected root cause (1-2 lines).
   - Recommended next action (1-2 lines).
   - Path to the full report (`docs/incident-<timestamp>.md`).

## Notes

- This skill does NOT re-run the verification gate. The user decides next steps.
- The Agent dispatch uses the `@incident-responder` definition vendored from
  `wshobson/agents` (see `claude/agents/incident-responder.md`).
- If `@incident-responder` is not available (e.g., pipelinekit installed without
  the vendored agents), fall back to an inline triage prompt run by the current
  model, and warn the user to re-run `./scripts/install.sh`.
- This skill is advisory and non-halting. It produces a report; it never
  modifies branches, commits, or remote state.
