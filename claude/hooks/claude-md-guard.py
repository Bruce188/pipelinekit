#!/usr/bin/env python3
"""CLAUDE.md validation hook for Claude Code PreToolUse events.

Hook contract:
  - Reads a JSON payload from stdin (Write or Edit PreToolUse event).
  - Extracts file_path; exits 0 silently if basename != CLAUDE.md.
  - Reconstructs proposed content; runs CM001-CM008 validation rules.
  - On any block-severity finding: prints findings to stderr, exits 2.
  - On warn-only findings: prints findings to stderr, exits 0.
  - On empty stdin or JSON parse error: prints WARN to stderr, exits 0 (fail-open).

Validation rules:
  CM001 block  UTF-8 encode error (lone surrogates, etc.)
  CM002 block  Line count > CLAUDE_MD_MAX_LINES (default 5000)
  CM003 block  No top-level heading (^# followed by space)
  CM004 warn   None of "## Core Principles", "## Tool Usage", "## Git" present
  CM005 warn   Banned phrases: Co-Authored-By, Generated with Claude, robot emoji
  CM006 warn   Any line > 500 chars (outside fenced code blocks)
  CM007 warn   More than 3 consecutive blank lines
  CM008 warn   Frontmatter starts with --- but has no closing ---

Environment knobs:
  CLAUDE_MD_MAX_LINES  integer, default 5000 (CM002 threshold)
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys


def read_stdin_payload() -> dict | None:
    """Read and parse JSON from stdin. Returns None on failure."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def reconstruct_content(tool_name: str, tool_input: dict) -> str | None:
    """Return proposed file content, or None to skip validation."""
    if tool_name == "Write":
        return tool_input.get("content", "")

    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, encoding="utf-8", errors="replace") as fh:
                current = fh.read()
        except OSError:
            return None
        if old_string not in current:
            return None  # Let Edit tool surface the error
        return current.replace(old_string, new_string, 1)

    return None


def validate(content: str) -> list[tuple[str, str, str]]:
    """Run CM001-CM008 against content. Returns list of (rule_id, severity, message)."""
    findings: list[tuple[str, str, str]] = []

    # CM001: UTF-8 encode check
    try:
        content.encode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        findings.append(("CM001", "block", "CM001: content contains invalid UTF-8 sequences"))

    lines = content.splitlines()

    # CM002: line count
    max_lines = int(os.environ.get("CLAUDE_MD_MAX_LINES", "5000"))
    if len(lines) > max_lines:
        findings.append((
            "CM002", "block",
            f"CM002: {len(lines)} lines exceeds limit of {max_lines}"
        ))

    # CM003: top-level heading
    has_h1 = any(re.match(r"^#\s", line) for line in lines)
    if not has_h1:
        findings.append(("CM003", "block", "CM003: no top-level '# Heading' found"))

    # CM004: recommended sections
    text = content
    missing = []
    for section in ("## Core Principles", "## Tool Usage", "## Git"):
        if section not in text:
            missing.append(section)
    if missing:
        findings.append((
            "CM004", "warn",
            f"CM004: missing recommended sections: {', '.join(missing)}"
        ))

    # CM005: banned phrases
    banned = [
        ("Co-Authored-By", "Co-Authored-By"),
        ("Generated with Claude", "Generated with Claude"),
        ("\U0001F916", "robot emoji \\U0001F916"),
    ]
    for phrase, label in banned:
        if phrase in text:
            findings.append(("CM005", "warn", f"CM005: banned phrase found: {label}"))

    # CM006: long lines outside fenced code blocks
    in_fence = False
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and len(line) > 500:
            findings.append((
                "CM006", "warn",
                f"CM006: line {i} exceeds 500 chars ({len(line)} chars)"
            ))
            break  # report only first offender

    # CM007: more than 3 consecutive blank lines
    if re.search(r"\n{5,}", content):  # 5 newlines = 4 blank lines
        findings.append(("CM007", "warn", "CM007: more than 3 consecutive blank lines found"))

    # CM008: malformed YAML frontmatter
    if content.startswith("---\n"):
        rest = content[4:]  # skip opening ---\n
        closing_found = False
        for line in rest.splitlines()[:500]:
            if line == "---":
                closing_found = True
                break
        if not closing_found:
            findings.append(("CM008", "warn", "CM008: frontmatter starts with '---' but no closing '---' found"))

    return findings


def format_findings(findings: list[tuple[str, str, str]]) -> str:
    """Format findings as prefixed lines for stderr output."""
    parts = []
    for rule_id, severity, message in findings:
        prefix = "BLOCK" if severity == "block" else "WARN"
        parts.append(f"{prefix}: {message}")
    return "\n".join(parts)


def main() -> int:
    payload = read_stdin_payload()
    if payload is None:
        print("WARN: could not parse stdin", file=sys.stderr)
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return 0

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if pathlib.PurePath(file_path).name != "CLAUDE.md":
        return 0

    content = reconstruct_content(tool_name, tool_input)
    if content is None:
        return 0

    findings = validate(content)
    if not findings:
        return 0

    print(format_findings(findings), file=sys.stderr)

    has_block = any(severity == "block" for _, severity, _ in findings)
    return 2 if has_block else 0


if __name__ == "__main__":
    sys.exit(main())
