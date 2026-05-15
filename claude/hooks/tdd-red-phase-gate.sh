#!/usr/bin/env bash
# PostToolUse hook: advisory TDD red-phase gate.
# Warns (to stderr) if an implementation commit lands on a Testable task
# without any prior test: commit in the task window on the branch.
# Always exits 0 — this hook is advisory only.

set -euo pipefail

# Trap any error and still exit 0 (hook must never fail a tool call)
trap 'exit 0' ERR

# Read stdin (PostToolUse JSON payload)
INPUT=$(cat)

# --- Cheap shell pre-filter ---
# Extract tool_name using sed (avoid python3 startup cost on hot path)
TOOL_NAME=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)

case "$TOOL_NAME" in
    Bash)
        # Only care about git commit invocations
        CMD=$(printf '%s' "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
        case "$CMD" in
            *"git commit"*) ;;  # proceed
            *) exit 0 ;;
        esac
        ;;
    Agent)
        # Proceed — no command filter needed for Agent calls
        ;;
    *)
        exit 0
        ;;
esac

# --- Check that progress.md exists at repo root ---
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
PROGRESS_FILE="$REPO_ROOT/docs/progress.md"
[ -f "$PROGRESS_FILE" ] || exit 0

# --- Parse progress.md and prompts file in python3 ---
python3 - "$REPO_ROOT" "$PROGRESS_FILE" << 'PYEOF'
import sys, os, re, subprocess

repo_root = sys.argv[1]
progress_file = sys.argv[2]

# Read progress.md
with open(progress_file) as f:
    progress_content = f.read()

# Find the Prompts: pointer
prompts_match = re.search(r'^\*\*Prompts:\*\*\s*(.+)$', progress_content, re.MULTILINE)
if not prompts_match:
    sys.exit(0)
prompts_rel = prompts_match.group(1).strip()
prompts_file = os.path.join(repo_root, prompts_rel)
if not os.path.isfile(prompts_file):
    sys.exit(0)

# Find the single 'doing' row in the status table
# Table rows look like: | 1.1  | Name | doing | Notes |
doing_rows = re.findall(
    r'^\|\s*(\S+)\s*\|\s*[^|]*\|\s*doing\s*\|',
    progress_content,
    re.MULTILINE
)
if len(doing_rows) != 1:
    # Zero or multiple doing rows — cannot determine task
    sys.exit(0)
task_id = doing_rows[0].strip()

# Read prompts file
with open(prompts_file) as f:
    prompts_content = f.read()

# Find the matching task block
# Look for ### Task <id>: ... up to the next ### Task or end of file
task_id_esc = re.escape(task_id)
block_match = re.search(
    rf'###\s+Task\s+{task_id_esc}:.*?(?=\n###\s+Task\s+|\Z)',
    prompts_content,
    re.DOTALL
)
if not block_match:
    sys.exit(0)
task_block = block_match.group(0)

# Check **Testable:** field
testable_match = re.search(r'^\*\*Testable:\*\*\s*(\S+)', task_block, re.MULTILINE)
if not testable_match:
    sys.exit(0)
testable_val = testable_match.group(1).strip().lower()
if testable_val != 'yes':
    sys.exit(0)

# --- Determine task window (worktree-aware) ---
cwd = os.getcwd()

if '/.claude/worktrees/' in cwd:
    # Worktree: scope to commits on this worktree branch since its branch point
    branch = subprocess.run(
        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
        capture_output=True, text=True, cwd=cwd
    ).stdout.strip()
    if not branch or branch == 'HEAD':
        sys.exit(0)
    # Find the merge-base with the parent branch
    merge_base_result = subprocess.run(
        ['git', 'merge-base', 'HEAD', 'origin/HEAD'],
        capture_output=True, text=True, cwd=cwd
    )
    if merge_base_result.returncode != 0:
        # Fall back: try common base branches
        merge_base = ''
        for base in ('origin/main', 'origin/master', 'main', 'master'):
            r = subprocess.run(
                ['git', 'merge-base', 'HEAD', base],
                capture_output=True, text=True, cwd=cwd
            )
            if r.returncode == 0:
                merge_base = r.stdout.strip()
                break
    else:
        merge_base = merge_base_result.stdout.strip()
    if not merge_base:
        sys.exit(0)
    git_range = f'{merge_base}..HEAD'
    git_cwd = cwd
else:
    # Main worktree: scope from branch point (base branch) to HEAD
    branch = subprocess.run(
        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
        capture_output=True, text=True, cwd=repo_root
    ).stdout.strip()
    if not branch or branch == 'HEAD':
        sys.exit(0)
    # Base Branch Detection (from workflow.md § Base Branch Detection)
    base = subprocess.run(
        ['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'],
        capture_output=True, text=True, cwd=repo_root
    ).stdout.strip().replace('refs/remotes/origin/', '')
    if not base:
        for candidate in ('main', 'master'):
            r = subprocess.run(
                ['git', 'rev-parse', '--verify', candidate],
                capture_output=True, text=True, cwd=repo_root
            )
            if r.returncode == 0:
                base = candidate
                break
    if not base:
        base = 'main'
    merge_base_result = subprocess.run(
        ['git', 'merge-base', 'HEAD', base],
        capture_output=True, text=True, cwd=repo_root
    )
    if merge_base_result.returncode != 0:
        sys.exit(0)
    merge_base = merge_base_result.stdout.strip()
    if not merge_base:
        sys.exit(0)
    git_range = f'{merge_base}..HEAD'
    git_cwd = repo_root

# --- Walk commits in window ---
log_result = subprocess.run(
    ['git', 'log', git_range, '--format=%s'],
    capture_output=True, text=True, cwd=git_cwd
)
if log_result.returncode != 0:
    sys.exit(0)
subjects = [s.strip() for s in log_result.stdout.splitlines() if s.strip()]

# If ANY commit subject starts with test:, red phase is satisfied
for subj in subjects:
    if subj.startswith('test:'):
        sys.exit(0)

# No test: commit found — emit advisory warning
print(
    f"WARNING: TDD red-phase gate — task {task_id} is **Testable:** yes but no 'test:' commit "
    f"exists in the task window on branch {branch}. "
    f"Expected: a 'test: ...' commit before any non-test commit for this task. "
    f"(advisory; /implement-plan Step 2c.5 should catch this)",
    file=sys.stderr
)
sys.exit(0)
PYEOF

exit 0
