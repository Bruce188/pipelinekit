#!/usr/bin/env bash
set -euo pipefail
# research-loop.sh — Karpathy autoresearch loop driver.
#
# Purpose: one `claude -p` per iteration.
# Each iteration: read prior TSV row → hypothesize → mutate one file →
# run benchmark → grep metric → git keep-or-reset → append TSV row.
#
# TSV columns: commit	metric	memory	status	description
# Commit prefix: chore: research <tag> iter N — metric=<value>
# cost_log.py dispatch-mode: subagent for start/end bookends; the per-iter claude invocation
# uses JSON output format and its stdout is piped through cost_log.py (the parse_json subcommand)
# which writes an end event with dispatch_mode=subprocess and real cost_usd.
# This script NEVER calls `git push`. Branches stay local.
#
# Usage:
#   bash claude/skills/research/research-loop.sh \
#     --goal "speed up X" \
#     --target-file src/x.py \
#     --benchmark-cmd "make bench" \
#     --metric-regex "throughput=([0-9.]+)" \
#     [--memory-regex "mem_kb=([0-9]+)"] \
#     [--max-iterations 20] [--max-usd 5.00] [--max-turns 200] \
#     [--accept-when "metric > 1000"] [--stop-when "metric > 2000"] \
#     [--research-tag my-experiment] [--worker <class>] [--dry-run]
#
# Worker routing (--worker flag):
#   Resolution order per iteration:
#     1. per-iteration `worker:` directive in experiment manifest
#     2. --worker <class> global flag
#     3. WORKER_CLASS env var
#     4. default: claude (always-available in-session)
#   If the resolved class's host-adapter exits 2 (runtime absent):
#     log WORKER_UNAVAILABLE: <class> (host-adapter missing) to stderr
#     fall back to ClaudeWorker (in-session) for that iteration.
#   If the resolved class's host-adapter exits other non-zero:
#     log WORKER_FALLBACK: <iter-id> <class> -> claude (exit <rc>) to stderr
#     retry once via ClaudeWorker; second failure marks iteration failed.
#   Note: WORKER_FALLBACK semantics are documented in
#     claude/lib/worker-provider/interface.md but not yet wired in this loop —
#     exits other than 2 currently fall through to the WORKER_UNAVAILABLE
#     branch above. Behavioral implementation is deferred until a working
#     codex CLI is installed (plan-v22 Task 3.2 § Tests note).
#   Aggregation (keep-or-reset + TSV append) always runs in-session regardless.
#   Artifacts written to .claude/tasks/<experiment-id>/output/iter-<N>/

# ---------------------------------------------------------------------------
# Constants (LOCKED — do not modify without updating SKILL.md and plan)
# ---------------------------------------------------------------------------
TSV_PATH="docs/research-results.tsv"
TSV_HEADER=$'commit\tmetric\tmemory\tstatus\tdescription'
COMMIT_PREFIX_TEMPLATE='chore: research %s iter %d — metric=%s'
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
COST_LOG="claude/hooks/cost_log.py"

# ---------------------------------------------------------------------------
# Arg parser
# ---------------------------------------------------------------------------
GOAL=""
TARGET_FILE=""
BENCHMARK_CMD=""
METRIC_REGEX=""
MEMORY_REGEX=""
MAX_ITERATIONS=-1     # -1 = unlimited
MAX_USD=""            # empty = unlimited
MAX_TURNS=""          # empty = unlimited
ACCEPT_WHEN=""
STOP_WHEN=""
RESEARCH_TAG=""
WORKER_FLAG=""        # --worker <class> global flag; empty = use WORKER_CLASS env or claude
RESTART_FROM_ITER=0   # 0 = off sentinel; positive int = skip iters 1..N-1
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: research-loop.sh --goal <text> --target-file <path> --benchmark-cmd <cmd>
                        --metric-regex <regex> [OPTIONS]

Required:
  --goal <text>           Natural-language optimization goal.
  --target-file <path>    Single file the loop may mutate per iteration.
  --benchmark-cmd <cmd>   Shell command to run after each mutation.
  --metric-regex <regex>  ERE pattern with one capture group for numeric metric.

Optional:
  --memory-regex <regex>  Like --metric-regex but for a secondary memory measurement.
  --max-iterations N      Iteration hard cap (default: unlimited / -1).
  --max-usd F             USD budget cap; halt at iteration boundary when exceeded.
  --max-turns N           Sub-agent turn cap; halt at iteration boundary when exceeded.
  --accept-when <expr>    Shell expression with $metric; if true, commit unconditionally.
  --stop-when <expr>      Shell expression with $metric; if true, exit loop after commit.
  --research-tag <slug>   Slug for commit messages and cost-log feature name.
  --worker <class>        Worker class for mutation phase (claude|codex|...).
                          Resolution order: per-iteration directive > this flag >
                          WORKER_CLASS env > default claude.
                          If resolved class unavailable (exit 2): WORKER_UNAVAILABLE
                          logged and in-session claude used as fallback.
  --restart-from-iter N   Skip iterations 1..N-1 and begin at N (requires TSV row for iter N-1).
  --dry-run               Print resolved arg surface and exit 0 without side effects.
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --goal)           GOAL="$2";             shift 2 ;;
    --target-file)    TARGET_FILE="$2";      shift 2 ;;
    --benchmark-cmd)  BENCHMARK_CMD="$2";    shift 2 ;;
    --metric-regex)   METRIC_REGEX="$2";     shift 2 ;;
    --memory-regex)   MEMORY_REGEX="$2";     shift 2 ;;
    --max-iterations) MAX_ITERATIONS="$2";   shift 2 ;;
    --max-usd)        MAX_USD="$2";          shift 2 ;;
    --max-turns)      MAX_TURNS="$2";        shift 2 ;;
    --accept-when)    ACCEPT_WHEN="$2";      shift 2 ;;
    --stop-when)      STOP_WHEN="$2";        shift 2 ;;
    --research-tag)   RESEARCH_TAG="$2";     shift 2 ;;
    --worker)         WORKER_FLAG="$2";      shift 2 ;;
    --restart-from-iter) RESTART_FROM_ITER="$2"; shift 2 ;;
    --dry-run)        DRY_RUN=1;             shift ;;
    --help|-h)        usage ;;
    *) echo "error: unknown argument: $1" >&2; usage ;;
  esac
done

# ---------------------------------------------------------------------------
# Validation — required flags
# ---------------------------------------------------------------------------
MISSING=()
[[ -z "$GOAL"          ]] && MISSING+=(--goal)
[[ -z "$TARGET_FILE"   ]] && MISSING+=(--target-file)
[[ -z "$BENCHMARK_CMD" ]] && MISSING+=(--benchmark-cmd)
[[ -z "$METRIC_REGEX"  ]] && MISSING+=(--metric-regex)
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "error: missing required flags: ${MISSING[*]}" >&2
  usage
fi

# Default RESEARCH_TAG from current branch if it matches research/<slug>-...
if [[ -z "$RESEARCH_TAG" ]]; then
  _branch=$(git branch --show-current 2>/dev/null || true)
  if [[ "$_branch" == research/* ]]; then
    # Strip leading "research/" and trailing "-YYYY-MM-DD" date suffix
    _slug="${_branch#research/}"
    _slug="${_slug%-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]}"
    RESEARCH_TAG="$_slug"
  else
    RESEARCH_TAG="unnamed"
  fi
fi

# ---------------------------------------------------------------------------
# Validation — --restart-from-iter (runs BEFORE dry-run short-circuit)
# ---------------------------------------------------------------------------
if [[ -n "$RESTART_FROM_ITER" && "$RESTART_FROM_ITER" != "0" ]]; then
  if ! [[ "$RESTART_FROM_ITER" =~ ^[1-9][0-9]*$ ]]; then
    echo "error: --restart-from-iter must be a positive integer, got: $RESTART_FROM_ITER" >&2
    exit 2
  fi
  if [[ "$MAX_ITERATIONS" -ge 0 && "$RESTART_FROM_ITER" -gt "$MAX_ITERATIONS" ]]; then
    echo "error: --restart-from-iter ($RESTART_FROM_ITER) > --max-iterations ($MAX_ITERATIONS)" >&2
    exit 2
  fi
  if [[ "$RESTART_FROM_ITER" -gt 1 ]]; then
    need=$((RESTART_FROM_ITER - 1))
    have=0
    if [[ -f "$TSV_PATH" ]]; then
      have=$(( $(wc -l < "$TSV_PATH") - 1 ))
      [[ "$have" -lt 0 ]] && have=0
    fi
    if [[ "$have" -lt "$need" ]]; then
      echo "error: --restart-from-iter $RESTART_FROM_ITER requires TSV row for iter $need, have $have rows in $TSV_PATH" >&2
      exit 2
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Dry-run short-circuit
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
  cat <<EOF
DRY-RUN — resolved arg surface:
  goal            = $GOAL
  target-file     = $TARGET_FILE
  benchmark-cmd   = $BENCHMARK_CMD
  metric-regex    = $METRIC_REGEX
  memory-regex    = ${MEMORY_REGEX:-(unset)}
  max-iterations  = $MAX_ITERATIONS
  max-usd         = ${MAX_USD:-(unlimited)}
  max-turns       = ${MAX_TURNS:-(unlimited)}
  accept-when     = ${ACCEPT_WHEN:-(default: improve vs. last keep)}
  stop-when       = ${STOP_WHEN:-(unset)}
  research-tag    = $RESEARCH_TAG
  worker          = ${WORKER_FLAG:-(default: WORKER_CLASS env or claude)}
  restart-from-iter = $RESTART_FROM_ITER
  tsv-path        = $TSV_PATH
  cost-log        = $COST_LOG
  dispatch-mode   = subagent
No changes made. Exiting.
EOF
  exit 0
fi

# ---------------------------------------------------------------------------
# TSV header bootstrap
# ---------------------------------------------------------------------------
if [[ ! -f "$TSV_PATH" ]]; then
  # Ensure docs/ directory exists (may not exist in fresh repos)
  mkdir -p "$(dirname "$TSV_PATH")"
  printf '%s\n' "$TSV_HEADER" > "$TSV_PATH"
  echo "info: created $TSV_PATH with header"
fi

# ---------------------------------------------------------------------------
# Helper: _resolve_worker <global_flag> [per_iter_directive]
# Returns the worker class to use for a given iteration.
# Resolution order:
#   1. Per-iteration directive (non-empty second arg)
#   2. --worker flag (WORKER_FLAG global)
#   3. WORKER_CLASS env var
#   4. Default: claude
# ---------------------------------------------------------------------------
_resolve_worker() {
  local global_flag="${1:-}"
  local per_iter="${2:-}"

  if [[ -n "$per_iter" ]]; then
    echo "$per_iter"
    return
  fi

  if [[ -n "$global_flag" ]]; then
    echo "$global_flag"
    return
  fi

  if [[ -n "${WORKER_CLASS:-}" ]]; then
    echo "$WORKER_CLASS"
    return
  fi

  echo "claude"
}

# ---------------------------------------------------------------------------
# Helper: _dispatch_mutation <class> <iter_id> <output_dir>
# Dispatches the mutation phase to the resolved worker class.
# Falls back to in-session claude if the class is unavailable.
# Returns the effective worker class used (after any fallback).
# ---------------------------------------------------------------------------
_dispatch_mutation() {
  local class="$1"
  local iter_id="$2"
  local output_dir="$3"

  mkdir -p "$output_dir"

  if [[ "$class" == "claude" ]]; then
    # ClaudeWorker — in-session (already running via claude -p at call site)
    echo "claude"
    return 0
  fi

  # Attempt via host-adapter
  local adapter="$REPO_ROOT/claude/host-adapters/${class}.sh"
  if [[ ! -f "$adapter" ]]; then
    echo "WORKER_UNAVAILABLE: $class (host-adapter missing)" >&2
    echo "claude"
    return 0
  fi

  # Check runtime availability: run adapter with no-op args to probe exit code
  # Convention: exit 2 = runtime absent
  local probe_exit=0
  bash "$adapter" /dev/null /dev/null 2>/dev/null || probe_exit=$?
  if [[ "$probe_exit" -eq 2 ]]; then
    echo "WORKER_UNAVAILABLE: $class (host-adapter missing)" >&2
    echo "claude"
    return 0
  fi

  echo "$class"
  return 0
}

# ---------------------------------------------------------------------------
# Helper: get last keep metric from TSV for the "improves vs. last keep" heuristic
# ---------------------------------------------------------------------------
_last_keep_metric() {
  # Returns the metric value from the most recent status=keep row, or empty string.
  grep $'\tkeep\t' "$TSV_PATH" 2>/dev/null | tail -1 | cut -f2
}

# ---------------------------------------------------------------------------
# Helper: extract metric from a log file
# ---------------------------------------------------------------------------
_extract_metric() {
  local logfile="$1" regex="$2"
  grep -oE "$regex" "$logfile" 2>/dev/null \
    | head -1 \
    | grep -oE '[0-9]+(\.[0-9]+)?' \
    | head -1 || true
}

# ---------------------------------------------------------------------------
# Helper: sanitize a one-line description (strip tabs, newlines, truncate)
# ---------------------------------------------------------------------------
_sanitize_desc() {
  local s="$1"
  # Replace tabs and newlines with spaces, truncate to 200 chars
  s="${s//$'\t'/ }"
  s="${s//$'\n'/ }"
  printf '%s' "${s:0:200}"
}

# ---------------------------------------------------------------------------
# Helper: check if metric passes accept condition
# ---------------------------------------------------------------------------
_should_accept() {
  local metric="$1"
  if [[ -n "$ACCEPT_WHEN" ]]; then
    # Evaluate user-supplied expression with $metric in scope
    if bash -c "metric='$metric'; [[ $ACCEPT_WHEN ]]" 2>/dev/null; then
      return 0
    fi
    return 1
  else
    # Default heuristic: numeric improvement vs. last keep row
    local last_keep
    last_keep=$(_last_keep_metric)
    if [[ -z "$last_keep" ]]; then
      # No prior keep → accept the first measurable result
      return 0
    fi
    # Accept if metric is strictly greater than last_keep (higher-is-better default)
    # Note: user should supply --accept-when for lower-is-better metrics
    if awk "BEGIN { exit !($metric > $last_keep) }"; then
      return 0
    fi
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Helper: check stop-when predicate
# ---------------------------------------------------------------------------
_should_stop() {
  local metric="$1"
  [[ -z "$STOP_WHEN" ]] && return 1
  bash -c "metric='$metric'; [[ $STOP_WHEN ]]" 2>/dev/null && return 0
  return 1
}

# ---------------------------------------------------------------------------
# Helper: cumulative USD from cost_log.py (best-effort; returns 0.0 on failure)
# ---------------------------------------------------------------------------
_cumulative_usd() {
  python3 "$COST_LOG" report "research/$RESEARCH_TAG" 2>/dev/null \
    | awk 'NR>1 { sum += $NF } END { printf "%.6f", sum }' || echo "0.0"
}

# ---------------------------------------------------------------------------
# Helper: cumulative turns (approximated from end events in cost-events.jsonl)
# ---------------------------------------------------------------------------
_cumulative_turns() {
  local log_path="$HOME/.claude/logs/cost-events.jsonl"
  [[ -f "$log_path" ]] || { echo "0"; return; }
  python3 - <<PYEOF
import json, sys
path = "$log_path"
feature = "research/$RESEARCH_TAG"
count = 0
try:
    with open(path) as f:
        for line in f:
            try:
                ev = json.loads(line)
                if ev.get("feature") == feature and ev.get("event") == "end":
                    count += 1
            except Exception:
                pass
except Exception:
    pass
print(count)
PYEOF
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
iter=0
if [[ "$RESTART_FROM_ITER" -gt 0 ]]; then
  iter=$((RESTART_FROM_ITER - 1))
  echo "info: --restart-from-iter $RESTART_FROM_ITER — skipping iterations 1..$iter"
fi
LOOP_START_TS=$(date -u +%s)

echo "info: research loop starting — tag=$RESEARCH_TAG target=$TARGET_FILE max-iter=$MAX_ITERATIONS"

while true; do
  # --- Iteration cap check (before increment) ---
  if [[ "$MAX_ITERATIONS" -ge 0 && "$iter" -ge "$MAX_ITERATIONS" ]]; then
    echo "info: max-iterations ($MAX_ITERATIONS) reached — exiting"
    break
  fi

  iter=$((iter + 1))
  AGENT_ID="research-pid$$"
  ITER_LOG="/tmp/research-iter-${iter}.log"
  BENCH_LOG="/tmp/research-bench-${iter}.log"

  echo "info: === iteration $iter ==="

  # --- Cost log: start event ---
  python3 "$COST_LOG" start "research/$RESEARCH_TAG" "iter-$iter" \
      --dispatch-mode subagent --agent-id "$AGENT_ID" \
      --worker-class "${WORKER_FLAG:-claude}" 2>/dev/null || true

  # --- Budget check at iteration start (before spawning claude -p) ---
  if [[ -n "$MAX_USD" ]]; then
    cum_usd=$(_cumulative_usd)
    if awk "BEGIN { exit !($cum_usd >= $MAX_USD) }"; then
      echo "info: budget-halt — cumulative USD $cum_usd >= max-usd $MAX_USD"
      printf '%s\t%s\t%s\t%s\t%s\n' \
        "" "" "" "budget-halt" "budget-halt: usd $cum_usd >= $MAX_USD" >> "$TSV_PATH"
      python3 "$COST_LOG" end "research/$RESEARCH_TAG" "iter-$iter" \
          --dispatch-mode subagent --agent-id "$AGENT_ID" --usd 0.0 2>/dev/null || true
      break
    fi
  fi
  if [[ -n "$MAX_TURNS" ]]; then
    cum_turns=$(_cumulative_turns)
    if [[ "$cum_turns" -ge "$MAX_TURNS" ]] 2>/dev/null; then
      echo "info: budget-halt — cumulative turns $cum_turns >= max-turns $MAX_TURNS"
      printf '%s\t%s\t%s\t%s\t%s\n' \
        "" "" "" "budget-halt" "budget-halt: turns $cum_turns >= $MAX_TURNS" >> "$TSV_PATH"
      python3 "$COST_LOG" end "research/$RESEARCH_TAG" "iter-$iter" \
          --dispatch-mode subagent --agent-id "$AGENT_ID" --usd 0.0 2>/dev/null || true
      break
    fi
  fi

  # --- Read prior TSV row for hypothesis context ---
  PRIOR_ROW=""
  if [[ -f "$TSV_PATH" ]]; then
    PRIOR_ROW=$(tail -1 "$TSV_PATH" || true)
    # If TSV only has the header, PRIOR_ROW equals the header — treat as empty
    if [[ "$PRIOR_ROW" == "$TSV_HEADER" ]]; then
      PRIOR_ROW=""
    fi
  fi

  # --- Resolve worker for this iteration ---
  # Per-iteration directive: check for ITER_WORKER_<N> env (set externally from manifest).
  # For now, the per-iteration override can be passed via _RESEARCH_ITER_WORKER env var
  # (set to empty string or the class name).
  ITER_WORKER_OVERRIDE="${_RESEARCH_ITER_WORKER:-}"
  RESOLVED_WORKER=$(_resolve_worker "$WORKER_FLAG" "$ITER_WORKER_OVERRIDE")

  # Check worker availability and apply fallback if needed
  ITER_OUTPUT_DIR=".claude/tasks/research-${RESEARCH_TAG}/output/iter-${iter}"
  EFFECTIVE_WORKER=$(_dispatch_mutation "$RESOLVED_WORKER" "iter-$iter" "$ITER_OUTPUT_DIR")

  echo "info: iter $iter: worker=$EFFECTIVE_WORKER"

  # --- Compose hypothesis prompt ---
  HYPOTHESIS_PROMPT="You are an automated code optimizer running iteration $iter of a Karpathy autoresearch loop.

Goal: $GOAL
Target file (the ONLY file you may modify): $TARGET_FILE
Benchmark command: $BENCHMARK_CMD
Metric regex: $METRIC_REGEX

Prior TSV row (commit, metric, memory, status, description):
${PRIOR_ROW:-(first iteration — no prior row)}

Instructions:
1. Read the current contents of $TARGET_FILE.
2. Propose a single, focused mutation that advances the goal.
3. Apply the mutation to $TARGET_FILE only — do NOT edit any other file.
4. Output a one-line description of the change (max 200 chars, no tabs or newlines).

Do not run the benchmark — the driver handles that.
Do not commit — the driver handles that.
Do not modify any file other than $TARGET_FILE."

  # --- Invoke claude -p (mutate step) — aggregation always runs in-session ---
  CLAUDE_OUTPUT=""
  MUTATION_EXIT=0
  if ! CLAUDE_OUTPUT=$(claude -p --output-format json "$HYPOTHESIS_PROMPT" 2>"$ITER_LOG"); then
    MUTATION_EXIT=$?
  fi

  # Pipe the captured JSON to cost_log.py (parse_json subcommand) — captures real cost_usd.
  # `|| true` keeps the loop alive on malformed JSON; the trailing `end` event
  # at line 533 then fires as zero-cost fallback (additive zero is harmless).
  if [[ "$MUTATION_EXIT" -eq 0 && -n "$CLAUDE_OUTPUT" ]]; then
    printf '%s' "$CLAUDE_OUTPUT" | python3 "$COST_LOG" parse-json - \
        "research/$RESEARCH_TAG" "iter-$iter" --agent-id "$AGENT_ID" 2>/dev/null || true
  fi

  if [[ "$MUTATION_EXIT" -ne 0 ]]; then
    # Typo / shell error path: fix-and-retry — do NOT advance counter, do NOT write TSV row
    echo "warn: iter $iter: shell error (claude -p exit $MUTATION_EXIT) — fix-and-retry" >&2
    git reset --hard HEAD 2>/dev/null || true
    python3 "$COST_LOG" end "research/$RESEARCH_TAG" "iter-$iter" \
        --dispatch-mode subagent --agent-id "$AGENT_ID" --usd 0.0 2>/dev/null || true
    iter=$((iter - 1))  # do not advance iteration counter
    continue
  fi

  # Extract description from claude output (result field from JSON output)
  DESCRIPTION=$(python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
    text = (d.get("result") or "").strip()
except Exception:
    text = ""
# last non-empty line
for line in reversed(text.splitlines()):
    line = line.strip()
    if line:
        print(line)
        break
' <<< "$CLAUDE_OUTPUT" || echo "iter $iter mutation")
  DESCRIPTION=$(_sanitize_desc "$DESCRIPTION")

  # --- Run benchmark ---
  BENCH_EXIT=0
  if ! eval "$BENCHMARK_CMD" > "$BENCH_LOG" 2>&1; then
    BENCH_EXIT=$?
  fi

  if [[ "$BENCH_EXIT" -ne 0 ]]; then
    # Typo / shell error path: benchmark returned non-zero — fix-and-retry
    echo "warn: iter $iter: benchmark non-zero exit ($BENCH_EXIT) — fix-and-retry" >&2
    git reset --hard HEAD 2>/dev/null || true
    python3 "$COST_LOG" end "research/$RESEARCH_TAG" "iter-$iter" \
        --dispatch-mode subagent --agent-id "$AGENT_ID" --usd 0.0 2>/dev/null || true
    iter=$((iter - 1))  # do not advance iteration counter
    continue
  fi

  # --- Grep metric ---
  metric=$(_extract_metric "$BENCH_LOG" "$METRIC_REGEX")

  if [[ -z "$metric" ]] || [[ "$metric" == "nan" ]] || [[ "$metric" == "NaN" ]]; then
    # "Idea broken" path: write crash row, reset, advance counter
    echo "warn: iter $iter: idea broken — metric not found or invalid; status=crash" >&2
    git reset --hard HEAD 2>/dev/null || true
    ITER_USD=0.0
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "" "" "" "crash" "$DESCRIPTION (idea broken: no metric)" >> "$TSV_PATH"
    python3 "$COST_LOG" end "research/$RESEARCH_TAG" "iter-$iter" \
        --dispatch-mode subagent --agent-id "$AGENT_ID" --usd "$ITER_USD" 2>/dev/null || true
    continue
  fi

  # --- Optional memory grep ---
  memory=""
  if [[ -n "$MEMORY_REGEX" ]]; then
    memory=$(_extract_metric "$BENCH_LOG" "$MEMORY_REGEX")
  fi

  # --- Decision: keep or reject ---
  COMMIT_SHA=""
  STATUS="reject"
  if _should_accept "$metric"; then
    COMMIT_MSG=$(printf "$COMMIT_PREFIX_TEMPLATE" "$RESEARCH_TAG" "$iter" "$metric")
    if git add -A && git commit -m "$COMMIT_MSG" 2>/dev/null; then
      COMMIT_SHA=$(git rev-parse HEAD)
      STATUS="keep"
      echo "info: iter $iter: KEEP — metric=$metric sha=${COMMIT_SHA:0:8}"
    else
      echo "warn: iter $iter: commit failed — treating as reject" >&2
      git reset --hard HEAD 2>/dev/null || true
    fi
  else
    git reset --hard HEAD 2>/dev/null || true
    echo "info: iter $iter: reject — metric=$metric (did not improve vs. last keep)"
  fi

  # --- Append TSV row ---
  ITER_USD=0.0
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$COMMIT_SHA" "$metric" "$memory" "$STATUS" "$DESCRIPTION" >> "$TSV_PATH"

  # --- Cost log: end event ---
  python3 "$COST_LOG" end "research/$RESEARCH_TAG" "iter-$iter" \
      --dispatch-mode subagent --agent-id "$AGENT_ID" --usd "$ITER_USD" 2>/dev/null || true

  # --- Stop-when predicate ---
  if _should_stop "$metric"; then
    echo "info: stop-when condition met at iter $iter (metric=$metric) — exiting"
    break
  fi
done

# ---------------------------------------------------------------------------
# Post-loop summary
# ---------------------------------------------------------------------------
TOTAL_ITERS=$iter
TOTAL_USD=$(_cumulative_usd 2>/dev/null || echo "0.0")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

cat <<EOF

Research loop complete.
  Iterations run : $TOTAL_ITERS
  Research tag   : $RESEARCH_TAG
  Branch         : $BRANCH
  TSV path       : $TSV_PATH
  Cumulative USD : $TOTAL_USD (best-effort from cost_log.py)

Review results:
  column -t -s \$'\\t' $TSV_PATH

This script never pushed. Branch stays local until you decide to publish.
EOF

exit 0
