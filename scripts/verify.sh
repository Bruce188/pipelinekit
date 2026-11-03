#!/usr/bin/env bash
# Verify a pipelinekit install in $CLAUDE_HOME. Exits non-zero on failure.
set -uo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
pass() { printf '  [pass] %s\n' "$*"; }
fail() { printf '  [fail] %s\n' "$*"; FAIL=$((FAIL+1)); }

echo "Verifying pipelinekit at $CLAUDE_HOME"

for f in CLAUDE.md config/never-stage.txt; do
  [[ -f "$CLAUDE_HOME/$f" ]] && pass "exists: $f" || fail "missing: $f"
done
grep -qE '\$\{(USER_NAME|USER_EMAIL|CLAUDE_HOME)\}' "$CLAUDE_HOME/CLAUDE.md" 2>/dev/null \
  && fail "CLAUDE.md has unrendered placeholders" || pass "CLAUDE.md rendered"

for h in bash-guard.py block-bare-repo-markers.py post-edit-format.sh; do
  [[ -x "$CLAUDE_HOME/hooks/$h" ]] && pass "hook: $h" || fail "hook missing or not executable: $h"
done

for g in commit-msg pre-commit pre-push; do
  [[ -x "$CLAUDE_HOME/git-hooks/$g" ]] && pass "git hook: $g" || fail "git hook missing or not executable: $g"
done
HP="$(git config --global --get core.hooksPath || true)"
[[ "$HP" == "$CLAUDE_HOME/git-hooks" ]] && pass "git: global core.hooksPath set" \
  || echo "  [info] global core.hooksPath is '${HP:-unset}' (kit git hooks inactive)"
command -v gitleaks >/dev/null && pass "gitleaks: $(gitleaks version 2>&1 | head -1)" \
  || echo "  [info] gitleaks not installed (pre-commit secret scan skipped)"

for s in dotnet-conventions deploy exchange-api-keys docs-writer mobile; do
  [[ -f "$CLAUDE_HOME/skills/$s/SKILL.md" ]] && pass "skill: $s" || fail "skill missing: $s"
done

# Every hook command in settings.json must resolve; attribution off; env scrub
# and secret deny rules present.
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
if (d.get("env") or {}).get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") != "1":
    bad.append("env scrub off")
if "Read(.env)" not in (d.get("permissions") or {}).get("deny", []):
    bad.append("secret deny rules missing")
print("\n".join(bad))
sys.exit(1 if bad else 0)
PY
)"; then
    pass "settings.json: hook commands resolve, attribution off, env scrub on, deny rules present"
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
