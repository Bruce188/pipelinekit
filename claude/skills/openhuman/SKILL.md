---
name: openhuman
description: Pause for out-of-band human approval before destructive actions
disable-model-invocation: true
allowed-tools: Bash(curl *) Read Edit
---

# openhuman — Human-in-the-Loop Approval Gate

`openhuman` pauses `/pipeline` before destructive actions (today: `git merge --squash`; deferred follow-ups: prod deploy, schema migration) and waits for an out-of-band human approval signal. The skill is invoked by a `PreToolUse` hook handler — never by model invocation (see `disable-model-invocation: true` frontmatter).

The concept and name are borrowed from `tinyhumansai/openhuman` (GPL-3.0 personal AI desktop agent); zero source code is imported. See `claude/skills/openhuman/NOTICE.md` for full attribution.

## When this skill fires

The `PreToolUse` hook handler at `claude/skills/openhuman/handler.sh` is wired in `scripts/install.sh § maybe_install_settings` against the Bash matcher with an `if` clause that narrows to `git merge --squash *` invocations:

```python
{"matcher": "Bash",
 "hooks": [{"type": "command",
            "command": f"{h}/skills/openhuman/handler.sh",
            "if": "Bash(git merge --squash *)"}]}
```

The handler also checks the env-var gate `PIPELINE_HUMAN_REVIEW`:

- Unset or `0` → passthrough. The handler emits `{"hookSpecificOutput":{"permissionDecision":"allow"}}` and exits 0 without polling. This makes the standard install **inert** when the user does not pass `--human-review` to `/pipeline`.
- `1+` → enabled with the given number of minutes as the polling timeout.

`/pipeline` Step 1's argument parser exports `PIPELINE_HUMAN_REVIEW=<minutes>` from one of:

| Invocation | Value |
|------------|-------|
| `/pipeline` (no flag) | `0` (gate off — same as `--no-human-review`) |
| `/pipeline --no-human-review` | `0` |
| `/pipeline --human-review` | `30` (bare-flag default) |
| `/pipeline --human-review <N>` | `<N>` (positive integer; regex `^[1-9][0-9]*$`) |

`--human-review` and `--no-human-review` are mutually exclusive.

## Approval surface

When the gate fires, the handler mints a signal-file path:

```
.claude/openhuman/<feature-name>-<unix-timestamp>.json
```

The `.claude/` directory is gitignored per the standard pipelinekit never-stage list — signal files are never committed.

The handler then invokes `claude/hooks/notify-emit.sh --mode beacon` (F9's helper — CONSUMED unchanged) with the 6 standard `NOTIFY_*` env vars to surface the approval prompt via the canonical notification chain (PushNotification → terminalSequence → no-op fallback). The handler then polls the signal-file path every 5 seconds until either the file appears OR the timeout elapses.

To **approve**, a human writes a JSON file at the signal-file path:

```json
{
  "decision": "allow",
  "reason": "Reviewed diff; safe to merge.",
  "reviewer": "bruce",
  "ts": "2026-05-18T20:30:00Z"
}
```

To **deny**: `{"decision": "deny"}`. Only `decision` is required; `reason`, `reviewer`, and `ts` are optional.

**Atomic write** (required to avoid the polling loop reading a half-written file):

```bash
printf '%s' "$JSON" > "$SIGNAL.tmp" && mv "$SIGNAL.tmp" "$SIGNAL"
```

## Timeout semantics

- **Default = 0** when `--human-review` flag is absent. Gate disabled — squash-merge proceeds without pause.
- **Default = 30 minutes** when `--human-review` is bare (no minutes argument).
- **User-supplied minutes** when `--human-review <N>` (positive integer).

**Fail-safe = abort.** On timeout, the handler emits:

```json
{"hookSpecificOutput":{"permissionDecision":"deny",
                       "permissionDecisionReason":"OPENHUMAN_TIMEOUT: <minutes> elapsed without approval"}}
```

The pipeline **never auto-approves** on timeout. This is the audit-driven default per the 2026-05-18 native-Claude-Code-compliance audit Dimension 6 finding (defaulting to a non-zero timeout with auto-approve creates a silent-auto-approve drift hazard).

On malformed signal-file (invalid JSON, missing `decision` field), the handler emits `permissionDecision: "deny"` with reason `OPENHUMAN_MALFORMED_SIGNAL: <signal-path>`.

## Fallback chain

The approval prompt fans out via three surfaces in priority order, all driven by `notify-emit.sh --mode beacon`:

1. **PushNotification** — interactive session + Remote Control enabled in the Claude Code mobile app. Delivers the prompt to the user's phone.
2. **terminalSequence (OSC 777)** — terminal-attached fallback. The hook-mode helper emits `\x1b]777;notify;Claude Code;<text>\x07` which the harness writes to the host terminal.
3. **Signal file** (always) — the canonical response channel. Even when neither push nor terminalSequence reaches the user, the handler still polls the filesystem signal-file path. A human can write the file by any out-of-band channel (SSH, file-share, web UI, etc.) and the polling loop will unblock the merge.

## Cross-feature payload notes (NB1/NB2)

The handler binds to F9's 6-field payload schema (`feature_index`, `step`, `event_type`, `text`, `action_link`, `feature_name`):

- **NB1 — `feature_index` shape:** when the gate fires inside a `/pipeline` run, the orchestrator exports `PIPELINE_FEATURE_INDEX="<N>/<M>"` (e.g., `10/23`) from `docs/pipeline-state.md` line `**Feature:**`. The handler propagates this verbatim into `NOTIFY_FEATURE_INDEX`. For ad-hoc `/openhuman` invocation outside an active pipeline run, `PIPELINE_FEATURE_INDEX` is unset → the handler emits with `NOTIFY_FEATURE_INDEX=""` (empty string per F9's optional-field default).

- **NB2 — byte-based 200-cap caveat:** `notify-emit.sh` enforces a 200-byte truncation on the `text` field (197 + `...` ellipsis). The cap is byte-based, not character-based. **Do not embed emoji or multi-byte CJK** in the approval prompt text — a 2-byte or 3-byte glyph may straddle the truncation boundary and produce an invalid UTF-8 byte sequence. Keep approval prompt text in plain ASCII.

## What this skill does NOT do

- Does **not** POST plan, charter, analysis, or review file contents to external services. The `curl` allowed-tool entry is defensive only — any `curl` in the handler MUST be localhost-only (AC12 enforces).
- Does **not** auto-approve on timeout. Fail-safe = abort.
- Does **not** modify F9's `claude/hooks/notify-emit.sh`. The helper is CONSUMED unchanged — the 6-field payload schema and the 200-byte cap are the cross-feature contract.
- Does **not** read `docs/plan*.md`, `docs/charter*.md`, `docs/review*.md`, or `docs/analysis*.md`. The notification payload comes from env vars only.
- Does **not** propagate `--human-review` to `/review`, `/implement-plan`, or any sub-skill. The flag belongs to `/pipeline` Step 1 only. Sub-skills receive the gate via the installed `PreToolUse` hook, not via flag propagation.

## Reference

- Hook wiring: `scripts/install.sh § maybe_install_settings` (PreToolUse Bash matcher with `if: Bash(git merge --squash *)` clause).
- Handler script: `claude/skills/openhuman/handler.sh`.
- F9 cross-feature contract: `claude/hooks/notify-emit.sh` + `claude/skills/pipeline/reference.md § Notification payload schema`.
- Pipeline appendix: `claude/skills/pipeline/reference.md § Human-Review Gate (--human-review)`.
- User-facing docs: `documentation/docs/SKILL_PIPELINE.html` § Human-Review Gate.
- Upstream attribution: `claude/skills/openhuman/NOTICE.md`.
