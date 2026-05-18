# NOTICE — openhuman

**Upstream:** https://github.com/tinyhumansai/openhuman
**License:** GPL-3.0 (attribution-only context — NO source imported)
**Pinned SHA:** TBD (placeholder; resolve via `gh api repos/tinyhumansai/openhuman/commits/HEAD --jq .sha` at re-vendor time)
**Vendoring scope:** concept and name only — NO source code imported; pipelinekit implementation is original Bash + Python 3, MIT licensed under the project root LICENSE.

## Why concept-only

The 2026-05-18 native-Claude-Code-compliance audit (`documentation/audits/claude-code-compliance-features-2026-05-18.html § f-openhuman`, lines 207-238) and the `/analyze` phase WebFetch verdict established that `tinyhumansai/openhuman` upstream is a **12.5k-star personal AI desktop agent** (Rust + Tauri shell + OAuth integrations + Memory Tree + voice), NOT a human-in-the-loop approval library. Upstream has no webhook channels, no SSE channels, no filesystem signal channels, and no PreToolUse / Notification hook integration. The surface area is entirely mismatched with pipelinekit's requirement (pause a pipeline before destructive actions via a Claude Code hook).

Vendoring is therefore reduced to **concept and name only**. The pipelinekit `openhuman` skill is an original Bash + Python 3 implementation that:

- Wires a `PreToolUse` Bash matcher with an `if: "Bash(git merge --squash *)"` clause via `scripts/install.sh § maybe_install_settings`.
- Polls a filesystem signal file at `.claude/openhuman/<feature-name>-<unix-timestamp>.json` for the human reviewer's JSON response.
- Reuses F9's canonical notification helper (`claude/hooks/notify-emit.sh`) for the approval prompt — does not fork or reimplement it.
- Fails closed on timeout (`permissionDecision: "deny"`) per the audit Dimension 6 finding.

Zero GPL-3.0 source code is imported into the pipelinekit tree. The in-tree files at `claude/skills/openhuman/SKILL.md` and `claude/skills/openhuman/handler.sh` are original works under the project root MIT LICENSE.

## Re-vendor procedure

concept-only — no re-vendor needed unless adopting upstream code in a future iteration, which would require a GPL-3.0-compatibility audit. If such an iteration lands:

1. Run the GPL-3.0-compatibility audit. If the in-tree license does not change to GPL-3.0-compatible, do not import upstream source.
2. Pick a new HEAD SHA:
   ```bash
   gh api repos/tinyhumansai/openhuman/commits/HEAD --jq .sha
   ```
3. Update this NOTICE.md's `**Pinned SHA:**` line to the resolved SHA.
4. Document each upstream path that gets imported, with the new short SHA prepended as an HTML-comment attribution header at the top of the imported file.
5. Commit with `chore: re-vendor tinyhumansai/openhuman @ <short-sha>` (subject to license-compatibility outcomes).

For the current concept-only state, this NOTICE.md is the sole upstream-attribution artifact. There is nothing to re-vendor.
