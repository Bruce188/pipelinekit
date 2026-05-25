---
name: codegraph-init
description: Initialize codegraph index in the current project. Walks the 50k-file pre-flight gate. Use when starting symbolic-graph work in a new repo.
argument-hint: "[--force]"
disable-model-invocation: true
allowed-tools:
  - Bash
paths:
  - claude/skills/codegraph-init/**
---

# /codegraph-init

Initialize the `codegraph` symbolic-graph database for the current project.
Produces `.codegraph/codegraph.db` (never staged — see `claude/config/never-stage.txt`).

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
    -not -path './.codegraph/*' \
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
    echo "[codegraph-init] WARNING: repository has >= 50k files ($COUNT via $COUNT_METHOD). Proceeding with --force."
  else
    echo "[codegraph-init] ERROR: repository has >= 50k files ($COUNT via $COUNT_METHOD)."
    echo "[codegraph-init] codegraph init may OOM. Re-invoke with --force to proceed."
    echo "[codegraph-init] Example: /codegraph-init --force"
    exit 1
  fi
else
  echo "[codegraph-init] Pre-flight OK: $COUNT files (via $COUNT_METHOD). Proceeding."
fi
```

## Step 2: Init

Run `codegraph init` to initialise the project configuration and create the graph database.

```bash
npx -y @colbymchenry/codegraph@^0.9.4 init
```

## Step 3: Index

Index the project source into the graph database.

```bash
npx -y @colbymchenry/codegraph@^0.9.4 index
```

After indexing completes, `.codegraph/codegraph.db` is present in the project root and the
`codegraph` MCP server (registered in `~/.claude/.mcp.json` by `scripts/install.sh`) can
serve symbolic-graph queries to Claude Code.

## Reference

### `/mnt/*` paths on WSL2

The upstream `@colbymchenry/codegraph` README recommends keeping projects off `/mnt/` (i.e.
Windows filesystem mounts) to avoid inotify watcher issues. The install-side `provision_codegraph_mcp()`
cannot enforce this at install time — the restriction is advisory. If you experience slow or
missing watch events, move the project under `~/` (Linux filesystem) before running `/codegraph-init`.

### Pin rationale

`@^0.9.4` (caret-pin: `>= 0.9.4 < 0.10.0`) captures the OOM-fix release per feature spec.
The upper bound (`< 0.10.0`) prevents inadvertent major-API breakage on next `npx -y` fetch.

### Output artifact

- `.codegraph/codegraph.db` — project-local graph database. Never staged; excluded via
  `claude/config/never-stage.txt` and `.git/info/exclude`.
