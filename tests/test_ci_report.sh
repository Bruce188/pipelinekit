#!/usr/bin/env bash
# scripts/ci-report.sh against a stub gh: one issue per failure streak.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
URL="https://github.com/o/r/actions/runs/123"
TITLE="Weekly self-check failed"

mkdir "$T/bin"
cat > "$T/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Logs each call on one line; answers `issue list` from $STUB/list.json.
printf '%s\n' "$(printf '%q ' "$@")" >> "$STUB/calls"
case "$1 $2" in
  "issue list")
    [ -f "$STUB/list-fails" ] && { echo "HTTP 502" >&2; exit 1; }
    cat "$STUB/list.json" ;;
  "issue create")
    if [ -f "$STUB/no-label" ] && [[ " $* " == *" --label "* ]]; then
      echo "could not add label: 'bug' not found" >&2
      exit 1
    fi
    echo "https://github.com/o/r/issues/9" ;;
  "issue comment") echo "https://github.com/o/r/issues/$3#issuecomment-1" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH" STUB="$T"

fail() { echo "FAIL: $1" >&2; [ -f "$T/calls" ] && cat "$T/calls" >&2; exit 1; }
reset() { rm -f "$T/calls" "$T/list-fails" "$T/no-label"; echo "$1" > "$T/list.json"; }
calls() { grep -c -- "^issue $1 " "$T/calls" || true; }
report() { bash "$REPO_ROOT/scripts/ci-report.sh" "$@" > "$T/out" 2> "$T/err"; }

# No open issue: one is created, with the label, the title and the run link.
reset '[]'
report "$URL" || fail "create: exit $?"
[ "$(calls create)" = 1 ] && [ "$(calls comment)" = 0 ] || fail "create: wrong calls"
grep -q -- "--title Weekly\\\\ self-check\\\\ failed --label bug" "$T/calls" || fail "create: title or label"
grep -q "actions/runs/123" "$T/calls" || fail "create: no run link in the body"

# The issue is open: a comment on it, no second issue.
reset "[{\"number\": 31, \"title\": \"$TITLE\"}, {\"number\": 12, \"title\": \"$TITLE\"}]"
report "$URL" || fail "comment: exit $?"
[ "$(calls comment)" = 1 ] && [ "$(calls create)" = 0 ] || fail "comment: wrong calls"
grep -q "^issue comment 12 " "$T/calls" || fail "comment: not on the oldest open issue"
grep -q "actions/runs/123" "$T/calls" || fail "comment: no run link"

# A title that only looks alike is another issue.
reset "[{\"number\": 5, \"title\": \"$TITLE on my machine\"}]"
report "$URL" || fail "alike: exit $?"
[ "$(calls create)" = 1 ] && [ "$(calls comment)" = 0 ] || fail "alike: wrong calls"

# Without the label in the repository the issue is still opened.
reset '[]'
touch "$T/no-label"
report "$URL" || fail "no label: exit $?"
[ "$(calls create)" = 2 ] || fail "no label: expected a second try"
tail -n 1 "$T/calls" | grep -q -- "--label" && fail "no label: second try still has the label"

# gh cannot list the issues: an error, and nothing is opened.
reset '[]'
touch "$T/list-fails"
report "$URL" && fail "list fails: exit 0"
[ "$(calls create)" = 0 ] && [ "$(calls comment)" = 0 ] || fail "list fails: wrote anyway"

# Anything but a plain https link is refused before gh is called.
for bad in "" "not-a-url" "http://github.com/o/r" 'https://x/$(id)' "https://x/a b" 'https://x/"; rm'; do
  reset '[]'
  rc=0
  report "$bad" || rc=$?
  [ "$rc" = 2 ] || fail "bad link '$bad': exit $rc"
  [ ! -f "$T/calls" ] || fail "bad link '$bad': gh was called"
done

echo "test_ci_report: ok"