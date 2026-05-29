#!/usr/bin/env bash
# tests/test_install_fail_closed.sh — assert the three supply-chain fail-closed
# gates in scripts/install.sh + scripts/cloud/{oracle,hetzner}-bootstrap.sh.
#
# Each gate has two assertions:
#   (a) refuse path  — without the opt-out env var, the gate dies with a
#       refusal message naming both opt-out options.
#   (b) accept path  — with the opt-out env var set, the gate falls through
#       and does NOT die.
#
# We do NOT run the full installer (that would mutate $HOME). Instead we
# extract the conditional block from each script and replay it in a subshell
# with a stubbed `die`/`warn`/`log`.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_SH="$REPO_ROOT/scripts/install.sh"
ORACLE_SH="$REPO_ROOT/scripts/cloud/oracle-bootstrap.sh"
HETZNER_SH="$REPO_ROOT/scripts/cloud/hetzner-bootstrap.sh"

PASS=0; FAIL=0
ok()   { echo "PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

# Common stub functions injected into every gate replay.
# `die` exits non-zero so the gate's `die "..."` short-circuits cleanly; `log`
# and `warn` echo to stderr without touching disk.
STUBS=$(cat <<'STUB_EOF'
log()  { printf '[install] %s\n' "$*" >&2; }
warn() { printf '[install][warn] %s\n' "$*" >&2; }
die()  { printf '[install][error] %s\n' "$*" >&2; exit 1; }
STUB_EOF
)

# ── Helper: extract a fenced gate block from a source file.
# Uses fixed-string line matching (grep -F) to avoid regex-metacharacter issues
# with brackets and braces in shell conditionals.
# Usage: extract_block <file> <start-fixed-string> <end-fixed-string>
extract_block() {
  local f="$1" start_str="$2" end_str="$3"
  local start_ln end_ln
  start_ln=$(grep -Fn -- "$start_str" "$f" | head -1 | cut -d: -f1)
  if [[ -z "$start_ln" ]]; then return; fi
  # Find the first end_str at or after start_ln.
  end_ln=$(awk -v s="$start_ln" -v e="$end_str" '
    NR >= s && index($0, e) == 1 { print NR; exit }
  ' "$f")
  if [[ -z "$end_ln" ]]; then return; fi
  sed -n "${start_ln},${end_ln}p" "$f"
}

# ── Gate 1: serena rolling-ref refusal (scripts/install.sh) ───────────────

serena_block=$(extract_block "$INSTALL_SH" \
  '# Fail-closed supply-chain gate: refuse rolling' \
  'fi')

# AC-1: SERENA_REF=main without opt-out → exit non-zero, stderr names both opt-outs.
out1=$(SERENA_REF=main SERENA_ALLOW_ROLLING= bash -c "
$STUBS
$serena_block
" 2>&1)
rc1=$?
if [[ "$rc1" -ne 0 ]] \
   && echo "$out1" | grep -q "Refusing to install serena" \
   && echo "$out1" | grep -q "SERENA_REF=" \
   && echo "$out1" | grep -q "SERENA_ALLOW_ROLLING=1"; then
  ok "AC-1 serena refuse path (exit=$rc1, refusal stderr cites both opt-outs)"
else
  fail "AC-1 serena refuse path (exit=$rc1, output below)"
  echo "$out1" | sed 's/^/    /'
fi

# AC-2: SERENA_REF=main with SERENA_ALLOW_ROLLING=1 → exit 0 (no refusal).
out2=$(SERENA_REF=main SERENA_ALLOW_ROLLING=1 bash -c "
$STUBS
$serena_block
" 2>&1)
rc2=$?
if [[ "$rc2" -eq 0 ]] && ! echo "$out2" | grep -q "Refusing to install serena"; then
  ok "AC-2 serena opt-out path (exit=$rc2, no refusal stderr)"
else
  fail "AC-2 serena opt-out path (exit=$rc2, output below)"
  echo "$out2" | sed 's/^/    /'
fi

# ── Gate 3: Claude CLI sha256 mandatory (oracle-bootstrap.sh) ─────────────

claude_block=$(extract_block "$ORACLE_SH" \
  'if [ -z "${CLAUDE_CLI_SHA256:-}" ] && [ "${CLAUDE_CLI_ALLOW_UNVERIFIED:-0}" != "1" ]' \
  'fi')

# AC-3: CLAUDE_CLI_SHA256 empty + no opt-out → exit non-zero, stderr cites both opt-outs.
out3=$(CLAUDE_CLI_SHA256= CLAUDE_CLI_ALLOW_UNVERIFIED= bash -c "
$STUBS
$claude_block
" 2>&1)
rc3=$?
if [[ "$rc3" -ne 0 ]] \
   && echo "$out3" | grep -q "Refusing to install Claude CLI" \
   && echo "$out3" | grep -q "CLAUDE_CLI_SHA256=" \
   && echo "$out3" | grep -q "CLAUDE_CLI_ALLOW_UNVERIFIED=1"; then
  ok "AC-3 claude-cli refuse path (exit=$rc3, refusal stderr cites both opt-outs)"
else
  fail "AC-3 claude-cli refuse path (exit=$rc3, output below)"
  echo "$out3" | sed 's/^/    /'
fi

# AC-4: CLAUDE_CLI_SHA256 empty + CLAUDE_CLI_ALLOW_UNVERIFIED=1 → exit 0.
out4=$(CLAUDE_CLI_SHA256= CLAUDE_CLI_ALLOW_UNVERIFIED=1 bash -c "
$STUBS
$claude_block
" 2>&1)
rc4=$?
if [[ "$rc4" -eq 0 ]] && ! echo "$out4" | grep -q "Refusing to install Claude CLI"; then
  ok "AC-4 claude-cli opt-out path (exit=$rc4, no refusal stderr)"
else
  fail "AC-4 claude-cli opt-out path (exit=$rc4, output below)"
  echo "$out4" | sed 's/^/    /'
fi

# ── Gate 3 parity: hetzner-bootstrap.sh carries the same gate. ────────────

hetzner_block=$(extract_block "$HETZNER_SH" \
  'if [ -z "${CLAUDE_CLI_SHA256:-}" ] && [ "${CLAUDE_CLI_ALLOW_UNVERIFIED:-0}" != "1" ]' \
  'fi')

if [[ -n "$hetzner_block" ]] && echo "$hetzner_block" | grep -q "Refusing to install Claude CLI"; then
  ok "hetzner-bootstrap.sh contains the same Claude CLI fail-closed gate"
else
  fail "hetzner-bootstrap.sh missing the Claude CLI fail-closed gate"
fi

# ── Gate 2 surface check: Azure verify path present + sha256sum on .deb. ──
# (Gate 2 is opt-in — the default path is unchanged. We assert the verify
#  branch exists and calls sha256sum, plus that mismatch reaches `die`.)

if grep -q 'INSTALL_AZURE_CLI_DOWNLOAD_AND_VERIFY' "$INSTALL_SH" \
   && grep -q 'AZURE_CLI_DEB_SHA256' "$INSTALL_SH" \
   && grep -q 'sha256sum -c' "$INSTALL_SH" \
   && grep -q 'Azure CLI .deb sha256 mismatch' "$INSTALL_SH"; then
  ok "AC-5 azure-cli opt-in verify path wired (env vars + sha256sum + mismatch die)"
else
  fail "AC-5 azure-cli opt-in verify path incomplete"
fi

# ── Template surface check: serena pin present, placeholder gone from serena entry. ──
# (Note: <PIN-TO-COMMIT-SHA> may still appear in other entries — e.g. ios-simulator-mcp —
# which are out of scope for this feature.)

TEMPLATE="$REPO_ROOT/.mcp.json.template"
serena_entry=$(python3 -c "
import json
d = json.load(open('$TEMPLATE'))
print(' '.join(d['mcpServers']['serena']['args']))
")
if echo "$serena_entry" | grep -qF '9b292a6c8b03c8306f117efeabb0ea7afdb0b3c0' \
   && ! echo "$serena_entry" | grep -qF '<PIN-TO-COMMIT-SHA>'; then
  ok "AC-6 .mcp.json.template serena entry carries 40-char SHA + placeholder removed"
else
  fail "AC-6 .mcp.json.template serena entry SHA pin missing or placeholder still present"
  echo "    serena.args: $serena_entry"
fi

# ── AC-7: install.sh default SERENA_REF is a pinned SHA (NOT rolling 'main')
#    and matches the .mcp.json.template serena pin. This is the drift guard that
#    keeps `bash scripts/install.sh` from tripping its own fail-closed serena
#    gate (AC-1) on hosts that have uv installed — the default install must
#    complete, not die. See scripts/install.sh top-of-file SERENA_REF default.
install_default_ref=$(grep -oE 'SERENA_REF="\$\{SERENA_REF:-[0-9a-f]{40}\}"' "$INSTALL_SH" | grep -oE '[0-9a-f]{40}' | head -1)
template_ref=$(echo "$serena_entry" | grep -oE '[0-9a-f]{40}' | head -1)
if [[ -n "$install_default_ref" ]] && [[ "$install_default_ref" == "$template_ref" ]]; then
  ok "AC-7 install.sh default SERENA_REF pinned + matches .mcp.json.template ($install_default_ref)"
else
  fail "AC-7 install.sh default SERENA_REF drift (install='$install_default_ref' template='$template_ref')"
fi

# ── Summary ──────────────────────────────────────────────────────────────

echo
echo "Results: $PASS PASS / $FAIL FAIL"
exit $FAIL
