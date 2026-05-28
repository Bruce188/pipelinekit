#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

# detect_applicable_mcps.sh — pure detection helper for pipeline Step 0.5 (MCP Preflight).
#
# PURE: NO network I/O, NO `claude mcp list`, NO `claude mcp add` — filesystem detection + emit only.
#
# Subcommands:
#   --applicable       Emit applicable MCP names, one per line (always-on 3 first, then serena if applicable)
#   --wire-cmd <mcp>   Emit the exact `claude mcp add ...` command string (or VERIFY_ONLY for agentmemory)
#   --auto-wire-set    Emit the 4 auto-wireable MCP names, one per line
#   --suggestions      Emit the 3 suggestion-only MCP names, one per line
#   --selftest         Run built-in hermetic assertions; prints "selftest: N/N PASS"; exits 0 on success
#
# Built-in applicable-MCP map:
#   MCP                  Applicability                     Auto-wire?
#   context7             always                            yes
#   agentmemory          always (install-provisioned)      yes (verify-only — NEVER runs mcp add)
#   sequential-thinking  always-optional                   yes
#   serena               repo has source in a serena-      yes
#                          supported language
#   codegraph            SUGGESTION only                   NEVER
#   graphify             SUGGESTION only                   NEVER
#   local-rag            SUGGESTION only                   NEVER
#
# Serena applicability: repo contains a source file in a serena-supported language.
# Extension map (derived from .serena/project.yml enumeration):
#   .py→python  .ts .tsx .js .jsx→typescript  .go→go  .rs→rust  .java→java
#   .cs→csharp  .rb→ruby  .php→php  .c .h .cpp .cc .hpp .hh .cxx→cpp
#   .kt .kts→kotlin  .scala→scala  .swift→swift  .zig→zig  .sh .bash→bash
#   .lua→lua  .dart→dart  .ex .exs→elixir  .clj .cljs→clojure  .hs→haskell
#
# Wire commands (verbatim — helper EMITS them; orchestrator EXECUTES them):
#   context7:            claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp@latest
#   serena:              claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd
#   sequential-thinking: claude mcp add --scope user sequential-thinking -- npx -y @modelcontextprotocol/server-sequential-thinking
#   agentmemory:         VERIFY_ONLY (install-provisioned; do NOT run mcp add)

# ---------------------------------------------------------------------------
# Serena language probe — extension-based, bounded depth, skip-dirs applied.
# Returns 0 if serena is applicable, 1 otherwise.
# ---------------------------------------------------------------------------
_serena_applicable() {
  # Prune dirs: .git, node_modules, .serena/cache, __pycache__
  # Extensions (ordered by likelihood for speed):
  #   .sh .bash .py .ts .tsx .js .jsx .go .rs .java .cs .rb .php
  #   .c .h .cpp .cc .hpp .hh .cxx .kt .kts .scala .swift .zig
  #   .lua .dart .ex .exs .clj .cljs .hs
  local match
  match=$(find . -maxdepth 6 \
    \( -name '.git' -o -name 'node_modules' -o -name '__pycache__' \
       -o -path '*/.serena/cache' \) -prune \
    -o -type f \( \
         -name '*.sh'   -o -name '*.bash' \
      -o -name '*.py'   \
      -o -name '*.ts'   -o -name '*.tsx'  -o -name '*.js'   -o -name '*.jsx' \
      -o -name '*.go'   \
      -o -name '*.rs'   \
      -o -name '*.java' \
      -o -name '*.cs'   \
      -o -name '*.rb'   \
      -o -name '*.php'  \
      -o -name '*.c'    -o -name '*.h'    -o -name '*.cpp'  -o -name '*.cc' \
      -o -name '*.hpp'  -o -name '*.hh'   -o -name '*.cxx'  \
      -o -name '*.kt'   -o -name '*.kts'  \
      -o -name '*.scala'\
      -o -name '*.swift'\
      -o -name '*.zig'  \
      -o -name '*.lua'  \
      -o -name '*.dart' \
      -o -name '*.ex'   -o -name '*.exs'  \
      -o -name '*.clj'  -o -name '*.cljs' \
      -o -name '*.hs'   \
    \) -print -quit 2>/dev/null || true)
  [[ -n "$match" ]]
}

# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

cmd_applicable() {
  # Always-on three (deterministic order: context7, agentmemory, sequential-thinking)
  printf 'context7\n'
  printf 'agentmemory\n'
  printf 'sequential-thinking\n'
  # Serena: applicable iff repo has a serena-supported source file
  if _serena_applicable; then
    printf 'serena\n'
  fi
}

cmd_wire_cmd() {
  local mcp="${1:-}"
  case "$mcp" in
    context7)
      printf 'claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp@latest\n'
      ;;
    serena)
      printf 'claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd\n'
      ;;
    sequential-thinking)
      printf 'claude mcp add --scope user sequential-thinking -- npx -y @modelcontextprotocol/server-sequential-thinking\n'
      ;;
    agentmemory)
      # install-provisioned: verify-only sentinel — orchestrator interprets as "do NOT mcp add"
      printf 'VERIFY_ONLY\n'
      ;;
    codegraph|graphify|local-rag)
      printf 'error: %s is suggestion-only — no auto-wire command exists\n' "$mcp" >&2
      return 2
      ;;
    "")
      printf 'usage: detect_applicable_mcps.sh --wire-cmd <mcp>\n' >&2
      return 2
      ;;
    *)
      printf 'error: unknown MCP %s — no wire command\n' "$mcp" >&2
      return 2
      ;;
  esac
}

cmd_auto_wire_set() {
  # Exactly the 4 auto-wireable names (codegraph/graphify/local-rag MUST be absent)
  printf 'context7\n'
  printf 'agentmemory\n'
  printf 'serena\n'
  printf 'sequential-thinking\n'
}

cmd_suggestions() {
  # Advisory only — never auto-wired
  printf 'codegraph\n'
  printf 'graphify\n'
  printf 'local-rag\n'
}

cmd_selftest() {
  local pass=0
  local total=0
  local failed=0

  _assert() {
    local desc="$1" got="$2" expected="$3"
    total=$((total + 1))
    if [[ "$got" == "$expected" ]]; then
      pass=$((pass + 1))
    else
      printf 'selftest FAIL [%s]: expected %q, got %q\n' "$desc" "$expected" "$got" >&2
      failed=$((failed + 1))
    fi
  }

  _assert_contains() {
    local desc="$1" haystack="$2" needle="$3"
    total=$((total + 1))
    if printf '%s' "$haystack" | grep -qF "$needle"; then
      pass=$((pass + 1))
    else
      printf 'selftest FAIL [%s]: output did not contain %q\n' "$desc" "$needle" >&2
      failed=$((failed + 1))
    fi
  }

  _assert_not_contains() {
    local desc="$1" haystack="$2" needle="$3"
    total=$((total + 1))
    if ! printf '%s' "$haystack" | grep -qF "$needle"; then
      pass=$((pass + 1))
    else
      printf 'selftest FAIL [%s]: output unexpectedly contained %q\n' "$desc" "$needle" >&2
      failed=$((failed + 1))
    fi
  }

  # --- Test 1: wire-cmd context7
  _assert "wire-cmd context7" \
    "$(cmd_wire_cmd context7)" \
    "claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp@latest"

  # --- Test 2: wire-cmd serena
  _assert "wire-cmd serena" \
    "$(cmd_wire_cmd serena)" \
    "claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd"

  # --- Test 3: wire-cmd sequential-thinking
  _assert "wire-cmd sequential-thinking" \
    "$(cmd_wire_cmd sequential-thinking)" \
    "claude mcp add --scope user sequential-thinking -- npx -y @modelcontextprotocol/server-sequential-thinking"

  # --- Test 4: wire-cmd agentmemory → VERIFY_ONLY
  _assert "wire-cmd agentmemory" "$(cmd_wire_cmd agentmemory)" "VERIFY_ONLY"

  # --- Test 5: wire-cmd suggestion-only returns exit 2
  if cmd_wire_cmd codegraph >/dev/null 2>&1; then
    printf 'selftest FAIL [wire-cmd codegraph should exit 2]: returned 0\n' >&2
    failed=$((failed + 1))
  else
    pass=$((pass + 1))
  fi
  total=$((total + 1))

  # --- Test 6: auto-wire-set has exactly 4 names, no suggestions
  local aws
  aws=$(cmd_auto_wire_set)
  _assert_contains "auto-wire-set contains context7" "$aws" "context7"
  _assert_contains "auto-wire-set contains agentmemory" "$aws" "agentmemory"
  _assert_contains "auto-wire-set contains serena" "$aws" "serena"
  _assert_contains "auto-wire-set contains sequential-thinking" "$aws" "sequential-thinking"
  _assert_not_contains "auto-wire-set excludes codegraph" "$aws" "codegraph"
  _assert_not_contains "auto-wire-set excludes graphify" "$aws" "graphify"
  _assert_not_contains "auto-wire-set excludes local-rag" "$aws" "local-rag"

  # --- Test 7: suggestions
  local sugg
  sugg=$(cmd_suggestions)
  _assert_contains "suggestions contains codegraph" "$sugg" "codegraph"
  _assert_contains "suggestions contains graphify" "$sugg" "graphify"
  _assert_contains "suggestions contains local-rag" "$sugg" "local-rag"

  # --- Test 8: serena applicable in python sandbox
  local sandbox1
  sandbox1=$(mktemp -d)
  trap "rm -rf '$sandbox1'" EXIT
  touch "$sandbox1/app.py"
  if (cd "$sandbox1" && _serena_applicable); then
    pass=$((pass + 1))
  else
    printf 'selftest FAIL [serena applicable in py sandbox]: expected applicable\n' >&2
    failed=$((failed + 1))
  fi
  total=$((total + 1))

  # --- Test 9: serena NOT applicable in docs-only sandbox
  local sandbox2
  sandbox2=$(mktemp -d)
  trap "rm -rf '$sandbox2'" EXIT
  touch "$sandbox2/README.md" "$sandbox2/notes.txt"
  if ! (cd "$sandbox2" && _serena_applicable); then
    pass=$((pass + 1))
  else
    printf 'selftest FAIL [serena not applicable in docs-only sandbox]: expected NOT applicable\n' >&2
    failed=$((failed + 1))
  fi
  total=$((total + 1))

  # --- Test 10: serena applicable in bash sandbox (.sh file)
  local sandbox3
  sandbox3=$(mktemp -d)
  trap "rm -rf '$sandbox3'" EXIT
  touch "$sandbox3/run.sh"
  if (cd "$sandbox3" && _serena_applicable); then
    pass=$((pass + 1))
  else
    printf 'selftest FAIL [serena applicable in sh sandbox]: expected applicable\n' >&2
    failed=$((failed + 1))
  fi
  total=$((total + 1))

  # --- Test 11: --applicable from pipelinekit root includes serena + 3 always-on
  local app_out
  app_out=$(cmd_applicable)
  _assert_contains "applicable includes context7" "$app_out" "context7"
  _assert_contains "applicable includes agentmemory" "$app_out" "agentmemory"
  _assert_contains "applicable includes sequential-thinking" "$app_out" "sequential-thinking"
  _assert_contains "applicable includes serena (pipelinekit has .sh sources)" "$app_out" "serena"

  if [[ $failed -eq 0 ]]; then
    printf 'selftest: %d/%d PASS\n' "$pass" "$total"
    return 0
  else
    printf 'selftest: %d/%d PASS (%d FAILED)\n' "$pass" "$total" "$failed" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

main() {
  case "${1:-}" in
    --applicable)
      cmd_applicable
      ;;
    --wire-cmd)
      shift
      cmd_wire_cmd "${1:-}"
      ;;
    --auto-wire-set)
      cmd_auto_wire_set
      ;;
    --suggestions)
      cmd_suggestions
      ;;
    --selftest)
      cmd_selftest
      ;;
    *)
      printf 'usage: detect_applicable_mcps.sh [--applicable | --wire-cmd <mcp> | --auto-wire-set | --suggestions | --selftest]\n' >&2
      return 2
      ;;
  esac
}

main "$@"
