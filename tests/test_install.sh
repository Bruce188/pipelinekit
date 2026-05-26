#!/usr/bin/env bash
# tests/test_install.sh — smoke harness for the modes-overlay feature.
# Validates:
#   (1) bash scripts/install.sh --selftest runs the 2 new modes-overlay cases
#       and they BOTH report PASS.
#   (2) The 5 claude/modes/<provider>.md files exist and are non-empty.
#   (3) claude/CLAUDE.md.template contains exactly one `@~/.claude/modes/active.md`
#       overlay reference line.
#
# Pre-existing selftest cases (notably _selftest_settings_env_block AC#6
# tripwire) may FAIL inside an active worktree because they detect any
# unstaged changes under claude/ — that is by design and is independent of
# the modes-overlay logic this harness exists to test. We grep for the
# specific PASS lines we wrote rather than rely on the overall exit code.
set -euo pipefail

PASS=0; FAIL=0
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }
ok()   { echo "PASS: $1"; PASS=$((PASS+1)); }

# ── (1) selftest emits both modes-overlay PASS lines ─────────────────────────

LOG=$(mktemp)
trap "rm -f $LOG" EXIT
# Note: || true — exit code may be non-zero due to unrelated tripwires when
# run inside an in-flight worktree. We assert on substring matches instead.
bash "$REPO_ROOT/scripts/install.sh" --selftest >"$LOG" 2>&1 || true

if grep -qE '^PASS: _selftest_modes_overlay_active_present$' "$LOG"; then
  ok "active-present case emitted PASS"
else
  fail "active-present case did NOT emit PASS — selftest output:"
  sed -n '/modes_overlay_active_present/,+2p' "$LOG" >&2
fi

if grep -qE '^PASS: _selftest_modes_overlay_active_absent$' "$LOG"; then
  ok "active-absent case emitted PASS"
else
  fail "active-absent case did NOT emit PASS — selftest output:"
  sed -n '/modes_overlay_active_absent/,+2p' "$LOG" >&2
fi

# ── (2) 5 mode files exist + non-empty ──────────────────────────────────────

for provider in azure vercel railway render digitalocean; do
  f="$REPO_ROOT/claude/modes/${provider}.md"
  if [[ -f "$f" && -s "$f" ]]; then
    ok "claude/modes/${provider}.md exists and non-empty"
  else
    fail "claude/modes/${provider}.md missing or empty"
  fi
done

# ── (3) overlay reference exactly once in template ──────────────────────────

template="$REPO_ROOT/claude/CLAUDE.md.template"
ref_count=$(grep -cF '@~/.claude/modes/active.md' "$template" || true)
if [[ "$ref_count" == "1" ]]; then
  ok "overlay reference present exactly once in CLAUDE.md.template"
else
  fail "overlay reference count = $ref_count (expected 1) in CLAUDE.md.template"
fi

# ── summary ─────────────────────────────────────────────────────────────────

echo
echo "Results: $PASS PASS / $FAIL FAIL"
exit "$FAIL"
