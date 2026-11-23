"""The move filter of hunks.patch: a diff without the lines that only moved.

A line only moved when its text, ignoring indentation, was removed in one hunk
and added in another, inside a block of at least MIN_BLOCK letters or digits. A
text removed and added in the same hunk is an edit in place (indentation, line
ends, the newline at the end of a file), never a move.
Short lines (a lone `}` or `pass`) are found in many places, so they count as
moved only inside such a block. Blank lines between, before or after moved
lines go with them. Stdlib only; it works on bytes, as git gives them.
"""

from __future__ import annotations

import re
from collections import Counter

CONTEXT = 5
MIN_BLOCK = 20
HUNK = re.compile(rb"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)")
ALNUM = re.compile(rb"[A-Za-z0-9]")


class Hunk:
    """One hunk: its start lines, the text after its header, its lines."""

    def __init__(self, old, new, section):
        self.old, self.new, self.section = old, new, section
        self.lines: list[bytes] = []
        self.moved: list[bool] = []


def parse(patch):
    """[(header lines, [Hunk])] of a git diff. A hunk takes as many lines as its
    header counts, so a removed line that starts with "--" stays a line."""
    files = []
    lines = patch.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        hit = HUNK.match(line) if files else None
        if line.startswith(b"diff --git ") or not files:
            files.append(([line], []))
            continue
        if not hit:
            files[-1][0].append(line)
            continue
        old_left = int(hit[2]) if hit[2] is not None else 1
        new_left = int(hit[4]) if hit[4] is not None else 1
        hunk = Hunk(int(hit[1]), int(hit[3]), hit[5])
        while i < len(lines) and (old_left > 0 or new_left > 0):
            body = lines[i]
            tag = body[:1]
            if tag == b"-":
                old_left -= 1
            elif tag == b"+":
                new_left -= 1
            elif tag != b"\\":
                old_left -= 1
                new_left -= 1
            hunk.lines.append(body)
            i += 1
        while i < len(lines) and lines[i].startswith(b"\\"):
            hunk.lines.append(lines[i])
            i += 1
        hunk.moved = [False] * len(hunk.lines)
        files[-1][1].append(hunk)
    return files


def key(line):
    return line[1:].strip()


def runs(hunk):
    """The runs of a hunk: [indices] of neighbouring lines with the same sign."""
    out, last = [], None
    for j, line in enumerate(hunk.lines):
        tag = line[:1]
        if tag in (b"+", b"-") and tag == last:
            out[-1].append(j)
        elif tag in (b"+", b"-"):
            out.append([j])
        last = tag
    return out


def mark_moved(files):
    """Mark the lines that only moved."""
    hunks = [hunk for _, found in files for hunk in found]
    seen = {b"-": Counter(), b"+": Counter()}
    in_place = []
    for hunk in hunks:
        sides = {b"-": set(), b"+": set()}
        for line in hunk.lines:
            if line[:1] in sides and key(line):
                sides[line[:1]].add(key(line))
        here = sides[b"-"] & sides[b"+"]
        in_place.append(here)
        for line in hunk.lines:
            k = key(line)
            if line[:1] in seen and k and k not in here:
                seen[line[:1]][k] += 1
    pool = {k: min(n, seen[b"+"][k]) for k, n in seen[b"-"].items() if k in seen[b"+"]}
    left = {b"-": Counter(pool), b"+": Counter(pool)}
    for hunk, here in zip(hunks, in_place, strict=True):
        for j, line in enumerate(hunk.lines):
            tag, k = line[:1], key(line)
            if tag in left and k and k not in here and left[tag][k] > 0:
                left[tag][k] -= 1
                hunk.moved[j] = True
        for run in runs(hunk):
            keep_blocks(hunk, run)


def keep_blocks(hunk, run):
    """Unmark moved lines in blocks of fewer than MIN_BLOCK letters or digits;
    mark blank lines whose non-blank neighbours in the run all moved."""
    filled = [j for j in run if key(hunk.lines[j])]
    block: list[int] = []
    for j in [*filled, None]:
        if j is not None and hunk.moved[j]:
            block.append(j)
            continue
        size = sum(len(ALNUM.findall(hunk.lines[b])) for b in block)
        if size < MIN_BLOCK:
            for b in block:
                hunk.moved[b] = False
        block = []
    near: dict[int, list[int]] = {}
    for order in (run, run[::-1]):
        last = None
        for j in order:
            if key(hunk.lines[j]):
                last = j
            else:
                near.setdefault(j, [])
                if last is not None:
                    near[j].append(last)
    for j, found in near.items():
        hunk.moved[j] = bool(found) and all(hunk.moved[b] for b in found)


def kept_lines(hunk):
    """[bool] per line: a change that did not only move, its context within
    CONTEXT lines (up to a moved line), and the "\\ No newline" note after a
    kept line."""
    lines, keep = hunk.lines, [False] * len(hunk.lines)
    changes = [
        j
        for j, line in enumerate(lines)
        if line[:1] in (b"+", b"-") and not hunk.moved[j]
    ]
    for j in changes:
        keep[j] = True
        for step in (-1, 1):
            k, seen = j + step, 0
            while 0 <= k < len(lines) and seen < CONTEXT:
                tag = lines[k][:1]
                if tag in (b"+", b"-"):
                    break
                if tag != b"\\":
                    keep[k] = True
                    seen += 1
                k += step
    for j, line in enumerate(lines):
        if line[:1] == b"\\" and j and keep[j - 1]:
            keep[j] = True
    return keep


def chunks(hunk):
    """The kept lines of a hunk as hunks of their own, each with a header that
    counts its lines."""
    out = []
    keep = kept_lines(hunk)
    old, new = hunk.old, hunk.new
    current = None
    for j, line in enumerate(hunk.lines):
        tag = line[:1]
        if keep[j]:
            if current is None:
                current = [old, new, 0, 0, []]
                out.append(current)
            current[4].append(line)
            if tag != b"+" and tag != b"\\":
                current[2] += 1
            if tag != b"-" and tag != b"\\":
                current[3] += 1
        else:
            current = None
        if tag != b"+" and tag != b"\\":
            old += 1
        if tag != b"-" and tag != b"\\":
            new += 1
    text = []
    for o, n, oc, nc, body in out:
        o -= 1 if oc == 0 else 0
        n -= 1 if nc == 0 else 0
        head = f"@@ -{o},{oc} +{n},{nc} @@".encode() + hunk.section
        text += [head, *body]
    return text


def unmoved(patch):
    """(patch without the lines that only moved, changed lines kept, changed
    lines in all). Every file keeps its header (a deleted or new file, binary,
    mode); a hunk with nothing left goes."""
    files = parse(patch)
    mark_moved(files)
    out, kept, total = [], 0, 0
    for header, found in files:
        body = []
        for hunk in found:
            for j, line in enumerate(hunk.lines):
                if line[:1] in (b"+", b"-"):
                    total += 1
                    kept += not hunk.moved[j]
            body += chunks(hunk)
        out += header + body
    return (b"\n".join(out) + b"\n" if out else b""), kept, total
