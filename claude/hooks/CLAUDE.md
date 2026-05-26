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

## Registering in install.sh

Every Claude-harness hook in this directory (every `<name>.sh` and `<name>.py` excluding `_`-prefixed helpers and the git-only `validate-task-spec.py`) MUST appear in the canonical-dict python heredoc inside `scripts/install.sh:57-103` (`maybe_install_settings`). Re-running the installer with `CLAUDE_INSTALL_SETTINGS=1` rewrites `~/.claude/settings.json` from this dict — a hook missing from the dict will not be wired, even though the file ships in the overlay.

Event mapping is canonical at `claude/skills/build-hook/SKILL.md` § "Existing Hooks" — consult that table when adding a new hook to decide which event array gets the new entry. Within each event array, order hooks alphabetically.

Parity is gated by `claude/hooks/tests/test_install_settings_shape.sh` test_05 (`full_inventory_parity`). The test runs the installer in a sandbox `CLAUDE_HOME` and asserts every `*.sh` + `*.py` (minus exclusions) appears as a `command` value in the produced `settings.json`. Add a new hook → re-run the test → fix the install.sh heredoc until green.

Exclusions:
- `validate-task-spec.py` — git pre-commit hook (lives at `.git/hooks/pre-commit` after install). NOT a Claude-harness hook; never appears in `settings.json`.
- `cost_log.py` — pipeline cost-event CLI invoked by skills (e.g. `claude/skills/research/research-loop.sh`). Requires positional `start|end|report|parse-json` args, so wiring it raw to `PostToolUse` emits an argparse usage error on every tool call. NOT a hook; never appears in `settings.json`.
- `commit-msg-wrapper.sh` — native git commit-msg hook adapter (installed as a symlink at `<git_dir>/hooks/commit-msg` by `scripts/install.sh:install_native_commit_msg_hook`). Bridges git's argv-passed message-file contract to `validate-commit-msg.sh`'s PreToolUse JSON-stdin contract so the conventional-commit gate fires on EVERY git commit, not just harness-mediated ones. NOT a Claude-harness hook; never appears in `settings.json`.

## Denial Tracking

Hooks that block repeatedly on the same surface burn agent tokens in retry loops. The `denial_tracker.py` helper records consecutive denials per `(tool, rule)` pair and, after 3 hits in 5 minutes, converts the block into an `ask` advisory so the agent stops banging on the gate. See `block-stage-sensitive.sh` (search for `denial_tracker`) for the integration pattern. New gating hooks SHOULD wire through the tracker for any rule that the agent is likely to hit more than once per session.

## Pipeline Smoke Gate

Every `claude/hooks/tests/test_*.sh` file is auto-discovered by the pipeline at Step 5.5.7 (`claude/skills/pipeline/SKILL.md` per-feature loop) and run via `bash <file>` before the review phase dispatches. Tests MUST:

- Exit 0 on success and non-zero on any failure mode (no warnings-as-failures, no exit-code overloading).
- Be idempotent — safe to re-run any number of times against the same workspace without external state mutation.
- Sandbox via `mktemp -d` (with `trap cleanup EXIT`) or sandbox `CLAUDE_HOME` — never touch `~/.claude/`, the live repo `.git/`, or production credentials.
- Complete in ≤ 5 seconds per file. Over-budget tests will land but are flagged as drift in `/code-health` review.

A non-zero exit fails the per-feature verify step and skips to the next feature with `HOOK_SMOKE_FAILED: <test-path>`. Directory absent or empty → gate emits `HOOK_SMOKE_NO_TESTS_FOUND` and continues. See `claude/skills/pipeline/SKILL.md` § "Step 5.5.7: Hook smoke-test gate (additive verify)" for the orchestrator-side contract.

## See Also

- Root rules: `../../CLAUDE.md`.
- Sibling subdir rules: `../skills/CLAUDE.md`, `../agents/CLAUDE.md`.
- Notification surface: `./notify-emit.sh` is the canonical 6-field payload builder for the orchestrator.
