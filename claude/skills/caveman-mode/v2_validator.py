#!/usr/bin/env python3
"""
v2_validator.py — validate v2 bounded-paraphrase output against pre-image.

Runs 7 checks on (pre_text, post_text):
  1. All URLs in pre present byte-exact in post.
  2. All fenced code blocks byte-exact.
  3. MUST/NEVER literal counts in post >= pre counts.
  4. Heading count and order preserved.
  5. Bullet count within +/-10% of pre.
  6. Length ratio 40-90% of pre.
  7. Negation density (no|not|never|don't per 1k chars) within +/-15% of pre.

Pure stdlib. No third-party deps. No LLM invocation.

CLI:
  python3 v2_validator.py <pre_file> <post_file>
  exit 0 = all checks passed
  exit 1 = at least one check failed (failures printed to stderr)
  exit 2 = usage error

Library:
  from v2_validator import validate, ValidationResult
  result = validate(pre_text, post_text)
  if result.passed: ...
  else: print(result.failures)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import List


URL_RE = re.compile(r"https?://[^\s)]+")
MUST_NEVER_RE = re.compile(r"\b(MUST|NEVER|DO NOT|do not|Do not)\b")
HEADING_RE = re.compile(r"^(#+)\s+(.+?)\s*$", re.MULTILINE)
BULLET_RE = re.compile(r"^(?:[-*]\s|\d+\.\s)", re.MULTILINE)
NEGATION_RE = re.compile(r"\b(no|not|never|don't)\b", re.IGNORECASE)


@dataclass
class ValidationResult:
    passed: bool = True
    failures: List[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.passed = False
        self.failures.append(msg)


def _extract_fenced_blocks(text: str) -> List[List[str]]:
    """Return list-of-blocks, each block is list-of-lines including fence lines."""
    blocks: List[List[str]] = []
    current: List[str] | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if current is None:
                current = [line]
            else:
                current.append(line)
                blocks.append(current)
                current = None
        elif current is not None:
            current.append(line)
    # unterminated fence: still record (treat as a block) so it can be compared
    if current is not None:
        blocks.append(current)
    return blocks


def _extract_headings(text: str) -> List[str]:
    """Return list of normalized headings in source order (e.g. '## Foo')."""
    out: List[str] = []
    for m in HEADING_RE.finditer(text):
        out.append(f"{m.group(1)} {m.group(2)}")
    return out


def validate(pre_text: str, post_text: str) -> ValidationResult:
    result = ValidationResult()

    if not pre_text:
        result.fail("pre file empty")
        return result
    if not post_text:
        result.fail("post file empty")
        return result

    # Check 1: URL preservation
    pre_urls = URL_RE.findall(pre_text)
    for url in pre_urls:
        if url not in post_text:
            result.fail(f"URL missing from post: {url}")

    # Check 2: Fenced code blocks byte-exact (as line-lists)
    pre_blocks = _extract_fenced_blocks(pre_text)
    post_blocks = _extract_fenced_blocks(post_text)
    pre_block_strs = ["\n".join(b) for b in pre_blocks]
    post_block_strs = ["\n".join(b) for b in post_blocks]
    for blk in pre_block_strs:
        if blk not in post_block_strs:
            head = blk.splitlines()[0] if blk else "<empty>"
            result.fail(f"fenced code block missing or modified: {head[:80]}")

    # Check 3: MUST/NEVER literal count post >= pre
    pre_must_count = len(MUST_NEVER_RE.findall(pre_text))
    post_must_count = len(MUST_NEVER_RE.findall(post_text))
    if post_must_count < pre_must_count:
        result.fail(
            f"MUST/NEVER literal count dropped: pre={pre_must_count} post={post_must_count}"
        )

    # Check 4: Heading order preserved
    pre_headings = _extract_headings(pre_text)
    post_headings = _extract_headings(post_text)
    if pre_headings != post_headings:
        result.fail(
            f"heading order/count changed: pre={len(pre_headings)} post={len(post_headings)}"
        )

    # Check 5: Bullet count within +/-10%
    pre_bullets = len(BULLET_RE.findall(pre_text))
    post_bullets = len(BULLET_RE.findall(post_text))
    if pre_bullets == 0:
        if post_bullets != 0:
            result.fail(
                f"bullet check: pre had 0 bullets but post has {post_bullets}"
            )
        # else: skip (no signal)
    else:
        delta = abs(post_bullets - pre_bullets) / pre_bullets
        if delta > 0.10:
            result.fail(
                f"bullet count out of +/-10%: pre={pre_bullets} post={post_bullets} delta={delta:.2%}"
            )

    # Check 6: Length ratio 40-90%
    ratio = len(post_text) / len(pre_text)
    if not (0.40 <= ratio <= 0.90):
        result.fail(
            f"length ratio out of [40%, 90%]: post/pre = {ratio:.2%}"
        )

    # Check 7: Negation density +/-15%
    def density(text: str) -> float:
        n = len(NEGATION_RE.findall(text))
        return (n * 1000.0) / max(len(text), 1)

    pre_density = density(pre_text)
    post_density = density(post_text)
    if pre_density == 0.0:
        if post_density > 0.0:
            # post introduced negations not in pre — flag as polarity drift
            result.fail(
                f"negation density: pre had none but post density = {post_density:.3f}/1k chars"
            )
    else:
        delta = abs(post_density - pre_density) / pre_density
        if delta > 0.15:
            result.fail(
                f"negation density drift > 15%: pre={pre_density:.3f} post={post_density:.3f} delta={delta:.2%}"
            )

    return result


def _main(argv: List[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: python3 v2_validator.py <pre_file> <post_file>",
            file=sys.stderr,
        )
        return 2
    pre_path, post_path = argv[1], argv[2]
    try:
        with open(pre_path, "r", encoding="utf-8") as f:
            pre_text = f.read()
        with open(post_path, "r", encoding="utf-8") as f:
            post_text = f.read()
    except OSError as e:
        print(f"read error: {e}", file=sys.stderr)
        return 1
    result = validate(pre_text, post_text)
    if result.passed:
        return 0
    for fail in result.failures:
        print(f"FAIL: {fail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
