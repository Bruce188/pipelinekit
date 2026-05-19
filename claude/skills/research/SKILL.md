---
name: research
description: Karpathy autoresearch loop — hypothesize, mutate one file, run benchmark, keep-or-reset, append TSV row. Repeat until budget or iteration cap.
argument-hint: --goal <text> --target-file <path> --benchmark-cmd <cmd> --metric-regex <regex> [--memory-regex <regex>] [--max-iterations N] [--max-usd F] [--max-turns N] [--accept-when <expr>] [--stop-when <expr>]
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Edit
  - Grep
  - AskUserQuestion
---

# Research — Karpathy autoresearch loop

Runs a self-steering optimization loop over a single target file. Each iteration: derive a mutation hypothesis from the prior TSV row → apply the edit → run a benchmark → grep the metric → keep or reset → append a TSV row. Repeat until a budget cap or stop condition is met.

The actual loop body lives in `claude/skills/research/research-loop.sh`. This SKILL.md documents the contract, flags, and iteration phases. It does NOT inline the bash loop.

## Usage

Minimal invocation (unbounded iterations):

```bash
bash claude/skills/research/research-loop.sh \
  --goal "speed up X" \
  --target-file src/x.py \
  --benchmark-cmd "make bench" \
  --metric-regex "throughput=([0-9.]+)"
```

With caps (recommended for unattended runs):

```bash
bash claude/skills/research/research-loop.sh \
  --goal "reduce memory allocation in the hot path" \
  --target-file src/allocator.py \
  --benchmark-cmd "python bench/run.py --json" \
  --metric-regex "peak_mb=([0-9.]+)" \
  --memory-regex "alloc_calls=([0-9]+)" \
  --max-iterations 20 \
  --max-usd 5.00 \
  --max-turns 200 \
  --accept-when "metric < 512" \
  --stop-when "metric < 256"
```

Create the research branch first (before running the loop):

```bash
/new-branch --research-tag speed-allocator
# → creates branch research/speed-allocator-YYYY-MM-DD
bash claude/skills/research/research-loop.sh --goal ... --research-tag speed-allocator ...
```

## Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--goal` | string | **required** | Natural-language description of what to optimize. Fed to `claude -p` as the hypothesis seed each iteration. |
| `--target-file` | path | **required** | The single file the loop is allowed to mutate per iteration. |
| `--benchmark-cmd` | string | **required** | Shell command to run after each mutation. Stdout/stderr captured to a per-iteration log. |
| `--metric-regex` | regex | **required** | ERE pattern with one capture group (`([0-9.]+)`) to extract the numeric metric from benchmark output. |
| `--memory-regex` | regex | `""` (optional) | Like `--metric-regex` but for a secondary memory/resource measurement. Leave unset to omit the `memory` column. |
| `--max-iterations` | integer | `-1` (unlimited) | Hard cap on the number of iterations. Loop exits after this many iterations regardless of metric. |
| `--max-usd` | float | `""` (unlimited) | Halt at iteration boundary when cumulative cost (from `cost_log.py report-current`) reaches this value. |
| `--max-turns` | integer | `""` (unlimited) | Halt at iteration boundary when cumulative sub-agent turns reach this value. |
| `--accept-when` | shell expr | `""` | Shell expression evaluated with `$metric` in scope. If true, commit the iteration unconditionally. Overrides the default "improve vs. last keep" heuristic. |
| `--stop-when` | shell expr | `""` | Shell expression evaluated with `$metric` in scope. If true, exit the loop after committing. |
| `--research-tag` | slug | current branch | Kebab-case slug used in the commit message (`chore: research <slug> iter N — metric=<value>`) and in cost-log feature name (`research/<slug>`). Defaults to the portion of the current branch name after `research/` if the branch matches that pattern. |
| `--worker` | class | `claude` | Worker class for the mutation phase (`claude`, `codex`, etc.). Resolution order: per-iteration `_RESEARCH_ITER_WORKER` env override > this flag > `WORKER_CLASS` env var > default `claude`. Aggregation (keep-or-reset + TSV append) always runs in-session regardless of mutation worker. If the resolved class is unavailable (host-adapter exits 2), `WORKER_UNAVAILABLE: <class>` is logged to stderr and the iteration falls back to in-session Claude. |
| `--dry-run` | flag | unset | Print the resolved arg surface and exit 0 without mutating anything, spawning `claude -p`, or writing to the TSV. |

## Worker routing

The mutation phase (step 2) can be delegated to a non-default worker class via `--worker <class>`. The aggregation phase (steps 5–6: keep-or-reset and TSV append) always runs in-session regardless of the mutation worker.

Worker class resolution per iteration:
1. Per-iteration directive: `_RESEARCH_ITER_WORKER` env var (set externally from experiment manifest). Takes priority over everything.
2. `--worker <class>` global flag.
3. `WORKER_CLASS` env var.
4. Default: `claude` (always-available in-session).

Fallback semantics:
- If the resolved class is absent (host-adapter exits 2): log `WORKER_UNAVAILABLE: <class> (host-adapter missing)` and fall back to in-session Claude for that iteration. Iteration counter advances normally.
- If the host-adapter exits other non-zero: log `WORKER_FALLBACK: <iter-id> <class> -> claude (exit <rc>)` and retry once via ClaudeWorker. Second failure marks the iteration as a crash row in the TSV.

Artifacts from delegated mutation phases are written to `.claude/tasks/research-<tag>/output/iter-<N>/` (stdout, stderr, exit files).

## Iteration phases

Each iteration runs these six phases in order:

1. **Hypothesize** — Read the prior TSV row (or the `--goal` alone on iteration 1) to derive a one-shot mutation idea. The idea is expressed as a `claude -p` prompt that constrains the mutation to `--target-file` only. The prompt includes the full goal, the target file path, the prior TSV row as context, and the metric regex so the model understands what success looks like.

2. **Mutate one file** — Invoke `claude -p "$HYPOTHESIS_PROMPT"` as a subprocess. The subprocess edits `--target-file` in-place. No other files may be touched. Stdout/stderr are captured to `/tmp/research-iter-N.log`. The loop driver never enforces this at the filesystem level — it is the responsibility of the hypothesis prompt to constrain the model.

3. **Run benchmark** — Execute `--benchmark-cmd`. Stdout/stderr are captured to `/tmp/research-bench-N.log`. If the command exits non-zero, the **typo / shell error** path fires (see Crash policy below). A non-zero exit is treated as a tooling failure, not a semantic failure.

4. **Grep metric** — Extract the numeric value using `--metric-regex` against the benchmark log. The regex must have exactly one capture group returning a float or integer. If no match is found, or the value is empty or NaN, the **"idea broken"** path fires (see Crash policy below).

5. **Git keep-or-reset** — If the metric passes the accept condition (`--accept-when` expr or "improves vs. last keep" heuristic): `git add -A && git commit -m "chore: research <slug> iter N — metric=<value>"`. Otherwise: `git reset --hard HEAD`. The commit fires the full hook chain (`validate-commit-msg.sh`, `strip-ai-attribution.sh`, `block-stage-sensitive.sh`).

6. **Append row to `docs/research-results.tsv`** — Write one tab-separated row in the locked Karpathy column order. The TSV is NEVER staged (see § What's Next). Only `keep`, `reject`, `crash`, and `budget-halt` iterations append a row; typo/shell-error iterations do not advance the counter and do not append.

## Resumability

Every iteration is independently resumable. The loop reads state exclusively from:
- The prior TSV row (`tail -1 docs/research-results.tsv`) for hypothesis context.
- The current `git status` (working tree should be clean at iteration start; any partial mutation is reset via `git reset --hard HEAD` before the iteration is re-attempted).

Crash recovery procedure: re-run `bash claude/skills/research/research-loop.sh` with the same flags. The loop picks up at the next iteration automatically — the TSV row count tells it where it left off.

Optional `--restart-from-iter N` skips iterations 1..N-1 and begins normal execution at N. Useful when the TSV log is intact but you need to re-run a specific iteration window. Refuses when N exceeds `--max-iterations` or no TSV row exists for iter N-1.

## TSV columns

Locked column order (Karpathy interop — do NOT reorder):

```
commit	metric	memory	status	description
```

- `commit` — the git SHA if the iteration was kept, empty string otherwise.
- `metric` — numeric value extracted by `--metric-regex`.
- `memory` — numeric value extracted by `--memory-regex`, or empty string if `--memory-regex` is unset.
- `status` — one of: `keep` | `reject` | `crash` | `budget-halt`.
- `description` — one-line free-text hypothesis summary (truncated to 200 chars; tabs and newlines sanitized).

The header line (`commit\tmetric\tmemory\tstatus\tdescription`) is written once on the first iteration if `docs/research-results.tsv` does not yet exist. Subsequent iterations append rows only — the header is never rewritten.

## Crash policy

Two distinct failure modes require different responses:

**Typo / shell error** (non-zero exit from benchmark command, or subprocess scaffolding failure):
- Do NOT write a TSV row.
- Do NOT advance the iteration counter.
- `git reset --hard HEAD` to discard any partial file mutation.
- Log the error to stderr: `iter N: shell error — fix-and-retry`.
- On the next outer-loop pass, the same iteration number is retried from scratch.

**"Idea broken"** (benchmark runs cleanly but `--metric-regex` extracts no valid number, or the value is NaN / empty, or a user-defined hard-fail predicate matches):
- Write a TSV row with `status=crash`.
- `git reset --hard HEAD`.
- Advance the iteration counter (the idea is logged as failed; a new hypothesis is attempted next).
- Log: `iter N: idea broken — status=crash`.

## Budget caps

Both `--max-usd` and `--max-turns` are honored via `cost_log.py`. Caps are checked at each **iteration boundary** — before spawning the next `claude -p` subprocess. This mirrors the phase-boundary halts used by `/pipeline`.

The loop emits `start`/`end` events per iteration:

```bash
python3 claude/hooks/cost_log.py start "research/<tag>" "iter-N" \
    --dispatch-mode subagent --agent-id "research-pid$$"
# ... claude -p subprocess runs ...
python3 claude/hooks/cost_log.py end "research/<tag>" "iter-N" \
    --dispatch-mode subagent --agent-id "research-pid$$" --usd "$ITER_USD"
```

Cost-log dispatch-mode is **always `subagent`** — `subprocess` is silently rejected by the argparse `choices` filter at `cost_log.py` line 224 and MUST NOT be used.

The per-iteration `--usd` value is best-effort: if `claude -p` does not expose per-call cost in its output, the loop passes `--usd 0.0` to the end event. A future iteration of this skill can parse `claude -p --output-format json` to extract the `cost_usd` field.

At each iteration boundary the loop checks whether the next iteration would exceed `--max-usd` or `--max-turns`. If so, the loop writes a final TSV row with `status=budget-halt` and exits 0. Both caps are independent — either one can trigger a halt regardless of the other.

## Commit message format

Keep iterations use this exact format:

```
chore: research <slug> iter N — metric=<value>
```

Example: `chore: research speed-allocator iter 7 — metric=341.2`

**Why `chore:` and not `research:`?** The `validate-commit-msg.sh` hook at line 325 enforces an allowlist of `(feat|fix|refactor|docs|test|chore|perf|style|build|ci)`. The literal `research:` prefix is NOT in the allowlist. Using `chore:` is the smaller-blast-radius choice — it requires no edit to `validate-commit-msg.sh`. This is the correct convention for this project.

## Branch naming

Before starting a research loop, create a date-stamped branch:

```bash
/new-branch --research-tag <slug>
```

This produces a branch named `research/<slug>-YYYY-MM-DD` (UTC date). The `--research-tag` flag bypasses the type-prefix validator in `new-branch` — the `research/` prefix is intentionally not in the conventional allowlist. All other `new-branch` validation rules (kebab-case, not `main`/`master`, base-branch detection) still apply.

Pass the same `<slug>` to the loop via `--research-tag <slug>` so the commit messages and cost-log feature name align with the branch name.

## What's Next

The loop appends rows to `docs/research-results.tsv` after each iteration. This file is **never staged** — `block-stage-sensitive.sh` blocks it because `docs/research-results.tsv` is listed under the `# Research artifacts` section of `claude/config/never-stage.txt`.

After the loop exits, review the TSV manually:

```bash
column -t -s $'\t' docs/research-results.tsv
```

To cherry-pick a specific keep iteration into a PR, identify its commit SHA from the TSV and use `git cherry-pick`. The loop never calls `git push` — the branch stays local until you decide to publish.

See `claude/skills/research/research-loop.sh` for the complete bash implementation.
