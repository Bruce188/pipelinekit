---
name: build-hook
description: Generate a Claude Code hook from a description. Creates the shell script and settings.json entry. Use when user wants to add workflow automation, enforce a rule, or react to Claude Code events.
argument-hint: <description of what the hook should do>
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
context: fork
effort: medium
paths:
  - claude/skills/build-hook/**
  - claude/hooks/**
---

# Build Hook — Claude Code Hook Generator

Generate production-ready hooks for this environment.

## Usage

```
/build-hook Block git push --force
/build-hook Auto-format Python files after editing
/build-hook Send notification when agent completes
```

## Process

### Step 1: Determine Hook Type

Based on the user's description, select the appropriate event:

| Event | Use When | Can Block? |
|-------|----------|------------|
| `PreToolUse` | Validate/block before a tool runs | Yes (exit 2) |
| `PostToolUse` | React after a tool runs (format, log) | No |
| `UserPromptSubmit` | Add context or validate user input | Yes (exit 2) |
| `SessionStart` | Load context at session start | No |
| `PostCompact` | Reinject rules after compaction | No |
| `SubagentStop` | Validate agent output | Yes (exit 2) |
| `Stop` | Force continuation or cleanup | Yes (exit 2) |
| `Notification` | Desktop alerts | No |

### Step 2: Generate the Shell Script

**CRITICAL**: This system does NOT have `jq`. All hooks MUST use `python3` for JSON parsing.

Standard JSON parsing pattern:
```bash
#!/bin/bash
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)
```

Available fields from stdin JSON (PreToolUse/PostToolUse):
- `tool_input.command` — the bash command being run
- `tool_input.file_path` — file being read/written/edited
- `tool_input.description` — command description
- `tool_name` — which tool (Bash, Read, Write, Edit, etc.)

For SubagentStop:
- `agent_worktree_path` — worktree path if agent used isolation

### Step 3: Write to `~/.claude/hooks/<hook-name>.sh`

Follow these rules:
- Script must be executable (`chmod +x`)
- Use `exit 0` for pass, `exit 2` for block (blocking hooks only)
- Write error messages to stderr: `echo "BLOCKED: reason" >&2`
- Always handle missing/empty input gracefully with `2>/dev/null`
- Never use `jq` — always use `python3`
- Keep hooks fast (under 2 seconds for PreToolUse, under 10 for others)

### Step 4: Generate the settings.json entry

Format for `~/.claude/settings.local.json`:
```json
{
  "hooks": {
    "<EventName>": [
      {
        "matcher": "<tool-name-or-empty>",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/<hook-name>.sh",
            "timeout": <seconds>
          }
        ]
      }
    ]
  }
}
```

Matcher values:
- `"Bash"` — only Bash tool commands
- `"Edit|Write"` — file modification tools
- `""` or omit — all events of this type

### Step 5: Install

1. Write the shell script to `~/.claude/hooks/`
2. Make it executable
3. Add the hook entry to `~/.claude/settings.local.json` (merge into existing hooks object)
4. Show the user the final hook and settings entry
5. Test: `echo '{"tool_input":{"command":"test"}}' | bash ~/.claude/hooks/<hook-name>.sh`

## Existing Hooks (do not duplicate)

| Hook | Event | Purpose |
|------|-------|---------|
| agent-caveman-gate.sh | PreToolUse (Agent) | Blocks Agent dispatches missing the caveman-subagent contract when caveman is active |
| block-push-main.sh | PreToolUse | Blocks push to main/master |
| block-stage-sensitive.sh | PreToolUse | Blocks staging .env, .claude/, workflow docs |
| strip-ai-attribution.sh | PostToolUse | Removes claude-code-assisted label + Co-authored-by from PRs |
| verify-worktree-commit.sh | SubagentStop | Blocks agents that don't commit in worktree |
| post-compact-context.sh | PostCompact | Reinjects critical rules after compaction |
| context-warning.py | PostCompact | Warns when compaction fires |
| context-budget-advisor.py | UserPromptSubmit | Advises `/compact` when session passes ~200K tokens |
| test-logger.sh | PreToolUse | Logs test executions |

## Hook Templates

### Blocking Hook (PreToolUse)
```bash
#!/bin/bash
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)
# Your condition here
if echo "$COMMAND" | grep -q "PATTERN"; then
  echo "BLOCKED: Reason" >&2
  exit 2
fi
exit 0
```

### Reactive Hook (PostToolUse)
```bash
#!/bin/bash
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)
# Your action here (runs after tool completes, cannot block)
exit 0
```

### Context Injection Hook (PostCompact/SessionStart)
```bash
#!/bin/bash
cat << 'EOF'
## Context Reminder
Your context here — this text gets injected into the conversation.
EOF
```
