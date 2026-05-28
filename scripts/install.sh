#!/usr/bin/env bash
# pipelinekit installer.
# Idempotent. Re-run to update. Supports interactive and non-interactive modes.
#
# Env:
#   CLAUDE_HOME                 Target overlay dir (default: $HOME/.claude)
#   CLAUDE_INSTALL_NONINTERACTIVE=1   Skip all prompts; assume sane defaults
#   CLAUDE_INSTALL_OPTIONALS    deprecated; flag is a no-op (kept for backward-compat). All components are installed by default.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
PIPELINEKIT_VERSION="$( [[ -f "$REPO_ROOT/VERSION" ]] && cat "$REPO_ROOT/VERSION" || echo unknown )"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
if [[ "$CLAUDE_HOME" == *'${containerEnv:HOME}'* ]]; then
  CLAUDE_HOME="${CLAUDE_HOME//\$\{containerEnv:HOME\}/$HOME}"
fi
TS="$(date +%Y%m%d-%H%M%S)"
LOG="${CLAUDE_INSTALL_LOG:-$HOME/.cache/pipelinekit-install.log}"
mkdir -p "$(dirname "$LOG")"

# Supply-chain refs. Override via env vars before running install.
# Default = `main` (rolling); CI/prod use should pin to a commit SHA.
SERENA_REF="${SERENA_REF:-main}"
# Override UNDERSTAND_ANYTHING_SHA=<commit-sha> to pin to a specific commit.
UNDERSTAND_ANYTHING_SHA="${UNDERSTAND_ANYTHING_SHA:-470cc01dc5f9236a93eb704afdd479cd5db79710}"
# CLAUDE_CLI_SHA256 — sha256 of the Claude CLI installer at https://claude.ai/install.sh.
# Pin to a known-good value for reproducible installs; consult Anthropic release notes
# (https://docs.claude.com/en/release-notes/claude-code) for the current installer
# checksum. Cloud-bootstrap scripts (scripts/cloud/oracle-bootstrap.sh and
# scripts/cloud/hetzner-bootstrap.sh) refuse to install the Claude CLI when this is
# empty unless CLAUDE_CLI_ALLOW_UNVERIFIED=1 is set. See docs-source/supply-chain.md.
CLAUDE_CLI_SHA256="${CLAUDE_CLI_SHA256:-}"
readonly GRAPHIFY_VERSION="0.8.18"
LSP_FAILURES=0

log()  { printf '[install] %s\n' "$*" | tee -a "$LOG"; }
warn() { printf '[install][warn] %s\n' "$*" | tee -a "$LOG" >&2; }
die()  { printf '[install][error] %s\n' "$*" | tee -a "$LOG" >&2; exit 1; }

# ---------- selftest harness ----------
_selftest_main() {
  local pass=0 fail=0
  # Enumerate _selftest_* functions; skip _selftest_main itself.
  local fn
  while IFS= read -r fn; do
    [[ "$fn" == "_selftest_main" ]] && continue
    if ( "$fn" ); then
      pass=$((pass+1))
      echo "  [PASS] $fn"
    else
      fail=$((fail+1))
      echo "  [FAIL] $fn"
    fi
  done < <(declare -F | awk '/_selftest_[a-z_]+$/ {print $NF}')
  echo "Results: $pass PASS / $fail FAIL"
  return "$fail"
}

_selftest_smoke_harness() {
  # Placeholder: proves the harness fires at least one case.
  return 0
}

_selftest_agentmemory_mcp_provisioned() {
  local sandbox
  sandbox=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-XXXX") || return 1
  # shellcheck disable=SC2064
  trap "rm -rf '$sandbox'" RETURN
  local saved_home="${CLAUDE_HOME:-}"
  export CLAUDE_HOME="$sandbox/.claude"
  mkdir -p "$CLAUDE_HOME"

  # AC #2 canary: synthesize a settings.json and sha256 it.
  cat > "$CLAUDE_HOME/settings.json" <<'JSON'
{ "_canary": "agentmemory-must-not-touch-this" }
JSON
  local sha_before
  sha_before=$(python3 -c "import hashlib;print(hashlib.sha256(open('$CLAUDE_HOME/settings.json','rb').read()).hexdigest())")

  # AC #1: VOYAGE_API_KEY set → voyage provider, npx command, pinned version arg.
  ( VOYAGE_API_KEY=test_voyage OPENAI_API_KEY="" provision_agentmemory_mcp >/dev/null 2>&1 )
  python3 -c "
import json,sys
d=json.load(open('$CLAUDE_HOME/.mcp.json'))
assert 'agentmemory' in d['mcpServers'], 'AC-1 missing agentmemory key'
e=d['mcpServers']['agentmemory']
assert e['command']=='npx', 'AC-1 command not npx'
assert any('@agentmemory/agentmemory@0.9.21' in a for a in e['args']), 'AC-1 pin missing'
assert e['env']['AGENTMEMORY_EMBED_PROVIDER']=='voyage', 'AC-1 provider not voyage'
" || { echo "AC-1 FAIL"; return 1; }

  # AC #5: no API keys → local-onnx-quant + stderr contains Voyage.
  rm -f "$CLAUDE_HOME/.mcp.json"
  local ac5_stderr
  ac5_stderr=$( VOYAGE_API_KEY="" OPENAI_API_KEY="" provision_agentmemory_mcp 2>&1 >/dev/null )
  python3 -c "
import json
d=json.load(open('$CLAUDE_HOME/.mcp.json'))
assert d['mcpServers']['agentmemory']['env']['AGENTMEMORY_EMBED_PROVIDER']=='local-onnx-quant', 'AC-5 provider'
" || { echo "AC-5 FAIL provider"; return 1; }
  printf '%s\n' "$ac5_stderr" | grep -qi "voyage" || { echo "AC-5 FAIL Voyage warning missing"; return 1; }

  # AC #2: settings.json byte-identical (sha256 unchanged after provisioning).
  local sha_after
  sha_after=$(python3 -c "import hashlib;print(hashlib.sha256(open('$CLAUDE_HOME/settings.json','rb').read()).hexdigest())")
  [[ "$sha_before" == "$sha_after" ]] || { echo "AC-2 FAIL settings.json mutated"; return 1; }

  # AC #3: WSL2 + 2 GB mock → gate refuses (non-zero exit + stderr mentions WSL2 + 4 GB).
  local gate_stderr
  gate_stderr=$( { __pkit_mock_wsl_2gb=1 _wsl2_ram_gate 2>&1; echo "exit=$?"; } 2>&1 )
  printf '%s\n' "$gate_stderr" | grep -q "exit=1" || { echo "AC-3 FAIL gate accepted 2 GB"; return 1; }
  printf '%s\n' "$gate_stderr" | grep -q "WSL2" || { echo "AC-3 FAIL stderr missing WSL2"; return 1; }
  printf '%s\n' "$gate_stderr" | grep -q "4 GB" || { echo "AC-3 FAIL stderr missing 4 GB"; return 1; }

  # AC #4: same mock + PIPELINE_FORCE_INSTALL=1 → gate accepts.
  ( __pkit_mock_wsl_2gb=1 PIPELINE_FORCE_INSTALL=1 _wsl2_ram_gate ) 2>/dev/null \
    || { echo "AC-4 FAIL override rejected"; return 1; }

  # Restore env.
  [[ -n "$saved_home" ]] && export CLAUDE_HOME="$saved_home" || unset CLAUDE_HOME
  return 0
}

_selftest_codegraph_mcp_provisioned() {
  # AC #1: .mcp.json contains codegraph entry with correct pin + args.
  # AC #4: settings.json sha256 byte-identity (provision_codegraph_mcp must NOT touch settings.json).
  # AC #4: pgrep pre/post snapshot equality (no daemon spawned).
  # AC #3: never-stage.txt contains `.codegraph/`.
  # AC #2: codegraph-init SKILL.md exists with correct frontmatter.
  # AC #6: CLAUDE.md.template contains codegraph bullet + /codegraph-init reference.
  # Cross-MCP no-collision canary: agentmemory + understand-anything keys still present after codegraph write.
  # NEW: user-scope ~/.claude.json (${HOME}/.claude.json) contains codegraph entry with correct shape.
  local sandbox
  sandbox=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$sandbox'" RETURN
  local saved_home="${CLAUDE_HOME:-}"
  export CLAUDE_HOME="$sandbox/.claude"
  mkdir -p "$CLAUDE_HOME"
  # HOME sandbox: saves operator's real $HOME; user-scope write lands in sandbox.
  local saved_real_home="${HOME}"
  export HOME="$sandbox"

  # Synthesize known settings.json to detect any mutation.
  printf '{"hooks":{}}\n' > "$CLAUDE_HOME/settings.json"
  local sha_before
  sha_before=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')

  # Synthesize .mcp.json with existing sibling keys (agentmemory + understand-anything canary).
  python3 -c "
import json
d = {
  'mcpServers': {
    'agentmemory': {'type': 'stdio', 'command': 'npx', 'args': []},
    'understand-anything': {'type': 'stdio', 'command': 'npx', 'args': []}
  }
}
with open('$CLAUDE_HOME/.mcp.json', 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')
"

  # Pgrep snapshot before invocation.
  local pgrep_before
  pgrep_before=$(pgrep -f "codegraph serve" 2>/dev/null | wc -l)

  # Invoke the function under test.
  provision_codegraph_mcp

  # Pgrep snapshot after invocation.
  local pgrep_after
  pgrep_after=$(pgrep -f "codegraph serve" 2>/dev/null | wc -l)

  # Helper: restore both HOME and CLAUDE_HOME on every early-return path.
  _cg_restore() {
    export HOME="$saved_real_home"
    [[ -n "$saved_home" ]] && export CLAUDE_HOME="$saved_home" || unset CLAUDE_HOME
  }

  # Assertion 1: .mcp.json exists and has correct codegraph entry shape.
  if ! python3 -c "
import json, sys
try:
    d = json.load(open('$CLAUDE_HOME/.mcp.json'))
    assert d['mcpServers']['codegraph']['command'] == 'npx', 'command mismatch'
    assert '@colbymchenry/codegraph@^0.9.4' in d['mcpServers']['codegraph']['args'], 'pin missing'
    assert 'serve' in d['mcpServers']['codegraph']['args'], 'serve missing'
    assert '--mcp' in d['mcpServers']['codegraph']['args'], '--mcp missing'
except Exception as e:
    sys.exit(f'AC#1 JSON shape FAIL: {e}')
" 2>&1; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — AC#1 JSON shape"
    _cg_restore; return 1
  fi

  # Assertion 2: caret-pin regex matches literal @^0.9.x.
  if ! python3 -c "
import json, re, sys
d = json.load(open('$CLAUDE_HOME/.mcp.json'))
args = d['mcpServers']['codegraph']['args']
pin_args = [a for a in args if re.search(r'@\^0\.9\.\d+', a)]
if not pin_args:
    sys.exit('AC#1 pin regex FAIL: no arg matches @^0.9.x')
" 2>&1; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — AC#1 pin regex"
    _cg_restore; return 1
  fi

  # Assertion 3: settings.json sha256 unchanged (provision_codegraph_mcp must not touch it).
  local sha_after
  sha_after=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')
  if [[ "$sha_before" != "$sha_after" ]]; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — AC#4 settings.json sha256 changed"
    _cg_restore; return 1
  fi

  # Assertion 4: pgrep snapshot unchanged (no daemon spawned).
  if [[ "$pgrep_after" -ne "$pgrep_before" ]]; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — AC#4 codegraph serve daemon count changed"
    _cg_restore; return 1
  fi

  # Assertion 5: never-stage.txt contains .codegraph/.
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if ! grep -q '^\.codegraph/$' "$script_dir/../claude/config/never-stage.txt" 2>/dev/null; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — AC#3 .codegraph/ missing from never-stage.txt"
    _cg_restore; return 1
  fi

  # Assertion 6: codegraph-init SKILL.md exists with correct frontmatter.
  local skill_path="$script_dir/../claude/skills/codegraph-init/SKILL.md"
  if ! [[ -f "$skill_path" ]] \
      || ! grep -qE "^name: codegraph-init$" "$skill_path" \
      || ! grep -qE "^[[:space:]]+-[[:space:]]Bash$" "$skill_path"; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — AC#2 SKILL.md missing or frontmatter incomplete"
    _cg_restore; return 1
  fi

  # Assertion 7: CLAUDE.md.template has codegraph bullet + /codegraph-init reference.
  local template_path="$script_dir/../claude/CLAUDE.md.template"
  if ! grep -q "codegraph" "$template_path" 2>/dev/null \
      || ! grep -q "/codegraph-init" "$template_path" 2>/dev/null; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — AC#6 CLAUDE.md.template missing codegraph/codegraph-init"
    _cg_restore; return 1
  fi

  # Assertion 8: Cross-MCP no-collision canary — agentmemory + understand-anything keys still present.
  if ! python3 -c "
import json, sys
d = json.load(open('$CLAUDE_HOME/.mcp.json'))
missing = [k for k in ('agentmemory', 'understand-anything') if k not in d.get('mcpServers', {})]
if missing:
    sys.exit(f'AC canary FAIL: sibling keys removed: {missing}')
" 2>&1; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — cross-MCP no-collision canary"
    _cg_restore; return 1
  fi

  # Assertion 9 (NEW): user-scope ${HOME}/.claude.json has codegraph entry with correct shape.
  # HOME was redirected to $sandbox, so this reads $sandbox/.claude.json.
  local user_scope_json="${HOME}/.claude.json"
  if ! python3 -c "
import json, sys
try:
    d = json.load(open('$user_scope_json'))
    entry = d['mcpServers']['codegraph']
    assert entry['command'] == 'npx', f'user-scope command mismatch: {entry[\"command\"]!r}'
    args = entry['args']
    assert '@colbymchenry/codegraph@^0.9.4' in args, 'user-scope pin missing'
    assert 'serve' in args, 'user-scope serve missing'
    assert '--mcp' in args, 'user-scope --mcp missing'
except Exception as e:
    sys.exit(f'user-scope AC#9 FAIL: {e}')
" 2>&1; then
    echo "FAIL: _selftest_codegraph_mcp_provisioned — user-scope ~/.claude.json shape"
    _cg_restore; return 1
  fi

  _cg_restore
  echo "PASS: _selftest_codegraph_mcp_provisioned"
  return 0
}

_selftest_graphify_mcp_provisioned() {
  # AC #1: .mcp.json contains graphify entry with correct args (SB-2/SB-3 enforcement).
  # AC #2: settings.json sha256 byte-identity (provision_graphify_mcp must NOT touch settings.json).
  # AC #3: no bracket-syntax extras in args or provision_graphify_mcp source body.
  # AC #4: never-stage.txt contains `.graphify/`.
  # AC #5: graphify-init SKILL.md exists with correct frontmatter.
  # AC #6: no daemon process spawned (pgrep snapshot equality).
  # AC #7: CLAUDE.md.template has graphify bullet + /graphify-init reference.
  # Cross-MCP no-collision canary: agentmemory + codegraph keys still present after graphify write.
  # NEW: user-scope ${HOME}/.claude.json contains graphify entry with correct shape.
  local sandbox
  sandbox=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$sandbox'" RETURN
  local saved_home="${CLAUDE_HOME:-}"
  export CLAUDE_HOME="$sandbox/.claude"
  mkdir -p "$CLAUDE_HOME"
  # HOME sandbox: saves operator's real $HOME; user-scope write lands in sandbox.
  local saved_real_home="${HOME}"
  export HOME="$sandbox"

  # Synthesize known settings.json to detect any mutation.
  printf '{"hooks":{}}\n' > "$CLAUDE_HOME/settings.json"
  local sha_before
  sha_before=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')

  # Synthesize .mcp.json with existing sibling keys (agentmemory + codegraph canary).
  python3 -c "
import json
d = {
  'mcpServers': {
    'agentmemory': {'type': 'stdio', 'command': 'npx', 'args': []},
    'codegraph': {'type': 'stdio', 'command': 'npx', 'args': []}
  }
}
with open('$CLAUDE_HOME/.mcp.json', 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')
"

  # Helper: restore both HOME and CLAUDE_HOME on every early-return path.
  _gy_restore() {
    export HOME="$saved_real_home"
    [[ -n "$saved_home" ]] && export CLAUDE_HOME="$saved_home" || unset CLAUDE_HOME
  }

  # Pgrep snapshot before invocation.
  local pgrep_before
  pgrep_before=$(pgrep -f "graphify.*--mcp" 2>/dev/null | wc -l)

  # Invoke the function under test (mock mode — skip uv tool install).
  __pkit_mock_graphify_install_skip=1 provision_graphify_mcp

  # Pgrep snapshot after invocation.
  local pgrep_after
  pgrep_after=$(pgrep -f "graphify.*--mcp" 2>/dev/null | wc -l)

  # Assertion 1: .mcp.json exists and has correct graphify entry shape (AC #1 / SB-2 / SB-3).
  if ! python3 -c "
import json, sys
try:
    d = json.load(open('$CLAUDE_HOME/.mcp.json'))
    entry = d['mcpServers']['graphify']
    assert entry['command'] == 'uv', 'command mismatch: expected uv'
    args = entry['args']
    assert 'tool' in args, 'tool missing from args'
    assert 'run' in args, 'run missing from args'
    assert '--from' in args, '--from missing from args'
    assert 'graphifyy' in args, 'graphifyy missing from args'
    assert 'graphify' in args, 'graphify missing from args'
    assert '--mcp' in args, '--mcp missing from args'
    assert '.' in args, '. missing from args'
    assert 'serve' not in args, 'serve in args (SB-2 violation)'
    assert not any('[' in a for a in args), 'bracket-syntax leak in args'
except Exception as e:
    sys.exit(f'AC#1 JSON shape FAIL: {e}')
" 2>&1; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — AC#1 JSON shape"
    _gy_restore; return 1
  fi

  # Assertion 2: pin regex — install.sh body contains graphifyy==0.8.18.
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local install_sh="$script_dir/install.sh"
  if ! python3 -c "
import re, sys
body = open('$install_sh').read()
if not re.search(r'graphifyy==0\\.8\\.18', body):
    sys.exit('AC#1 pin regex FAIL: graphifyy==0.8.18 not found in install.sh')
" 2>&1; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — AC#1 pin regex"
    _gy_restore; return 1
  fi

  # Assertion 3: settings.json sha256 unchanged (provision_graphify_mcp must not touch it).
  local sha_after
  sha_after=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')
  if [[ "$sha_before" != "$sha_after" ]]; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — AC#2 settings.json sha256 changed"
    _gy_restore; return 1
  fi

  # Assertion 4: no bracket-syntax extras in install.sh source (AC #3).
  if grep -qE 'graphifyy\[' "$install_sh" 2>/dev/null; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — AC#3 bracket-syntax leak in install.sh"
    _gy_restore; return 1
  fi

  # Assertion 5: pgrep snapshot unchanged — no daemon spawned (AC #6).
  if [[ "$pgrep_after" -ne "$pgrep_before" ]]; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — AC#6 graphify daemon count changed"
    _gy_restore; return 1
  fi

  # Assertion 6: never-stage.txt contains .graphify/ (AC #4).
  if ! grep -q '^\.graphify/$' "$script_dir/../claude/config/never-stage.txt" 2>/dev/null; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — AC#4 .graphify/ missing from never-stage.txt"
    _gy_restore; return 1
  fi

  # Assertion 7: graphify-init SKILL.md exists with correct frontmatter (AC #5).
  local skill_path="$script_dir/../claude/skills/graphify-init/SKILL.md"
  if ! [[ -f "$skill_path" ]] \
      || ! grep -qE "^name: graphify-init$" "$skill_path" \
      || ! grep -qE "^disable-model-invocation: true$" "$skill_path" \
      || ! grep -qE "^## Step 1: Pre-flight" "$skill_path" \
      || ! grep -qE "^[[:space:]]+-[[:space:]]Bash$" "$skill_path"; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — AC#5 SKILL.md missing or frontmatter incomplete"
    _gy_restore; return 1
  fi

  # Assertion 8: CLAUDE.md.template has graphify bullet + /graphify-init reference (AC #7).
  local template_path="$script_dir/../claude/CLAUDE.md.template"
  if ! grep -q "graphify" "$template_path" 2>/dev/null \
      || ! grep -q "/graphify-init" "$template_path" 2>/dev/null; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — AC#7 CLAUDE.md.template missing graphify/graphify-init"
    _gy_restore; return 1
  fi

  # Assertion 9: Cross-MCP no-collision canary — agentmemory + codegraph keys still present.
  if ! python3 -c "
import json, sys
d = json.load(open('$CLAUDE_HOME/.mcp.json'))
missing = [k for k in ('agentmemory', 'codegraph') if k not in d.get('mcpServers', {})]
if missing:
    sys.exit(f'AC canary FAIL: sibling keys removed: {missing}')
" 2>&1; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — cross-MCP no-collision canary"
    _gy_restore; return 1
  fi

  # Assertion 10 (NEW): user-scope ${HOME}/.claude.json has graphify entry with correct shape.
  # HOME was redirected to $sandbox, so this reads $sandbox/.claude.json.
  local user_scope_json="${HOME}/.claude.json"
  if ! python3 -c "
import json, sys
try:
    d = json.load(open('$user_scope_json'))
    entry = d['mcpServers']['graphify']
    assert entry['command'] == 'uv', f'user-scope command mismatch: {entry[\"command\"]!r}'
    args = entry['args']
    assert 'tool' in args, 'user-scope tool missing'
    assert 'run' in args, 'user-scope run missing'
    assert '--from' in args, 'user-scope --from missing'
    assert 'graphifyy' in args, 'user-scope graphifyy missing'
    assert 'graphify' in args, 'user-scope graphify missing'
    assert '.' in args, 'user-scope . missing'
    assert '--mcp' in args, 'user-scope --mcp missing'
    assert 'serve' not in args, 'user-scope serve present (SB-2 violation)'
    assert not any('[' in a for a in args), 'user-scope bracket-syntax leak'
except Exception as e:
    sys.exit(f'user-scope AC#10 FAIL: {e}')
" 2>&1; then
    echo "FAIL: _selftest_graphify_mcp_provisioned — user-scope ~/.claude.json shape"
    _gy_restore; return 1
  fi

  _gy_restore
  echo "PASS: _selftest_graphify_mcp_provisioned"
  return 0
}

_selftest_serena_mcp_provisioned() {
  # Asserts the new provision_serena_mcp user-scope write.
  # Gate hermeticity: uses __pkit_mock_serena_gate_skip=1 to bypass the uvx
  # availability check (approach (b) from plan Task 1.3 — preferred for determinism).
  # Sandboxes both HOME and CLAUDE_HOME so the operator's real ~/.claude.json is never touched.
  local sandbox
  sandbox=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$sandbox'" RETURN

  # Sandbox both CLAUDE_HOME and HOME.
  local saved_ch="${CLAUDE_HOME:-}"
  export CLAUDE_HOME="$sandbox/.claude"
  mkdir -p "$CLAUDE_HOME"
  local saved_real_home="${HOME}"
  export HOME="$sandbox"

  # Helper: restore both env vars on every early-return path.
  _se_restore() {
    export HOME="$saved_real_home"
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
  }

  # settings.json canary: create known contents and sha before invocation.
  printf '{"hooks":{}}\n' > "$CLAUDE_HOME/settings.json"
  local sha_before
  sha_before=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')

  # Invoke the function under test (mock mode — bypass uvx gate for determinism).
  __pkit_mock_serena_gate_skip=1 provision_serena_mcp >/dev/null 2>&1

  # Assertion 1: user-scope ${HOME}/.claude.json has correct serena entry shape.
  local user_scope_json="${HOME}/.claude.json"
  if ! python3 -c "
import json, sys
try:
    d = json.load(open('$user_scope_json'))
    entry = d['mcpServers']['serena']
    assert entry['command'] == 'serena', f'command mismatch: {entry[\"command\"]!r}'
    args = entry['args']
    assert args == ['start-mcp-server', '--context', 'claude-code', '--project-from-cwd'], \
        f'args mismatch: {args!r}'
except Exception as e:
    sys.exit(f'AC#1 serena user-scope FAIL: {e}')
" 2>&1; then
    echo "FAIL: _selftest_serena_mcp_provisioned — user-scope ~/.claude.json shape"
    _se_restore; return 1
  fi

  # Assertion 2: settings.json sha256 byte-identity (provision_serena_mcp must NOT touch settings.json).
  local sha_after
  sha_after=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')
  if [[ "$sha_before" != "$sha_after" ]]; then
    echo "FAIL: _selftest_serena_mcp_provisioned — settings.json sha256 changed"
    _se_restore; return 1
  fi

  _se_restore
  echo "PASS: _selftest_serena_mcp_provisioned"
  return 0
}

_selftest_understand_anything_provisioned() {
  # AC #1: marketplace-path mock — function logs invocation but does NOT execute live CLI.
  # AC #2: settings.json sha256 byte-identity before/after invocation.
  # AC #4: never-stage.txt contains `.understand-anything/`.
  # AC #5: clone-failure mock — function emits warn + exits 0 (non-fatal).
  local tmp; tmp=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN
  export CLAUDE_HOME="$tmp/.claude"
  mkdir -p "$CLAUDE_HOME"
  # Synthesize a known settings.json to detect any mutation.
  printf '{"hooks":{}}\n' > "$CLAUDE_HOME/settings.json"
  local pre_sha; pre_sha=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')

  # AC #1 marketplace mock — should not invoke live CLI.
  local m_out
  m_out=$( __pkit_mock_understand_anything_marketplace=1 provision_understand_anything 2>&1 )
  echo "$m_out" | grep -q "would invoke: claude plugin marketplace add Lum1104/Understand-Anything" \
    || { echo "FAIL: marketplace mock did not emit expected log line"; return 1; }

  # AC #5 clone-fail mock — should warn + return 0 (non-fatal).
  __pkit_mock_understand_anything_clone_fail=1 provision_understand_anything >/dev/null 2>&1
  local clone_rc=$?
  [[ $clone_rc -eq 0 ]] \
    || { echo "FAIL: clone-fail mock did not return 0 (got $clone_rc)"; return 1; }

  # AC #2 settings.json byte-identity after invocation.
  local post_sha; post_sha=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')
  [[ "$pre_sha" == "$post_sha" ]] \
    || { echo "FAIL: settings.json sha256 changed (pre=$pre_sha post=$post_sha)"; return 1; }

  # AC #4 never-stage.txt contains the new pattern (resolve relative to repo root).
  local NEVERSTAGE; NEVERSTAGE="$(dirname "${BASH_SOURCE[0]}")/../claude/config/never-stage.txt"
  grep -q '^\.understand-anything/$' "$NEVERSTAGE" \
    || { echo "FAIL: .understand-anything/ not found in $NEVERSTAGE"; return 1; }

  echo "PASS: _selftest_understand_anything_provisioned"
  return 0
}

_selftest_understand_anything_reconcile() {
  # Hermetic: NO live `claude` CLI, NO network. Directly exercises
  # _reconcile_understand_anything_enable() against a sandboxed CLAUDE_HOME.
  #
  # Case 1 (dangling, no cache): settings.json has enabledPlugins entry,
  #   cache dir absent → entry must be stripped; extraKnownMarketplaces + hooks intact.
  # Case 2 (cached): same settings.json but cache dir exists → entry preserved.
  # Case 3 (no settings.json): no file, no cache → reconcile exits 0, no error.

  local saved_ch="${CLAUDE_HOME:-}"

  # ----- Case 1 -----
  local sb1
  sb1=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-ua-reconcile-XXXX") || return 1
  export CLAUDE_HOME="$sb1"
  mkdir -p "$CLAUDE_HOME"
  printf '{"enabledPlugins":{"understand-anything@understand-anything":true},"extraKnownMarketplaces":["understand-anything"],"hooks":{}}\n' \
    > "$CLAUDE_HOME/settings.json"
  # No cache dir — reconcile should strip the enabledPlugins key.
  _reconcile_understand_anything_enable 2>/dev/null
  # Assert: understand-anything@understand-anything key gone.
  python3 - "$CLAUDE_HOME/settings.json" <<'PYCHECK1' || {
import json, sys
p = sys.argv[1]
d = json.load(open(p))
ep = d.get("enabledPlugins", {})
assert "understand-anything@understand-anything" not in ep, \
  f"Case 1: dangling key still present in enabledPlugins: {ep}"
# extraKnownMarketplaces must be intact.
mkts = d.get("extraKnownMarketplaces", [])
assert "understand-anything" in mkts, \
  f"Case 1: extraKnownMarketplaces lost understand-anything: {mkts}"
# hooks must be intact.
assert "hooks" in d, "Case 1: hooks key lost"
# Must still be valid JSON (implicitly proved by load above).
PYCHECK1
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb1"
    echo "FAIL: _selftest_understand_anything_reconcile — Case 1 assertion"
    return 1
  }
  rm -rf "$sb1"

  # ----- Case 2 -----
  local sb2
  sb2=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-ua-reconcile-XXXX") || return 1
  export CLAUDE_HOME="$sb2"
  mkdir -p "$CLAUDE_HOME"
  printf '{"enabledPlugins":{"understand-anything@understand-anything":true},"extraKnownMarketplaces":["understand-anything"],"hooks":{}}\n' \
    > "$CLAUDE_HOME/settings.json"
  # Create cache dir — reconcile should preserve the enabledPlugins key.
  mkdir -p "$CLAUDE_HOME/plugins/cache/understand-anything/understand-anything/2.7.5"
  _reconcile_understand_anything_enable 2>/dev/null
  # Assert: understand-anything@understand-anything key preserved.
  python3 - "$CLAUDE_HOME/settings.json" <<'PYCHECK2' || {
import json, sys
p = sys.argv[1]
d = json.load(open(p))
ep = d.get("enabledPlugins", {})
assert "understand-anything@understand-anything" in ep, \
  f"Case 2: enabledPlugins key was stripped even though cache dir exists: {ep}"
PYCHECK2
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb2"
    echo "FAIL: _selftest_understand_anything_reconcile — Case 2 assertion"
    return 1
  }
  rm -rf "$sb2"

  # ----- Case 3 -----
  local sb3
  sb3=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-ua-reconcile-XXXX") || return 1
  export CLAUDE_HOME="$sb3"
  mkdir -p "$CLAUDE_HOME"
  # No settings.json, no cache dir — reconcile must exit 0 without errors.
  _reconcile_understand_anything_enable 2>/dev/null
  local rc3=$?
  [[ $rc3 -eq 0 ]] || {
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb3"
    echo "FAIL: _selftest_understand_anything_reconcile — Case 3 non-zero exit ($rc3)"
    return 1
  }
  rm -rf "$sb3"

  # Restore CLAUDE_HOME.
  [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME

  echo "PASS: _selftest_understand_anything_reconcile"
  return 0
}

_selftest_settings_env_block() {
  # Per docs/analysis-v101.md § R1. 5 cases (A, B, C, D, E) — assert additive-merge invariants (env + top-level keys).
  local tmp; tmp=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  ## --- Case A: empty sandbox → both keys appear with defaults ---
  export CLAUDE_HOME="$tmp/case_a/.claude"
  mkdir -p "$CLAUDE_HOME"
  CLAUDE_INSTALL_SETTINGS=1 maybe_install_settings "" >/dev/null 2>&1 \
    || { echo "FAIL: Case A maybe_install_settings exit non-zero"; return 1; }
  python3 -c "
import json, sys
d = json.load(open('$CLAUDE_HOME/settings.json'))
e = d.get('env', {})
assert e.get('CLAUDE_CODE_DISABLE_1M_CONTEXT') == '1', f'Case A: DISABLE_1M_CONTEXT = {e.get(\"CLAUDE_CODE_DISABLE_1M_CONTEXT\")!r}'
assert 'hooks' in d, 'Case A: hooks key missing'
" || { echo "FAIL: Case A assertions"; return 1; }

  ## --- Case B: pre-existing CUSTOM_VAR survives, new keys added ---
  local case_b_home="$tmp/case_b/.claude"
  local case_b_backup="$tmp/case_b/backup"
  mkdir -p "$case_b_home" "$case_b_backup"
  cat > "$case_b_backup/settings.json" <<'JSON'
{"env": {"CUSTOM_VAR": "foo"}, "hooks": {}}
JSON
  export CLAUDE_HOME="$case_b_home"
  CLAUDE_INSTALL_SETTINGS=1 maybe_install_settings "$case_b_backup" >/dev/null 2>&1 \
    || { echo "FAIL: Case B maybe_install_settings exit non-zero"; return 1; }
  python3 -c "
import json
d = json.load(open('$case_b_home/settings.json'))
e = d.get('env', {})
assert e.get('CUSTOM_VAR') == 'foo', f'Case B: CUSTOM_VAR clobbered → {e.get(\"CUSTOM_VAR\")!r}'
assert e.get('CLAUDE_CODE_DISABLE_1M_CONTEXT') == '1', 'Case B: new DISABLE_1M_CONTEXT missing'
" || { echo "FAIL: Case B assertions"; return 1; }

  ## --- Case C: pre-existing DISABLE_1M_CONTEXT=0 survives (user wins) ---
  local case_c_home="$tmp/case_c/.claude"
  local case_c_backup="$tmp/case_c/backup"
  mkdir -p "$case_c_home" "$case_c_backup"
  cat > "$case_c_backup/settings.json" <<'JSON'
{"env": {"CLAUDE_CODE_DISABLE_1M_CONTEXT": "0"}}
JSON
  export CLAUDE_HOME="$case_c_home"
  CLAUDE_INSTALL_SETTINGS=1 maybe_install_settings "$case_c_backup" >/dev/null 2>&1 \
    || { echo "FAIL: Case C maybe_install_settings exit non-zero"; return 1; }
  python3 -c "
import json
d = json.load(open('$case_c_home/settings.json'))
e = d.get('env', {})
assert e.get('CLAUDE_CODE_DISABLE_1M_CONTEXT') == '0', f'Case C: user value clobbered → {e.get(\"CLAUDE_CODE_DISABLE_1M_CONTEXT\")!r}'
" || { echo "FAIL: Case C assertions"; return 1; }

  ## --- Case D: malformed prior JSON → swallow + start fresh (no crash) ---
  local case_d_home="$tmp/case_d/.claude"
  local case_d_backup="$tmp/case_d/backup"
  mkdir -p "$case_d_home" "$case_d_backup"
  printf '{' > "$case_d_backup/settings.json"   # syntactically invalid
  export CLAUDE_HOME="$case_d_home"
  CLAUDE_INSTALL_SETTINGS=1 maybe_install_settings "$case_d_backup" >/dev/null 2>&1 \
    || { echo "FAIL: Case D maybe_install_settings exit non-zero (should swallow + continue)"; return 1; }
  python3 -c "
import json
d = json.load(open('$case_d_home/settings.json'))
e = d.get('env', {})
assert e.get('CLAUDE_CODE_DISABLE_1M_CONTEXT') == '1', 'Case D: defaults missing after malformed prior'
" || { echo "FAIL: Case D assertions"; return 1; }

  ## --- Case E: prior settings.json has many top-level keys → ALL preserved + new env defaults added ---
  local case_e_home="$tmp/case_e/.claude"
  local case_e_backup="$tmp/case_e/backup"
  mkdir -p "$case_e_home" "$case_e_backup"
  cat > "$case_e_backup/settings.json" <<'JSON'
{
  "model": "opus",
  "enabledPlugins": {"foo": "bar"},
  "extraKnownMarketplaces": {"baz": {}},
  "env": {"CUSTOM_VAR": "x"},
  "hooks": {}
}
JSON
  export CLAUDE_HOME="$case_e_home"
  CLAUDE_INSTALL_SETTINGS=1 maybe_install_settings "$case_e_backup" >/dev/null 2>&1 \
    || { echo "FAIL: Case E maybe_install_settings exit non-zero"; return 1; }
  python3 -c "
import json
d = json.load(open('$case_e_home/settings.json'))
e = d.get('env', {})
assert d.get('model') == 'opus', f'Case E: model not preserved → {d.get(\"model\")!r}'
assert d.get('enabledPlugins', {}).get('foo') == 'bar', f'Case E: enabledPlugins not preserved → {d.get(\"enabledPlugins\")!r}'
assert d.get('extraKnownMarketplaces', {}).get('baz') == {}, f'Case E: extraKnownMarketplaces not preserved → {d.get(\"extraKnownMarketplaces\")!r}'
assert e.get('CUSTOM_VAR') == 'x', f'Case E: CUSTOM_VAR not preserved → {e.get(\"CUSTOM_VAR\")!r}'
assert e.get('CLAUDE_CODE_DISABLE_1M_CONTEXT') == '1', f'Case E: DISABLE_1M_CONTEXT default missing'
assert d.get('hooks') and len(d['hooks']) > 0, 'Case E: hooks block missing or empty'
" || { echo "FAIL: Case E assertions"; return 1; }

  ## --- AC #6 tripwire: heredoc must not have touched repo-local claude/ ---
  local repo_root="$(dirname "${BASH_SOURCE[0]}")/.."
  if [[ -d "$repo_root/.git" ]]; then
    local dirty
    dirty=$(cd "$repo_root" && git status --porcelain claude/ 2>/dev/null)
    if [[ -n "$dirty" ]]; then
      echo "FAIL: AC#6 tripwire — heredoc mutated repo-local claude/: $dirty"
      return 1
    fi
  fi

  echo "PASS: _selftest_settings_env_block"
  return 0
}

_selftest_modes_overlay_active_present() {
  # Exercise provision_modes_overlay when docs/active-deployment selects a
  # valid provider: expect symlink at $CLAUDE_HOME/modes/active.md → railway.md
  # and the rendered CLAUDE.md to still contain the overlay reference line.
  local tmp; tmp=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  export CLAUDE_HOME="$tmp/.claude"
  export REPO_ROOT="$tmp/repo"
  mkdir -p "$CLAUDE_HOME/modes" "$REPO_ROOT/docs"
  printf '## Railway Mode\nstub content\n' > "$CLAUDE_HOME/modes/railway.md"
  printf '## Azure Mode\nstub content\n'   > "$CLAUDE_HOME/modes/azure.md"
  cat > "$CLAUDE_HOME/CLAUDE.md" <<MD
# header

body

@~/.claude/modes/active.md

## User Identity
MD
  printf 'railway\n' > "$REPO_ROOT/docs/active-deployment"

  provision_modes_overlay >/dev/null 2>&1 \
    || { echo "FAIL: provision_modes_overlay exit non-zero (active present)"; return 1; }

  [[ -L "$CLAUDE_HOME/modes/active.md" ]] \
    || { echo "FAIL: active.md is not a symlink"; return 1; }
  local resolved
  resolved="$(readlink "$CLAUDE_HOME/modes/active.md")"
  [[ "$resolved" == "$CLAUDE_HOME/modes/railway.md" ]] \
    || { echo "FAIL: active.md → '$resolved' (expected railway.md)"; return 1; }
  grep -qF '@~/.claude/modes/active.md' "$CLAUDE_HOME/CLAUDE.md" \
    || { echo "FAIL: overlay reference stripped despite active-deployment present"; return 1; }

  echo "PASS: _selftest_modes_overlay_active_present"
  return 0
}

_selftest_modes_overlay_active_absent() {
  # Exercise provision_modes_overlay when docs/active-deployment is missing:
  # expect no symlink + overlay reference stripped from rendered CLAUDE.md.
  local tmp; tmp=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  export CLAUDE_HOME="$tmp/.claude"
  export REPO_ROOT="$tmp/repo"
  mkdir -p "$CLAUDE_HOME/modes" "$REPO_ROOT/docs"
  printf '## Railway Mode\nstub content\n' > "$CLAUDE_HOME/modes/railway.md"
  cat > "$CLAUDE_HOME/CLAUDE.md" <<MD
# header

body

@~/.claude/modes/active.md

## User Identity
MD
  # Deliberately do NOT create $REPO_ROOT/docs/active-deployment.

  provision_modes_overlay >/dev/null 2>&1 \
    || { echo "FAIL: provision_modes_overlay exit non-zero (active absent)"; return 1; }

  [[ ! -e "$CLAUDE_HOME/modes/active.md" ]] \
    || { echo "FAIL: active.md unexpectedly created when no active-deployment"; return 1; }
  if grep -qF '@~/.claude/modes/active.md' "$CLAUDE_HOME/CLAUDE.md"; then
    echo "FAIL: overlay reference not stripped from rendered CLAUDE.md"
    return 1
  fi

  echo "PASS: _selftest_modes_overlay_active_absent"
  return 0
}

_selftest_native_commit_msg_hook_install() {
  # Sandbox: fresh git repo, scoped $REPO_ROOT override so install_native_commit_msg_hook
  # writes into the sandbox .git/hooks rather than the real pipelinekit checkout.
  local sandbox
  sandbox=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-native-hook-XXXX") || return 1
  # shellcheck disable=SC2064
  trap "rm -rf '$sandbox'" RETURN

  # Stage a fake "REPO_ROOT" that contains the wrapper AND is its own git repo
  # (install_native_commit_msg_hook reads $REPO_ROOT both for wrapper source AND
  # for git-common-dir resolution).
  mkdir -p "$sandbox/claude/hooks"
  cp -a "$REPO_ROOT/claude/hooks/commit-msg-wrapper.sh" "$sandbox/claude/hooks/commit-msg-wrapper.sh"
  cp -a "$REPO_ROOT/claude/hooks/validate-commit-msg.sh" "$sandbox/claude/hooks/validate-commit-msg.sh"
  chmod +x "$sandbox/claude/hooks/commit-msg-wrapper.sh" "$sandbox/claude/hooks/validate-commit-msg.sh"
  ( cd "$sandbox" && git init -b main >/dev/null 2>&1 ) || { echo "FAIL: git init"; return 1; }

  local saved_repo_root="$REPO_ROOT"
  REPO_ROOT="$sandbox"

  # AC #1: first invocation creates symlink at .git/hooks/commit-msg.
  install_native_commit_msg_hook >/dev/null 2>&1
  if [[ ! -L "$sandbox/.git/hooks/commit-msg" ]]; then
    REPO_ROOT="$saved_repo_root"
    echo "FAIL AC-1: symlink not created at .git/hooks/commit-msg"
    return 1
  fi
  local link_target
  link_target="$(readlink "$sandbox/.git/hooks/commit-msg")"
  if [[ "$link_target" != "$sandbox/claude/hooks/commit-msg-wrapper.sh" ]]; then
    REPO_ROOT="$saved_repo_root"
    echo "FAIL AC-1: symlink target wrong (got $link_target)"
    return 1
  fi

  # AC #2: idempotency — second invocation no-op, symlink unchanged.
  local mtime_before
  mtime_before=$(stat -c '%Y' "$sandbox/.git/hooks/commit-msg" 2>/dev/null || stat -f '%m' "$sandbox/.git/hooks/commit-msg")
  install_native_commit_msg_hook >/dev/null 2>&1
  local mtime_after
  mtime_after=$(stat -c '%Y' "$sandbox/.git/hooks/commit-msg" 2>/dev/null || stat -f '%m' "$sandbox/.git/hooks/commit-msg")
  # We accept either same mtime, or different mtime as long as target still matches.
  link_target="$(readlink "$sandbox/.git/hooks/commit-msg")"
  if [[ "$link_target" != "$sandbox/claude/hooks/commit-msg-wrapper.sh" ]]; then
    REPO_ROOT="$saved_repo_root"
    echo "FAIL AC-2: idempotency broke symlink target"
    return 1
  fi

  # AC #3: alien pre-existing hook is backed up to .pre-pipelinekit.
  rm -f "$sandbox/.git/hooks/commit-msg" "$sandbox/.git/hooks/commit-msg.pre-pipelinekit"
  cat > "$sandbox/.git/hooks/commit-msg" <<'ALIEN'
#!/bin/sh
exit 0
ALIEN
  chmod +x "$sandbox/.git/hooks/commit-msg"
  install_native_commit_msg_hook >/dev/null 2>&1
  if [[ ! -L "$sandbox/.git/hooks/commit-msg" ]]; then
    REPO_ROOT="$saved_repo_root"
    echo "FAIL AC-3: collision did not produce symlink"
    return 1
  fi
  if [[ ! -e "$sandbox/.git/hooks/commit-msg.pre-pipelinekit" ]]; then
    REPO_ROOT="$saved_repo_root"
    echo "FAIL AC-3: alien hook not backed up"
    return 1
  fi

  REPO_ROOT="$saved_repo_root"
  echo "PASS: _selftest_native_commit_msg_hook_install"
  return 0
}

_selftest_caveman_active_marker() {
  # Verify that maybe_install_settings (CLAUDE_INSTALL_SETTINGS=1) touches
  # $CLAUDE_HOME/.caveman-active, and that .caveman-off suppresses it.
  # 3 cases: no-opt-out, opt-out, idempotency.

  # --- Case 1: no .caveman-off → .caveman-active must be created ---
  local sb1
  sb1=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-caveman-XXXX") || return 1
  local saved_ch="${CLAUDE_HOME:-}"
  export CLAUDE_HOME="$sb1"
  mkdir -p "$CLAUDE_HOME"
  CLAUDE_INSTALL_SETTINGS=1 maybe_install_settings "" >/dev/null 2>&1
  local exit1=$?
  if [[ $exit1 -ne 0 ]]; then
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb1"
    echo "FAIL: _selftest_caveman_active_marker — Case 1 maybe_install_settings exit non-zero ($exit1)"
    return 1
  fi
  if [[ ! -e "$sb1/.caveman-active" ]]; then
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb1"
    echo "FAIL: _selftest_caveman_active_marker — Case 1 .caveman-active not created"
    return 1
  fi
  rm -rf "$sb1"

  # --- Case 2: .caveman-off present → .caveman-active must NOT be created ---
  local sb2
  sb2=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-caveman-XXXX") || return 1
  export CLAUDE_HOME="$sb2"
  mkdir -p "$CLAUDE_HOME"
  touch "$CLAUDE_HOME/.caveman-off"
  CLAUDE_INSTALL_SETTINGS=1 maybe_install_settings "" >/dev/null 2>&1
  local exit2=$?
  if [[ $exit2 -ne 0 ]]; then
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb2"
    echo "FAIL: _selftest_caveman_active_marker — Case 2 maybe_install_settings exit non-zero ($exit2)"
    return 1
  fi
  if [[ -e "$sb2/.caveman-active" ]]; then
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb2"
    echo "FAIL: _selftest_caveman_active_marker — Case 2 .caveman-active created despite .caveman-off"
    return 1
  fi
  rm -rf "$sb2"

  # --- Case 3: idempotency — re-run with marker already present, exits 0, marker still exists ---
  local sb3
  sb3=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-caveman-XXXX") || return 1
  export CLAUDE_HOME="$sb3"
  mkdir -p "$CLAUDE_HOME"
  touch "$CLAUDE_HOME/.caveman-active"   # pre-create the marker
  CLAUDE_INSTALL_SETTINGS=1 maybe_install_settings "" >/dev/null 2>&1
  local exit3=$?
  if [[ $exit3 -ne 0 ]]; then
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb3"
    echo "FAIL: _selftest_caveman_active_marker — Case 3 maybe_install_settings exit non-zero ($exit3)"
    return 1
  fi
  if [[ ! -e "$sb3/.caveman-active" ]]; then
    [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME
    rm -rf "$sb3"
    echo "FAIL: _selftest_caveman_active_marker — Case 3 .caveman-active missing after re-run"
    return 1
  fi
  rm -rf "$sb3"

  # Restore CLAUDE_HOME
  [[ -n "$saved_ch" ]] && export CLAUDE_HOME="$saved_ch" || unset CLAUDE_HOME

  echo "PASS: _selftest_caveman_active_marker"
  return 0
}

_wsl2_ram_gate() {
  # TEST HOOK: __pkit_mock_wsl_2gb=1 forces "WSL2 + 2 GB" path. Do not set in production.
  if [[ "${__pkit_mock_wsl_2gb:-0}" == "1" ]]; then
    [[ "${PIPELINE_FORCE_INSTALL:-0}" == "1" ]] && return 0
    printf '[install][error] WSL2 host has < 4 GB MemTotal. agentmemory MCP requires 4 GB minimum.\n' >&2
    printf '[install][error] Override via PIPELINE_FORCE_INSTALL=1.\n' >&2
    return 1
  fi
  # Skip on non-Linux (gate is a no-op for Darwin/etc.).
  [[ ! -r /proc/version ]] && return 0
  # Probe WSL2 marker.
  grep -qi microsoft /proc/version || return 0
  # Override switch.
  [[ "${PIPELINE_FORCE_INSTALL:-0}" == "1" ]] && return 0
  # Parse MemTotal in kB.
  local mem_kb
  mem_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
  if [[ "$mem_kb" -lt 4194304 ]]; then
    printf '[install][error] WSL2 host has < 4 GB MemTotal (%s kB). agentmemory MCP requires 4 GB minimum.\n' "$mem_kb" >&2
    printf '[install][error] Override via PIPELINE_FORCE_INSTALL=1 (caveat: install may OOM on heavy MCP load).\n' >&2
    return 1
  fi
  return 0
}

provision_agentmemory_mcp() {
  # Step 1: WSL2 RAM gate — warn-and-continue on insufficient RAM.
  if ! _wsl2_ram_gate; then
    warn "agentmemory MCP install skipped (WSL2 RAM gate)"
    return 0
  fi

  # Step 2: Resolve embedding provider via env-var probe chain.
  local EMBED_PROVIDER
  if [[ -n "${VOYAGE_API_KEY:-}" ]]; then
    EMBED_PROVIDER="voyage"
  elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    EMBED_PROVIDER="openai"
  else
    EMBED_PROVIDER="local-onnx-quant"
    warn "agentmemory: no VOYAGE_API_KEY / OPENAI_API_KEY in env — falling back to local-onnx-quant. Add VOYAGE_API_KEY to ~/.bashrc for better recall quality."
  fi

  # Step 3: Write MCP entry to BOTH user-scope (~/.claude.json `mcpServers` block,
  # the canonical location Claude CLI reads) AND the legacy ${CLAUDE_HOME}/.mcp.json
  # path (preserved for selftest fixtures + downstream tooling that grepped the
  # legacy location). Claude CLI ignores ${CLAUDE_HOME}/.mcp.json — only the
  # user-scope ~/.claude.json `mcpServers` block surfaces in `claude mcp list`.
  # Previous behaviour wrote ONLY to the legacy phantom path → agentmemory never
  # connected. See fix/agentmemory-restore-or-demote for the diagnostic that
  # surfaced this. The legacy write stays in place for backward-compat and is
  # the surface the existing _selftest_agentmemory_mcp_provisioned sandbox
  # exercises.

  # 3a — legacy ${CLAUDE_HOME}/.mcp.json write (preserved for selftest + tooling).
  local mcp_target="${CLAUDE_HOME}/.mcp.json"
  if [[ -f "$mcp_target" ]]; then
    local mcp_bak="${mcp_target}.bak-$(date +%s)"
    cp -a "$mcp_target" "$mcp_bak"
    log "Backed up existing .mcp.json → $mcp_bak"
  fi

  # Compose env block: ALWAYS include EMBED_PROVIDER, FALLBACK, DB_PATH. Include
  # VOYAGE_API_KEY / OPENAI_API_KEY only when the corresponding shell env var
  # is set — otherwise Claude CLI warns about missing env vars (it does not
  # silently drop literal `${...}` placeholders for unset vars) and refuses to
  # connect the server.
  local _have_voyage="0" _have_openai="0"
  [[ -n "${VOYAGE_API_KEY:-}" ]] && _have_voyage="1"
  [[ -n "${OPENAI_API_KEY:-}" ]] && _have_openai="1"

  python3 - "$mcp_target" "$EMBED_PROVIDER" "$_have_voyage" "$_have_openai" <<'PYEOF'
import json, os, sys

dst, embed_provider, have_voyage, have_openai = sys.argv[1:5]
have_voyage = have_voyage == "1"
have_openai = have_openai == "1"

# Load existing JSON or start fresh.
if os.path.isfile(dst):
    with open(dst, 'r', encoding='utf-8') as f:
        data = json.load(f)
else:
    data = {"mcpServers": {}}

if "mcpServers" not in data:
    data["mcpServers"] = {}

env_block = {
    "AGENTMEMORY_EMBED_PROVIDER": embed_provider,
    "AGENTMEMORY_EMBED_FALLBACK": "local-onnx-quant",
    "AGENTMEMORY_DB_PATH": ".agentmemory/agentmemory.db",
}
if have_voyage:
    env_block["VOYAGE_API_KEY"] = "${VOYAGE_API_KEY}"
if have_openai:
    env_block["OPENAI_API_KEY"] = "${OPENAI_API_KEY}"

data["mcpServers"]["agentmemory"] = {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@agentmemory/agentmemory@0.9.21", "mcp"],
    "env": env_block,
}

# Atomic write via temp file + os.replace.
tmp = dst + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, dst)
print(f"agentmemory MCP entry written to {dst} (provider={embed_provider})")
PYEOF

  log "agentmemory MCP entry written to legacy path $mcp_target (provider=$EMBED_PROVIDER)"

  # 3b — user-scope ~/.claude.json write (the actual location Claude CLI reads).
  # Skip if HOME unset or if the file isn't a valid JSON object (don't corrupt
  # an existing settings file). The script is idempotent: re-running merges
  # rather than replacing, and preserves all unrelated top-level keys.
  local user_scope_target="${HOME}/.claude.json"
  if [[ -z "${HOME:-}" ]]; then
    warn "agentmemory: HOME unset — skipping user-scope ~/.claude.json registration; only legacy $mcp_target written"
  else
    if [[ -f "$user_scope_target" ]]; then
      local user_scope_bak="${user_scope_target}.bak-$(date +%s)"
      cp -a "$user_scope_target" "$user_scope_bak"
      log "Backed up existing ~/.claude.json → $user_scope_bak"
    fi
    python3 - "$user_scope_target" "$EMBED_PROVIDER" "$_have_voyage" "$_have_openai" <<'PYEOF'
import json, os, sys

dst, embed_provider, have_voyage, have_openai = sys.argv[1:5]
have_voyage = have_voyage == "1"
have_openai = have_openai == "1"

# Load existing JSON or start fresh — ~/.claude.json holds user-wide Claude
# Code settings (auth metadata, onboarding flags, mcpServers, ...). We touch
# ONLY the `mcpServers.agentmemory` subkey; every other top-level key is
# preserved byte-for-byte (modulo JSON-roundtrip whitespace, which Claude CLI
# also rewrites on its own mutations).
if os.path.isfile(dst):
    with open(dst, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            sys.stderr.write(
                f"[install][warn] {dst} is not valid JSON ({exc}); refusing to overwrite — agentmemory user-scope registration SKIPPED\n"
            )
            sys.exit(0)
else:
    data = {}

if not isinstance(data, dict):
    sys.stderr.write(
        f"[install][warn] {dst} top-level is not a JSON object; refusing to overwrite — agentmemory user-scope registration SKIPPED\n"
    )
    sys.exit(0)

mcp_servers = data.setdefault("mcpServers", {})
if not isinstance(mcp_servers, dict):
    sys.stderr.write(
        f"[install][warn] {dst} `mcpServers` is not a JSON object; refusing to overwrite — agentmemory user-scope registration SKIPPED\n"
    )
    sys.exit(0)

env_block = {
    "AGENTMEMORY_EMBED_PROVIDER": embed_provider,
    "AGENTMEMORY_EMBED_FALLBACK": "local-onnx-quant",
    "AGENTMEMORY_DB_PATH": ".agentmemory/agentmemory.db",
}
if have_voyage:
    env_block["VOYAGE_API_KEY"] = "${VOYAGE_API_KEY}"
if have_openai:
    env_block["OPENAI_API_KEY"] = "${OPENAI_API_KEY}"

mcp_servers["agentmemory"] = {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@agentmemory/agentmemory@0.9.21", "mcp"],
    "env": env_block,
}

tmp = dst + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, dst)
print(f"agentmemory MCP entry merged into user-scope {dst} (provider={embed_provider})")
PYEOF
    log "agentmemory MCP entry merged into user-scope $user_scope_target (provider=$EMBED_PROVIDER)"
  fi

  # Step 4: Doctor smoke — warn-and-continue on failure.
  if command -v npx >/dev/null 2>&1; then
    (timeout 30 npx -y @agentmemory/agentmemory@0.9.21 doctor 2>>"$LOG" 1>>"$LOG") \
      || warn "agentmemory doctor smoke failed — first MCP-client invocation will lazily re-fetch; see $LOG"
  fi
}

# ---------- Codegraph MCP (symbolic-graph layer; inert until first MCP client call) ----------
# Writes a single JSON entry to ${CLAUDE_HOME}/.mcp.json. Does NOT invoke
# `codegraph init`, `codegraph index`, or any stateful subcommand — those are
# deferred to the user invoking `/codegraph-init` per project.
# AC #1/#4 binding — see docs/features-mem-graph-stack.md § feat/codegraph-default-mcp.
provision_codegraph_mcp() {
  # Step 1: Backup existing .mcp.json if present.
  local mcp_target="${CLAUDE_HOME}/.mcp.json"
  if [[ -f "$mcp_target" ]]; then
    local mcp_bak="${mcp_target}.bak-$(date +%s)"
    cp -a "$mcp_target" "$mcp_bak"
    log "Backed up existing .mcp.json → $mcp_bak"
  fi

  # Step 2: Write codegraph MCP entry via python3 heredoc (atomic temp + os.replace).
  python3 - "$mcp_target" <<'PYEOF'
import json, os, sys

dst = sys.argv[1]

# Load existing JSON or start fresh.
if os.path.isfile(dst):
    with open(dst, 'r', encoding='utf-8') as f:
        data = json.load(f)
else:
    data = {"mcpServers": {}}

if "mcpServers" not in data:
    data["mcpServers"] = {}

data["mcpServers"]["codegraph"] = {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@colbymchenry/codegraph@^0.9.4", "serve", "--mcp"]
}

# Atomic write via temp file + os.replace.
tmp = dst + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, dst)
print(f"codegraph MCP entry written to {dst}")
PYEOF

  # Step 3: Log completion.
  log "codegraph MCP entry written (pin @^0.9.4)"
  # NO doctor smoke — codegraph has no documented doctor subcommand.
  # NO daemon spawn — npx -y lazily fetches + spawns at first MCP-client tool call.
  # NO codegraph init / index — deferred to user invocation of /codegraph-init per project.

  # Step 2b — user-scope ${HOME}/.claude.json write (the actual location Claude CLI reads).
  # Mirrors agentmemory 3b: backup, JSONDecodeError guard, isinstance guards,
  # setdefault idempotent merge, atomic tmp+os.replace. HOME-unset → skip.
  local user_scope_target="${HOME}/.claude.json"
  if [[ -z "${HOME:-}" ]]; then
    warn "codegraph: HOME unset — skipping user-scope ~/.claude.json registration; only legacy $mcp_target written"
  else
    if [[ -f "$user_scope_target" ]]; then
      local user_scope_bak="${user_scope_target}.bak-$(date +%s)"
      cp -a "$user_scope_target" "$user_scope_bak"
      log "Backed up existing ~/.claude.json → $user_scope_bak"
    fi
    python3 - "$user_scope_target" <<'PYEOF'
import json, os, sys

dst = sys.argv[1]

if os.path.isfile(dst):
    with open(dst, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            sys.stderr.write(
                f"[install][warn] {dst} is not valid JSON ({exc}); refusing to overwrite — codegraph user-scope registration SKIPPED\n"
            )
            sys.exit(0)
else:
    data = {}

if not isinstance(data, dict):
    sys.stderr.write(
        f"[install][warn] {dst} top-level is not a JSON object; refusing to overwrite — codegraph user-scope registration SKIPPED\n"
    )
    sys.exit(0)

mcp_servers = data.setdefault("mcpServers", {})
if not isinstance(mcp_servers, dict):
    sys.stderr.write(
        f"[install][warn] {dst} `mcpServers` is not a JSON object; refusing to overwrite — codegraph user-scope registration SKIPPED\n"
    )
    sys.exit(0)

mcp_servers["codegraph"] = {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@colbymchenry/codegraph@^0.9.4", "serve", "--mcp"]
}

tmp = dst + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, dst)
print(f"codegraph MCP entry merged into user-scope {dst}")
PYEOF
    log "codegraph MCP entry merged into user-scope $user_scope_target"
  fi
  return 0
}

# ---------- Graphify MCP (knowledge-graph layer; inert until first MCP client call) ----------
# Writes a single JSON entry to ${CLAUDE_HOME}/.mcp.json. Does NOT invoke
# `graphify .` or any stateful build subcommand — those are deferred to the user
# invoking `/graphify-init` per project.
# Pre-flight: probes for `uv` (required) and Python 3.10+ (required). If either
# is absent, logs an actionable message and returns 0 (non-fatal skip).
# Hermeticity: honour __pkit_mock_graphify_install_skip=1 to skip uv tool install
# (used by _selftest_graphify_mcp_provisioned for hermetic testing).
provision_graphify_mcp() {
  # Step 1: Pre-flight — probe for uv.
  if ! command -v uv >/dev/null 2>&1; then
    log "SKIP provision_graphify_mcp: uv not found. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh"
    return 0
  fi

  # Step 1b: Pre-flight — probe for Python 3.10+ (Style B: exit-code only).
  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    log "SKIP provision_graphify_mcp: Python 3.10+ not found (python3 exited non-zero). Install Python >= 3.10 and re-run."
    return 0
  fi

  # Step 2: Install graphifyy (skip under mock env var for hermetic selftest).
  if [[ "${__pkit_mock_graphify_install_skip:-0}" != "1" ]]; then
    log "Installing graphifyy==${GRAPHIFY_VERSION} via uv tool install"
    uv tool install "graphifyy==${GRAPHIFY_VERSION}" 2>>"$LOG" \
      || { log "WARN: uv tool install graphifyy failed — MCP entry still written; re-run install to retry."; }
  else
    log "SKIP uv tool install graphifyy (mock mode __pkit_mock_graphify_install_skip=1)"
  fi

  # Step 3: Backup existing .mcp.json if present.
  local mcp_target="${CLAUDE_HOME}/.mcp.json"
  if [[ -f "$mcp_target" ]]; then
    local mcp_bak="${mcp_target}.bak-$(date +%s)"
    cp -a "$mcp_target" "$mcp_bak"
    log "Backed up existing .mcp.json → $mcp_bak"
  fi

  # Step 4: Write graphify MCP entry via python3 heredoc (atomic temp + os.replace).
  python3 - "$mcp_target" <<'PYEOF'
import json, os, sys

dst = sys.argv[1]

# Load existing JSON or start fresh.
if os.path.isfile(dst):
    with open(dst, 'r', encoding='utf-8') as f:
        data = json.load(f)
else:
    data = {"mcpServers": {}}

if "mcpServers" not in data:
    data["mcpServers"] = {}

data["mcpServers"]["graphify"] = {
    "type": "stdio",
    "command": "uv",
    "args": ["tool", "run", "--from", "graphifyy", "graphify", ".", "--mcp"]
}

# Atomic write via temp file + os.replace.
tmp = dst + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, dst)
print(f"graphify MCP entry written to {dst}")
PYEOF

  # Step 5: Log completion.
  log "graphify MCP entry written (graphifyy==${GRAPHIFY_VERSION})"
  # NO doctor smoke — graphify has no documented doctor subcommand.
  # NO daemon spawn — uv tool run lazily invokes at first MCP-client tool call.
  # NO graph build / eager index — deferred to user invocation of /graphify-init per project.
  # NO mutation of settings.json.

  # Step 4b — user-scope ${HOME}/.claude.json write (the actual location Claude CLI reads).
  # Mirrors agentmemory 3b: backup, JSONDecodeError guard, isinstance guards,
  # setdefault idempotent merge, atomic tmp+os.replace. HOME-unset → skip.
  local user_scope_target="${HOME}/.claude.json"
  if [[ -z "${HOME:-}" ]]; then
    warn "graphify: HOME unset — skipping user-scope ~/.claude.json registration; only legacy $mcp_target written"
  else
    if [[ -f "$user_scope_target" ]]; then
      local user_scope_bak="${user_scope_target}.bak-$(date +%s)"
      cp -a "$user_scope_target" "$user_scope_bak"
      log "Backed up existing ~/.claude.json → $user_scope_bak"
    fi
    python3 - "$user_scope_target" <<'PYEOF'
import json, os, sys

dst = sys.argv[1]

if os.path.isfile(dst):
    with open(dst, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            sys.stderr.write(
                f"[install][warn] {dst} is not valid JSON ({exc}); refusing to overwrite — graphify user-scope registration SKIPPED\n"
            )
            sys.exit(0)
else:
    data = {}

if not isinstance(data, dict):
    sys.stderr.write(
        f"[install][warn] {dst} top-level is not a JSON object; refusing to overwrite — graphify user-scope registration SKIPPED\n"
    )
    sys.exit(0)

mcp_servers = data.setdefault("mcpServers", {})
if not isinstance(mcp_servers, dict):
    sys.stderr.write(
        f"[install][warn] {dst} `mcpServers` is not a JSON object; refusing to overwrite — graphify user-scope registration SKIPPED\n"
    )
    sys.exit(0)

mcp_servers["graphify"] = {
    "type": "stdio",
    "command": "uv",
    "args": ["tool", "run", "--from", "graphifyy", "graphify", ".", "--mcp"]
}

tmp = dst + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, dst)
print(f"graphify MCP entry merged into user-scope {dst}")
PYEOF
    log "graphify MCP entry merged into user-scope $user_scope_target"
  fi
  return 0
}

# ---------- Serena MCP (semantic code navigation; user-scope registration only) ----------
# Writes the serena entry into ${HOME}/.claude.json `mcpServers`. Does NOT perform
# any package install — the package is installed earlier in the script via uv/pip.
# Pre-flight gate: if `uvx` is not on PATH, log SKIP + return 0 (warn-and-continue).
# Hermeticity: honour __pkit_mock_serena_gate_skip=1 to bypass the uvx gate for selftests.
provision_serena_mcp() {
  # Pre-flight gate: uvx required (mirrors graphify's uv gate shape).
  # Use __pkit_mock_serena_gate_skip=1 to bypass for hermetic selftest (preferred over
  # conditional assertion, so the test always exercises the write path).
  if [[ "${__pkit_mock_serena_gate_skip:-0}" != "1" ]]; then
    if ! command -v uvx >/dev/null 2>&1; then
      log "SKIP provision_serena_mcp: uvx not found. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh"
      return 0
    fi
  fi

  # User-scope ${HOME}/.claude.json write (the actual location Claude CLI reads).
  # Mirrors agentmemory 3b: backup, JSONDecodeError guard, isinstance guards,
  # setdefault idempotent merge, atomic tmp+os.replace. HOME-unset → skip.
  local user_scope_target="${HOME}/.claude.json"
  if [[ -z "${HOME:-}" ]]; then
    warn "serena: HOME unset — skipping user-scope ~/.claude.json registration"
    return 0
  fi

  if [[ -f "$user_scope_target" ]]; then
    local user_scope_bak="${user_scope_target}.bak-$(date +%s)"
    cp -a "$user_scope_target" "$user_scope_bak"
    log "Backed up existing ~/.claude.json → $user_scope_bak"
  fi

  python3 - "$user_scope_target" <<'PYEOF'
import json, os, sys

dst = sys.argv[1]

if os.path.isfile(dst):
    with open(dst, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            sys.stderr.write(
                f"[install][warn] {dst} is not valid JSON ({exc}); refusing to overwrite — serena user-scope registration SKIPPED\n"
            )
            sys.exit(0)
else:
    data = {}

if not isinstance(data, dict):
    sys.stderr.write(
        f"[install][warn] {dst} top-level is not a JSON object; refusing to overwrite — serena user-scope registration SKIPPED\n"
    )
    sys.exit(0)

mcp_servers = data.setdefault("mcpServers", {})
if not isinstance(mcp_servers, dict):
    sys.stderr.write(
        f"[install][warn] {dst} `mcpServers` is not a JSON object; refusing to overwrite — serena user-scope registration SKIPPED\n"
    )
    sys.exit(0)

mcp_servers["serena"] = {
    "type": "stdio",
    "command": "serena",
    "args": ["start-mcp-server", "--context", "claude-code", "--project-from-cwd"]
}

tmp = dst + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, dst)
print(f"serena MCP entry merged into user-scope {dst}")
PYEOF
  log "serena MCP entry merged into user-scope $user_scope_target"
  return 0
}

# ---------- Understand-Anything plugin (Claude Code plugin, NOT MCP) ----------

# _reconcile_understand_anything_enable — strip dangling enabledPlugins entry.
# `claude plugin install` writes enabledPlugins into settings.json, but if the
# plugin cache dir is absent (network failure / partial install / later removed),
# the dangling flag causes Claude Code's plugin loader to fail EVERY session.
# This helper checks the cache dir and, when absent, removes only the
# `understand-anything@*` key(s) from enabledPlugins (non-fatal either way).
# extraKnownMarketplaces is intentionally left intact — a registered marketplace
# with no enabled plugin does NOT break the loader.
# Reads $CLAUDE_HOME (expected to be set by caller).
_reconcile_understand_anything_enable() {
  local ua_cache="${CLAUDE_HOME:-$HOME/.claude}/plugins/cache/understand-anything"
  local ua_settings="${CLAUDE_HOME:-$HOME/.claude}/settings.json"
  if [[ ! -d "$ua_cache" ]]; then
    warn "Understand-Anything enabled but not cached at $ua_cache — removing the dangling enabledPlugins entry so plugin loading does not fail every session. Re-enable later with: claude plugin install understand-anything"
    if [[ -f "$ua_settings" ]]; then
      python3 - "$ua_settings" <<'PYRECONCILE'
import json, os, sys
p = sys.argv[1]
try:
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
except (json.JSONDecodeError, OSError):
    sys.exit(0)
if not isinstance(d, dict):
    sys.exit(0)
ep = d.get("enabledPlugins")
if not isinstance(ep, dict):
    sys.exit(0)
removed = [k for k in ep if k.startswith("understand-anything@")]
for k in removed:
    del ep[k]
if removed:
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
        f.write("\n")
    os.replace(tmp, p)
    print(f"reconciled: removed dangling enabledPlugins {removed} from {p}")
PYRECONCILE
    fi
  fi
}

# Probes for the `claude plugin marketplace add` CLI subcommand; falls back to
# git-clone + pinned-SHA when absent. Network failure is non-fatal (warn + return 0).
# AC #1/#2/#3/#5 binding — see docs/features-mem-graph-stack.md § feat/understand-anything-plugin.
provision_understand_anything() {
  local UA_URL="https://github.com/Lum1104/Understand-Anything"
  local UA_DIR="${CLAUDE_HOME:-$HOME/.claude}/plugins/understand-anything"
  local UA_SOURCE=""
  local UA_MODE=""

  # SHA-pin policy: warn if user overrides to a floating ref.
  if [[ ! "$UNDERSTAND_ANYTHING_SHA" =~ ^[0-9a-f]{40}$ ]]; then
    warn "UNDERSTAND_ANYTHING_SHA=$UNDERSTAND_ANYTHING_SHA is not a 40-char hex commit SHA (floating ref); proceeding but supply-chain pin is weakened."
  fi

  # Mock hooks for selftest (hermetic; never hit live network).
  if [[ "${__pkit_mock_understand_anything_marketplace:-0}" == "1" ]]; then
    log "[mock] understand-anything marketplace path forced; skipping live CLI."
    UA_MODE="marketplace"
    UA_SOURCE="Lum1104/Understand-Anything"
    log "[mock] would invoke: claude plugin marketplace add $UA_SOURCE"
    log "[mock] would invoke: claude plugin install understand-anything"
    return 0
  fi
  if [[ "${__pkit_mock_understand_anything_clone_fail:-0}" == "1" ]]; then
    warn "[mock] understand-anything git-clone synthesized failure; install skipped."
    return 0
  fi

  # Capability probe: NO leading slash. Spec text used `/plugin` which is an in-session
  # slash command, not a CLI subcommand — see analysis-v93 § OQ-1.
  if command -v claude >/dev/null 2>&1 \
     && claude plugin marketplace --help 2>/dev/null | grep -q "^[[:space:]]*add "; then
    UA_MODE="marketplace"
    UA_SOURCE="Lum1104/Understand-Anything"
  else
    UA_MODE="git-clone"
    UA_SOURCE="$UA_DIR"
  fi

  log "Installing Understand-Anything plugin via $UA_MODE path (SHA=$UNDERSTAND_ANYTHING_SHA)"

  if [[ "$UA_MODE" == "git-clone" ]]; then
    # Three-step pinned clone (portable across git versions; see analysis-v93 § OQ-2).
    if [[ -d "$UA_DIR/.git" ]]; then
      log "Understand-Anything already cloned at $UA_DIR; skipping clone."
    else
      mkdir -p "$(dirname "$UA_DIR")"
      git clone --depth 1 "$UA_URL" "$UA_DIR" 2>>"$LOG" \
        || { warn "Understand-Anything git clone failed (network?); continuing without plugin."; return 0; }
      git -C "$UA_DIR" fetch --depth 1 origin "$UNDERSTAND_ANYTHING_SHA" 2>>"$LOG" \
        || { warn "Understand-Anything fetch of pinned SHA failed; cloned dir left at HEAD."; }
      git -C "$UA_DIR" checkout --detach "$UNDERSTAND_ANYTHING_SHA" 2>>"$LOG" \
        || { warn "Understand-Anything checkout of pinned SHA failed; cloned dir left at HEAD."; }
    fi
  fi

  # Uniform finalize per analysis-v93 § Risk-4 (A): both paths end in
  # `claude plugin marketplace add <source>` — only `<source>` differs.
  if command -v claude >/dev/null 2>&1; then
    claude plugin marketplace add "$UA_SOURCE" 2>&1 | tee -a "$LOG" \
      || warn "Understand-Anything marketplace registration failed (exit $?); continuing."
    # Optimistic enable (Risk-3); warn-and-continue on failure.
    claude plugin install understand-anything 2>&1 | tee -a "$LOG" \
      || warn "Understand-Anything plugin enable failed; user may enable manually via /plugin."
  else
    warn "claude CLI not on PATH; Understand-Anything plugin files staged but not registered."
  fi

  # Reconcile dangling enabledPlugins entry: if `claude plugin install` wrote
  # the flag but the cache dir is absent, strip the flag so the plugin loader
  # stays healthy on every subsequent session.
  _reconcile_understand_anything_enable
}

# ---------- modes overlay (per-provider deploy-mode mini-CLAUDE.md) ----------
# Reads $REPO_ROOT/docs/active-deployment (a single-line file, one provider slug),
# symlinks $CLAUDE_HOME/modes/<value>.md → $CLAUDE_HOME/modes/active.md, and
# strips the `@~/.claude/modes/active.md` line from the rendered CLAUDE.md when
# no active deployment is set. Atomic symlink via `ln -sfn`. User-wins: a
# regular file at $CLAUDE_HOME/modes/active.md is preserved untouched.
# Caller provides $CLAUDE_HOME and $REPO_ROOT. Side-effects only; no return value.
provision_modes_overlay() {
  local modes_dir="$CLAUDE_HOME/modes"
  local active_link="$modes_dir/active.md"
  local rendered_md="$CLAUDE_HOME/CLAUDE.md"
  local deploy_file="$REPO_ROOT/docs/active-deployment"
  local overlay_line='@~/.claude/modes/active.md'
  local allowed='^(azure|vercel|railway|render|digitalocean)$'

  # Pre-flight: nothing to do if modes dir wasn't staged.
  [[ -d "$modes_dir" ]] || { log "INSTALL_MODE_NO_MODES_DIR (skip — overlay not provisioned)"; return 0; }

  # Branch 1: docs/active-deployment absent → strip overlay line, no symlink.
  if [[ ! -f "$deploy_file" ]]; then
    log "INSTALL_MODE_NO_ACTIVE_DEPLOYMENT"
    if [[ -f "$rendered_md" ]] && grep -qF "$overlay_line" "$rendered_md"; then
      # Strip the overlay reference + the blank line that follows it (if any).
      python3 - "$rendered_md" "$overlay_line" <<'PYSTRIP'
import sys
path, marker = sys.argv[1], sys.argv[2]
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
out = []
i = 0
while i < len(lines):
    if lines[i].rstrip('\n') == marker:
        # Skip the marker; also swallow a single trailing blank line.
        i += 1
        if i < len(lines) and lines[i].strip() == '':
            i += 1
        continue
    out.append(lines[i])
    i += 1
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(out)
PYSTRIP
    fi
    return 0
  fi

  # Branch 2: docs/active-deployment present — read + validate.
  local value
  value="$(head -n 1 "$deploy_file" | tr -d '[:space:]')"
  if [[ ! "$value" =~ $allowed ]]; then
    log "INSTALL_MODE_UNKNOWN_PROVIDER: $value (skip symlink + strip overlay line)"
    if [[ -f "$rendered_md" ]] && grep -qF "$overlay_line" "$rendered_md"; then
      python3 - "$rendered_md" "$overlay_line" <<'PYSTRIP2'
import sys
path, marker = sys.argv[1], sys.argv[2]
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
out = []
i = 0
while i < len(lines):
    if lines[i].rstrip('\n') == marker:
        i += 1
        if i < len(lines) and lines[i].strip() == '':
            i += 1
        continue
    out.append(lines[i])
    i += 1
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(out)
PYSTRIP2
    fi
    return 0
  fi

  local target_md="$modes_dir/${value}.md"
  if [[ ! -f "$target_md" ]]; then
    warn "INSTALL_MODE_TARGET_MISSING: $target_md (overlay file not staged; skip symlink)"
    return 0
  fi

  # User-wins: if active.md exists as a regular file (not a symlink), preserve it.
  if [[ -e "$active_link" && ! -L "$active_link" ]]; then
    log "INSTALL_MODE_SKIPPED_USER_FILE (preserved user-set $active_link)"
    return 0
  fi

  # Atomic symlink swap.
  ln -sfn "$target_md" "$active_link"
  log "INSTALL_MODE_SYMLINKED: $value"
}

# ---------- native git commit-msg hook ----------
# Installs a symlink at <git_dir>/hooks/commit-msg pointing to the in-repo
# wrapper claude/hooks/commit-msg-wrapper.sh. The wrapper bridges git's
# argv-passed message-file contract to the existing PreToolUse JSON-stdin
# contract of claude/hooks/validate-commit-msg.sh, so the conventional-commit
# gate fires on EVERY git commit (Claude-mediated, bare-shell, CI, IDE) — not
# just commits driven through the harness PreToolUse event.
#
# Worktree-compat: uses `git rev-parse --git-common-dir` (returns the main
# .git/ from linked worktrees) — commit-msg hooks live in the shared hook dir.
# Idempotent: re-runs no-op when the symlink already points at the wrapper.
# Backup-on-collision: any pre-existing commit-msg (regular file OR alien
# symlink) is preserved at <hook>.pre-pipelinekit; collision adds .<ts> suffix.
install_native_commit_msg_hook() {
  # Resolve the wrapper path (must exist in the staged overlay's source repo).
  local wrapper_src="$REPO_ROOT/claude/hooks/commit-msg-wrapper.sh"
  if [[ ! -f "$wrapper_src" ]]; then
    log "INSTALL_NATIVE_HOOK_NO_WRAPPER: $wrapper_src missing — skip"
    return 0
  fi
  chmod +x "$wrapper_src" 2>/dev/null || true

  # Resolve the hook destination via git-common-dir; tolerate non-git pwd.
  local git_common_dir
  git_common_dir="$(cd "$REPO_ROOT" && git rev-parse --git-common-dir 2>/dev/null)" || {
    log "INSTALL_NATIVE_HOOK_NO_GIT_DIR (pwd not inside a git repo) — skip"
    return 0
  }
  # rev-parse may return a relative path; absolutise against $REPO_ROOT.
  case "$git_common_dir" in
    /*) ;;
    *) git_common_dir="$REPO_ROOT/$git_common_dir" ;;
  esac
  local hook_dir="$git_common_dir/hooks"
  mkdir -p "$hook_dir"
  local hook_target="$hook_dir/commit-msg"

  # Fast-path: symlink already points at the wrapper.
  if [[ -L "$hook_target" ]]; then
    local existing
    existing="$(readlink "$hook_target")"
    if [[ "$existing" == "$wrapper_src" ]]; then
      log "INSTALL_NATIVE_HOOK_ALREADY_LINKED: $hook_target"
      return 0
    fi
  fi

  # Collision: preserve any pre-existing hook (regular file OR alien symlink).
  if [[ -e "$hook_target" || -L "$hook_target" ]]; then
    local backup="$hook_target.pre-pipelinekit"
    [[ -e "$backup" ]] && backup="$backup.$(date +%s)"
    mv "$hook_target" "$backup"
    log "INSTALL_NATIVE_HOOK_BACKED_UP: $backup"
  fi

  ln -sfn "$wrapper_src" "$hook_target"
  log "INSTALL_NATIVE_HOOK_SYMLINKED: $hook_target -> $wrapper_src"
}

# ---------- pre-commit hook (chains validate-task-spec.py + scan-secrets-staged.sh) ----------
# Writes a dispatcher shim at <git_dir>/hooks/pre-commit that invokes each
# chained hook in order, short-circuiting on the first non-zero exit. Both
# chained hooks are existence-guarded so a missing source is non-fatal.
# Pre-existing alien pre-commit hooks are backed up to .pre-pipelinekit.
install_pre_commit_hook() {
  local validate_src="$REPO_ROOT/claude/hooks/validate-task-spec.py"
  local scanner_src="$REPO_ROOT/claude/hooks/scan-secrets-staged.sh"

  # Make sure source hooks are executable (no-op if already +x).
  [[ -f "$validate_src" ]] && chmod +x "$validate_src" 2>/dev/null || true
  [[ -f "$scanner_src" ]]  && chmod +x "$scanner_src"  2>/dev/null || true

  # Resolve hook destination via git-common-dir; tolerate non-git pwd.
  local git_common_dir
  git_common_dir="$(cd "$REPO_ROOT" && git rev-parse --git-common-dir 2>/dev/null)" || {
    log "INSTALL_PRE_COMMIT_NO_GIT_DIR (pwd not inside a git repo) -- skip"
    return 0
  }
  case "$git_common_dir" in
    /*) ;;
    *) git_common_dir="$REPO_ROOT/$git_common_dir" ;;
  esac
  local hook_dir="$git_common_dir/hooks"
  mkdir -p "$hook_dir"
  local hook_target="$hook_dir/pre-commit"

  local SENTINEL='# pipelinekit pre-commit dispatcher'

  # Idempotent: if our dispatcher is already installed, no-op.
  if [[ -f "$hook_target" ]] && head -2 "$hook_target" 2>/dev/null | grep -qF "$SENTINEL"; then
    log "INSTALL_PRE_COMMIT_ALREADY_INSTALLED: $hook_target"
    return 0
  fi

  # Collision: preserve any pre-existing alien hook (regular file OR symlink).
  if [[ -e "$hook_target" || -L "$hook_target" ]]; then
    local backup="$hook_target.pre-pipelinekit"
    [[ -e "$backup" ]] && backup="$backup.$(date +%s)"
    mv "$hook_target" "$backup"
    log "INSTALL_PRE_COMMIT_BACKED_UP: $backup"
  fi

  # Write dispatcher (chains both hooks; each guarded by existence check).
  cat > "$hook_target" <<DISPATCH
#!/usr/bin/env bash
$SENTINEL -- chains validate-task-spec.py + scan-secrets-staged.sh
set -e
VALIDATE="$validate_src"
SCANNER="$scanner_src"
if [[ -f "\$VALIDATE" ]]; then
  python3 "\$VALIDATE" || exit \$?
fi
if [[ -f "\$SCANNER" ]]; then
  bash "\$SCANNER" || exit \$?
fi
exit 0
DISPATCH
  chmod +x "$hook_target"
  log "INSTALL_PRE_COMMIT_HOOK_WRITTEN: $hook_target"
}

# ---------- optional: settings.json hook wiring ----------
# Gated by CLAUDE_INSTALL_SETTINGS=1. Off by default — safe for existing users.
# When the flag is unset and the previous install backed up a settings.json,
# restore it into the new overlay so user customizations survive the swap.
# $1 = backup dir (the $BACKUP path captured at swap time, or "" if no backup).
maybe_install_settings() {
  local backup_dir="${1:-}"
  local target="$CLAUDE_HOME/settings.json"

  if [[ "${CLAUDE_INSTALL_SETTINGS:-}" == "1" ]]; then
    # Opt-in: back up any existing settings.json (may live in the backup dir from
    # the overlay swap, since the swap moves $CLAUDE_HOME wholesale), then write
    # the hook template.
    local prev_settings=""
    if [[ -f "$target" ]]; then
      prev_settings="$target"
    elif [[ -n "$backup_dir" && -f "$backup_dir/settings.json" ]]; then
      prev_settings="$backup_dir/settings.json"
    fi
    if [[ -n "$prev_settings" ]]; then
      local bak
      bak="$target.bak-$(date +%s)"
      cp -a "$prev_settings" "$bak"
      log "Backed up existing settings.json → $bak"
    fi
    python3 - "$CLAUDE_HOME" "${prev_settings:-}" <<'PYEOF'
import json, os, sys

h = sys.argv[1]

# Additive merge: preserve ALL top-level keys from the prior settings.json,
# overlay pipelinekit env defaults UNDER any prior env (user wins on collision),
# then re-attach the pipelinekit-canonical hooks block last.
prev_settings_path = sys.argv[2] if len(sys.argv) > 2 else ""
prev = {}
if prev_settings_path and os.path.exists(prev_settings_path):
    try:
        with open(prev_settings_path, "r", encoding="utf-8") as pf:
            loaded = json.load(pf)
        if isinstance(loaded, dict):
            prev = loaded
    except (json.JSONDecodeError, OSError):
        prev = {}

new_env_defaults = {
    "CLAUDE_CODE_DISABLE_1M_CONTEXT": "1",
}
# User wins on collision — never clobber an explicitly-set value.
existing_env = dict(prev.get("env", {})) if isinstance(prev.get("env"), dict) else {}
merged_env = {**new_env_defaults, **existing_env}

def hook(cmd, args=None):
    return [{"type": "command", "command": cmd, "args": args or []}]

# Start from prior top-level keys, drop pipelinekit-owned hooks, then re-assemble.
settings = {k: v for k, v in prev.items() if k != "hooks"}
settings["env"] = merged_env
settings["hooks"] = {
        "SessionStart": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/session-start-caveman.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/session-start-context.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/kill-rogue-mcp-daemon.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/mcp-rss-cap.sh")}
        ],
        "PreToolUse": [
            {"matcher": "Agent",      "hooks": hook(f"{h}/hooks/agent-caveman-gate.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/block-dangerous-commands.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/block-push-main.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/block-stage-sensitive.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/env-scrub.py")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/test-logger.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/validate-commit-msg.sh")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/claude-md-guard.py")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/pre-edit-protect.sh")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/tdd-order-check.sh")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/tdd-red-phase-gate.sh")},
            {"matcher": "Skill",      "hooks": hook(f"{h}/hooks/skill_budget.py")},
            {"matcher": "Write",      "hooks": hook(f"{h}/hooks/block-bare-repo-markers.py")}
        ],
        "PostToolUse": [
            {"matcher": "Edit|Write",   "hooks": hook(f"{h}/hooks/post-edit-format.sh")},
            {"matcher": "WebFetch|Read","hooks": hook(f"{h}/hooks/scan-tool-output.sh")},
            {"matcher": "Bash",         "hooks": hook(f"{h}/hooks/strip-ai-attribution.sh")}
        ],
        "Stop": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/memory-journal.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/stop-completion-gate.sh")}
        ],
        "SubagentStop": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/verify-worktree-commit.sh")}
        ],
        "Notification": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/denial_tracker.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")}
        ],
        "PermissionRequest": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")}
        ],
        "PostCompact": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/context-warning.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/post-compact-context.sh")}
        ],
        "UserPromptSubmit": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/context-budget-advisor.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/subagent-first-nudge.sh")}
        ]
}

dst = os.path.join(h, "settings.json")
with open(dst, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"installed: {dst} (28 hooks wired, {len(merged_env)} env vars)")
PYEOF

    # Activate caveman mode immediately. session-start-caveman.sh touches this
    # marker on the NEXT session, but the agent-caveman-gate.sh PreToolUse hook
    # (wired just above) needs it present NOW for the rest of THIS session.
    # Respect the .caveman-off opt-out, mirroring session-start-caveman.sh.
    if [[ -e "$CLAUDE_HOME/.caveman-off" ]]; then
      log "Skipped caveman activation (.caveman-off present)"
    else
      mkdir -p "$CLAUDE_HOME"
      touch "$CLAUDE_HOME/.caveman-active"
      log "Activated caveman mode (touched $CLAUDE_HOME/.caveman-active)"
    fi
  else
    # Flag not set: restore user's previous settings.json from backup if present.
    if [[ -n "$backup_dir" && -f "$backup_dir/settings.json" ]]; then
      cp -a "$backup_dir/settings.json" "$target"
      log "Preserved existing $target (re-run with CLAUDE_INSTALL_SETTINGS=1 to wire hooks)"
    fi
  fi
}

# ---------- help dispatcher ----------
# Short-circuit: `bash scripts/install.sh --help` prints version + usage and exits 0.
# First line MUST be `pipelinekit v<VERSION>` (regression-checked by AC #3 grep).
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf 'pipelinekit v%s\n' "$PIPELINEKIT_VERSION"
  cat <<'HELP'

Usage: bash scripts/install.sh [--help|-h] [--selftest]

  --help, -h    Print version + usage and exit 0.
  --selftest    Run the embedded selftest harness and exit.

Environment variables (selected):
  CLAUDE_HOME                       Target overlay dir (default: $HOME/.claude)
  CLAUDE_INSTALL_NONINTERACTIVE=1   Skip all prompts; assume sane defaults.
  CLAUDE_INSTALL_SETTINGS=1         Wire optional hooks into ~/.claude/settings.json.
  SERENA_REF                        serena MCP commit ref (default: main).
  CLAUDE_CLI_SHA256                 Optional sha256 of https://claude.ai/install.sh.

Source: https://github.com/Bruce188/pipelinekit
HELP
  exit 0
fi

# ---------- selftest dispatcher ----------
# Short-circuit: `bash scripts/install.sh --selftest` runs only the selftest harness
# and exits before touching the filesystem (STAGE/mv/BACKUP surface). Positioned
# after all function definitions so selftests can reference any function above.
if [[ "${1:-}" == "--selftest" ]]; then _selftest_main; exit $?; fi

# ---------- preflight ----------
command -v bash    >/dev/null || die "bash required"
command -v git     >/dev/null || die "git required"
command -v python3 >/dev/null || die "python3 required (used by hooks for JSON parsing)"
command -v rsync   >/dev/null || die "rsync required"

log "pipelinekit v$PIPELINEKIT_VERSION"

NONINTERACTIVE="${CLAUDE_INSTALL_NONINTERACTIVE:-0}"
ask() {
  local prompt="$1" default="$2" var
  if [[ "$NONINTERACTIVE" == "1" ]]; then
    printf '%s\n' "$default"
    return
  fi
  read -r -p "$prompt [$default]: " var
  printf '%s\n' "${var:-$default}"
}

# ---------- stage overlay atomically (avoids TOCTOU on $CLAUDE_HOME) ----------
STAGE="$CLAUDE_HOME.new-$TS"
log "Staging overlay at $STAGE"
mkdir -p "$STAGE"
rsync -a \
  --exclude='memory/projects' \
  --exclude='.credentials.json' \
  --exclude='*.bak' \
  --exclude='__pycache__' \
  "$REPO_ROOT/claude/" "$STAGE/"

# Hooks must be executable (recursive — subdirs may contain helpers).
find "$STAGE/hooks" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod +x {} +

# ---------- swap into place ----------
# Resolve actual target (symlinks rejected: stale symlinks are unsafe to follow).
if [[ -L "$CLAUDE_HOME" ]]; then
  log "Removing stale symlink at $CLAUDE_HOME"
  rm "$CLAUDE_HOME"
fi
BACKUP=""
if [[ -e "$CLAUDE_HOME" ]]; then
  BACKUP="$CLAUDE_HOME.bak-$TS"
  log "Existing $CLAUDE_HOME → backing up to $BACKUP"
  mv "$CLAUDE_HOME" "$BACKUP"
fi
mv "$STAGE" "$CLAUDE_HOME"
maybe_install_settings "$BACKUP"

# ---------- render CLAUDE.md from template ----------
# Use python3 with env-var-driven substitution; sed is unsafe when values contain
# pipe/backslash/ampersand/newline (e.g. multiline git config user.name).
if [[ -f "$CLAUDE_HOME/CLAUDE.md.template" ]]; then
  log "Rendering CLAUDE.md from template"
  export _CP_CLAUDE_HOME="$CLAUDE_HOME"
  export _CP_USER_EMAIL="${USER_EMAIL:-$(git config --global user.email 2>/dev/null || echo 'you@example.com')}"
  export _CP_USER_NAME="${USER_NAME:-$(git config --global user.name 2>/dev/null || echo 'developer')}"
  python3 - "$CLAUDE_HOME/CLAUDE.md.template" "$CLAUDE_HOME/CLAUDE.md" <<'PYEOF'
import os, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src, 'r', encoding='utf-8') as f:
    body = f.read()
# Strip control chars from substitution values; cap length to 200 chars.
def clean(v):
    return ''.join(c for c in v if c == '\t' or c == ' ' or (c.isprintable() and ord(c) >= 32))[:200]
mapping = {
    '${CLAUDE_HOME}': clean(os.environ.get('_CP_CLAUDE_HOME', '')),
    '${USER_EMAIL}':  clean(os.environ.get('_CP_USER_EMAIL', '')),
    '${USER_NAME}':   clean(os.environ.get('_CP_USER_NAME', '')),
}
for k, v in mapping.items():
    body = body.replace(k, v)
with open(dst, 'w', encoding='utf-8') as f:
    f.write(body)
PYEOF
  unset _CP_CLAUDE_HOME _CP_USER_EMAIL _CP_USER_NAME
fi

# ---------- deploy-mode overlay ----------
# Activates the per-provider mini-CLAUDE.md fragment (claude/modes/<provider>.md)
# referenced from CLAUDE.md.template as `@~/.claude/modes/active.md`. Reads
# docs/active-deployment for the provider slug. Absent file ⇒ strip overlay line.
provision_modes_overlay

# ---------- native git commit-msg hook ----------
# Symlinks <git_dir>/hooks/commit-msg → claude/hooks/commit-msg-wrapper.sh so the
# conventional-commit gate fires on EVERY git commit (bare shell, CI, IDE,
# Claude-mediated alike) — not just commits driven through the harness
# PreToolUse event. Idempotent, worktree-compat, backs up alien hooks.
install_native_commit_msg_hook

# ---------- native git pre-commit hook (secret scanner chain) ----------
# Writes <git_dir>/hooks/pre-commit dispatcher that chains the task-spec
# validator with the gitleaks-backed secret scanner. Both chained hooks
# degrade gracefully when their dependencies (gitleaks binary; staged
# task-spec files) are absent. Idempotent + backs up alien hooks.
install_pre_commit_hook

# ---------- env file ----------
ENV_FILE="$REPO_ROOT/.env"
if [[ -f "$ENV_FILE" && "${CLAUDE_REFRESH_ENV:-0}" != "1" ]]; then
  log "Existing $ENV_FILE preserved (set CLAUDE_REFRESH_ENV=1 to overwrite)"
else
  cat > "$ENV_FILE" <<EOF
# pipelinekit local env (re-generated by install.sh)
CLAUDE_HOME=$CLAUDE_HOME
USER_EMAIL=${USER_EMAIL:-you@example.com}
USER_NAME=${USER_NAME:-developer}
PIPELINE_NIT_FIRST=0
# Supply-chain pins (override before re-running install for reproducibility)
SERENA_REF=$SERENA_REF
EOF
  log "Wrote $ENV_FILE"
fi

# ---------- optionals (deprecated env-var, all components default-on) ----------
[[ -n "${CLAUDE_INSTALL_OPTIONALS:-}" ]] && log "CLAUDE_INSTALL_OPTIONALS is deprecated; flag is a no-op (kept for backward-compat). All components install by default."

# tresor already bundled in overlay copy step; no-op confirmation.
log "Tresor resources present at $CLAUDE_HOME/tresor-resources"

# LSP servers. Each failure increments LSP_FAILURES; summary printed at end.
log "Installing LSP servers (pyright, typescript, csharp, gopls, rust-analyzer)"
# --ignore-scripts denies postinstall RCE from typosquats; safe for these known packages.
if command -v npm >/dev/null; then
  npm install -g --silent --ignore-scripts pyright typescript typescript-language-server 2>>"$LOG" \
    || { warn "npm LSP install partial"; LSP_FAILURES=$((LSP_FAILURES+1)); }
fi
if command -v dotnet >/dev/null; then
  dotnet tool install --global csharp-ls 2>>"$LOG" \
    || warn "csharp-ls already installed or failed"
fi
if command -v go >/dev/null; then
  go install golang.org/x/tools/gopls@latest 2>>"$LOG" \
    || { warn "gopls install failed"; LSP_FAILURES=$((LSP_FAILURES+1)); }
fi
if command -v rustup >/dev/null; then
  rustup component add rust-analyzer 2>>"$LOG" \
    || { warn "rust-analyzer add failed"; LSP_FAILURES=$((LSP_FAILURES+1)); }
fi

# Swift LSP (macOS only; ships with Xcode — no separate install).
if [[ "$(uname -s)" == "Darwin" ]]; then
  if command -v xcrun >/dev/null && xcrun --find sourcekit-lsp >/dev/null 2>&1; then
    log "sourcekit-lsp present (bundled with Xcode)"
  else
    warn "sourcekit-lsp not found — install full Xcode (App Store) to enable Swift LSP"
    # Intentionally not incrementing LSP_FAILURES — sourcekit-lsp ships with Xcode, not a separate install.
  fi
else
  warn "sourcekit-lsp is macOS-only (ships with Xcode); skipping on $(uname -s)"
  # Intentionally not incrementing LSP_FAILURES — platform-skip is not a failure.
fi

# Kotlin LSP (cross-platform). On Darwin use brew; elsewhere fall back to pinned binary release.
if command -v kotlin-language-server >/dev/null; then
  log "kotlin-language-server already installed; skipping"
elif [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null; then
  brew install kotlin-language-server 2>>"$LOG" \
    || { warn "kotlin-language-server brew install failed"; LSP_FAILURES=$((LSP_FAILURES+1)); }
else
  KLS_VERSION="${KLS_VERSION:-1.3.13}"
  KLS_URL="https://github.com/fwcd/kotlin-language-server/releases/download/${KLS_VERSION}/server.zip"
  KLS_DIR="$HOME/.local/share/kotlin-language-server"
  mkdir -p "$HOME/.local/bin" "$KLS_DIR"
  if command -v curl >/dev/null && command -v unzip >/dev/null \
     && curl -fsSL -o /tmp/kls.zip "$KLS_URL" \
     && unzip -q -o /tmp/kls.zip -d "$KLS_DIR" \
     && ln -sf "$KLS_DIR/server/bin/kotlin-language-server" "$HOME/.local/bin/kotlin-language-server" \
     && chmod +x "$HOME/.local/bin/kotlin-language-server"; then
    log "kotlin-language-server installed to $HOME/.local/bin (v${KLS_VERSION})"
    rm -f /tmp/kls.zip
  else
    warn "kotlin-language-server install failed (curl/unzip missing or download failed)"
    LSP_FAILURES=$((LSP_FAILURES+1))
    rm -f /tmp/kls.zip
  fi
fi

# MCP servers (npx-based, no global install).
log "Provisioning .mcp.json template (copy to project roots as needed)"
if [[ -f "$REPO_ROOT/.mcp.json.template" ]]; then
  log "  -> cp $REPO_ROOT/.mcp.json.template <your-project>/.mcp.json"
fi

# Serena (semantic MCP). Pinnable via $SERENA_REF.
# Fail-closed supply-chain gate: refuse rolling 'main' unless explicit opt-out.
if [[ "$SERENA_REF" == "main" && "${SERENA_ALLOW_ROLLING:-0}" != "1" ]]; then
  cat >&2 <<'SERENA_REFUSE'
[install][error] Refusing to install serena from rolling ref 'main'.

The serena MCP is installed from git+https://github.com/oraios/serena and
loaded at MCP-client startup; an upstream takeover at the floating 'main'
branch would execute arbitrary code on your host. Choose one:

  1. Pin to a commit SHA (recommended):
       export SERENA_REF=<40-char commit hash>
     A current pin is documented in .mcp.json.template under the
     serena entry.

  2. Opt out of the safety gate (NOT recommended for shared / CI hosts):
       export SERENA_ALLOW_ROLLING=1

Re-run the installer after setting one of the above.
SERENA_REFUSE
  die "serena rolling-ref refusal (set SERENA_REF=<sha> or SERENA_ALLOW_ROLLING=1)"
fi
log "Installing serena (semantic code MCP) @ ref=$SERENA_REF"
if [[ "$SERENA_REF" == "main" ]]; then
  warn "serena pinned to 'main' (rolling) — SERENA_ALLOW_ROLLING=1 acknowledged. Pin to a SHA in CI/prod."
fi
if command -v uv >/dev/null; then
  uv tool install --quiet "git+https://github.com/oraios/serena@${SERENA_REF}" 2>>"$LOG" || warn "serena install failed"
else
  pip install --quiet "git+https://github.com/oraios/serena@${SERENA_REF}" 2>>"$LOG" || warn "serena install failed (need uv or pip)"
fi

# Agentmemory MCP (default-on; cloud embeddings preferred with local-ONNX-quant fallback).
log "Provisioning agentmemory MCP (default-on; cloud embeddings preferred)"
provision_agentmemory_mcp
provision_understand_anything
provision_codegraph_mcp
provision_graphify_mcp
provision_serena_mcp

# gstack is a third-party overlay project (alirezarezvani/gstack); install instructions live in its own README.
log "gstack is a third-party overlay; for install instructions see https://github.com/alirezarezvani/gstack"

# Mobile MCPs (XcodeBuildMCP + ios-simulator-mcp). Both pulled JIT via npx/uvx — no global install.
log "Mobile MCPs available as advisory uncomment-to-enable in .mcp.json.template:"
log "  - XcodeBuildMCP      (iOS build automation; requires Xcode on host)"
log "  - ios-simulator-mcp  (iOS Simulator control; requires Xcode on host)"
if [[ -f "$REPO_ROOT/.mcp.json.template" ]]; then
  log "  -> Uncomment the _mobile_mcpServers block in .mcp.json.template before copying into <your-project>/.mcp.json"
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
  warn "Mobile MCPs require Xcode on host. $(uname -s) detected — XcodeBuildMCP supports remote macOS builds; ios-simulator-mcp will not function locally."
fi

# Azure CLI. Auto-installed via Microsoft-published one-liner on Debian/Ubuntu.
#
# Trust posture for Azure CLI install:
#
#   Default path (no env var) — curl-to-bash from https://aka.ms/InstallAzureCLIDeb.
#   Microsoft does not publish a sha256 for this script, so trust is bound to the
#   https origin (and CT logs). This is the same trust path documented at
#   https://learn.microsoft.com/cli/azure/install-azure-cli-linux. Equivalent to
#   prior pipelinekit behaviour; preserved as the default for backward-compat.
#
#   Opt-in verified path — set INSTALL_AZURE_CLI_DOWNLOAD_AND_VERIFY=1 and provide
#   AZURE_CLI_DEB_URL plus AZURE_CLI_DEB_SHA256. The installer downloads the .deb,
#   verifies sha256, and installs via `dpkg -i`. Mismatch → die. .deb files are
#   published under https://packages.microsoft.com/repos/azure-cli/pool/main/a/azure-cli/.
#
# User is responsible for `az login` afterwards — the install does NOT authenticate.
if command -v az >/dev/null; then
  log "az already installed; skipping (run 'az version' to check version)"
elif [[ "$(uname -s)" == "Linux" ]]; then
  if [[ -f /etc/os-release ]] && grep -qE 'ID(_LIKE)?=.*(ubuntu|debian)' /etc/os-release; then
    if [[ "${INSTALL_AZURE_CLI_DOWNLOAD_AND_VERIFY:-0}" == "1" ]]; then
      az_deb_url="${AZURE_CLI_DEB_URL:-}"
      az_deb_sha="${AZURE_CLI_DEB_SHA256:-}"
      if [[ -z "$az_deb_url" || -z "$az_deb_sha" ]]; then
        warn "INSTALL_AZURE_CLI_DOWNLOAD_AND_VERIFY=1 requires both AZURE_CLI_DEB_URL and AZURE_CLI_DEB_SHA256 — falling back to curl-to-bash default."
        log "Installing Azure CLI via Microsoft one-liner (https://aka.ms/InstallAzureCLIDeb) — default trust path"
        if curl -sL https://aka.ms/InstallAzureCLIDeb | bash 2>>"$LOG"; then
          log "Azure CLI installed."
        else
          warn "Azure CLI install failed — see $LOG. Manual install: https://learn.microsoft.com/cli/azure/install-azure-cli-linux"
        fi
      else
        log "Azure CLI verified-path install: $az_deb_url (sha256 verify on)"
        az_tmp="$(mktemp /tmp/azure-cli.XXXXXX.deb)"
        if curl -fsSL "$az_deb_url" -o "$az_tmp" 2>>"$LOG"; then
          if echo "${az_deb_sha}  ${az_tmp}" | sha256sum -c - >>"$LOG" 2>&1; then
            if sudo -n true 2>/dev/null; then
              sudo dpkg -i "$az_tmp" 2>>"$LOG" || warn "dpkg -i azure-cli failed — see $LOG"
            else
              dpkg -i "$az_tmp" 2>>"$LOG" || warn "dpkg -i azure-cli failed (no sudo) — see $LOG"
            fi
            log "Azure CLI installed via verified .deb."
          else
            rm -f "$az_tmp"
            die "Azure CLI .deb sha256 mismatch (expected ${az_deb_sha}). Refusing to install."
          fi
        else
          warn "Azure CLI .deb download failed from $az_deb_url — see $LOG."
        fi
        rm -f "$az_tmp"
      fi
    else
      log "Installing Azure CLI via Microsoft one-liner (https://aka.ms/InstallAzureCLIDeb) — default trust path"
      log "  (opt-in sha256-verified path: INSTALL_AZURE_CLI_DOWNLOAD_AND_VERIFY=1 + AZURE_CLI_DEB_URL + AZURE_CLI_DEB_SHA256)"
      if curl -sL https://aka.ms/InstallAzureCLIDeb | bash 2>>"$LOG"; then
        log "Azure CLI installed. Authenticate yourself with the standard interactive sign-in (the installer does not log you in)."
      else
        warn "Azure CLI install failed — see $LOG. Manual install: https://learn.microsoft.com/cli/azure/install-azure-cli-linux"
      fi
    fi
  else
    warn "Azure CLI auto-install supports Debian/Ubuntu only. Other Linux distros: see https://learn.microsoft.com/cli/azure/install-azure-cli-linux"
  fi
elif [[ "$(uname -s)" == "Darwin" ]]; then
  warn "Azure CLI on macOS: install via Homebrew — 'brew install azure-cli' (auto-install is Debian/Ubuntu-only)"
else
  warn "Azure CLI auto-install skipped on $(uname -s). See https://learn.microsoft.com/cli/azure/install-azure-cli"
fi

# Vercel CLI. Probed via PATH; install + authenticate manually outside Claude.
# Prints the official npm install one-liner and reminds the user to run
# `vercel login` themselves. Never auto-installs the CLI and NEVER auto-authenticates.
# NEVER auto-run `vercel login` — user authenticates manually outside Claude.
if command -v vercel >/dev/null 2>&1; then
  log "vercel CLI already installed; skipping (run 'vercel --version' to check version)"
else
  warn "Vercel CLI not on PATH. Install: npm i -g vercel"
fi
log "Authenticate via: vercel login   (run outside Claude before invoking /pipeline)"

# Claude-Context MCP (community — @zilliztech, NOT Anthropic). Codebase semantic RAG via npx;
# AST-aware chunking + Merkle-tree incremental indexing. local-mode (no Milvus account) is
# documented in .mcp.json.template; cloud-mode uses Milvus/Zilliz creds via env vars.
# Skip below ~50k LOC: indexing adds latency with no semantic-retrieval benefit at that scale.
log "Claude-Context MCP available (community — @zilliztech/claude-context, NOT Anthropic)."
log "  - Codebase semantic RAG: AST-aware chunking + Merkle-tree incremental indexing"
log "  - local-mode setup: see .mcp.json.template _claude_context_mcpServers block for env-var skeleton"
log "  - cloud-mode setup: same block — swap in MILVUS_ADDRESS / MILVUS_TOKEN for Zilliz cloud"
log "  - 50k LOC heuristic: /analyze skips semantic retrieval below 50000 LOC; opt-in indexing on smaller repos via direct MCP query"
log "  - Re-indexing budget: <5s per 'git pull' (upstream benchmark; not a guarantee)"
if [[ -f "$REPO_ROOT/.mcp.json.template" ]]; then
  log "  -> Uncomment the _claude_context_mcpServers block in .mcp.json.template before copying into <your-project>/.mcp.json"
fi
warn "@zilliztech/claude-context is a community MCP (NOT Anthropic-official). Review upstream before sandbox use; PIN the npx package to a specific version for reproducibility."


# claude-skills is a third-party skill collection (alirezarezvani/claude-skills); install instructions live in its own README.
log "claude-skills is a third-party skill collection; for install instructions see https://github.com/alirezarezvani/claude-skills"

# Claude CLI version-floor check for EnterWorktree / ExitWorktree (v2.1.72+).
# Soft: warn only. Below-floor users keep working via the manual `git worktree add` fallback.
if command -v claude >/dev/null 2>&1; then
  CLAUDE_VER=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  if [[ -z "$CLAUDE_VER" ]]; then
    warn "could not parse Claude CLI version from 'claude --version' output"
  else
    MIN_VER="2.1.72"
    LOWEST=$(printf '%s\n%s\n' "$CLAUDE_VER" "$MIN_VER" | sort -V | head -1)
    if [[ "$LOWEST" != "$MIN_VER" ]]; then
      warn "Claude CLI ${CLAUDE_VER} is below ${MIN_VER}. Native EnterWorktree / ExitWorktree tools will be unavailable; pipelinekit will fall back to manual 'git worktree add'. Upgrade with: https://claude.ai/install.sh"
    fi
  fi
fi

# ---------- verify ----------
log "Verifying install"
bash "$SCRIPT_DIR/verify.sh" || warn "Verification reported issues — see $LOG"

if [[ "$LSP_FAILURES" -gt 0 ]]; then
  warn "LSP install had $LSP_FAILURES failure(s) — language-server features will be limited until fixed. See $LOG."
fi

log "Install complete. Open a new terminal and run: claude"
log "Tell Claude:  /pipeline   (after creating docs/features.md in your project)"
log "Tip: to wire the optional hooks (cost logging, env scrubbing, TDD gate, notify-emit, etc.), re-run with CLAUDE_INSTALL_SETTINGS=1"
