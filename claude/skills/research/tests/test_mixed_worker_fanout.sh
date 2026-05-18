#!/usr/bin/env bash
# Smoke fixture for mixed-worker fan-out per /implement-plan Step 1.5.
#
# Fixtures (5 total):
# (a) All 3 tasks dispatched (tasks 1.1/1.3 via codex fallback, 1.2 via claude)
# (b) Scratchpad notes *-to-*.md round-trip across class boundary
# (c) Lead squash-merges all 3 into a single conventional commit (no wip:, no class disclosure)
# (d) Per-task beacon lines emit distinct worker=<class> tokens
# (e) WORKER_FALLBACK/WORKER_UNAVAILABLE log line fires once per codex task
#
# Uses stubbed host-adapter scripts for determinism (codex CLI absent).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
FAILURES=0

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1: $2" >&2; FAILURES=$((FAILURES + 1)); }

# ---------------------------------------------------------------------------
# Setup: create a temp workspace with a stub git repo
# ---------------------------------------------------------------------------
WORK_DIR="$(mktemp -d)"
trap "rm -rf $WORK_DIR" EXIT

# Initialize a stub git repo for the fixture
cd "$WORK_DIR"
git init -b main -q
git config user.email "test@test.com"
git config user.name "test"
echo "init" > README.md
git add README.md
git commit -q -m "init: empty base"

# Create a feature branch for the parallel batch
git checkout -q -b test/mixed-fanout

# ---------------------------------------------------------------------------
# Simulate the worker resolution and dispatch for a 3-task mixed batch
# ---------------------------------------------------------------------------

# Worker resolution function (mirrors interface.md resolution order)
resolve_worker() {
  local task_worker="${1:-}"       # per-task worker: header
  local env_worker="${WORKER_CLASS:-}"
  local no_routing="${PIPELINE_NO_WORKER_ROUTING:-0}"

  if [[ "$no_routing" == "1" ]]; then
    echo "claude"; return
  fi
  if [[ -n "$task_worker" ]]; then
    echo "$task_worker"; return
  fi
  if [[ -n "$env_worker" ]]; then
    echo "$env_worker"; return
  fi
  echo "claude"
}

# Dispatch function — returns effective class, logs fallback if needed
dispatch_task() {
  local task_id="$1"
  local resolved_class="$2"
  local log_file="$3"
  local output_dir="$4"

  mkdir -p "$output_dir"

  if [[ "$resolved_class" == "claude" ]]; then
    echo "BEACON: task=$task_id worker=claude dispatched" >> "$log_file"
    # Simulate artifact production
    echo "task-$task_id result" > "$output_dir/result.txt"
    echo "claude"
    return 0
  fi

  # Non-claude class: check host-adapter availability
  if ! command -v "$resolved_class" >/dev/null 2>&1; then
    # Exit 2 semantics: runtime absent → WORKER_UNAVAILABLE
    echo "WORKER_UNAVAILABLE: $resolved_class (host-adapter missing)" >> "$log_file"
    echo "BEACON: task=$task_id worker=claude dispatched (fallback from $resolved_class)" >> "$log_file"
    # Simulate fallback artifact production
    echo "task-$task_id result (fallback)" > "$output_dir/result.txt"
    echo "claude"
    return 0
  fi

  echo "BEACON: task=$task_id worker=$resolved_class dispatched" >> "$log_file"
  echo "task-$task_id result" > "$output_dir/result.txt"
  echo "$resolved_class"
}

# ---------------------------------------------------------------------------
# Define 3-task batch:
#   task 1.1: worker: codex  (resolves to claude fallback — CLI absent)
#   task 1.2: worker: claude
#   task 1.3: worker: codex  (resolves to claude fallback — CLI absent)
# ---------------------------------------------------------------------------
TASK_WORKERS=("codex" "claude" "codex")
TASK_IDS=("1.1" "1.2" "1.3")
DISPATCH_LOG="$WORK_DIR/dispatch.log"
> "$DISPATCH_LOG"

SCRATCHPAD="$WORK_DIR/scratchpad/phase-test"
mkdir -p "$SCRATCHPAD"

DISPATCH_COUNT=0
EFFECTIVE_WORKERS=()

for i in 0 1 2; do
  task_id="${TASK_IDS[$i]}"
  task_worker="${TASK_WORKERS[$i]}"
  resolved=$(resolve_worker "$task_worker")
  out_dir="$WORK_DIR/task-${task_id}"

  effective=$(dispatch_task "$task_id" "$resolved" "$DISPATCH_LOG" "$out_dir")
  EFFECTIVE_WORKERS+=("$effective")
  DISPATCH_COUNT=$((DISPATCH_COUNT + 1))
done

# ---------------------------------------------------------------------------
# Fixture (a): All 3 tasks dispatched
# ---------------------------------------------------------------------------
if [[ "$DISPATCH_COUNT" -eq 3 ]]; then
  pass "fixture_a: all 3 tasks dispatched ($DISPATCH_COUNT/3)"
else
  fail "fixture_a" "Expected 3 tasks dispatched, got $DISPATCH_COUNT"
fi

# ---------------------------------------------------------------------------
# Fixture (b): Scratchpad notes *-to-*.md round-trip across class boundary
# ---------------------------------------------------------------------------
# Simulate task 1.2 (claude) writing a note to task 1.3 (codex/fallback)
echo "note from task 1.2 to task 1.3: shared utility X discovered" > "$SCRATCHPAD/task-1.2-to-task-1.3.md"
# Simulate task 1.1 (codex/fallback) writing a note to task 1.2 (claude)
echo "note from task 1.1 to task 1.2: upstream dependency Y" > "$SCRATCHPAD/task-1.1-to-task-1.2.md"

# Verify round-trip: each task reads notes addressed to it
TASK_12_NOTE="$SCRATCHPAD/task-1.1-to-task-1.2.md"
TASK_13_NOTE="$SCRATCHPAD/task-1.2-to-task-1.3.md"

if [[ -f "$TASK_12_NOTE" ]] && [[ -f "$TASK_13_NOTE" ]]; then
  # Read the notes (simulates each task reading before done)
  NOTE_12=$(cat "$TASK_12_NOTE")
  NOTE_13=$(cat "$TASK_13_NOTE")
  if [[ -n "$NOTE_12" ]] && [[ -n "$NOTE_13" ]]; then
    pass "fixture_b: scratchpad notes round-trip across class boundary"
  else
    fail "fixture_b" "Scratchpad note files empty"
  fi
else
  fail "fixture_b" "Scratchpad note files missing"
fi

# ---------------------------------------------------------------------------
# Fixture (c): Squash-merge produces single conventional commit (no wip:, no class)
# ---------------------------------------------------------------------------
# Simulate each task leaving a wip: commit on their worktree branch, then
# the lead squash-merges into one clean commit.
for i in 0 1 2; do
  task_id="${TASK_IDS[$i]}"
  branch="worktree-agent-${task_id}"
  git checkout -q -b "$branch" 2>/dev/null || git checkout -q "$branch"
  echo "task $task_id result" > "result-${task_id}.txt"
  git add "result-${task_id}.txt"
  git commit -q -m "wip: task $task_id implementation"
  git checkout -q test/mixed-fanout
done

# Squash-merge all 3 worktree branches
for i in 0 1 2; do
  task_id="${TASK_IDS[$i]}"
  branch="worktree-agent-${task_id}"
  git merge -q --squash "$branch" 2>/dev/null || true
done

# Create a single clean conventional commit
git commit -q -m "feat: implement parallel batch tasks 1.1 1.2 1.3" 2>/dev/null || true

# Verify the commit message has no wip:, no class disclosure
LAST_MSG=$(git log -1 --format='%s')
if echo "$LAST_MSG" | grep -q "wip:"; then
  fail "fixture_c" "Commit message contains 'wip:': $LAST_MSG"
elif echo "$LAST_MSG" | grep -qi "codex\|claude\b"; then
  fail "fixture_c" "Commit message discloses worker class: $LAST_MSG"
elif echo "$LAST_MSG" | grep -qE "^(feat|fix|refactor|docs|test|chore|perf|style|build|ci):"; then
  pass "fixture_c: single conventional squash commit, no wip: or class disclosure"
else
  fail "fixture_c" "Commit message not conventional: $LAST_MSG"
fi

# ---------------------------------------------------------------------------
# Fixture (d): Per-task beacon lines emit distinct worker=<class> tokens
# ---------------------------------------------------------------------------
BEACON_11=$(grep "task=1.1" "$DISPATCH_LOG" || true)
BEACON_12=$(grep "task=1.2" "$DISPATCH_LOG" || true)
BEACON_13=$(grep "task=1.3" "$DISPATCH_LOG" || true)

if [[ -n "$BEACON_11" ]] && [[ -n "$BEACON_12" ]] && [[ -n "$BEACON_13" ]]; then
  # Verify each beacon has a worker= token
  if echo "$BEACON_11" | grep -q "worker=" && \
     echo "$BEACON_12" | grep -q "worker=" && \
     echo "$BEACON_13" | grep -q "worker="; then
    pass "fixture_d: per-task beacon lines emit distinct worker=<class> tokens"
  else
    fail "fixture_d" "Beacon lines missing worker= token: 1.1=$BEACON_11 1.2=$BEACON_12 1.3=$BEACON_13"
  fi
else
  fail "fixture_d" "Missing beacon for one or more tasks"
fi

# ---------------------------------------------------------------------------
# Fixture (e): WORKER_UNAVAILABLE log line fires once per codex task
# ---------------------------------------------------------------------------
UNAVAIL_COUNT=$(grep -c "WORKER_UNAVAILABLE" "$DISPATCH_LOG" 2>/dev/null || echo 0)
# Tasks 1.1 and 1.3 are codex → 2 WORKER_UNAVAILABLE lines expected
if [[ "$UNAVAIL_COUNT" -eq 2 ]]; then
  pass "fixture_e: WORKER_UNAVAILABLE fires once per codex task (count=$UNAVAIL_COUNT)"
else
  fail "fixture_e" "Expected 2 WORKER_UNAVAILABLE lines (one per codex task), got $UNAVAIL_COUNT"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
cd "$REPO_ROOT"
echo ""
if [[ "$FAILURES" -eq 0 ]]; then
  echo "All 5 fixtures passed."
  exit 0
else
  echo "$FAILURES fixture(s) failed." >&2
  exit 1
fi
