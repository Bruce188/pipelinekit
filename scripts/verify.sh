#!/usr/bin/env bash
# Verify a pipelinekit install in $CLAUDE_HOME. Exits non-zero on failure.
set -uo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
pass() { printf '  [pass] %s\n' "$*"; }
fail() { printf '  [fail] %s\n' "$*"; FAIL=$((FAIL+1)); }

echo "Verifying pipelinekit at $CLAUDE_HOME"

for f in CLAUDE.md config/never-stage.txt agents/docs-writer.md; do
  [[ -f "$CLAUDE_HOME/$f" ]] && pass "exists: $f" || fail "missing: $f"
done
grep -qE '\$\{(USER_NAME|USER_EMAIL|CLAUDE_HOME)\}' "$CLAUDE_HOME/CLAUDE.md" 2>/dev/null \
  && fail "CLAUDE.md has unrendered placeholders" || pass "CLAUDE.md rendered"

for h in block-stage-sensitive.sh block-dangerous-commands.sh block-push-main.sh env-scrub.py \
         scan-tool-output.sh block-bare-repo-markers.py validate-commit-msg.sh \
         pre-edit-protect.sh post-edit-format.sh _never_stage_match.py _pathguard.py \
         _promptguard.py denial_tracker.py; do
  [[ -x "$CLAUDE_HOME/hooks/$h" ]] && pass "hook: $h" || fail "hook missing or not executable: $h"
done

for s in commit-conventions security-conventions dotnet-conventions deploy docs-writer expo ios; do
  [[ -f "$CLAUDE_HOME/skills/$s/SKILL.md" ]] && pass "skill: $s" || fail "skill missing: $s"
done

# Every hook command in settings.json must resolve; attribution must be off.
if [[ -f "$CLAUDE_HOME/settings.json" ]]; then
  if OUT="$(python3 - "$CLAUDE_HOME/settings.json" <<'PY'
import json, os, sys
d = json.load(open(sys.argv[1]))
bad = []
for groups in (d.get("hooks") or {}).values():
    for g in groups:
        for h in g.get("hooks", []):
            first = os.path.expanduser((h.get("command") or "").split(" ")[0])
            first = first.replace("$HOME", os.environ["HOME"]).replace("${HOME}", os.environ["HOME"])
            if first.startswith("/") and not os.path.exists(first):
                bad.append(first)
a = d.get("attribution")
if not (a is False or (isinstance(a, dict) and a.get("commit") == "" and a.get("pr") == "")):
    bad.append("attribution not disabled")
print("\n".join(bad))
sys.exit(1 if bad else 0)
PY
)"; then
    pass "settings.json: hook commands resolve, attribution off"
  else
    fail "settings.json: ${OUT//$'\n'/, }"
  fi
else
  fail "missing: settings.json"
fi

# Personal-data leak guard (repo checkout only).
if [[ -d "$REPO_ROOT/claude" ]]; then
  LEAK=$(grep -rIn -E "(brucieboyy[0-9]*|/home/bruce(/|\$)|-home-bruce\b)" "$REPO_ROOT/claude" 2>/dev/null | wc -l)
  [[ "$LEAK" -eq 0 ]] && pass "no personal data leaks" || fail "$LEAK personal data references in claude/"
fi

if command -v claude >/dev/null 2>&1; then
  pass "claude CLI: $(claude --version 2>&1 | head -1)"
else
  echo "  [info] claude CLI not on PATH (install: https://claude.ai/install.sh)"
fi

echo
if [[ "$FAIL" -gt 0 ]]; then
  echo "Verification FAILED ($FAIL issues)"
  exit 1
fi
echo "Verification PASSED"
