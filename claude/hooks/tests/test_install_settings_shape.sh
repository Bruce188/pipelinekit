#!/usr/bin/env bash
set -euo pipefail
# test_install_settings_shape.sh — assert scripts/install.sh emits exec-form hooks
#
# Runs the installer in a sandboxed CLAUDE_HOME and parses the produced
# settings.json to verify every wired hook entry carries both "command" and
# "args" keys, and no "command" value contains a space (rejects legacy shell form).
#
# Expected result: Results: 4 PASS / 0 FAIL

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

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
    echo "FAIL: $name — $detail"
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# Run the installer in a non-interactive sandbox
# ---------------------------------------------------------------------------
CLAUDE_HOME="$SANDBOX/.claude" \
CLAUDE_INSTALL_SETTINGS=1 \
CLAUDE_INSTALL_NONINTERACTIVE=1 \
  bash "$REPO_ROOT/scripts/install.sh" >/dev/null 2>&1 || true

SETTINGS_FILE="$SANDBOX/.claude/settings.json"

# ---------------------------------------------------------------------------
# test_04: settings.json is well-formed JSON
# ---------------------------------------------------------------------------
if python3 - "$SETTINGS_FILE" <<'PYEOF'
import json, sys
json.load(open(sys.argv[1]))
PYEOF
then
  record "test_04_settings_json_well_formed" PASS
else
  record "test_04_settings_json_well_formed" FAIL "settings.json missing or invalid at $SETTINGS_FILE"
  # Remaining tests can't run if settings.json is broken
  echo "Results: $PASS PASS / $FAIL FAIL"
  exit 1
fi

# ---------------------------------------------------------------------------
# test_01: every hook entry has both "command" and "args" keys; "args" is a list
# ---------------------------------------------------------------------------
if python3 - "$SETTINGS_FILE" <<'PYEOF'
import json, sys

settings = json.load(open(sys.argv[1]))
hooks_section = settings.get("hooks", {})
failures = []

for event, matchers in hooks_section.items():
    for matcher_obj in matchers:
        matcher = matcher_obj.get("matcher", "?")
        for i, entry in enumerate(matcher_obj.get("hooks", [])):
            loc = "{}/{} [{}]".format(event, matcher, i)
            if "command" not in entry:
                failures.append("{}: missing key 'command'".format(loc))
            if "args" not in entry:
                failures.append("{}: missing key 'args'".format(loc))
            elif not isinstance(entry["args"], list):
                failures.append("{}: 'args' is not a list (got {})".format(
                    loc, type(entry["args"]).__name__))

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
PYEOF
then
  record "test_01_every_hook_has_command_and_args" PASS
else
  record "test_01_every_hook_has_command_and_args" FAIL "one or more entries missing command/args"
fi

# ---------------------------------------------------------------------------
# test_02: no "command" value contains a space (rejects legacy shell form)
# ---------------------------------------------------------------------------
if python3 - "$SETTINGS_FILE" <<'PYEOF'
import json, sys

settings = json.load(open(sys.argv[1]))
hooks_section = settings.get("hooks", {})
failures = []

for event, matchers in hooks_section.items():
    for matcher_obj in matchers:
        matcher = matcher_obj.get("matcher", "?")
        for i, entry in enumerate(matcher_obj.get("hooks", [])):
            cmd = entry.get("command", "")
            if " " in cmd:
                loc = "{}/{} [{}]".format(event, matcher, i)
                failures.append("{}: command contains space: {!r}".format(loc, cmd))

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
PYEOF
then
  record "test_02_no_command_contains_space" PASS
else
  record "test_02_no_command_contains_space" FAIL "command value(s) contain spaces"
fi

# ---------------------------------------------------------------------------
# test_05: every shipping Claude-harness hook is registered in settings.json
#   - expected_set = basename of every claude/hooks/*.sh + claude/hooks/*.py,
#     EXCLUDING underscore-prefixed helpers and validate-task-spec.py (git only).
#   - actual_set   = basename of every command path in settings.json hooks arrays.
# ---------------------------------------------------------------------------
if python3 - "$SETTINGS_FILE" "$REPO_ROOT" <<'PYEOF'
import json, os, sys
from pathlib import Path

settings_path = sys.argv[1]
repo_root = sys.argv[2]
hooks_dir = Path(repo_root) / "claude" / "hooks"

expected = set()
for p in sorted(hooks_dir.glob("*.sh")):
    if p.name.startswith("_"):
        continue
    # commit-msg-wrapper.sh is a native git commit-msg hook adapter installed
    # as a symlink at <git_dir>/hooks/commit-msg — NOT a Claude-harness hook.
    # See claude/hooks/CLAUDE.md § Exclusions.
    if p.name == "commit-msg-wrapper.sh":
        continue
    # scan-secrets-staged.sh is a native git pre-commit hook chained inside
    # <git_dir>/hooks/pre-commit via the dispatcher written by
    # scripts/install.sh:install_pre_commit_hook. NOT a Claude-harness hook.
    # See claude/hooks/CLAUDE.md § Exclusions.
    if p.name == "scan-secrets-staged.sh":
        continue
    expected.add(p.name)
for p in sorted(hooks_dir.glob("*.py")):
    if p.name.startswith("_"):
        continue
    if p.name == "validate-task-spec.py":
        continue
    if p.name == "cost_log.py":
        continue
    expected.add(p.name)

settings = json.load(open(settings_path))
actual = set()
for event, matchers in settings.get("hooks", {}).items():
    for m in matchers:
        for entry in m.get("hooks", []):
            cmd = entry.get("command", "")
            actual.add(os.path.basename(cmd))

missing = expected - actual
if missing:
    print("missing from settings.json: {}".format(sorted(missing)), file=sys.stderr)
    sys.exit(1)
PYEOF
then
  record "test_05_full_inventory_parity" PASS
else
  record "test_05_full_inventory_parity" FAIL "one or more shipping hooks not registered in settings.json"
fi

# ---------------------------------------------------------------------------
echo "Results: $PASS PASS / $FAIL FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED_NAMES[*]}"
  exit 1
fi
exit 0
