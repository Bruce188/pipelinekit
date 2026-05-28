# Host adapters

Interface contract for routing pipeline phase dispatches to alternate hosts.

**v1 scope: interface scaffold + orchestrator call site.** Only `claude.sh` is functional. `codex.sh`, `cursor.sh`, `gemini.sh` are stubs that exit 2 with `not implemented`. The pipeline orchestrator wires host adapters via the public helper `run_host_adapter <host> <worktree> <prompt-file> <output-file> [args...]`. The helper resolves `host-adapters/${host}.sh`, refuses to execute when the adapter is missing (stderr + exit `2`), and wraps the invocation in `sandbox_enter` / `sandbox_exit` with a `SANDBOX_ENTER: provider=<X>, task=host:<host>:<pid>, image=<image>` observability line.

## Interface

```
host-adapters/<host>.sh <prompt-file> <output-file> [--model <m>] [--max-turns N]
```

Exit codes:
- `0` — success
- `2 — runtime unavailable (stub or missing CLI)`
- non-zero — failure

## Adding a new host

1. Drop `<host>.sh` in this directory.
2. Implement the interface above.
3. `chmod +x <host>.sh`.
4. Set `PIPELINE_HOST=<host>` before invoking the orchestrator.
