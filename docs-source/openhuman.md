# openhuman — Human-in-the-Loop Approval Gate

A `PreToolUse` hook that pauses `/pipeline` before destructive actions (today: `git merge --squash`) and waits for an out-of-band human approval signal. Default is **off** — the gate only engages when you pass `--human-review` to `/pipeline`. Fail-safe abort on timeout (never auto-approve).

<div data-snippet="chooser-quiz" data-question-set="openhuman"></div>

## What it does

When `git merge --squash` is about to run inside a `/pipeline` execution AND the gate is enabled, the openhuman hook intercepts the tool call, mints a signal-file path, fires a notification through the standard pipelinekit notification chain (PushNotification → terminalSequence → no-op fallback), and polls the filesystem every 5 seconds for a JSON response from a human reviewer. If the human writes `{"decision":"allow"}` to the signal path, the merge proceeds. If they write `{"decision":"deny"}`, the merge is denied. If neither happens before the timeout elapses, the merge is denied (fail-safe abort).

The skill is invoked **only** by the hook handler — never by model invocation (the SKILL frontmatter sets `disable-model-invocation: true`). The concept and name are borrowed from [tinyhumansai/openhuman](https://github.com/tinyhumansai/openhuman) (a personal AI desktop agent, GPL-3.0); **zero source code is imported** — pipelinekit's implementation is original Bash + Python under the project's root MIT license. See [`claude/skills/openhuman/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/openhuman/NOTICE.md) for the full audit trail.

## When to enable it

The gate has the same operational cost regardless of whether anyone is watching: the pipeline pauses, fires a notification, and waits. The judgment call is whether you actually need a human gating the merge.

**Enable openhuman when:**

- You're running `/pipeline` **unattended** (overnight, on a CI runner, or while you sleep) AND the merge target is something where a bad merge costs more than the time spent reviewing.
- You're on **shared infrastructure** where a runaway autonomous run could affect other people's work.
- The repo ships to **production** customers, regardless of whether you're at the terminal.

**Skip openhuman when:**

- You're running `/pipeline` **interactively** at the terminal — you already eyeball every PR open and merge manually.
- The repo is a **solo sandbox** with no consumers — the blast radius is zero.
- You've already configured **GitHub branch protection** with required reviewers; the human-review pause then happens at the GitHub merge button, not before the PR opens. (openhuman gates the local squash, not the GitHub merge — these are different events.)

## How to enable

Pass `--human-review` to `/pipeline` at invocation time:

```bash
/pipeline                              # gate off (default — same as --no-human-review)
/pipeline --no-human-review            # explicit: gate off
/pipeline --human-review               # bare flag → 30 minute default timeout
/pipeline --human-review 60            # explicit 60 minute timeout
/pipeline --human-review 180           # 3 hours
```

The argument parser exports `PIPELINE_HUMAN_REVIEW=<minutes>` from one of these forms. The `PreToolUse` hook handler reads the env var: `0` (unset or explicit) means passthrough; positive integer means engage with that timeout.

`--human-review` and `--no-human-review` are mutually exclusive — passing both is a CLI error.

## The signal-file mechanism

When the gate fires, the handler mints a path:

```
.claude/openhuman/<feature-name>-<unix-timestamp>.json
```

`.claude/` is gitignored per pipelinekit's never-stage list, so signal files are **never committed**. The handler polls this path every 5 seconds.

To **approve**, a human writes the following JSON to the signal path:

```json
{
  "decision": "allow",
  "reason": "Reviewed diff; safe to merge.",
  "reviewer": "bruce",
  "ts": "2026-05-18T20:30:00Z"
}
```

To **deny**: `{"decision":"deny"}`. Only `decision` is required; `reason`, `reviewer`, and `ts` are optional.

**Atomic write is required** to avoid the polling loop reading a half-written file:

```bash
printf '%s' "$JSON" > "$SIGNAL.tmp" && mv "$SIGNAL.tmp" "$SIGNAL"
```

The notification fires through three surfaces in priority order:

1. **PushNotification** — interactive session + Remote Control enabled in the Claude Code mobile app. Delivers the prompt to your phone. You tap the notification, read the prompt, and respond.
2. **terminalSequence (OSC 777)** — terminal-attached fallback. Surfaces as a desktop notification on hosts that support OSC 777.
3. **Filesystem signal-file (always)** — the canonical response channel. Even when neither notification surface reaches you, the handler still polls the signal file. You can write the approval JSON via any out-of-band path: SSH, file-share, web UI, a teammate writing it for you, whatever works.

## Timeout semantics

The timeout is the maximum time the handler will wait for a signal-file before giving up. **Fail-safe: deny on timeout. Never auto-approve.**

| Invocation | Timeout |
|---|---|
| `/pipeline` (no flag) | `0` — gate disabled (no pause, merge proceeds) |
| `/pipeline --no-human-review` | `0` — same as above, explicit |
| `/pipeline --human-review` | `30` minutes (bare-flag default) |
| `/pipeline --human-review <N>` | `<N>` minutes (positive integer; regex `^[1-9][0-9]*$`) |

When the timeout elapses without an approval, the handler emits:

```json
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "permissionDecisionReason": "OPENHUMAN_TIMEOUT: <minutes> elapsed without approval"
  }
}
```

The pipeline halts at that point. The feature is left in its pre-merge state — branch pushed, PR open, but not merged. You can manually merge the PR via GitHub afterward, or re-run `/pipeline` with the gate enabled (or disabled) on the next iteration.

The fail-safe-abort default was driven by the 2026-05-18 native-Claude-Code-compliance audit Dimension 6 finding: "defaulting to a non-zero timeout with auto-approve creates a silent-auto-approve drift hazard." Auto-approve on timeout would let an inattentive operator effectively disable the gate by setting a long timeout and never responding.

**Malformed signal-file** (invalid JSON or missing `decision` field) is also treated as deny, with reason `OPENHUMAN_MALFORMED_SIGNAL: <path>`. The handler never guesses what the human meant.

## Cross-feature payload contract

The handler binds to the canonical 6-field notification payload schema shared with the F9 pipeline-mobile-notifications surface. Field-by-field:

| Field | Source | Notes |
|---|---|---|
| `feature_index` | `PIPELINE_FEATURE_INDEX` env (e.g. `10/23`) | Exported by `/pipeline` Step 1 from `docs/pipeline-state.md` line `**Feature:**`. Empty string for ad-hoc `/openhuman` outside an active pipeline run. |
| `step` | Hardcoded `5.8-pre-merge` | Identifies the gate firing point. |
| `event_type` | `human-review` | F9 event-type taxonomy. |
| `text` | Composed by handler (≤ 200 bytes) | The approval prompt body. **Byte-based** truncation — do not embed emoji or CJK characters; a 2-byte or 3-byte glyph may straddle the 200-byte boundary. |
| `action_link` | Signal-file path | The reviewer writes JSON here. |
| `feature_name` | `PIPELINE_FEATURE_NAME` env | From the same `docs/pipeline-state.md` field. |

The 200-byte text cap is a hard limit. Full charter / analysis / plan / review file contents never appear in the notification — they're not in scope, and the cap would truncate them anyway. The handler reads payload data from env vars only — it never opens `docs/plan*.md`, `docs/charter*.md`, etc.

## What openhuman does NOT do

- **Does NOT auto-approve on timeout.** Fail-safe = abort.
- **Does NOT modify the F9 notification helper** (`claude/hooks/notify-emit.sh`). The helper is consumed unchanged; the 6-field payload schema and the 200-byte text cap are the cross-feature contract.
- **Does NOT read** `docs/plan*.md`, `docs/charter*.md`, `docs/review*.md`, or `docs/analysis*.md`. Notification payload comes from env vars only — no file contents leak.
- **Does NOT POST plan / charter / analysis / review content to external services.** The handler's `allowed-tools` line includes `Bash(curl *)` for defensive reasons only; any `curl` invocation inside the handler MUST be localhost-only (enforced by AC12 in the original feature acceptance criteria).
- **Does NOT propagate `--human-review` to `/review`, `/implement-plan`, or any sub-skill.** The flag belongs to `/pipeline` Step 1 only. Sub-skills receive the gate via the installed `PreToolUse` hook, not via flag propagation. This keeps the gate semantically anchored at the destructive action, not at intermediate phases.
- **Does NOT pause `/ppr` itself.** `/ppr` opens the PR — that's non-destructive. The gate fires later when `/post-merge` (or whatever downstream skill) runs `git merge --squash`. PRs can always be opened; only the local squash is gated.
- **Does NOT pause GitHub's merge button.** openhuman is a local hook; GitHub-side merge gating belongs to branch protection rules. Use both together for defense-in-depth.

## Failure modes

| Condition | Behavior |
|---|---|
| Gate disabled (`PIPELINE_HUMAN_REVIEW=0`) | Passthrough. Handler emits `permissionDecision: "allow"` immediately. |
| Timeout elapses with no signal file | `permissionDecision: "deny"` with reason `OPENHUMAN_TIMEOUT: <minutes> elapsed without approval`. Pipeline halts; PR is left open. |
| Signal file appears with `{"decision":"allow"}` | Merge proceeds; pipeline continues. |
| Signal file appears with `{"decision":"deny"}` | `permissionDecision: "deny"` with reason `OPENHUMAN_DENIED_BY_REVIEWER: <reviewer or "anonymous">`. Pipeline halts. |
| Signal file is malformed (invalid JSON, missing `decision`) | `permissionDecision: "deny"` with reason `OPENHUMAN_MALFORMED_SIGNAL: <path>`. Pipeline halts. |
| `notify-emit.sh` fails to fire | Handler still polls the filesystem signal path. The notification surface is best-effort; the signal-file path is the canonical response channel. |
| Mobile app not enrolled / Remote Control off | terminalSequence fallback fires. If that also fails (no OSC 777 support), the human can still write the signal-file via any out-of-band path. |

## See also

- **[/pipeline](pipeline.html)** § Human-Review Gate — the orchestrator's flag parser + the `PIPELINE_HUMAN_REVIEW` env var contract.
- **[/ppr](ppr.html)** § Integration with `--human-review` — why `/ppr` itself is NOT gated (the squash is the gated action, not the PR open).
- [`claude/skills/openhuman/NOTICE.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/openhuman/NOTICE.md) — full attribution to upstream `tinyhumansai/openhuman` and the concept-only vendoring scope.
- [`claude/hooks/notify-emit.sh`](https://github.com/Bruce188/pipelinekit/blob/main/claude/hooks/notify-emit.sh) — the F9 notification helper that openhuman consumes unchanged.
- [`claude/skills/pipeline/reference.md`](https://github.com/Bruce188/pipelinekit/blob/main/claude/skills/pipeline/reference.md) § Notification payload schema — the 6-field cross-feature contract.
