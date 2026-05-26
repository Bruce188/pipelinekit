#!/usr/bin/env bash
# scan-tool-output.sh -- PostToolUse advisory prompt-injection scanner.
#
# Scans tool output (WebFetch responses, outside-repo Read results) for
# prompt-injection patterns via `claude.hooks._promptguard.scan`. Advisory
# only -- exit 0 regardless of findings. Hard-block lands in a follow-up
# feature once the false-positive rate is empirically known.
#
# Triggers:
#   * tool_name == "WebFetch": always scan
#   * tool_name == "Read": only when file_path resolves outside the repo
#     root (`/tmp/`, `/var/`, `/home/<other>/`, absolute URL forms)
#   * any other tool: skip
#
# Logs only (source, pattern, position) triples to stderr -- never the
# scanned text itself (per the privacy constraint in the feature card).
#
# ACs:
#   1. Exit 0 always (advisory mode).
#   2. WebFetch with injection in tool_response -> stderr emits
#      `WARN: prompt-injection pattern detected: <pattern> in <source>`.
#   3. WebFetch clean -> stderr silent.
#   4. Read with file_path inside repo (cwd) -> skip even if pattern
#      present (in-repo content is trust-boundary internal).
#   5. Read with file_path outside repo -> scan.

set -uo pipefail

# Find the directory of THIS hook so we can put PKG_ROOT (one level above
# claude/hooks/) on PYTHONPATH for the python step.
HOOK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PKG_ROOT=$(cd "$HOOK_DIR/../.." && pwd)

INPUT=$(cat)

# Single python step: parse envelope (passed via TOOL_ENVELOPE env var so
# the heredoc body has stdin free), decide whether to scan, run scanner,
# emit warnings to stderr. Always exit 0 -- advisory only. Stdout is
# discarded (the hook produces no JSON payload); stderr passes through
# to the harness for surfacing to the operator.
PYTHONPATH="$PKG_ROOT" TOOL_ENVELOPE="$INPUT" python3 - >/dev/null <<'PY'
import json
import os
import sys

raw = os.environ.get("TOOL_ENVELOPE", "")
if not raw:
    sys.exit(0)
try:
    envelope = json.loads(raw)
except Exception:
    sys.exit(0)

tool_name = envelope.get("tool_name", "")
tool_input = envelope.get("tool_input", {}) or {}
tool_response = envelope.get("tool_response", "")
cwd = envelope.get("cwd") or os.getcwd()

# tool_response may be a list/dict for some tools -- coerce to string.
if not isinstance(tool_response, str):
    try:
        tool_response = json.dumps(tool_response)
    except Exception:
        tool_response = str(tool_response)

if not tool_response:
    sys.exit(0)

try:
    repo_root = os.path.realpath(cwd)
except Exception:
    sys.exit(0)


def is_outside_repo(path: str) -> bool:
    if not path:
        return False
    if "://" in path:  # URL form -- always outside
        return True
    try:
        real = os.path.realpath(path)
    except Exception:
        return True
    return not (real == repo_root or real.startswith(repo_root + os.sep))


scan_decision = False
source = ""
if tool_name == "WebFetch":
    scan_decision = True
    source = tool_input.get("url", "") or (tool_input.get("prompt", "") or "")[:120]
elif tool_name == "Read":
    fp = tool_input.get("file_path", "") or tool_input.get("path", "")
    if is_outside_repo(fp):
        scan_decision = True
        source = fp

if not scan_decision:
    sys.exit(0)

# Trim source to a single safe line; never echo body.
source = (source or "<unknown>").replace("\n", " ").replace("\r", " ")[:200]

# Import the scanner -- PYTHONPATH was set by the wrapping shell script.
try:
    from claude.hooks._promptguard import scan
except ImportError as e:
    sys.stderr.write(f"scan-tool-output: cannot import _promptguard ({e}) -- skipping\n")
    sys.exit(0)

for finding in scan(tool_response):
    sys.stderr.write(
        f"WARN: prompt-injection pattern detected: {finding.pattern} "
        f"in {source} (pos {finding.position})\n"
    )

sys.exit(0)
PY

# Advisory-only: never block.
exit 0
