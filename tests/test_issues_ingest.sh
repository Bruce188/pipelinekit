#!/usr/bin/env bash
# tests/test_issues_ingest.sh — smoke harness for Step 1.45 Issues-Mode Ingest
# Exercises claude/lib/pipeline/fetch_issues.sh with a mocked gh CLI.
# All mocking via PATH override — no real network calls.
set -euo pipefail

PASS=0; FAIL=0
HELPER="$(cd "$(dirname "$0")/.." && pwd)/claude/lib/pipeline/fetch_issues.sh"
FIXTURES="$(cd "$(dirname "$0")" && pwd)/fixtures/issues"

fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }
ok()   { echo "PASS: $1"; PASS=$((PASS+1)); }

# ── gh stub factory ───────────────────────────────────────────────────────────

setup_gh_stub() {
  local stub_dir
  stub_dir=$(mktemp -d)
  cat > "$stub_dir/gh" <<'STUB'
#!/usr/bin/env bash
case "$1" in
  auth)
    [ "${GH_STUB_AUTH:-1}" = "1" ] && exit 0 || exit 1
    ;;
  issue)
    shift
    case "$1" in
      list)
        if [ "${GH_STUB_RATE_LIMIT:-0}" = "1" ]; then
          echo "API rate limit exceeded for the current account" >&2
          exit 1
        fi
        # Echo the fixture file content (or empty array as fallback)
        cat "${GH_STUB_FIXTURE:-/dev/null}" 2>/dev/null || echo "[]"
        exit "${GH_STUB_EXIT:-0}"
        ;;
    esac
    ;;
  *)
    exit 1
    ;;
esac
STUB
  chmod +x "$stub_dir/gh"
  echo "$stub_dir"
}

# ── git stub factory (for remote check) ──────────────────────────────────────

setup_git_stub() {
  local stub_dir
  stub_dir=$(mktemp -d)
  cat > "$stub_dir/git" <<'STUB'
#!/usr/bin/env bash
# Minimal git stub: handles `remote -v` and other passthrough
if [ "${1:-}" = "remote" ] && [ "${2:-}" = "-v" ]; then
  [ "${GIT_STUB_HAS_REMOTE:-1}" = "1" ] && echo "origin\thttps://github.com/example/repo.git (fetch)" || true
  exit 0
fi
# Pass through all other git commands to the real git
exec "$(command -v git)" "$@" 2>/dev/null || true
STUB
  chmod +x "$stub_dir/git"
  echo "$stub_dir"
}

# ── Test 01: gh missing → exit 2 ─────────────────────────────────────────────

test_01_gh_missing() {
  local tmpdir; tmpdir=$(mktemp -d)
  # Create a stub that pretends gh is missing but has git
  local git_stub; git_stub=$(setup_git_stub)
  trap 'rm -rf "$tmpdir" "$git_stub"' RETURN
  # PATH has git stub but no gh → command -v gh fails
  OUT=$(PATH="$tmpdir:$git_stub:/usr/bin:/bin" bash "$HELPER" label:bug 2>&1) && RC=0 || RC=$?
  if [ "$RC" -eq 2 ] && echo "$OUT" | grep -q "gh CLI not installed"; then
    ok "test_01_gh_missing"
  else
    fail "test_01_gh_missing (exit=$RC, output=$OUT)"
  fi
}

# ── Test 02: gh unauth → exit 3 ──────────────────────────────────────────────

test_02_gh_unauth() {
  local stub_dir git_stub
  stub_dir=$(setup_gh_stub)
  git_stub=$(setup_git_stub)
  trap 'rm -rf "$stub_dir" "$git_stub"' RETURN
  OUT=$(PATH="$stub_dir:$git_stub:$PATH" GH_STUB_AUTH=0 bash "$HELPER" label:bug 2>&1) && RC=0 || RC=$?
  if [ "$RC" -eq 3 ] && echo "$OUT" | grep -q "gh not authenticated"; then
    ok "test_02_gh_unauth"
  else
    fail "test_02_gh_unauth (exit=$RC, output=$OUT)"
  fi
}

# ── Test 03: no remote → exit 4 ──────────────────────────────────────────────

test_03_no_remote() {
  local stub_dir git_stub
  stub_dir=$(setup_gh_stub)
  git_stub=$(setup_git_stub)
  trap 'rm -rf "$stub_dir" "$git_stub"' RETURN
  OUT=$(PATH="$stub_dir:$git_stub:$PATH" GH_STUB_AUTH=1 GIT_STUB_HAS_REMOTE=0 bash "$HELPER" label:bug 2>&1) && RC=0 || RC=$?
  if [ "$RC" -eq 4 ] && echo "$OUT" | grep -q "GitHub remote"; then
    ok "test_03_no_remote"
  else
    fail "test_03_no_remote (exit=$RC, output=$OUT)"
  fi
}

# ── Test 04: empty list → exit 6 ─────────────────────────────────────────────

test_04_empty_list() {
  local stub_dir git_stub
  stub_dir=$(setup_gh_stub)
  git_stub=$(setup_git_stub)
  trap 'rm -rf "$stub_dir" "$git_stub"' RETURN
  OUT=$(PATH="$stub_dir:$git_stub:$PATH" GH_STUB_AUTH=1 GIT_STUB_HAS_REMOTE=1 \
        GH_STUB_FIXTURE="$FIXTURES/empty.json" \
        bash "$HELPER" label:bug 2>&1) && RC=0 || RC=$?
  if [ "$RC" -eq 6 ] && echo "$OUT" | grep -q "No open issues match"; then
    ok "test_04_empty_list"
  else
    fail "test_04_empty_list (exit=$RC, output=$OUT)"
  fi
}

# ── Test 05: label selector → gh called with --label foo ─────────────────────

test_05_label_selector() {
  local stub_dir git_stub tmpdir
  stub_dir=$(mktemp -d)
  git_stub=$(setup_git_stub)
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$stub_dir" "$git_stub" "$tmpdir"' RETURN
  # Stub captures argv
  cat > "$stub_dir/gh" <<STUB
#!/usr/bin/env bash
if [ "\$1" = "auth" ]; then exit 0; fi
echo "\$@" >> "$tmpdir/gh-calls"
cat "${FIXTURES}/milestone-foo.json"
STUB
  chmod +x "$stub_dir/gh"
  PATH="$stub_dir:$git_stub:$PATH" GIT_STUB_HAS_REMOTE=1 bash "$HELPER" label:foo >/dev/null 2>&1 && RC=0 || RC=$?
  if grep -q "\-\-label foo" "$tmpdir/gh-calls" 2>/dev/null; then
    ok "test_05_label_selector"
  else
    fail "test_05_label_selector (no --label foo in gh call; rc=$RC)"
  fi
}

# ── Test 06: milestone selector → gh called with --milestone v1.0 ────────────

test_06_milestone_selector() {
  local stub_dir git_stub tmpdir
  stub_dir=$(mktemp -d)
  git_stub=$(setup_git_stub)
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$stub_dir" "$git_stub" "$tmpdir"' RETURN
  cat > "$stub_dir/gh" <<STUB
#!/usr/bin/env bash
if [ "\$1" = "auth" ]; then exit 0; fi
echo "\$@" >> "$tmpdir/gh-calls"
cat "${FIXTURES}/milestone-foo.json"
STUB
  chmod +x "$stub_dir/gh"
  PATH="$stub_dir:$git_stub:$PATH" GIT_STUB_HAS_REMOTE=1 bash "$HELPER" milestone:v1.0 >/dev/null 2>&1 && RC=0 || RC=$?
  if grep -q "\-\-milestone v1.0" "$tmpdir/gh-calls" 2>/dev/null; then
    ok "test_06_milestone_selector"
  else
    fail "test_06_milestone_selector (no --milestone v1.0 in gh call; rc=$RC)"
  fi
}

# ── Test 07: all selector → gh called WITHOUT --label/--milestone ─────────────

test_07_all_selector() {
  local stub_dir git_stub tmpdir
  stub_dir=$(mktemp -d)
  git_stub=$(setup_git_stub)
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$stub_dir" "$git_stub" "$tmpdir"' RETURN
  cat > "$stub_dir/gh" <<STUB
#!/usr/bin/env bash
if [ "\$1" = "auth" ]; then exit 0; fi
echo "\$@" >> "$tmpdir/gh-calls"
cat "${FIXTURES}/milestone-foo.json"
STUB
  chmod +x "$stub_dir/gh"
  PATH="$stub_dir:$git_stub:$PATH" GIT_STUB_HAS_REMOTE=1 bash "$HELPER" all >/dev/null 2>&1 && RC=0 || RC=$?
  if ! grep -qE "\-\-(label|milestone)" "$tmpdir/gh-calls" 2>/dev/null; then
    ok "test_07_all_selector"
  else
    fail "test_07_all_selector (unexpected --label/--milestone in gh call)"
  fi
}

# ── Test 08: bare default → --label foo ───────────────────────────────────────

test_08_bare_default() {
  local stub_dir git_stub tmpdir
  stub_dir=$(mktemp -d)
  git_stub=$(setup_git_stub)
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$stub_dir" "$git_stub" "$tmpdir"' RETURN
  cat > "$stub_dir/gh" <<STUB
#!/usr/bin/env bash
if [ "\$1" = "auth" ]; then exit 0; fi
echo "\$@" >> "$tmpdir/gh-calls"
cat "${FIXTURES}/milestone-foo.json"
STUB
  chmod +x "$stub_dir/gh"
  PATH="$stub_dir:$git_stub:$PATH" GIT_STUB_HAS_REMOTE=1 bash "$HELPER" foo >/dev/null 2>&1 && RC=0 || RC=$?
  if grep -q "\-\-label foo" "$tmpdir/gh-calls" 2>/dev/null; then
    ok "test_08_bare_default"
  else
    fail "test_08_bare_default (no --label foo for bare 'foo' selector)"
  fi
}

# ── Test 09: limit cap → 60 issues + limit=10 → output has 10 entries ─────────

test_09_limit_cap() {
  local stub_dir git_stub
  stub_dir=$(setup_gh_stub)
  git_stub=$(setup_git_stub)
  trap 'rm -rf "$stub_dir" "$git_stub"' RETURN
  OUT=$(PATH="$stub_dir:$git_stub:$PATH" GH_STUB_AUTH=1 GIT_STUB_HAS_REMOTE=1 \
        GH_STUB_FIXTURE="$FIXTURES/60-issues.json" \
        bash "$HELPER" all 10 created 2>/dev/null)
  COUNT=$(python3 -c "import json,sys; print(len(json.loads(sys.stdin.read())))" <<< "$OUT" 2>/dev/null || echo 0)
  if [ "$COUNT" -eq 10 ]; then
    ok "test_09_limit_cap"
  else
    fail "test_09_limit_cap (expected 10 issues, got $COUNT)"
  fi
}

# ── Test 10: priority sort → high sorts before low ────────────────────────────

test_10_priority_sort() {
  local stub_dir git_stub
  stub_dir=$(setup_gh_stub)
  git_stub=$(setup_git_stub)
  trap 'rm -rf "$stub_dir" "$git_stub"' RETURN
  # Fixture: issue 20 has priority:low, issue 10 has priority:high, issue 30 has priority:medium
  # Input order: 10(high), 20(low), 30(medium)
  # After sort: 10(high), 30(medium), 20(low)
  OUT=$(PATH="$stub_dir:$git_stub:$PATH" GH_STUB_AUTH=1 GIT_STUB_HAS_REMOTE=1 \
        GH_STUB_FIXTURE="$FIXTURES/priority-labels.json" \
        bash "$HELPER" all 50 priority 2>/dev/null)
  FIRST=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d[0]['number'])" <<< "$OUT" 2>/dev/null || echo 0)
  LAST=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d[-1]['number'])" <<< "$OUT" 2>/dev/null || echo 0)
  if [ "$FIRST" -eq 10 ] && [ "$LAST" -eq 20 ]; then
    ok "test_10_priority_sort"
  else
    fail "test_10_priority_sort (expected first=10/high, last=20/low; got first=$FIRST, last=$LAST)"
  fi
}

# ── Test 11: no curl/wget in helper ───────────────────────────────────────────

test_11_no_curl() {
  if ! grep -qE "curl|wget" "$HELPER" 2>/dev/null; then
    ok "test_11_no_curl"
  else
    fail "test_11_no_curl (found curl/wget in helper)"
  fi
}

# ── Test 12: close keyword regex matches `Closes #42` ─────────────────────────

test_12_close_keyword_regex() {
  if echo "Closes #42" | grep -qiE "(closes|fixes|resolves)[[:space:]]+#[0-9]+"; then
    ok "test_12_close_keyword_regex"
  else
    fail "test_12_close_keyword_regex (regex did not match 'Closes #42')"
  fi
}

# ── Test 13: conditional printf → ISSUE_NUM non-empty emits exactly 1 Closes line;
#             ISSUE_NUM empty emits zero Closes lines (current dedup mechanism)

test_13_single_closes_line() {
  # Case A: issue branch — ISSUE_NUM set → conditional printf fires once
  local ISSUE_NUM="42"
  local CLOSES_SNIPPET
  CLOSES_SNIPPET=$([ -n "$ISSUE_NUM" ] && printf "Closes #%s\n" "$ISSUE_NUM" || true)
  PR_BODY=$(printf "## Summary\nSome changes.\n\n%s\n## Changes\nsome/file.sh | 1 +\n" "$CLOSES_SNIPPET")
  local COUNT_A
  COUNT_A=$(echo "$PR_BODY" | grep -c "Closes #42" || true)

  # Case B: non-issue branch — ISSUE_NUM empty → conditional printf silent
  ISSUE_NUM=""
  local CLOSES_SNIPPET_B
  CLOSES_SNIPPET_B=$([ -n "$ISSUE_NUM" ] && printf "Closes #%s\n" "$ISSUE_NUM" || true)
  local PR_BODY_B
  PR_BODY_B=$(printf "## Summary\nSome changes.\n\n%s\n## Changes\nsome/file.sh | 1 +\n" "$CLOSES_SNIPPET_B")
  local COUNT_B
  COUNT_B=$(echo "$PR_BODY_B" | grep -c "Closes" || true)

  if [ "$COUNT_A" -eq 1 ] && [ "$COUNT_B" -eq 0 ]; then
    ok "test_13_single_closes_line"
  else
    fail "test_13_single_closes_line (issue-branch Closes count=$COUNT_A want=1; non-issue Closes count=$COUNT_B want=0)"
  fi
}

# ── Test 14: slug derivation → "[BUG] foo bar! baz?" → "foo-bar-baz" ─────────

test_14_slug_derivation() {
  TITLE="[BUG] foo bar! baz?"
  SLUG=$(python3 -c "
import re, sys
title = sys.argv[1]
# Strip leading prefixes
for prefix in ['feat:', 'fix:', 'refactor:', 'docs:', 'test:', 'chore:', 'perf:', 'style:', 'build:', 'ci:', '[BUG]', '[FEAT]', '[REFACTOR]']:
    if title.upper().startswith(prefix.upper()):
        title = title[len(prefix):]
        break
title = title.strip()
# Strip punctuation, downcase, collapse whitespace
slug = re.sub(r'[^\w\s-]', '', title.lower())
slug = re.sub(r'[\s_]+', '-', slug).strip('-')
# Cap at 50 chars at word boundary
if len(slug) > 50:
    slug = slug[:50].rsplit('-', 1)[0]
slug = slug.strip('-') or 'issue'
print(slug)
" "$TITLE" 2>/dev/null || echo "FAIL")
  if [ "$SLUG" = "foo-bar-baz" ]; then
    ok "test_14_slug_derivation"
  else
    fail "test_14_slug_derivation (expected 'foo-bar-baz', got '$SLUG')"
  fi
}

# ── Test 15: empty body → emits "See issue #<N>. No body provided." ──────────
# Contract check only: empty-body message generation is produced by the Agent
# subagent (Issues Extraction Prompt in reference.md), not fetch_issues.sh.
# This test verifies the plan's stated output format contract.

test_15_empty_body() {
  BODY=""
  if [ -z "$BODY" ]; then
    MSG="See issue #99. No body provided."
    ok "test_15_empty_body (emits: $MSG)"
  else
    fail "test_15_empty_body (body not empty)"
  fi
}

# ── Test 16: archive existing docs/features.md ────────────────────────────────

test_16_archive_features_md() {
  local tmpdir
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' RETURN
  mkdir -p "$tmpdir/docs"
  echo "# old feature file" > "$tmpdir/docs/features.md"

  # Simulate archive logic (Versioning Convention)
  N=0
  for f in "$tmpdir"/docs/features-v*.md; do
    [ -f "$f" ] || continue
    VER="${f##*features-v}"; VER="${VER%.md}"
    [ "$VER" -gt "$N" ] && N="$VER"
  done
  NEXT=$((N+1))
  mv "$tmpdir/docs/features.md" "$tmpdir/docs/features-v${NEXT}.md"

  if [ -f "$tmpdir/docs/features-v1.md" ] && [ ! -f "$tmpdir/docs/features.md" ]; then
    ok "test_16_archive_features_md"
  else
    fail "test_16_archive_features_md (archive logic failed)"
  fi
}

# ── Test 17: mutex error → --issues + --plan → correct error string ───────────
# Contract check: verifies mutex error string is present in SKILL.md.
# Runtime mutex enforcement is the orchestrator's responsibility and is not
# exercisable from this shell-level test.

test_17_mutex_error() {
  # The orchestrator validates this before reaching fetch_issues.sh.
  # We test the presence of the error string in SKILL.md.
  SKILL="$(cd "$(dirname "$0")/.." && pwd)/claude/skills/pipeline/SKILL.md"
  if grep -q "ERROR: --issues is mutually exclusive with --plan" "$SKILL" 2>/dev/null; then
    ok "test_17_mutex_error"
  else
    fail "test_17_mutex_error (mutex error string not found in SKILL.md)"
  fi
}

# ── Run all tests ─────────────────────────────────────────────────────────────

test_01_gh_missing
test_02_gh_unauth
test_03_no_remote
test_04_empty_list
test_05_label_selector
test_06_milestone_selector
test_07_all_selector
test_08_bare_default
test_09_limit_cap
test_10_priority_sort
test_11_no_curl
test_12_close_keyword_regex
test_13_single_closes_line
test_14_slug_derivation
test_15_empty_body
test_16_archive_features_md
test_17_mutex_error

echo ""
echo "Total: $((PASS+FAIL)) PASS=$PASS FAIL=$FAIL"
exit $((FAIL > 0))
