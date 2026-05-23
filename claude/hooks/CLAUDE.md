# claude/hooks

Authoring rules for pipelinekit hooks. A hook is one bash or python3 script registered with the harness to fire on a tool-call boundary. Hooks act as gates (block / allow / advise) — they never replace the tool itself.

## Hook Event Catalog

| Event | Fires when | Typical use |
|-------|------------|-------------|
| `PreToolUse` | Before any tool call dispatches | Validate inputs, block dangerous commands, sanitize args |
| `PostToolUse` | After a tool call returns | Format output, log results, trigger follow-up gates |
| `UserPromptSubmit` | User presses enter on a prompt | Inject session metadata, redact PII before send |
| `Stop` | Agent stops without further tool calls | Surface completion notification, run quality gate, emit cost log |
| `SessionStart` | New Claude Code session boots | Load per-project memory, set env vars, print intro banner |
| `Notification` | Harness emits a notification | Forward to push channels, write a desktop OSC sequence |
| `PreCompact` | Before context compaction runs | Snapshot in-progress work, save the active feature pointer |

Event names are case-sensitive and match the keys in the harness's hook registry (`~/.claude/settings.json` → `hooks.<EventName>`).

## Stdin/Stdout Contract

Every hook reads a JSON envelope from stdin and writes either JSON or a `terminalSequence` string to stdout. Minimal envelope:

```json
{
  "tool_input": {"command": "git commit -m 'feat: x'"},
  "tool_name": "Bash",
  "session_id": "abc123",
  "cwd": "/home/user/project"
}
```

Read the envelope with `python3 -c` (jq is NOT installed — see `~/.claude/memory/feedback_hooks_jq.md`):

```bash
INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('command', ''))
" 2>/dev/null)
```

For hooks that return JSON (Notification, Stop), emit a single-line JSON object on stdout — see `./notify-emit.sh` for the canonical `terminalSequence` shape and the OSC 777 byte sequence it produces.

## Exit-Code Semantics

- **exit 0** — Continue normally. Tool call dispatches. No message to the user.
- **exit 1** — Blocking error. The tool call is BLOCKED and stderr is surfaced as the block reason. Use for validator hooks (`validate-commit-msg.sh`) that catch contract violations.
- **exit 2** — Informational block. Tool call is BLOCKED and stderr is surfaced as a user advisory, but the session continues. The agent can adjust and retry. Use for staging gates (`block-stage-sensitive.sh`) where the agent should self-correct.

Stop hooks are the exception: by contract, ANY exit code from a `Stop` hook is non-blocking. Stop hooks never veto session termination — they exist to emit notifications and final logs, not to gate.

## Authoring Language Policy

- **bash** (`*.sh`) — preferred for thin gates that mostly route stdin → python3 → stdout. Use `set -euo pipefail` at the top.
- **python3** (`*.py`) — preferred for anything with non-trivial parsing, glob matching, or shared helper imports. Stdlib only; no `pip install`.
- **No** node, ruby, perl, go, or compiled binaries. The harness ships bash + python3; anything else is a portability bug.
- Helper modules go alongside the hook (`_pathguard.py`, `_never_stage_match.py`). Underscore-prefix marks them as internal — they are imported by other hooks, not registered directly.

## Authoring Conventions

- **Guard external commands.** Check tool availability before use: `command -v jq >/dev/null 2>&1 || python3_fallback`. The hook MUST gracefully fall back when a tool is absent; never assume `jq`, `yq`, `ripgrep`, or similar third-party CLIs are installed.
- **Always quote shell variables.** `[ -z "$VAR" ]`, `grep -F "$line"`, `echo "$COMMAND"`. Unquoted vars splatter on whitespace and break the gate.
- **Bound the input.** Hooks run on every matching tool call; a hot loop in a hook compounds session cost. Pre-filter stdin with bash builtins (`[[ "$INPUT" == *git* ]] || exit 0`) before invoking python3 — see `validate-commit-msg.sh` for the canonical pre-filter pattern.
- **Stdlib only for python hooks.** No `requests`, no `yaml`, no `click`. Use `json`, `os`, `sys`, `re`, `subprocess`, `pathlib`, `argparse`, `fnmatch`.
- **Stderr is the user surface on exit 1 / exit 2.** Write actionable messages: `error: <category>: <what failed> -- <how to fix>`. Avoid stack traces; catch and reformat exceptions.
- **Self-test mode.** Bash hooks SHOULD support `bash hook.sh --selftest` that runs inline test cases without harness involvement. See `validate-commit-msg.sh` for the canonical `--selftest` shape (case table + PASS/FAIL counter).

## When to Extend vs Add New

1. **Same event, same surface** → extend the existing hook. Adding a new forbidden token to `validate-commit-msg.sh`? Edit the regex constant; do not fork the hook.
2. **Same event, different surface** → consider extension. A new staging rule for a different file class probably belongs alongside the existing `block-stage-sensitive.sh` logic (the never-stage config file is the extension point, not a new hook).
3. **Different event entirely** → new hook. A `Stop` gate cannot live inside a `PreToolUse` hook; the harness routes by event, not by intent.
4. **Cross-cutting helper** (path validation, JSON parsing) → new underscore-prefixed module (`_pathguard.py`, `_never_stage_match.py`). Import from each hook that needs it.

Registration: adding a new hook means editing `~/.claude/settings.json` (or the project's `.claude/settings.json`) to attach the script to its event. The hook file itself is inert until the harness registers it.

## Denial Tracking

Hooks that block repeatedly on the same surface burn agent tokens in retry loops. The `denial_tracker.py` helper records consecutive denials per `(tool, rule)` pair and, after 3 hits in 5 minutes, converts the block into an `ask` advisory so the agent stops banging on the gate. See `block-stage-sensitive.sh` (search for `denial_tracker`) for the integration pattern. New gating hooks SHOULD wire through the tracker for any rule that the agent is likely to hit more than once per session.

## See Also

- Root rules: `../../CLAUDE.md`.
- Sibling subdir rules: `../skills/CLAUDE.md`, `../agents/CLAUDE.md`.
- Notification surface: `./notify-emit.sh` is the canonical 6-field payload builder for the orchestrator.
