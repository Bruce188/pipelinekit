# Host adapters

Interface contract for routing pipeline phase dispatches to alternate hosts.

**v1 scope: interface scaffold only.** Only `claude.sh` is functional. `codex.sh`, `cursor.sh`, `gemini.sh` are stubs that exit 2 with `not implemented`. There is no current orchestrator call site in pipelinekit — these scripts exist to fix the interface so a future `orchestrate.sh` (subprocess pipeline driver) can shell out as `host-adapters/${PIPELINE_HOST:-claude}.sh`.

## Interface

```
host-adapters/<host>.sh <prompt-file> <output-file> [--model <m>] [--max-turns N]
```

Exit codes:
- `0` — success
- `2` — not implemented (stub)
- non-zero — failure

## Adding a new host

1. Drop `<host>.sh` in this directory.
2. Implement the interface above.
3. `chmod +x <host>.sh`.
4. Set `PIPELINE_HOST=<host>` before invoking the orchestrator.
