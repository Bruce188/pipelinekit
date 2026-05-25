---
name: graphify-init
description: Initialize graphify build in the current project. Walks the 50k-file pre-flight gate. Use when starting graph-knowledge work in a new repo.
argument-hint: "[--force]"
disable-model-invocation: true
allowed-tools:
  - Bash
paths:
  - claude/skills/graphify-init/**
---

# /graphify-init

Initialize the `graphify` knowledge-graph for the current project.
Produces `.graphify/` (never staged — see `claude/config/never-stage.txt`).

## Step 1: Pre-flight (50k-file gate)

Repositories with ≥ 50k files risk OOM during initial indexing. This gate aborts unless
`--force` is supplied.

```bash
# Parse --force from $ARGUMENTS.
FORCE=0
for _arg in $ARGUMENTS; do
  [[ "$_arg" == "--force" ]] && FORCE=1
done

# Detect git repo and count tracked files.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  COUNT=$(git ls-files | wc -l)
  COUNT_METHOD="git ls-files"
else
  # Non-git fallback: bounded find with 5s timeout; short-circuits at 50001.
  COUNT=$(timeout 5s find . -type f \
    -not -path './.git/*' \
    -not -path './node_modules/*' \
    -not -path './.graphify/*' \
    -not -path './dist/*' \
    -not -path './build/*' \
    -not -path './target/*' \
    -not -path './.venv/*' \
    -print 2>/dev/null | head -n 50001 | wc -l)
  FIND_STATUS=$?
  COUNT_METHOD="find (non-git)"
  # If timeout fired (exit 124) or find errored, treat as huge repo.
  if [[ $FIND_STATUS -ne 0 ]]; then
    COUNT=50001
    COUNT_METHOD="find (timeout — treating as huge)"
  fi
fi

if [[ "$COUNT" -ge 50000 ]]; then
  if [[ "$FORCE" -eq 1 ]]; then
    echo "[graphify-init] WARNING: repository has >= 50k files ($COUNT via $COUNT_METHOD). Proceeding with --force."
  else
    echo "[graphify-init] ERROR: repository has >= 50k files ($COUNT via $COUNT_METHOD)."
    echo "[graphify-init] graphify build may OOM. Re-invoke with --force to proceed."
    echo "[graphify-init] Example: /graphify-init --force"
    exit 1
  fi
else
  echo "[graphify-init] Pre-flight OK: $COUNT files (via $COUNT_METHOD). Proceeding."
fi
```

## Step 2: Build

Run `graphify .` to build the knowledge-graph for the current project.

```bash
uv tool run --from graphifyy graphify .
```

If `uv` is absent, install via `curl -LsSf https://astral.sh/uv/install.sh | sh` then re-run.

The build produces `.graphify/` in the project root. This directory is never staged
(excluded via `claude/config/never-stage.txt` and `.git/info/exclude`).

## Step 3: MCP-ready confirmation

Verify the MCP server can start without error:

```bash
timeout 5s uv tool run --from graphifyy graphify --version
```

Expected output: a version string such as `graphify 0.8.18`. If this exits non-zero or prints
`ModuleNotFoundError`, re-install via:

```bash
uv tool install graphifyy==0.8.18
```

The `graphify` MCP server (registered in `~/.claude/.mcp.json` by `scripts/install.sh`) serves
knowledge-graph queries to Claude Code on the next MCP client tool call — no daemon pre-spawn
is needed.

## Reference

### Pin rationale

`0.8.18` is the canonical `info.version` per PyPI 2026-04-10. The pin is a one-line edit to
the `GRAPHIFY_VERSION` constant near the top of `scripts/install.sh`. Bump requires a corresponding
re-run of `uv tool install graphifyy==<new-version>`.

### Forbidden extras

The following extras MUST NOT be installed — each adds 0.5–4 GB of footprint with no benefit
to the default MCP workflow:

`[video]`, `[leiden]`, `[all]`, `[pdf]`, `[office]`, `[google]`, `[neo4j]`, `[svg]`,
`[ollama]`, `[openai]`, `[gemini]`, `[bedrock]`, `[sql]`

The install command in `scripts/install.sh` is intentionally free of bracket syntax:
`uv tool install "graphifyy==0.8.18"` — no extras.

### WSL2 `/mnt/*` advisory

The graphify build under `/mnt/*` (Windows-side filesystem mount) may experience slow inotify
watch events. Move the project under `~/` (Linux filesystem) for best performance before
running `/graphify-init`.
