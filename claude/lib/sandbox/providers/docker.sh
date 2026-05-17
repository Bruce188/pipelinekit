#!/usr/bin/env bash
# claude/lib/sandbox/providers/docker.sh — Docker sandbox provider.
#
# This provider is selected when SANDBOX_PROVIDER=docker (or SANDBOX_PROVIDER=auto,
# podman is not on PATH, and docker is on PATH).
#
# Public interface (implements the SandboxProvider contract):
#   sandbox_enter <worktree-path> <command...>   — run command inside a Docker container
#   sandbox_exit  <session-id>                    — no-op; --rm handles container cleanup
#
# Key behaviours:
#   - Bind-mounts the worktree directory READ-WRITE; NEVER copies worktree contents.
#     The worktree path inside the container matches the host path exactly, so all
#     relative-path references within the command continue to work unchanged.
#   - Composes with claude/hooks/env-scrub.py --wrap to apply the existing env scrub
#     prefix — do NOT redefine SCRUB_VARS here; env-scrub.py owns that list and
#     keeps it in sync with the Claude Code hook chain.
#   - Uses --rm so the container is removed automatically on exit; sandbox_exit is a no-op.
#   - Does NOT use --userns=keep-id (not universally supported by Docker).
#     File ownership inside the container follows the image's default USER directive.
#     On Linux hosts, run the container as the host UID by adding --user "$(id -u):$(id -g)"
#     to a custom wrapper if needed.
#   - Does NOT apply :Z SELinux relabelling (not all Docker installations support it).
#     On SELinux-enforcing systems, pass --security-opt label=disable or configure the
#     bind mount appropriately in the container runtime policy.
#
# PIPELINE_NO_SANDBOX=1: handled upstream by provider_detect() in SandboxProvider.sh;
#   this file is not sourced when that flag is set — worktree-only.sh is used instead.
#
# Env vars (all optional):
#   SANDBOX_DOCKER_IMAGE   — container image (default: pipelinekit-sandbox:latest)
#   CLAUDE_HOME            — path to the Claude Code config directory (default: $HOME/.claude)
#
# Runtime requirements:
#   - docker must be installed and the daemon must be running.
#     Detection is performed upstream in provider_detect(); if docker is absent when
#     SANDBOX_PROVIDER=auto was requested, the provider falls back to worktree-only
#     without reaching this file.
#
# This file is sourced, never executed directly.

# ---------------------------------------------------------------------------
# sandbox_enter <worktree-path> <command...>
#
# Runs the given command inside a Docker container with the worktree directory
# bind-mounted read-write.
#
# Arguments:
#   $1   — absolute path to the worktree directory (must exist on the host)
#   $@   — command and arguments to execute inside the container
#
# The env-scrub prefix is applied by env-scrub.py --wrap before the command
# is passed to `sh -c` inside the container, stripping sensitive env vars
# (ANTHROPIC_API_KEY, cloud credentials, etc.) from the container environment.
# ---------------------------------------------------------------------------
sandbox_enter() {
  local wt="$1"; shift
  local image="${SANDBOX_DOCKER_IMAGE:-pipelinekit-sandbox:latest}"
  local claude_home="${CLAUDE_HOME:-$HOME/.claude}"
  local scrubbed

  # env-scrub.py --wrap emits `env -u VAR1 -u VAR2 ... <command>` on stdout.
  # Capture that output and pass it to sh -c inside the container so the full
  # env-scrub prefix is applied in the container environment.
  scrubbed=$(python3 "${claude_home}/hooks/env-scrub.py" --wrap "$*")

  docker run --rm \
    --volume "$wt:$wt:rw" \
    --workdir "$wt" \
    "$image" \
    sh -c "$scrubbed"
}

# ---------------------------------------------------------------------------
# sandbox_exit <session-id>
#
# No-op for the Docker provider.
#
# The --rm flag on `docker run` removes the container automatically when the
# command exits. No persistent session or named container is created, so there
# is nothing to clean up in this hook.
#
# Arguments:
#   $1   — session ID (ignored; present for interface compatibility)
# ---------------------------------------------------------------------------
sandbox_exit() {
  # --rm cleans up the container; nothing else to do.
  return 0
}
