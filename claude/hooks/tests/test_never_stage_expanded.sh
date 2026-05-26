#!/usr/bin/env bash
# test_never_stage_expanded.sh -- coverage for the F10 secret-pattern expansion.
#
# Adds positive (block, exit 2) + negative (allow, exit 0) cases for each
# pattern family added by chore/never-stage-secret-expansion:
#
#   Env variants:           .env.*  .env.local  .env.production  .env.development
#   Crypto material:        *.pem  *.key  *.p12  *.pfx  *.cer  *.crt
#                           id_rsa*  id_ed25519*  id_dsa*  id_ecdsa*
#   Credential directories: .aws/  .ssh/  .gnupg/  .kube/config
#
# Sandboxes HOME via mktemp -d so the real ~/.claude/config is never touched.
# Trap-cleans on EXIT. Mirrors test_block_stage_sensitive.sh shape.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../block-stage-sensitive.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/pkit-never-stage-expanded-XXXXXX")
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
mkdir -p "$SANDBOX/home/.claude/config"
cp "$REPO_ROOT/claude/config/never-stage.txt" "$SANDBOX/home/.claude/config/never-stage.txt"

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

call_hook() {
  local cmd="$1"
  local payload
  payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input': {'command': sys.argv[1]}}))" "$cmd")
  # Wipe denial-log between calls so the 3-strike retry-limit advisory in
  # block-stage-sensitive.sh's pathguard / stage-sensitive gates does not
  # short-circuit the block→ask conversion mid-test-suite.
  rm -f "$SANDBOX/home/.claude/state/denial-log.jsonl" 2>/dev/null
  HOME="$SANDBOX/home" bash -c 'printf "%s" "$1" | bash "$2"' _ "$payload" "$HOOK"
}

# expect_block <name> <command>
expect_block() {
  local name="$1"; local cmd="$2"
  local exit_code=0
  local out
  out=$(call_hook "$cmd" 2>&1) || exit_code=$?
  if [ "$exit_code" -eq 2 ]; then
    pass "$name"
  else
    fail "$name" "expected exit 2 (blocked), got $exit_code; out=$out"
  fi
}

# expect_allow <name> <command>
expect_allow() {
  local name="$1"; local cmd="$2"
  local exit_code=0
  local out
  out=$(call_hook "$cmd" 2>&1) || exit_code=$?
  if [ "$exit_code" -eq 0 ]; then
    pass "$name"
  else
    fail "$name" "expected exit 0 (allowed), got $exit_code; out=$out"
  fi
}

# --- Env variants ----------------------------------------------------------
expect_block "env_local_blocked"        "git add .env.local"
expect_block "env_production_blocked"   "git add .env.production"
expect_block "env_development_blocked"  "git add .env.development"
expect_block "env_wildcard_blocked"     "git add .env.staging"
expect_allow "envrc_unrelated_allowed"  "git add .envrc.example.md"

# --- Crypto material -------------------------------------------------------
expect_block "pem_blocked"              "git add server.pem"
expect_block "key_blocked"              "git add private.key"
expect_block "p12_blocked"              "git add cert.p12"
expect_block "pfx_blocked"              "git add cert.pfx"
expect_block "cer_blocked"              "git add cert.cer"
expect_block "crt_blocked"              "git add server.crt"
expect_block "id_rsa_blocked"           "git add id_rsa"
expect_block "id_rsa_pub_blocked"       "git add id_rsa.pub"
expect_block "id_ed25519_blocked"       "git add id_ed25519"
expect_block "id_dsa_blocked"           "git add id_dsa"
expect_block "id_ecdsa_blocked"         "git add id_ecdsa"
expect_allow "pem_doc_allowed"          "git add docs-source/pem-notes.md"
expect_allow "key_alias_allowed"        "git add keymap.json"
expect_allow "id_other_allowed"         "git add identifier.txt"

# --- Credential directories ------------------------------------------------
expect_block "aws_dir_blocked"          "git add .aws/credentials"
expect_block "ssh_dir_blocked"          "git add .ssh/config"
expect_block "gnupg_dir_blocked"        "git add .gnupg/pubring.kbx"
expect_block "kube_config_blocked"      "git add .kube/config"
expect_allow "aws_lookalike_allowed"    "git add awsutils/README.md"
expect_allow "ssh_lookalike_allowed"    "git add ssh-helper/main.py"
expect_allow "kube_other_allowed"       "git add .kube/contexts.json"

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
