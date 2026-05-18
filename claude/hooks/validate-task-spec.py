#!/usr/bin/env python3
"""Pre-commit hook: validate that staged .claude/tasks/*/spec.md files
have a non-empty routing.worker_class field.

Exit codes:
  0 — all staged spec.md files pass, or none staged
  non-zero — one or more spec.md files missing/empty routing.worker_class

Class allowlist: NOT hard-coded here.
  claude/lib/worker-provider/ directory is the authoritative registry.
  This hook validates presence only — it does not restrict which classes
  are permitted.
"""

import re
import subprocess
import sys


def _staged_files() -> list[str]:
    """Return list of files currently staged (index vs HEAD)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _is_task_spec(path: str) -> bool:
    """Return True if the path matches .claude/tasks/*/spec.md."""
    return bool(re.match(r"^(\.claude/tasks/[^/]+/spec\.md)$", path))


def _get_staged_content(path: str) -> str | None:
    """Return the staged content of a file, or None on error."""
    result = subprocess.run(
        ["git", "show", f":{path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _extract_routing_worker_class(content: str) -> str | None:
    """Extract routing.worker_class from YAML front-matter.

    Looks for a routing: section inside --- fences and extracts
    worker_class: <value> from it.

    Returns the stripped value string, or None if not found/empty.
    """
    # Extract YAML front-matter between leading --- fences
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        # No front-matter at all — treat as missing
        return None

    front_matter = fm_match.group(1)

    # Find the routing: block and then worker_class within it.
    # Strategy: locate the "routing:" key and scan subsequent indented lines.
    # We parse only the routing sub-section to avoid false positives.
    routing_block_match = re.search(
        r"^routing:\s*\n((?:[ \t]+[^\n]*\n?)*)",
        front_matter,
        re.MULTILINE,
    )
    if not routing_block_match:
        return None

    routing_body = routing_block_match.group(1)

    # Look for worker_class: <value> inside the routing block
    wc_match = re.search(
        r"^\s+worker_class:\s*(.+)$",
        routing_body,
        re.MULTILINE,
    )
    if not wc_match:
        # worker_class key absent
        return None

    value = wc_match.group(1).strip()
    return value if value else None


def main() -> int:
    staged = _staged_files()
    spec_files = [p for p in staged if _is_task_spec(p)]

    if not spec_files:
        return 0

    failed = 0
    for path in spec_files:
        content = _get_staged_content(path)
        if content is None:
            print(
                f"error: {path}: could not read staged content — skipping",
                file=sys.stderr,
            )
            continue

        worker_class = _extract_routing_worker_class(content)
        if not worker_class:
            print(
                f"error: {path}: spec.md missing routing.worker_class"
                " — set explicitly (no implicit default on commit)",
                file=sys.stderr,
            )
            failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
