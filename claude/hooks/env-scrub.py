#!/usr/bin/env python3
"""Subprocess env-scrub helper + PreToolUse detection hook.

Two modes:

1. PreToolUse hook (default): read tool_input JSON from stdin. In
   scrub-enabled environments (GITHUB_ACTIONS, CI, or
   CLAUDE_CODE_SCRUB_SUBPROCESS=1), detect commands that reference
   sensitive env vars by name. Log the event to
   ~/.claude/logs/subprocess-scrub.log and block with a helpful
   message that includes the suggested 'env -u' prefix.

2. --wrap <command>: print the command with the scrub prefix applied.
   Users invoke this manually when they want explicit scrubbing:
     python3 env-scrub.py --wrap "curl https://foo.bar"
   Outputs:
     env -u ANTHROPIC_API_KEY -u ... curl https://foo.bar

Claude Code hooks cannot rewrite tool_input on the fly, so the
auto-rewrite behavior from the feature spec is adapted into a
detect-and-block flow that's functionally equivalent — the user or
caller reissues the command with the prefix.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

# Mirrors Claude Code's GHA_SUBPROCESS_SCRUB (NETMIND PDF 2 §6.1).
SCRUB_VARS = (
    # Authentication
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_CUSTOM_HEADERS",
    # Telemetry with tokens
    "OTEL_EXPORTER_OTLP_HEADERS",
    # Cloud credentials
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_CLIENT_SECRET",
    # GitHub Actions OIDC
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    # GitHub Actions cache (supply-chain attack surface)
    "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_RUNTIME_URL",
    # Misc high-risk
    "ALL_INPUTS",
    "SSH_SIGNING_KEY",
)

# Preserved even in scrub mode — PDF 2 §7.2: packaging script needs these.
PRESERVED = frozenset({"GITHUB_TOKEN", "GH_TOKEN"})

LOG_PATH = os.path.expanduser("~/.claude/logs/subprocess-scrub.log")


def scrub_enabled() -> bool:
    env = os.environ
    if env.get("CLAUDE_CODE_SCRUB_SUBPROCESS") == "1":
        return True
    if env.get("GITHUB_ACTIONS") == "true":
        return True
    if env.get("CI") == "true" or env.get("CI") == "1":
        return True
    return False


def build_env_u_prefix() -> str:
    """Return the 'env -u X -u Y ...' scrub prefix."""
    parts = ["env"]
    for v in SCRUB_VARS:
        if v in PRESERVED:
            continue
        parts.append("-u")
        parts.append(v)
    return " ".join(parts)


def detect_var_leaks(command: str) -> list[str]:
    """Return the list of SCRUB_VARS that the command references by name."""
    leaks: list[str] = []
    for v in SCRUB_VARS:
        pattern = r"\$\{?" + re.escape(v) + r"\}?"
        if re.search(pattern, command):
            leaks.append(v)
    return leaks


def ensure_log_dir() -> None:
    d = os.path.dirname(LOG_PATH)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass


def append_log(command: str, detected: list[str]) -> None:
    ensure_log_dir()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    prefix = command[:120].replace("\n", " ")
    line = f"{ts} scrub_detected vars={','.join(detected)} cmd={prefix}\n"
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line)
    except OSError:
        pass  # best effort


def hook_mode() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    command = data.get("tool_input", {}).get("command", "") or ""
    if not command:
        return 0

    if not scrub_enabled():
        return 0

    leaks = detect_var_leaks(command)
    if not leaks:
        return 0

    append_log(command, leaks)

    prefix = build_env_u_prefix()
    print("BLOCKED: subprocess env-scrub mode is active (CI/GITHUB_ACTIONS/", file=sys.stderr)
    print(f"CLAUDE_CODE_SCRUB_SUBPROCESS). Command references: {', '.join(leaks)}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Claude Code strips these vars from subprocesses in CI to block", file=sys.stderr)
    print("prompt-injection exfiltration via ${VAR}-style leaks.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Re-run with the scrub prefix explicitly:", file=sys.stderr)
    print(f"  {prefix} <command>", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"(GITHUB_TOKEN/GH_TOKEN preserved. See {LOG_PATH} for audit log.)", file=sys.stderr)
    return 2


def wrap_mode(cmd: str) -> int:
    prefix = build_env_u_prefix()
    print(f"{prefix} {cmd}")
    return 0


def prefix_args_mode() -> int:
    parts = ["env"]
    for v in SCRUB_VARS:
        if v in PRESERVED:
            continue
        parts.append("-u")
        parts.append(v)
    print("\n".join(parts))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--wrap":
        if len(sys.argv) < 3:
            print("usage: env-scrub.py --wrap <command>", file=sys.stderr)
            return 2
        return wrap_mode(" ".join(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--prefix-args":
        return prefix_args_mode()

    return hook_mode()


if __name__ == "__main__":
    raise SystemExit(main())
