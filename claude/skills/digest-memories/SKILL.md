---
name: digest-memories
description: Synthesize per-project memory proposals from the session journal written by memory-journal.sh. User-invoked via /digest-memories slash command. Reads recent sessions, proposes additions to ~/.claude/projects/<slug>/memory/, requires user confirmation before writing.
argument-hint: ([--since <date>] [--limit <N>] [--dry-run])
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
model: inherit
paths:
  - claude/skills/digest-memories/**
disable-model-invocation: true
---

# /digest-memories — Synthesize learnings from recent sessions

User-invoked slash command that reads the session journal (`~/.claude/projects/<slug>/memory-journal.jsonl`, written by `memory-journal.sh` Stop hook) and proposes additions to the project memory store.

## Why this is split from a Stop hook

The previous implementation (`stop-self-reflect.sh`, removed in #117) ran on every Stop event and spawned `claude -p` per turn for the synthesis. Empirically: 28/28 outputs were `{"proposals":[]}` — zero useful learnings — while burning Opus tokens and triggering recursive `claude -p` spawn that caused 12GB WSL memory lockups (#112).

This skill replaces the Stop-hook synthesis with **user-invoked, in-session** synthesis:

- The Stop hook (`memory-journal.sh`) does only journaling — no LLM call, no subprocess.
- This skill runs in the **current LEAD session's context** — no `claude -p` subprocess.
- The user controls when synthesis happens; cost is bounded and predictable.

## Arguments

| Arg | Default | Behavior |
|-----|---------|----------|
| `--since <YYYY-MM-DD>` | last digest marker, or 7 days ago if marker absent | Only consider journal entries on or after this date |
| `--limit <N>` | 25 | Cap on journal entries to digest in one run (oldest-first) |
| `--dry-run` | off | Print proposals to stdout but do NOT write memory files or update the marker |

## Process

### Step 1: Locate journal and marker

```bash
SLUG=$(printf '%s' "$PWD" | sed 's|/|-|g')
JOURNAL="$HOME/.claude/projects/$SLUG/memory-journal.jsonl"
MARKER="$HOME/.claude/projects/$SLUG/.last-digest"
MEM_DIR="$HOME/.claude/projects/$SLUG/memory"
```

If `$JOURNAL` does not exist: print `No journal at $JOURNAL — has the memory-journal Stop hook fired yet?` and exit.

### Step 2: Determine the cutoff

```bash
if [ -n "$ARG_SINCE" ]; then
  CUTOFF="$ARG_SINCE"
elif [ -f "$MARKER" ]; then
  CUTOFF=$(head -n1 "$MARKER")
else
  CUTOFF=$(date -u -d "7 days ago" +"%Y-%m-%dT00:00:00Z" 2>/dev/null \
           || date -u -v-7d +"%Y-%m-%dT00:00:00Z")
fi
```

### Step 3: Select journal entries

Read `$JOURNAL`, filter to entries with `ts >= CUTOFF`, cap at `--limit` (default 25), oldest-first. Use python3 (jq not installed):

```bash
python3 - <<PYEOF
import json, os, sys
cutoff = os.environ['CUTOFF']
limit = int(os.environ.get('LIMIT', '25'))
entries = []
with open(os.environ['JOURNAL']) as f:
    for line in f:
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get('ts', '') >= cutoff:
            entries.append(e)
entries.sort(key=lambda e: e.get('ts', ''))
for e in entries[:limit]:
    print(json.dumps(e))
PYEOF
```

If zero entries match: print `No journal entries since $CUTOFF.` and exit.

### Step 4: Sample transcripts

For each selected entry with a populated `transcript_path` that still exists, read the transcript (it is a JSONL file with one event per line; the last assistant message and the trailing user message are most informative).

**Cost cap:** read at most the LAST 2 KB of each transcript. Transcripts can be > 100 MB; full reads will overflow context. Use `tail -c 2048 <transcript_path>` then parse the partial JSONL tolerantly (the head of the slice may not start at a line boundary — drop the first partial line).

### Step 5: Synthesize proposals

In-session synthesis — you (the LEAD) read the sampled transcripts and propose memory additions. Use the four memory types defined in `~/.claude/CLAUDE.md § Memory System`:

- **user** — about the user's role, preferences, expertise
- **feedback** — corrections or validated approaches the user gave you
- **project** — work-in-progress context that won't live in code or git
- **reference** — pointers to external systems and their purpose

**Anti-noise filter** — propose ONLY items meeting ALL of these:

1. **Non-derivable** — cannot be reconstructed by reading code or `git log`.
2. **Re-applicable** — likely to influence work in a future session.
3. **Specific** — names a concrete preference, decision, or pointer (not "the user likes clean code").

If after applying the filter you have ZERO proposals, that is the correct answer. Print `No memory-worthy learnings extracted from <N> sessions since <CUTOFF>.` and skip Step 6.

### Step 6: User confirmation

For each proposal, present the candidate memory:

```
Proposed memory: <type>/<name>.md
  Description: <one-line>
  Body excerpt: <first 2 lines>
```

Use `AskUserQuestion` with options:
- `Write all proposals` — apply all
- `Review one-by-one` — iterate, asking per-proposal
- `Skip — write none`

In `--dry-run` mode: skip the `AskUserQuestion` and print all proposals to stdout instead.

### Step 7: Write memory files

For each approved proposal:

1. Compose the memory file with frontmatter per `~/.claude/CLAUDE.md § How to save memories`:
   ```markdown
   ---
   name: <kebab-case-slug>
   description: <one-line summary>
   metadata:
     type: <user|feedback|project|reference>
     last_seen: <today's date YYYY-MM-DD>
     confidence: 0.9
   ---

   <body>
   ```
2. Write to `$MEM_DIR/<type>_<slug>.md` (create `$MEM_DIR` if absent).
3. Append a one-line index entry to `$MEM_DIR/MEMORY.md` under the matching `## <Type>` section: `- [Title](file.md) — one-line hook`.
4. If `MEMORY.md` does not exist, create it with section headers (`## User`, `## Feedback`, `## Project`, `## Reference`).

### Step 8: Update the marker

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$MARKER"
```

In `--dry-run` mode: skip this step.

## Output format

After Step 7 / 8:

```
/digest-memories complete:
  Journal: <count> entries scanned (since <CUTOFF>)
  Proposals: <N> proposed, <M> written, <K> skipped
  Memory dir: <MEM_DIR>
  Next digest: anything from <now-iso>
```

## Constraints

- **No LLM subprocess.** This skill must NOT invoke `claude -p`, `claude --headless`, or any subprocess that spawns another Claude session. All synthesis happens in the current session.
- **No writes without confirmation.** Unless `--dry-run`, every memory file write must be user-approved via `AskUserQuestion` (per-proposal or batch).
- **Bounded transcript reads.** Cap at 2 KB tail per transcript to keep context cost predictable.
- **Idempotent.** Running `/digest-memories` twice with no new journal entries between runs should propose zero new memories (the marker prevents re-scanning the same range).
- **Per-project scope.** Only writes under `~/.claude/projects/$SLUG/memory/` — never touches another project's memory store.

## See Also

- Stop hook that writes the journal: `claude/hooks/memory-journal.sh`.
- Memory schema and decay rule: `~/.claude/CLAUDE.md § Memory System`.
- Why the previous Stop-hook synthesis was removed: PR #117 and `docs-source/changelog.md` § "Skill removals (breaking)".
