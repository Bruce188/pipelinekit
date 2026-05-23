---
name: landing-report
description: Pre-push version-slot collision detector. Reads VERSION or package.json:version, compares against existing git tags, prints a one-line status. Silent skip when neither marker is present. Invoked from /ppr Step 1.6.
argument-hint: (no arguments needed)
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
paths:
  - claude/skills/landing-report/**
  - docs/landing*.md
  - documentation/**
---

# Landing report

Detects whether the current `VERSION` (or `package.json` `version` field) would collide with an existing git tag, and surfaces a one-line status to stdout. Best-effort, advisory — collisions warn but do NOT stop the push.

## Detection logic

```bash
if [ -f VERSION ]; then
  CURRENT_VERSION="$(cat VERSION | tr -d '[:space:]')"
  SOURCE="VERSION"
elif [ -f package.json ]; then
  CURRENT_VERSION="$(python3 -c 'import json,sys;print(json.load(open("package.json")).get("version",""))')"
  SOURCE="package.json"
else
  echo "SKIP: no VERSION or package.json:version found" >&2
  exit 0
fi
[ -z "$CURRENT_VERSION" ] && { echo "SKIP: version field empty" >&2; exit 0; }
```

If neither marker is present: **silent skip** — exit 0 with a stderr `SKIP:` note, no stdout output.

## Collision detection

```bash
if git rev-parse "v${CURRENT_VERSION}" >/dev/null 2>&1 \
   || git rev-parse "${CURRENT_VERSION}" >/dev/null 2>&1; then
  COLLISION=1
else
  COLLISION=0
fi
LAST_TAG="$(git describe --tags --abbrev=0 2>/dev/null || echo none)"
```

## Output

**stdout (one line, machine-readable):**
```
landing-report: source=VERSION current=1.2.3 last_tag=v1.2.2 collision=no
```

**file (transient, gitignored):** `docs/landing-report.md` — markdown summary for the PR body. The pattern `docs/landing-report.md` should be added to `~/.claude/config/never-stage.txt` (deferred to a separate hook-config feature; in v1 the file is created but not staged because `docs/` is already broadly excluded).

## Exit codes

- `0` — always (advisory only). Collisions warn but never block.

## Invocation

Invoked from `/ppr` Step 1.6 and from the pipeline Path A push step (`reference.md` step 1.5). Both fire only when a `VERSION` file or `package.json:version` is present; otherwise the skill silently skips.

## Cost

< 100ms — three filesystem reads plus two `git rev-parse` calls.
