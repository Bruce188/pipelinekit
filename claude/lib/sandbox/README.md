# Sandbox Library

Pluggable sandbox boundary for Claude Code pipelines. Dispatches worker commands into an
isolation provider selected by environment variables.

---

## Contract

When `SANDBOX_PROVIDER` is unset, the dispatcher defaults to `auto` — engine-when-present
discovery (`podman` → `docker` → `worktree-only`). On hosts with no container engine, the
auto branch falls through to `worktree-only` and emits one stderr line:
`sandbox: container runtime not found — using worktree-only fallback`. This makes
container isolation default-on without breaking engine-less hosts (mobile, Codespaces,
minimal CI). Explicit opt-out: `SANDBOX_PROVIDER=worktree-only` or `PIPELINE_NO_SANDBOX=1`.
History: the original contract defaulted to `worktree-only` for backward compat (plan-v9);
F12 (2026-05-26) flipped the default to `auto` once the engine-when-present chain was
proven safe and the stderr-fallback log was added.

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
   → `auto` (F12 default — engine-when-present with stderr-logged fallback)

5. `SANDBOX_PROVIDER=<unknown-value>`
   → stderr warning + `worktree-only`
   (`sandbox: unknown SANDBOX_PROVIDER '<value>', falling back to worktree-only`)

---

## Default Discovery

`auto` is the default — used both when `SANDBOX_PROVIDER` is unset and when explicitly set
to `auto`. The dispatcher probes PATH in order: `podman` first, then `docker`, then falls
through to `worktree-only`. Discovery is silent on engine-present resolution. On
fall-through to `worktree-only`, one stderr line is emitted so users discover why
container isolation did not engage:
`sandbox: container runtime not found — using worktree-only fallback`. Callers that want
observability of the resolved provider can log it after calling `provider_detect`:

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
| `auto` | Discovery chain: `podman` → `docker` → `worktree-only` (stderr-logged fallback). |
| (unset) | Defaults to `auto` (F12 — engine-when-present, graceful fallback). |
| any other | stderr warning + `worktree-only` fallback. |

---

## Rationale

F12 (2026-05-26) flipped the unset default from `worktree-only` to `auto` for three
reasons: (1) the marketing claim in README.md ("sandbox-isolated execution by default")
was contradicted by the implementation — unset users got no isolation; (2) `docs-source/
pipeline.md` documented `auto` as the default while the code did not — drift; (3) the
engine-when-present chain is proven safe via four-case test coverage
(`tests/test_provider_auto_resolution.sh`). Hosts without a container engine fall through
to `worktree-only` with a single stderr line, preserving engine-less environments
(mobile, Codespaces, CI without runtimes). Users wanting the pre-F12 behaviour set
`SANDBOX_PROVIDER=worktree-only` or `PIPELINE_NO_SANDBOX=1`.

---

## Library Layout

- `SandboxProvider.sh` — dispatcher; defines `provider_detect()` and `sandbox_enter()`.
- `providers/worktree-only.sh` — no-op isolation; the default and the fallback.
- `providers/podman.sh` — rootless container isolation via podman.
- `providers/docker.sh` — container isolation via docker.
