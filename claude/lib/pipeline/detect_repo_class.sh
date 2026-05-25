#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

# detect_repo_class.sh — derive Repo class + Probe depth for pipeline Step 5.1.
#
# Subcommands:
#   --repo-class   Emit one of: workflow-toolkit | service | web-app | library
#   --probe-depth  Emit one of: light | standard | paranoid (default: standard)
#   --selftest     Run built-in assertions
#
# Precedence for --repo-class (R1; binding):
#   1) workflow-toolkit: scripts/install.sh AND claude/hooks/tests/ both present
#   2) service: *.sln present, OR package.json with "start" script,
#               OR pyproject.toml with [project.scripts]
#   3) web-app: pom.xml, OR package.json with "dev" script,
#               OR pyproject.toml with fastapi|flask|django
#   4) library: fallback

cmd_repo_class() {
  # 1) workflow-toolkit — checked FIRST per R1
  if [[ -f scripts/install.sh && -d claude/hooks/tests ]]; then
    printf 'workflow-toolkit\n'
    return 0
  fi

  # 2) service
  if compgen -G "*.sln" >/dev/null 2>&1; then
    printf 'service\n'
    return 0
  fi
  if [[ -f package.json ]] && python3 -c 'import json,sys; d=json.load(open("package.json")); sys.exit(0 if "start" in d.get("scripts",{}) else 1)' 2>/dev/null; then
    printf 'service\n'
    return 0
  fi
  if [[ -f pyproject.toml ]] && grep -q '^\[project\.scripts\]' pyproject.toml 2>/dev/null; then
    printf 'service\n'
    return 0
  fi

  # 3) web-app
  if [[ -f pom.xml ]]; then
    printf 'web-app\n'
    return 0
  fi
  if [[ -f package.json ]] && python3 -c 'import json,sys; d=json.load(open("package.json")); sys.exit(0 if "dev" in d.get("scripts",{}) else 1)' 2>/dev/null; then
    printf 'web-app\n'
    return 0
  fi
  if [[ -f pyproject.toml ]] && grep -qE '(fastapi|flask|django)' pyproject.toml 2>/dev/null; then
    printf 'web-app\n'
    return 0
  fi

  # 4) library — fallback
  printf 'library\n'
  return 0
}

cmd_probe_depth() {
  if [[ ! -f docs/charter.md ]]; then
    printf 'standard\n'
    printf 'CHARTER_PROBE_DEPTH_DEFAULTED: standard (no charter — --no-charter set on this run)\n' >&2
    return 0
  fi

  # Charter exists — look for ## Production-readiness probe depth H2
  local depth
  depth=$(awk '/^## Production-readiness probe depth$/{flag=1;next} /^## /{flag=0} flag && NF{print;exit}' docs/charter.md 2>/dev/null | tr -d '[:space:]' || true)

  if [[ -z "$depth" ]]; then
    printf 'standard\n'
    printf 'CHARTER_PROBE_DEPTH_DEFAULTED: standard (legacy charter)\n' >&2
    return 0
  fi

  case "$depth" in
    light|standard|paranoid)
      printf '%s\n' "$depth"
      return 0
      ;;
    *)
      printf 'standard\n'
      printf 'CHARTER_PROBE_DEPTH_DEFAULTED: standard (unrecognized value: %s)\n' "$depth" >&2
      return 0
      ;;
  esac
}

cmd_selftest() {
  # Hermetic — operates on $PWD; assumes current repo is workflow-toolkit (pipelinekit).
  local got
  got=$(cmd_repo_class)
  if [[ "$got" != "workflow-toolkit" ]]; then
    printf 'selftest FAIL: --repo-class on pipelinekit expected workflow-toolkit, got %s\n' "$got" >&2
    return 1
  fi
  printf 'selftest: 1/1 PASS\n'
  return 0
}

main() {
  case "${1:-}" in
    --repo-class)  cmd_repo_class ;;
    --probe-depth) cmd_probe_depth ;;
    --selftest)    cmd_selftest ;;
    *)
      printf 'usage: detect_repo_class.sh [--repo-class | --probe-depth | --selftest]\n' >&2
      return 2
      ;;
  esac
}

main "$@"
