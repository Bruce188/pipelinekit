#!/usr/bin/env bash
# Tests for tsv-viewer.sh.
#
# Four test functions:
#   1. test_exit_zero_on_fixture           — happy path: 3-row TSV, exit 0, file written
#   2. test_html_contains_rows             — row descriptions present in output HTML
#   3. test_missing_tsv_emits_clean_error  — non-existent input → non-zero exit + "error:" on stderr
#   4. test_html_is_well_formed_with_css_palette — </html>, <style>, all 7 F11 vars,
#                                                  dark-mode media query, no "cdn" substring
#
# Always passes --no-open so no browser is launched (hermetic).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TSV_VIEWER="$REPO_ROOT/claude/skills/research/tsv-viewer.sh"
FAILURES=0

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1: $2" >&2; FAILURES=$((FAILURES + 1)); }

# TSV header matching the locked constant in research-loop.sh
TSV_HEADER=$'commit\tmetric\tmemory\tstatus\tdescription'

# ---------------------------------------------------------------------------
# test_exit_zero_on_fixture
# Stage a 3-row TSV with mixed statuses. Assert exit 0 and output file exists.
# ---------------------------------------------------------------------------
test_exit_zero_on_fixture() {
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN

  mkdir -p "$tmp/docs"
  {
    printf '%s\n' "$TSV_HEADER"
    printf 'abc123\t1.5\t128MB\tkeep\tfixture description one\n'
    printf 'def456\t0.8\t64MB\treject\tfixture description two\n'
    printf 'ghi789\t2.1\t256MB\tkeep\tfixture description three\n'
  } > "$tmp/docs/research-results.tsv"

  local rc=0
  bash "$TSV_VIEWER" \
    --input "$tmp/docs/research-results.tsv" \
    --output "$tmp/out.html" \
    --no-open || rc=$?

  if [[ "$rc" -ne 0 ]]; then
    fail "test_exit_zero_on_fixture" "expected exit 0; got $rc"
    return
  fi

  if [ ! -f "$tmp/out.html" ]; then
    fail "test_exit_zero_on_fixture" "output file not created: $tmp/out.html"
    return
  fi

  pass "test_exit_zero_on_fixture"
}

# ---------------------------------------------------------------------------
# test_html_contains_rows
# After the same successful invocation as test 1, assert each of the 3 row
# descriptions appears in the output HTML via grep -F.
# ---------------------------------------------------------------------------
test_html_contains_rows() {
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN

  mkdir -p "$tmp/docs"
  {
    printf '%s\n' "$TSV_HEADER"
    printf 'abc123\t1.5\t128MB\tkeep\tfixture description one\n'
    printf 'def456\t0.8\t64MB\treject\tfixture description two\n'
    printf 'ghi789\t2.1\t256MB\tkeep\tfixture description three\n'
  } > "$tmp/docs/research-results.tsv"

  bash "$TSV_VIEWER" \
    --input "$tmp/docs/research-results.tsv" \
    --output "$tmp/out.html" \
    --no-open

  local ok=1
  for desc in "fixture description one" "fixture description two" "fixture description three"; do
    if ! grep -qF "$desc" "$tmp/out.html"; then
      fail "test_html_contains_rows" "description '$desc' not found in output HTML"
      ok=0
    fi
  done

  if [[ "$ok" -eq 1 ]]; then
    pass "test_html_contains_rows"
  fi
}

# ---------------------------------------------------------------------------
# test_missing_tsv_emits_clean_error
# Run the viewer with a non-existent input path. Assert non-zero exit AND
# stderr contains the literal substring "error:".
# ---------------------------------------------------------------------------
test_missing_tsv_emits_clean_error() {
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN

  local stderr_file
  stderr_file=$(mktemp)

  local rc=0
  bash "$TSV_VIEWER" \
    --input "$tmp/does-not-exist.tsv" \
    --output "$tmp/out.html" \
    --no-open \
    2>"$stderr_file" || rc=$?

  local stderr_content
  stderr_content=$(cat "$stderr_file")
  rm -f "$stderr_file"

  if [[ "$rc" -eq 0 ]]; then
    fail "test_missing_tsv_emits_clean_error" "expected non-zero exit; got 0"
    return
  fi

  if ! echo "$stderr_content" | grep -qF "error:"; then
    fail "test_missing_tsv_emits_clean_error" "expected 'error:' in stderr; got: $stderr_content"
    return
  fi

  pass "test_missing_tsv_emits_clean_error"
}

# ---------------------------------------------------------------------------
# test_html_is_well_formed_with_css_palette
# After a successful invocation (same 3-row TSV as test 1), assert:
#   - </html> present
#   - <style> block present
#   - All 7 F11 vars defined: --bg --fg --accent --surface --border --text-muted --link
#   - @media (prefers-color-scheme: dark) present
#   - "cdn" substring absent (case-insensitive) — F11 no-remote-resources contract
# ---------------------------------------------------------------------------
test_html_is_well_formed_with_css_palette() {
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN

  mkdir -p "$tmp/docs"
  {
    printf '%s\n' "$TSV_HEADER"
    printf 'abc123\t1.5\t128MB\tkeep\tfixture description one\n'
    printf 'def456\t0.8\t64MB\treject\tfixture description two\n'
    printf 'ghi789\t2.1\t256MB\tkeep\tfixture description three\n'
  } > "$tmp/docs/research-results.tsv"

  bash "$TSV_VIEWER" \
    --input "$tmp/docs/research-results.tsv" \
    --output "$tmp/out.html" \
    --no-open

  local ok=1

  if ! grep -q '</html>' "$tmp/out.html"; then
    fail "test_html_is_well_formed_with_css_palette" "missing </html>"
    ok=0
  fi

  if ! grep -q '<style>' "$tmp/out.html"; then
    fail "test_html_is_well_formed_with_css_palette" "missing <style>"
    ok=0
  fi

  for v in '--bg' '--fg' '--accent' '--surface' '--border' '--text-muted' '--link'; do
    if ! grep -qF -- "$v" "$tmp/out.html"; then
      fail "test_html_is_well_formed_with_css_palette" "F11 var $v not found in HTML"
      ok=0
    fi
  done

  if ! grep -q '@media (prefers-color-scheme: dark)' "$tmp/out.html"; then
    fail "test_html_is_well_formed_with_css_palette" "missing @media (prefers-color-scheme: dark)"
    ok=0
  fi

  if grep -qi 'cdn' "$tmp/out.html"; then
    fail "test_html_is_well_formed_with_css_palette" "found 'cdn' substring in HTML — F11 contract violation"
    ok=0
  fi

  if [[ "$ok" -eq 1 ]]; then
    pass "test_html_is_well_formed_with_css_palette"
  fi
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
test_exit_zero_on_fixture
test_html_contains_rows
test_missing_tsv_emits_clean_error
test_html_is_well_formed_with_css_palette

echo ""
echo "Results: $FAILURES failure(s)"
[[ "$FAILURES" -eq 0 ]]
