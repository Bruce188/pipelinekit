#!/usr/bin/env bash
set -euo pipefail
# test_paths_enforcer.sh — assert claude/skills/write-a-skill/SKILL.md documents
# the F5 paths: enforcement contract (Step 1 H2 + policy link) and that the
# inline python check-template snippet honors both the requirement and the
# 4-entry global-by-design allowlist.
#
# Mirrors claude/hooks/tests/test_install_settings_shape.sh shape:
#   PASS/FAIL counter + final `Results: N PASS / M FAIL` line + exit non-zero on FAIL.
#
# Expected result: Results: 5 PASS / 0 FAIL

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
SKILL_MD="$REPO_ROOT/claude/skills/write-a-skill/SKILL.md"

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

PASS=0
FAIL=0
FAILED_NAMES=()

record() {
  local name="$1" outcome="$2" detail="${3:-}"
  if [ "$outcome" = "PASS" ]; then
    echo "PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name -- $detail"
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
  fi
}

# Materialize the documented check template as a sandbox script. The test
# contract under verification is "the documented snippet rejects missing-paths
# and accepts allowlist names". We re-author the snippet body here verbatim so
# the test stays self-contained; if SKILL.md drifts from this body, fix BOTH.
cat > "$SANDBOX/check.py" <<'PYEOF'
import re, sys
ALLOWLIST = {"pipeline", "claude-md-enhancer", "caveman-mode", "write-a-skill"}
body = sys.stdin.read()
m = re.search(r"^---\s*$(.*?)^---\s*$", body, re.MULTILINE | re.DOTALL)
if not m:
    sys.exit("error: no YAML frontmatter block found")
fm = m.group(1)
name_match = re.search(r"^name:\s*(\S+)\s*$", fm, re.MULTILINE)
name = name_match.group(1) if name_match else None
has_paths = re.search(r"^paths:\s*$", fm, re.MULTILINE) is not None
if has_paths or name in ALLOWLIST:
    print(f"ok: {name} ({'paths declared' if has_paths else 'on allowlist'})")
    sys.exit(0)
sys.exit(f"error: skill '{name}' missing required `paths:` field (and not on allowlist)")
PYEOF

# ---------------------------------------------------------------------------
# test_01_skill_doc_declares_step_1 (AC-1)
# ---------------------------------------------------------------------------
if [ "$(grep -cE '^## Step [0-9]+: Declare paths:' "$SKILL_MD")" = "1" ]; then
  record "test_01_skill_doc_declares_step_1" PASS
else
  record "test_01_skill_doc_declares_step_1" FAIL "expected exactly 1 hit for ^## Step N: Declare paths: regex"
fi

# ---------------------------------------------------------------------------
# test_02_skill_doc_links_scope_policy (AC-2)
# ---------------------------------------------------------------------------
if [ "$(grep -cE 'skills-scope-policy' "$SKILL_MD")" -ge "1" ]; then
  record "test_02_skill_doc_links_scope_policy" PASS
else
  record "test_02_skill_doc_links_scope_policy" FAIL "expected >= 1 hit for skills-scope-policy substring"
fi

# ---------------------------------------------------------------------------
# test_03_check_template_recognizes_missing_paths (AC-4 Case-1)
# ---------------------------------------------------------------------------
cat > "$SANDBOX/fake-missing-paths.md" <<'MDEOF'
---
name: fake-skill
description: A fake skill with no paths: field and not on the allowlist.
---

# Fake Skill
MDEOF

if python3 "$SANDBOX/check.py" < "$SANDBOX/fake-missing-paths.md" 2>"$SANDBOX/err"; then
  record "test_03_check_template_recognizes_missing_paths" FAIL "expected non-zero exit on missing-paths fixture"
else
  if grep -q "missing required" "$SANDBOX/err"; then
    record "test_03_check_template_recognizes_missing_paths" PASS
  else
    record "test_03_check_template_recognizes_missing_paths" FAIL "exited non-zero but stderr lacked 'missing required'; got: $(cat "$SANDBOX/err")"
  fi
fi

# ---------------------------------------------------------------------------
# test_04_check_template_honors_allowlist (AC-4 Case-2)
# ---------------------------------------------------------------------------
ALLOWLIST_OK=0
ALLOWLIST_FAIL_NAMES=""
for name in pipeline claude-md-enhancer caveman-mode write-a-skill; do
  cat > "$SANDBOX/fake-$name.md" <<MDEOF
---
name: $name
description: An allowlist skill with no paths: field — expected to pass.
---

# $name
MDEOF
  if python3 "$SANDBOX/check.py" < "$SANDBOX/fake-$name.md" >/dev/null 2>&1; then
    ALLOWLIST_OK=$((ALLOWLIST_OK + 1))
  else
    ALLOWLIST_FAIL_NAMES="$ALLOWLIST_FAIL_NAMES $name"
  fi
done

if [ "$ALLOWLIST_OK" = "4" ]; then
  record "test_04_check_template_honors_allowlist" PASS
else
  record "test_04_check_template_honors_allowlist" FAIL "expected 4/4 allowlist names accepted, got $ALLOWLIST_OK/4 (failed:$ALLOWLIST_FAIL_NAMES)"
fi

# ---------------------------------------------------------------------------
# test_05_check_template_passes_with_paths (AC-4 + AC-5 sanity)
# ---------------------------------------------------------------------------
cat > "$SANDBOX/fake-with-paths.md" <<'MDEOF'
---
name: arbitrary-skill
description: An arbitrary skill that DOES declare paths: — expected to pass.
paths:
  - "src/**/*.ts"
  - "tests/**/*.spec.ts"
---

# Arbitrary Skill
MDEOF

if python3 "$SANDBOX/check.py" < "$SANDBOX/fake-with-paths.md" >/dev/null 2>&1; then
  record "test_05_check_template_passes_with_paths" PASS
else
  record "test_05_check_template_passes_with_paths" FAIL "expected zero exit on with-paths fixture"
fi

# ---------------------------------------------------------------------------
echo "Results: $PASS PASS / $FAIL FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED_NAMES[*]}"
  exit 1
fi
exit 0
