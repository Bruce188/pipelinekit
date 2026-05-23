#!/usr/bin/env bash
# check-skill-compliance.sh — Skill-Compliance Gates for /review.
#
# Three pipelinekit-canonical gates:
#   (a) Skill paths/allowlist (blocking).
#   (b) Hook denial_tracker integration (non-blocking).
#   (c) docs-source richness (blocking).
#
# Usage:
#   check-skill-compliance.sh                          # diff main...HEAD --name-only
#   check-skill-compliance.sh --files "<paths>"        # space/newline-separated list
#   check-skill-compliance.sh --diff <patch-path>      # parse a git-diff patch
#
# Exit codes: 0 (no findings), 1 (any blocking), 2 (non-blocking only).
# denial_tracker:no Mechanical compliance script — no shell denials to telemetry.

set -uo pipefail

# Resolve repo-root from script location so paths resolve regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

POLICY_FILE="${REPO_ROOT}/docs-source/skills-scope-policy.md"
RICHNESS_SCRIPT="${REPO_ROOT}/claude/skills/docs-writer/richness_check.py"

FINDINGS_FILE="$(mktemp)"
trap 'rm -f "$FINDINGS_FILE"' EXIT

# Parse args.
MODE="default"
ARG_VALUE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --files)
      MODE="files"
      ARG_VALUE="${2:-}"
      shift 2
      ;;
    --diff)
      MODE="diff"
      ARG_VALUE="${2:-}"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

# Collect changed file paths into $PATHS_FILE (one per line).
PATHS_FILE="$(mktemp)"
trap 'rm -f "$FINDINGS_FILE" "$PATHS_FILE"' EXIT

case "$MODE" in
  files)
    # Split on whitespace + newlines.
    printf '%s\n' $ARG_VALUE | sed '/^$/d' > "$PATHS_FILE"
    ;;
  diff)
    if [ -f "$ARG_VALUE" ]; then
      grep -E '^\+\+\+ b/' "$ARG_VALUE" | sed 's|^+++ b/||' > "$PATHS_FILE"
    fi
    ;;
  default)
    # Canonical base-branch detection.
    BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
    [ -z "$BASE" ] && BASE=$(git branch -l main master 2>/dev/null | head -1 | awk '{print $NF}')
    [ -z "$BASE" ] && BASE="main"
    git -C "$REPO_ROOT" diff "${BASE}...HEAD" --name-only 2>/dev/null > "$PATHS_FILE" || true
    ;;
esac

# Parse allowlist from policy file via inline python.
ALLOWLIST=""
if [ -f "$POLICY_FILE" ]; then
  ALLOWLIST=$(python3 - "$POLICY_FILE" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
# Find "Allowlist" or "Global-by-design allowlist" H2 section.
sections = re.split(r'^## ', text, flags=re.M)
names = []
for s in sections:
    if s.lower().startswith(('allowlist', 'global-by-design allowlist')):
        # Pull leading `- `<name>`` entries from the section body.
        for m in re.finditer(r'^-\s+`([^`]+)`', s, flags=re.M):
            names.append(m.group(1).strip())
        break
print(" ".join(names))
PY
  )
fi

# Inline python evaluates each path against the three gates and writes
# finding blocks (or empty) to stdout. We pipe all paths through one
# invocation so finding output is deterministic and fully buffered.
python3 - "$ALLOWLIST" "$RICHNESS_SCRIPT" "$REPO_ROOT" "$PATHS_FILE" >> "$FINDINGS_FILE" <<'PY'
import os, re, subprocess, sys, fnmatch
from pathlib import Path

allowlist = set(sys.argv[1].split()) if sys.argv[1] else set()
richness_script = sys.argv[2]
repo_root = Path(sys.argv[3])
paths_file = sys.argv[4]

with open(paths_file) as f:
    paths = [ln.strip() for ln in f if ln.strip()]


def emit(path, severity, issue, suggestion, scope, intent):
    print(f"**File:** {path}")
    print(f"**Severity:** {severity}")
    print(f"**Issue:** {issue}")
    print(f"**Suggestion:** {suggestion}")
    print(f"**Scope:** {scope}")
    print(f"**Intent:** {intent}")
    print()


def resolve(p: str) -> Path:
    """Return an absolute path. If path is absolute, use as-is. Otherwise resolve under repo_root."""
    pp = Path(p)
    if pp.is_absolute():
        return pp
    return repo_root / pp


def match_skill(p: str):
    # Match `claude/skills/<name>/SKILL.md` as suffix (allow absolute paths in tests).
    m = re.search(r'(?:^|/)claude/skills/([^/]+)/SKILL\.md$', p)
    return m.group(1) if m else None


def match_hook(p: str):
    m = re.search(r'(?:^|/)claude/hooks/([^/]+)\.(sh|py)$', p)
    if not m:
        return None
    base = m.group(1)
    # Exclude helpers (`_`-prefixed) and tests/.
    if base.startswith('_'):
        return None
    if '/claude/hooks/tests/' in p or p.startswith('claude/hooks/tests/'):
        return None
    return base


def match_docs_source(p: str):
    # Allow nested subdirs under docs-source — capture path relative to docs-source/.
    m = re.search(r'(?:^|/)docs-source/(.+)\.md$', p)
    return m.group(1) if m else None


def has_paths_key(skill_md_text: str) -> bool:
    # Find first frontmatter block.
    m = re.match(r'^---\s*\n(.*?)\n---', skill_md_text, flags=re.S)
    if not m:
        return False
    fm = m.group(1)
    # `paths:` at start of a line, top-level (no leading space).
    return bool(re.search(r'^paths:\s*(\n|$)', fm, flags=re.M))


for p in paths:
    abs_p = resolve(p)

    # Gate (a) — Skill paths/allowlist.
    skill_name = match_skill(p)
    if skill_name is not None:
        text = ""
        try:
            text = abs_p.read_text()
        except OSError:
            pass
        if not has_paths_key(text) and skill_name not in allowlist:
            emit(
                p,
                "blocking",
                f"Skill `{skill_name}` lacks `paths:` frontmatter declaration and is not on the allowlist.",
                f"Add `paths: [list, of, glob, patterns]` to the frontmatter; or, if intentionally global, add `{skill_name}` to the Allowlist section in `docs-source/skills-scope-policy.md`.",
                "gate-a (skill-paths-or-allowlist)",
                "Skill-Compliance Gate (a)",
            )
        continue

    # Gate (b) — Hook denial_tracker integration.
    hook_name = match_hook(p)
    if hook_name is not None:
        text = ""
        try:
            text = abs_p.read_text()
        except OSError:
            pass
        # Accept any reference to denial_tracker OR an opt-out comment.
        ok = (
            'denial_tracker' in text
            or re.search(r'#\s*denial_tracker:no\b', text) is not None
        )
        if not ok:
            emit(
                p,
                "non-blocking",
                "Hook does not reference `denial_tracker` and has no `# denial_tracker:no <reason>` opt-out comment.",
                "Call `python3 claude/hooks/denial_tracker.py` from the hook (matches the pattern in `claude/hooks/block-stage-sensitive.sh`); or, if denial tracking does not apply, add `# denial_tracker:no <reason>` near the top.",
                "gate-b (hook-denial-tracker)",
                "Skill-Compliance Gate (b)",
            )
        continue

    # Gate (c) — docs-source richness.
    docs_rel = match_docs_source(p)
    if docs_rel is not None:
        # Compute matching html path, preserving sub-directories under docs-source.
        html_rel = docs_rel + ".html"
        # Source absolute path may be under repo_root OR an absolute tmp dir (tests).
        if abs_p.is_absolute() and 'docs-source/' in str(abs_p):
            # In test mode, html_path mirrors the absolute layout: replace docs-source -> documentation.
            html_abs = Path(str(abs_p).replace('/docs-source/', '/documentation/').rsplit('.md', 1)[0] + '.html')
        else:
            html_abs = repo_root / "documentation" / html_rel

        src_text = ""
        try:
            src_text = abs_p.read_text()
        except OSError:
            pass

        # Check exempt marker in source.
        if re.search(r'<!--\s*richness-exempt:\s*[^\s].*?-->', src_text, flags=re.S):
            continue

        if not html_abs.exists():
            emit(
                p,
                "blocking",
                f"Source markdown has no corresponding rendered HTML at `{html_abs}`.",
                f"Render via `python3 claude/skills/docs-writer/render.py {p}` and commit the resulting HTML.",
                "gate-c (docs-richness-missing-render)",
                "Skill-Compliance Gate (c)",
            )
            continue

        # Run richness_check positionally; capture stdout+stderr + exit code.
        try:
            proc = subprocess.run(
                ['python3', richness_script, str(html_abs)],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                emit(
                    p,
                    "blocking",
                    f"Rendered documentation at `{html_abs}` fails richness check.",
                    "Add depth/examples/code blocks until richness_check passes; or mark exempt with `<!-- richness-exempt: <reason> -->` in the source.",
                    "gate-c (docs-richness-low)",
                    "Skill-Compliance Gate (c)",
                )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            # Treat infrastructure failure as non-blocking informational; do
            # not silently swallow — surface as blocking so it gets fixed.
            emit(
                p,
                "blocking",
                f"richness_check.py failed to execute against `{html_abs}` ({e}).",
                "Verify `claude/skills/docs-writer/richness_check.py` is reachable and re-run.",
                "gate-c (docs-richness-infra)",
                "Skill-Compliance Gate (c)",
            )
        continue
PY

# Count findings by severity.
BLOCKING_COUNT=$(grep -c '^\*\*Severity:\*\* blocking' "$FINDINGS_FILE" 2>/dev/null || true)
NON_BLOCKING_COUNT=$(grep -c '^\*\*Severity:\*\* non-blocking' "$FINDINGS_FILE" 2>/dev/null || true)
BLOCKING_COUNT=${BLOCKING_COUNT:-0}
NON_BLOCKING_COUNT=${NON_BLOCKING_COUNT:-0}

cat "$FINDINGS_FILE"
echo "# Skill-compliance: ${BLOCKING_COUNT} blocking, ${NON_BLOCKING_COUNT} non-blocking findings"

if [ "$BLOCKING_COUNT" -gt 0 ]; then
  exit 1
fi
if [ "$NON_BLOCKING_COUNT" -gt 0 ]; then
  exit 2
fi
exit 0
