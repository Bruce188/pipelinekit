#!/usr/bin/env bash
# Test richness_check.py topic-affinity layer.
#
# A "signature" snippet (one whose rendered content is baked-in and
# topic-specific, e.g. cost-budget-meter / architecture-diagram) must have at
# least one of its topic keywords present in the page's AUTHOR PROSE (the
# sibling markdown source). Otherwise the page FAILS even when its richness
# score clears the threshold. Generic container snippets (comparison-tabs, ...)
# carry no signature and are never affinity-checked. An override comment
# (<!-- topic-affinity-ok: <snippet> ... -->) suppresses one snippet's check.
#
# Scenarios:
#   a) signature snippet + keyword present in source -> OK   (exit 0)
#   b) signature snippet + keyword absent            -> FAIL (exit 1, "off-topic")
#   c) signature snippet + keyword absent + override -> OK   (exit 0)
#   d) neutral snippet (no signature) + no keyword   -> OK   (exit 0)
#   e) architecture-diagram + keyword absent         -> FAIL (exit 1, "off-topic")
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CHECK="python3 $REPO_ROOT/claude/skills/docs-writer/richness_check.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Neutral filler with none of the tested signatures' keywords.
NEUTRAL="alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"

# Helper: write a rendered-HTML fixture mounting $mount plus a sibling markdown
# source ($stem.md) carrying the AUTHOR PROSE the affinity check reads. The
# rendered HTML uses data-snippet-mount (post-render form); the source uses
# plain prose, mirroring how render.py expands a data-snippet placeholder.
#   override=yes -> emit a topic-affinity-ok comment for $mount in the HTML head
make_pair() {
    local stem="$1" mount="$2" prose="$3" override="$4"
    {
        echo '<!doctype html><html><head><title>t</title>'
        if [ "$override" = "yes" ]; then
            echo "<!-- topic-affinity-ok: $mount test override -->"
        fi
        echo '</head><body>'
        echo "<div data-snippet-mount=\"$mount\"></div>"
        echo 'body filler words to stay well under the 1500-word threshold'
        echo '</body></html>'
    } > "$TMP/$stem.html"
    printf '%s\n' "$prose" > "$TMP/$stem.md"
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

assert_contains() {
    local name="$1" needle="$2" out="$3"
    if grep -q "$needle" "$out"; then
        echo "  PASS  $name"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $name (output missing '$needle')"
        echo "  --- output ---"
        sed 's/^/    /' "$out"
        echo "  --------------"
        FAIL=$((FAIL + 1))
    fi
}

# Scenario a: cost-budget-meter + keyword present -> OK
make_pair sa cost-budget-meter "Tracking cost and spend in USD across the run." no
$CHECK "$TMP/sa.html" > "$TMP/sa.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario a: signature snippet + keyword present passes" 0 "$rc" "$TMP/sa.out"

# Scenario b: cost-budget-meter + keyword absent -> FAIL
make_pair sb cost-budget-meter "$NEUTRAL" no
$CHECK "$TMP/sb.html" > "$TMP/sb.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario b: signature snippet + keyword absent fails" 1 "$rc" "$TMP/sb.out"
assert_contains "scenario b: failure reported as off-topic" "off-topic" "$TMP/sb.out"

# Scenario c: cost-budget-meter + keyword absent + override -> OK
make_pair sc cost-budget-meter "$NEUTRAL" yes
$CHECK "$TMP/sc.html" > "$TMP/sc.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario c: topic-affinity-ok override suppresses failure" 0 "$rc" "$TMP/sc.out"

# Scenario d: neutral snippet (no signature) + no keyword -> OK
make_pair sd comparison-tabs "$NEUTRAL" no
$CHECK "$TMP/sd.html" > "$TMP/sd.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario d: neutral container snippet is not affinity-checked" 0 "$rc" "$TMP/sd.out"

# Scenario e: architecture-diagram + keyword absent -> FAIL (mirrors real bug)
make_pair se architecture-diagram "$NEUTRAL" no
$CHECK "$TMP/se.html" > "$TMP/se.out" 2>&1 && rc=$? || rc=$?
assert_exit "scenario e: off-topic architecture-diagram fails" 1 "$rc" "$TMP/se.out"
assert_contains "scenario e: failure reported as off-topic" "off-topic" "$TMP/se.out"

echo
echo "Total: $PASS pass, $FAIL fail"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "terminal OK: test_topic_affinity.sh"
exit 0
