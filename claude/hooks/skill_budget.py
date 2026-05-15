#!/usr/bin/env python3
"""Skill frontmatter token budget helper + PreToolUse advisory.

Per NETMIND Part 3 §8.1 and Part 1 §7.3, Claude Code runs a
preflight token budget estimate on skill frontmatter before the
skill is spawned. Replicates that locally for the user's workflow:
when the Agent tool is invoked with a prompt that references one
or more /skill-name commands, the hook sums the estimated
frontmatter costs and emits a warning if the sum exceeds the
configured budget.

This does NOT block the agent — the point is to surface context
pressure, not to gate spawning.

Two modes:

1. PreToolUse hook (default, stdin JSON tool_input for Agent):
   parse the sub-agent prompt for /<skill-name> references, sum
   estimated costs, warn if over budget.

2. CLI: skill_budget.py estimate <skill-name>
   skill_budget.py list
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

SKILLS_DIR = os.path.expanduser("~/.claude/skills")
SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")
DEFAULT_WARNING_TOKENS = 15_000
TRIVIAL_SKILL_THRESHOLD = 500


def _read_frontmatter(skill_path: str) -> str | None:
    """Return the frontmatter block of a SKILL.md, or None if absent."""
    try:
        with open(skill_path) as f:
            lines = f.readlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    fm: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return "".join(fm)
        fm.append(line)
    return None


def _estimate_tokens(text: str) -> int:
    """Naive estimate matching Claude Code's rough len/4 strategy."""
    return len(text) // 4


# mtime-keyed cache
_cache: dict[str, tuple[float, int]] = {}


def estimate_skill_cost(skill_name: str) -> int:
    """Return the estimated frontmatter token cost of a skill."""
    skill_path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    if not os.path.isfile(skill_path):
        return 0
    try:
        mtime = os.path.getmtime(skill_path)
    except OSError:
        return 0
    cached = _cache.get(skill_name)
    if cached and cached[0] == mtime:
        return cached[1]
    fm = _read_frontmatter(skill_path)
    cost = _estimate_tokens(fm) if fm else 0
    _cache[skill_name] = (mtime, cost)
    return cost


def estimate_agent_cost(skill_names: list[str]) -> int:
    return sum(estimate_skill_cost(s) for s in skill_names)


def _load_budget() -> int:
    try:
        with open(SETTINGS_PATH) as f:
            data: dict[str, Any] = json.load(f)
    except (OSError, ValueError):
        return DEFAULT_WARNING_TOKENS
    budget = data.get("skillBudget", {})
    if isinstance(budget, dict):
        v = budget.get("frontmatterWarningTokens", DEFAULT_WARNING_TOKENS)
        if isinstance(v, int):
            return v
    return DEFAULT_WARNING_TOKENS


SKILL_REFERENCE_RE = re.compile(r"(?<![A-Za-z0-9_])/([a-z][a-z0-9-]{1,})")

# Skills to skip entirely.
SKIP_SKILLS = frozenset({"fast", "clear", "help", "compact", "bug"})


def extract_skill_references(prompt: str) -> list[str]:
    """Pull candidate /skill-name tokens out of a prompt."""
    matches = SKILL_REFERENCE_RE.findall(prompt)
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        if m in SKIP_SKILLS:
            continue
        if m in seen:
            continue
        seen.add(m)
        result.append(m)
    return result


def list_all_estimates() -> list[tuple[str, int]]:
    """Return (skill_name, estimate) for every skill under SKILLS_DIR."""
    results: list[tuple[str, int]] = []
    if not os.path.isdir(SKILLS_DIR):
        return results
    for name in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if os.path.isfile(path):
            results.append((name, estimate_skill_cost(name)))
    return results


def hook_mode() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = data.get("tool_input", {})
    prompt = tool_input.get("prompt", "") or ""
    if not prompt:
        return 0

    refs = extract_skill_references(prompt)
    if not refs:
        return 0

    total = 0
    per_skill: list[tuple[str, int]] = []
    for r in refs:
        cost = estimate_skill_cost(r)
        if cost < TRIVIAL_SKILL_THRESHOLD:
            # Count it but don't warn based on trivial skills alone
            pass
        per_skill.append((r, cost))
        total += cost

    budget = _load_budget()
    if total > budget:
        print(
            f"ADVISORY (skill-budget): spawned agent prompt references "
            f"{len(refs)} skill(s) with estimated frontmatter total "
            f"{total} tokens, exceeding the budget ({budget}).",
            file=sys.stderr,
        )
        for name, cost in per_skill:
            print(f"  {name}: ~{cost} tokens", file=sys.stderr)
        print(
            "This is advisory — agent spawn continues. "
            "Raise skillBudget.frontmatterWarningTokens in settings "
            "to silence, or trim the sub-agent scope.",
            file=sys.stderr,
        )
    # Exit 0 in all cases — hook never blocks.
    return 0


def cli_estimate(name: str) -> int:
    cost = estimate_skill_cost(name)
    print(f"{name}: ~{cost} tokens")
    return 0 if cost > 0 else 1


def cli_list() -> int:
    entries = list_all_estimates()
    if not entries:
        print(f"no skills found under {SKILLS_DIR}", file=sys.stderr)
        return 1
    total = 0
    for name, cost in entries:
        print(f"{name:40s} {cost:>6} tokens")
        total += cost
    print(f"\n{'total':40s} {total:>6} tokens")
    print(f"budget: {_load_budget()} tokens")
    return 0


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1] == "estimate" and len(sys.argv) >= 3:
            return cli_estimate(sys.argv[2])
        if sys.argv[1] == "list":
            return cli_list()
        print("usage: skill_budget.py [estimate <name> | list]", file=sys.stderr)
        return 2
    return hook_mode()


if __name__ == "__main__":
    raise SystemExit(main())
