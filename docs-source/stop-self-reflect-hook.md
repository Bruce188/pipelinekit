# Stop self-reflection hook

The Stop self-reflection hook (`claude/hooks/stop-self-reflect.sh`) runs a headless `claude -p` call at the end of every Claude Code session and writes a JSON proposal artifact that suggests lean amendments to your project's `CLAUDE.md` files. The proposals are NEVER auto-applied — the artifact is for human review only.

This page covers what the hook does, where it writes output, how to apply proposals manually, how to opt out, and the cost-control posture you should adopt before enabling it.

<div data-snippet="terminal-simulator"></div>

## What the hook does

At every `Stop` event (the session is about to finish without further tool calls), the hook fires AFTER `notify-emit.sh` in the `Stop` hook array wired by `scripts/install.sh`. If the prior hooks allow the stop, the self-reflection hook:

1. Drains the JSON stdin envelope (the harness contract).
2. Checks the opt-out env-var `PIPELINE_NO_SELF_REFLECT` — if set to `1`, exits 0 immediately with no side effect.
3. Resolves the `claude` binary via `CLAUDE_BIN` (env override) or `command -v claude`. If neither resolves, logs an informational message to stderr and exits 0 (still non-blocking).
4. Computes the next version `N` for `docs/claude-md-proposal-v<N>.md` per the Versioning Convention (highest existing version + 1; `N = 1` if none exist).
5. Runs `claude -p --append-system-prompt "<reflection prompt>" "<session summary stub>"` with a hard 60-second timeout. On timeout (exit code 124) or any non-zero exit, the hook silently swallows the failure and exits 0 with no artifact written.
6. Writes the JSON output to `docs/claude-md-proposal-v<N>.md`, wrapped in a small Markdown shell.

Stop hooks are non-blocking by harness contract — this hook MUST exit 0 on every error path, and it does.

## Where the proposal artifact lives

The hook writes to `docs/claude-md-proposal-v<N>.md` RELATIVE TO THE SESSION CWD. `docs/` is the AI-workflow-only directory (gitignored via `.git/info/exclude`), so proposal artifacts never end up in version control by accident. Consecutive runs increment `N`:

- First run: `docs/claude-md-proposal-v1.md`
- Second run: `docs/claude-md-proposal-v2.md`
- And so on. The hook never overwrites an existing file.

The artifact format is:

    # CLAUDE.md Proposal — v<N>

    Generated at <ISO-8601 UTC timestamp>

    ## Raw JSON Output

    ```json
    {"proposals": [...]}
    ```

    ## Manual Apply

    Apply these proposals manually — they are NOT auto-applied.

The embedded JSON has shape:

    {
      "proposals": [
        {
          "file": "<path from repo root>",
          "line_anchor": "<heading or quoted line where the rule should land>",
          "proposed_text": "<insertion or replacement text>",
          "reason": "<why this would have helped>"
        }
      ]
    }

A `{"proposals": []}` payload is a legitimate no-op proposal — the JSON shape is preserved regardless. Empty proposal lists still write an artifact so you can see that the hook ran and chose not to amend.

## Applying proposals manually

Proposals are deliberately NOT auto-applied. Each proposal is a suggestion that you, the human reviewer, choose to accept or reject. Workflow:

1. Open `docs/claude-md-proposal-v<N>.md` after a session ends.
2. Read the `reason` field for each proposal. Compare against the work the session actually did.
3. For accepted proposals: open the target `file` at `line_anchor`, paste the `proposed_text` (insert or replace, depending on the anchor wording), and commit the change with a normal `docs:` or `chore:` conventional commit.
4. For rejected proposals: no action needed. The proposal artifact is gitignored and can be deleted, archived, or kept as a record of suggestions.

The proposal artifact itself is workflow metadata — do NOT commit `docs/claude-md-proposal-v<N>.md` to source control.

## Opting out

The hook ships enabled. To opt out per-session, set the env-var before starting Claude Code:

    export PIPELINE_NO_SELF_REFLECT=1
    claude

The hook short-circuits at step 2 and exits 0 with zero side effects (no `claude -p` call, no cost, no artifact). To re-enable later in the same shell:

    unset PIPELINE_NO_SELF_REFLECT

For a permanent disable, remove the `claude/hooks/stop-self-reflect.sh` entry from your `~/.claude/settings.json` `"Stop"` array. Re-running `scripts/install.sh` with `CLAUDE_INSTALL_SETTINGS=1` will restore it.

## Cost posture

Each Stop event triggers ONE headless `claude -p` call. Headless calls bill per Claude API usage, the same as any other model invocation. With Opus pricing and the prompt described above, the typical cost per call is sub-cent but accumulates across many short sessions.

The opt-out env-var is your primary cost control. Reasonable patterns:

- **Default-on for engineering work** — the proposal stream is most valuable when you are actively iterating on CLAUDE.md scope. Leave the hook enabled.
- **Default-off for ops sessions** — for short `az login` / `vercel logs` style sessions, set `PIPELINE_NO_SELF_REFLECT=1` in your shell rc. The hook adds nothing of value to a 30-second ops poke.
- **Project-scoped** — set `PIPELINE_NO_SELF_REFLECT=1` in a per-project `.envrc` (direnv) or a wrapper script for repos where you do not want CLAUDE.md drift.

The 60-second timeout caps the worst-case wall time of any single Stop event. If `claude -p` hangs or returns nothing, the hook still exits within ~65 seconds and writes no artifact.

## Selftest

Run the hook's selftest mode to verify the three primary code paths without the harness:

    bash claude/hooks/stop-self-reflect.sh --selftest

Expected output:

    PASS  case 1: opt-out env-var -> exit 0 + no artifact
    PASS  case 2: missing CLI -> exit 0 + no artifact
    PASS  case 3: happy path -> v1 artifact written

    Results: 3 passed, 0 failed

The full bash test suite lives at `claude/hooks/tests/test_stop_self_reflect.sh` and exercises six cases including version increment and timeout enforcement:

    bash claude/hooks/tests/test_stop_self_reflect.sh

## Implementation contract recap

- Stop hooks are non-blocking by harness contract — any exit code is silently swallowed; this hook still defensively exits 0 on every path.
- The hook does NOT write to stdout. Output goes to the artifact file or stderr (informational only).
- Proposals are NEVER auto-applied. The artifact is for human review.
- The 60-second timeout is enforced via the `timeout` coreutils binary — kill silently, exit 0 from the hook.
- The reflection prompt does NOT include AI-self-reference language. Proposed text is phrased neutrally for direct paste into target files.
- Charter MVP item 4.
