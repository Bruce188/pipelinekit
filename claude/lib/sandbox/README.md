# Sandbox Library

Pluggable sandbox boundary for Claude Code pipelines. Dispatches worker commands into an
isolation provider selected by environment variables.

---

## Contract

When `SANDBOX_PROVIDER` is unset, the dispatcher defaults to `worktree-only` — the same
no-op isolation that pipelinekit has always used. **No behavior change from pre-sandbox
pipelinekit.** This is a deliberate backward-compat promise (plan-v9 Constraint #1,
audited in review-v7 N1). Container isolation requires explicit opt-in.

---

## Resolution Order

Priority evaluated top-to-bottom; first match wins:

1. `PIPELINE_NO_SANDBOX=1` → `worktree-only`
   (escape hatch — unconditional, overrides any value of `SANDBOX_PROVIDER`)

2. `SANDBOX_PROVIDER=<known-name>` (worktree-only | podman | docker)
   → that provider if the binary is found on PATH; else stderr fallback message + `worktree-only`

3. `SANDBOX_PROVIDER=auto`
   → discovery chain: `podman` → `docker` → `worktree-only`

4. `SANDBOX_PROVIDER` unset
   → `worktree-only` (no behavior change from pre-sandbox pipelinekit)

5. `SANDBOX_PROVIDER=<unknown-value>`
   → stderr warning + `worktree-only`
   (`sandbox: unknown SANDBOX_PROVIDER '<value>', falling back to worktree-only`)

---

## Opt-In Discovery

`SANDBOX_PROVIDER=auto` is the explicit opt-in for container-runtime discovery. The
dispatcher probes PATH in order: `podman` first, then `docker`, then falls through to
`worktree-only`. Discovery is silent on success. On fall-through to `worktree-only`, no
stderr log is emitted — the fallback is intentional and expected. Callers that want
observability can log the resolved provider after calling `provider_detect`:

```bash
source "$CLAUDE_HOME/lib/sandbox/SandboxProvider.sh"
PROVIDER=$(provider_detect)
echo "resolved sandbox provider: $PROVIDER" >&2
source "$CLAUDE_HOME/lib/sandbox/providers/${PROVIDER}.sh"
```

---

## Escape Hatch

`PIPELINE_NO_SANDBOX=1` is the universal short-circuit. It unconditionally resolves to
`worktree-only` regardless of any `SANDBOX_PROVIDER` value — even an explicit `podman`
or `docker`. Use case: recovery for hosts where the chosen provider is broken (e.g.,
rootless podman fails on a hardened host, or a CI environment lacks a container runtime).

---

## Valid Values

`SANDBOX_PROVIDER` accepts exactly:

| Value | Behavior |
|-------|----------|
| `worktree-only` | No-op isolation; cd into worktree and exec the command directly. |
| `podman` | Rootless Podman container; falls back to `worktree-only` if podman not on PATH. |
| `docker` | Docker container; falls back to `worktree-only` if docker not on PATH. |
| `auto` | Discovery chain: `podman` → `docker` → `worktree-only`. |
| (unset) | Defaults to `worktree-only` (backward-compat contract). |
| any other | stderr warning + `worktree-only` fallback. |

---

## Rationale

Unset defaults to `worktree-only` rather than `auto` for three reasons: (1) backward
compatibility is the stronger contract — users who never set `SANDBOX_PROVIDER` should
not silently acquire container isolation; (2) silent activation of container isolation can
break CI environments and hardened hosts where container runtimes require specific
configuration; (3) `worktree-only` is the proven-production-safe default that has shipped
since the start of pipelinekit. The `auto` discovery path exists for users who explicitly
want it. See plan-v9 Constraint #1 for the original promise and review-v7 N1 for the
contradiction audit that produced this fix.

---

## Library Layout

- `SandboxProvider.sh` — dispatcher; defines `provider_detect()` and `sandbox_enter()`.
- `providers/worktree-only.sh` — no-op isolation; the default and the fallback.
- `providers/podman.sh` — rootless container isolation via podman.
- `providers/docker.sh` — container isolation via docker.
