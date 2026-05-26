#!/bin/bash
# Reinjects behavioral rules after context compaction.
# Only rules that depend on Claude's cooperation — hook-enforced rules are omitted.

# Consume stdin (hook protocol)
cat > /dev/null

# Clear the subagent-nudge marker so the next user prompt after compaction
# re-emits the default-mode banner. See claude/hooks/subagent-first-nudge.sh
# for the once-per-session cap mechanism.
rm -f "$HOME/.claude/.subagent-nudge-fired" 2>/dev/null || true

cat << 'EOF'
## Post-Compaction Reminders

1. **Verification First**: Run tests/build after EVERY change. Never skip.
2. **Commit Only When Asked**: Wait for explicit user confirmation.
3. **Plan Trust**: If plan has exact files/lines/changes — implement directly, skip exploration.
4. **No AI Attribution**: Zero Claude/AI references in commits, PRs, code, docs. No Co-authored-by lines.
5. **Current Context**: Read docs/progress.md for current task and plan.
EOF

# Optional caveman re-injection: only when the marker file exists.
# Mirrors the section in session-start-context.sh so the contract survives
# /compact + auto-compact, not only session boot.
if [ -f "$HOME/.claude/.caveman-active" ]; then
  CAVEMAN_LEVEL=$(head -n1 "$HOME/.claude/.caveman-active" 2>/dev/null || echo "")
  [ -z "$CAVEMAN_LEVEL" ] && CAVEMAN_LEVEL="wenyan-ultra"
  cat <<EOF

## Caveman state (re-injected after compact)

Active level: \`$CAVEMAN_LEVEL\`. The three-zone content split below applies BOTH to your own narrative prose AND to every subagent dispatch — not subagents only.

- Zone 1 (code / paths / commits / errors): normal English, exact strings.
- Zone 2 (narrative prose): real classical Chinese 文言, Han characters mandatory.
- Zone 3 (fragments / status / beacons): ultra English, drop articles + filler.

Subagent dispatch contract: \`~/.claude/snippets/caveman-subagent.md\`. Every \`Agent\` tool call MUST prepend the contract — wrapped in \`<caveman-inherited level="$CAVEMAN_LEVEL">\` … \`</caveman-inherited>\` — to its \`prompt\` parameter. The PreToolUse gate \`agent-caveman-gate.sh\` blocks dispatches missing the contract with \`exit 2\`.
EOF
fi
