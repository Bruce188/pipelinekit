<!--
diataxis: how-to
-->
# WSL2 performance: VmmemWSL RAM & the per-session MCP footprint

If `VmmemWSL` (the Windows-side process that mirrors your whole WSL2 VM) is eating RAM and making Windows lag, two levers fix almost all of it: a tuned `.wslconfig`, and keeping heavy MCP servers out of your global config. This page covers both. It complements [Memory + graph stack](memory-graph-stack.html), which documents the per-daemon RAM budget and the `PIPELINE_DISABLE_*` kill switches.

> [INFO] `pipelinekit`'s installer prints a `.wslconfig` advisory on WSL2 hosts (see `scripts/install.sh` → `_wslconfig_advisor`), and the `mcp-rss-cap.sh` SessionStart hook warns when the cumulative MCP footprint runs over budget. This page is the reference behind both.

## Why VmmemWSL balloons

`VmmemWSL` is not a process you can trim directly — it is the Windows-visible sum of everything running *inside* the WSL2 VM, plus the VM's page cache. Two defaults make it grow and stay grown:

- **No memory ceiling.** By default WSL2 may claim ~50% of physical RAM. On a 32 GB host that is ~16 GB the VM is free to hold.
- **No reclaim.** Without `autoMemoryReclaim`, pages the VM caches are **never returned to Windows**, so `VmmemWSL` stays at its high-water mark even after the workload that needed the RAM has exited.

The result: one heavy build or a few concurrent sessions push `VmmemWSL` to its peak, and it never shrinks back. Windows then runs short on RAM and feels sluggish.

## Tune `.wslconfig` (the key lever)

Create or edit `C:\Users\<you>\.wslconfig` on the **Windows** side:

```ini
[wsl2]
autoMemoryReclaim=gradual   # KEY: return idle cached RAM to Windows (shrinks VmmemWSL)
memory=16GB                 # ceiling, not a reservation — set to ~50-60% of physical RAM
processors=4                # example — set to (host logical CPUs minus a few for Windows)
swap=8GB                    # absorbs build/test spikes instead of OOM-killing your work
```

- **`autoMemoryReclaim=gradual`** is the single most important line — it is what lets `VmmemWSL` give memory back. `gradual` reclaims slowly as pages go idle; `dropcache` reclaims more aggressively on a schedule.
- **`memory`** is a *ceiling*, not a reservation. With `autoMemoryReclaim` on, the VM hovers near actual usage and only climbs toward the cap under load, leaving the rest for Windows.
- **`processors`** reserves cores for Windows. Capping below your logical-CPU count keeps the Windows foreground responsive while a build (e.g. a `dotnet`/`VBCSCompiler` spike) saturates the VM.

Apply the change from **PowerShell**:

```powershell
wsl --shutdown
```

This restarts the VM (it ends running WSL sessions), after which the new limits and reclaim behaviour take effect. To silence the installer's advisory, export `PIPELINE_NO_WSLCONFIG_ADVICE=1` before running `scripts/install.sh`.

## MCP servers multiply per session

This is the counter-intuitive part. A **stdio** MCP server is spawned **per Claude session**, not once per machine. So a server registered in your *global* `~/.claude.json` launches a fresh copy in **every** session — `N` concurrent sessions means `N` copies, whether or not that project uses the tool.

| Where it's configured | With `N` sessions |
|-----------------------|-------------------|
| Global stdio MCP (`~/.claude.json`) | **`N` copies** — one per session, used or not |
| Per-project stdio MCP (`<project>/.mcp.json`) | only sessions opened *in that project* spawn it |
| Shared HTTP/SSE daemon | **1 process**, many clients (true sharing) |

"Global" therefore does **not** mean "shared once" — it means "every session pays for it." The fix is to keep light, universal servers global and scope heavy or niche ones per-project:

- **Keep global:** `context7` (lightweight docs lookup), `agentmemory` (canonical memory, needed everywhere).
- **Scope per-project (`<project>/.mcp.json`):** `serena` — it drags heavy language servers (the bundled Java LSP alone runs with `-Xmx3G`); RAG servers like `local-rag`; and situational servers (`sequential-thinking`, `RepoMapper`). `pipelinekit`'s `.mcp.json.template` already places these per-project.
- **Drop entirely** anything you do not use in any session.

> [WARNING] Even per-project, opening the *same* project in two terminals spawns two copies — the multiplier is fundamentally per-session. The lever you control is how many servers each session starts, so scope aggressively.

### Hooks that watch the footprint

- **`mcp-rss-cap.sh`** (SessionStart) sums the RSS of the known MCP daemons — including `serena` and its language servers — and warns (never kills) when the total runs over budget. The cap is **per-session and scales by detected session count**, so running several sessions does not produce a false alarm; a sum over `count × PIPELINE_MAX_MCP_RSS_MB` indicates real leakage. The warning also suggests scoping `serena` per-project or closing idle sessions.
- **`kill-rogue-mcp-daemon.sh`** (SessionStart) reaps orphaned MCP daemons (parent died, running over an age threshold) — the original guard against a runaway-subprocess `VmmemWSL` lockup.

## Environment knobs

| Variable | Default | Effect |
|----------|---------|--------|
| `PIPELINE_NO_WSLCONFIG_ADVICE` | unset | `=1` suppresses the installer's `.wslconfig` advisory |
| `PIPELINE_MAX_MCP_RSS_MB` | `800` | Per-session RSS budget; effective cap = this × live session count |
| `PIPELINE_NO_RSS_CAP` | unset | `=1` disables the `mcp-rss-cap.sh` warning entirely |
| `PIPELINE_DISABLE_AGENTMEMORY` / `_CODEGRAPH` / `_GRAPHIFY` | unset | `=1` skips that daemon's launch (see [Memory + graph stack](memory-graph-stack.html)) |
| `PIPELINE_NO_ROGUE_REAPER` | unset | `=1` disables the orphan-daemon reaper |

## See also

- [Memory + graph stack](memory-graph-stack.html) — per-daemon RAM budget and the `PIPELINE_DISABLE_*` kill switches.
- [MCP LSP setup](mcp-lsp-setup.html) — the `serena` semantic-navigation MCP and its language servers.
