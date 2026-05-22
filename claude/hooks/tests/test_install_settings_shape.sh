#!/usr/bin/env bash
set -euo pipefail
# test_install_settings_shape.sh — assert scripts/install.sh emits exec-form hooks
#
# Runs the installer in a sandboxed CLAUDE_HOME and parses the produced
# settings.json to verify every wired hook entry carries both "command" and
# "args" keys, and no "command" value contains a space (rejects legacy shell form).
#
# Expected result: Results: 3 PASS / 0 FAIL

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
echo "Results: $PASS PASS / $FAIL FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED_NAMES[*]}"
  exit 1
fi
exit 0
