#!/usr/bin/env bash
set -euo pipefail
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT
REPO_ROOT=$(git rev-parse --show-toplevel)
AGENT="$REPO_ROOT/claude/agents/production-probe.md"

# 1) File exists
[ -f "$AGENT" ] || { echo "FAIL: $AGENT does not exist"; exit 1; }

# 2) Frontmatter parses as valid YAML and has required fields
python3 - <<PYEOF
import yaml, sys

with open('$AGENT') as f:
    content = f.read()

parts = content.split('---', 2)
if len(parts) < 3:
    print("FAIL: no YAML frontmatter block (need --- ... ---)")
    sys.exit(1)

fm_text = parts[1]
try:
    d = yaml.safe_load(fm_text)
except Exception as e:
    print(f"FAIL: frontmatter YAML parse error: {e}")
    sys.exit(1)

assert d.get('name') == 'production-probe', f"name mismatch: {d.get('name')}"
print(f"OK: name = {d['name']}")

tools = set(d.get('tools', []))
expected_tools = {'Bash', 'Read', 'Edit', 'WebFetch'}
assert tools == expected_tools, f"tools mismatch: expected {expected_tools}, got {tools}"
assert 'Write' not in tools, "tools must NOT include Write"
assert 'Task' not in tools, "tools must NOT include Task"
assert 'Agent' not in tools, "tools must NOT include Agent"
print(f"OK: tools = {sorted(tools)}")

assert d.get('model') == 'sonnet', f"model mismatch: {d.get('model')}"
print(f"OK: model = {d['model']}")

print("OK: frontmatter")
PYEOF

# 3) Body anchors: required H2 sections present
for h2 in "## Boundaries" "## Probe Loop" "## Idempotency" "## Honesty Contract" "## Anti-pattern Refusals"; do
  grep -qE "^${h2}" "$AGENT" || { echo "FAIL: missing section $h2"; exit 1; }
  echo "OK: found '$h2'"
done

# 4) No claude -p (PR #117 binding)
count=$(grep -c "claude -p" "$AGENT" || true)
[ "$count" -eq 0 ] || { echo "FAIL: claude -p must NOT appear (PR #117)"; exit 1; }
echo "OK: no 'claude -p'"

# 5) timeout 60 appears >= 3 times (R3 mitigation)
timeout_count=$(grep -c "timeout 60" "$AGENT" || true)
[ "$timeout_count" -ge 3 ] || { echo "FAIL: timeout 60 must appear >= 3 times, found $timeout_count"; exit 1; }
echo "OK: timeout 60 x$timeout_count"

# 6) NOT EXECUTED appears >= 4 times (honesty contract)
ne_count=$(grep -c "NOT EXECUTED" "$AGENT" || true)
[ "$ne_count" -ge 4 ] || { echo "FAIL: NOT EXECUTED must appear >= 4 times, found $ne_count"; exit 1; }
echo "OK: NOT EXECUTED x$ne_count"

echo "OK: test_production_probe_agent_shape.sh PASS"
