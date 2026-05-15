#!/bin/bash
# Reinjects behavioral rules after context compaction.
# Only rules that depend on Claude's cooperation — hook-enforced rules are omitted.

# Consume stdin (hook protocol)
cat > /dev/null

cat << 'EOF'
## Post-Compaction Reminders

1. **Verification First**: Run tests/build after EVERY change. Never skip.
2. **Commit Only When Asked**: Wait for explicit user confirmation.
3. **Plan Trust**: If plan has exact files/lines/changes — implement directly, skip exploration.
4. **No AI Attribution**: Zero Claude/AI references in commits, PRs, code, docs. No Co-authored-by lines.
5. **Current Context**: Read docs/progress.md for current task and plan.
EOF
