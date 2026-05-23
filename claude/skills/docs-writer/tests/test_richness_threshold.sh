#!/usr/bin/env bash
# Test richness_check.py >1500-body-word adaptive threshold logic.
#
# Scenarios:
#   1) 2000 words + 1 snippet               -> FAIL (exit 1)  [new behavior]
#   2) 2000 words + 2 distinct rich primitives -> OK (exit 0)
#   3) 1000 words + 1 snippet               -> OK (exit 0)    [legacy behavior preserved]
#   4) 2000 words + 0 snippets + exempt     -> OK (exit 0)    [exempt honored]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CHECK="python3 $REPO_ROOT/claude/skills/docs-writer/richness_check.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Helper: emit a minimal HTML doc with N body words and optional snippet/exempt.
# snippet:
#   none  -> no rich-pattern primitives in body
#   one   -> exactly one rich-pattern match (specific snippet mount)
#   two   -> two DISTINCT rich-pattern matches
# exempt:
#   yes -> emits <!-- richness-exempt: ... --> inside <head>
make_html() {
    local out="$1" words="$2" snippet="$3" exempt="$4"
    {
        echo '<!doctype html><html><head><title>t</title>'
        if [ "$exempt" = "yes" ]; then
            echo '<!-- richness-exempt: load-bearing test fixture -->'
        fi
        echo '</head><body>'
        case "$snippet" in
            one)
                echo '<div data-snippet-mount="comparison-tabs"></div>'
                ;;
            two)
                # Two DISTINCT richness-pattern matches:
                #   - specific snippet:comparison-tabs (mount placeholder)
                #   - custom-svg-diagram (viewBox >= 200x100)
                echo '<div data-snippet-mount="comparison-tabs"></div>'
                echo '<svg viewBox="0 0 600 400"><rect width="600" height="400"/></svg>'
                ;;
            none)
                : # no rich primitives
                ;;
        esac
        python3 -c "print(('lorem ' * $words).strip())"
        echo '</body></html>'
    } > "$out"
}

PASS=0
FAIL=0

assert_exit() {
    local name="$1" expected="$2" actual="$3" out="$4"
    if [ "$actual" = "$expected" ]; then
        echo "  PASS  $name"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $name (expected exit $expected, got $actual)"
        echo "  --- output ---"
        sed 's/^/    /' "$out"
        echo "  --------------"
        FAIL=$((FAIL + 1))
    fi
}

# Scenario 1: 2000 words + 1 snippet -> FAIL exit 1
make_html "$TMP/s1.html" 2000 one no
$CHECK "$TMP/s1.html" > "$TMP/s1.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario 1: 2000 words + 1 snippet fails new threshold" 1 "$rc" "$TMP/s1.out"

# Scenario 2: 2000 words + 2 distinct rich primitives -> OK exit 0
make_html "$TMP/s2.html" 2000 two no
$CHECK "$TMP/s2.html" > "$TMP/s2.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario 2: 2000 words + 2 distinct primitives passes" 0 "$rc" "$TMP/s2.out"

# Scenario 3: 1000 words + 1 snippet -> OK exit 0 (preserves old behavior)
make_html "$TMP/s3.html" 1000 one no
$CHECK "$TMP/s3.html" > "$TMP/s3.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario 3: 1000 words + 1 snippet preserves old threshold-1 behavior" 0 "$rc" "$TMP/s3.out"

# Scenario 4: 2000 words + 0 snippets + exempt marker -> OK exit 0 (exempt honored)
make_html "$TMP/s4.html" 2000 none yes
$CHECK "$TMP/s4.html" > "$TMP/s4.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario 4: 2000 words + 0 snippets + exempt honored" 0 "$rc" "$TMP/s4.out"

echo
echo "Total: $PASS pass, $FAIL fail"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "terminal OK: test_richness_threshold.sh"
exit 0
