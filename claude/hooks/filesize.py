#!/usr/bin/env python3
"""File size limit for the global pre-commit hook.

  filesize.py        (claude/git-hooks/pre-commit runs it inside the repo)

A hand-written text file has at most 1,500 lines and 50,000 bytes, so that a
person or an agent can read it whole in one go. The check refuses a commit
that adds a file over the limit, or that takes a file from under the limit to
over it. A file that was already over the limit before the commit gets a
warning and the commit goes through.

Never counted: binary files (a NUL byte in the first 8,000 bytes, or `-diff`
or `binary` in .gitattributes), deleted files, symlinks and submodules.
Exempt: the default patterns below (lock, vendored, generated and data files),
paths marked `linguist-generated` or `linguist-vendored` in .gitattributes,
and the patterns in the repository's `.file-size-exempt`.

Exit 0 = the commit may go on, 3 = refused; anything else means the check
itself failed, and the hook lets the commit through with a warning. A refusal
is logged through kitlog.py with the path and its size, never the content.
Stdlib only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

MAX_LINES = 1500
MAX_BYTES = 50_000
REFUSED = 3
RULE = "pre-commit.file-size"
WARN_RULE = "pre-commit.file-size-over"
EXEMPT_FILE = ".file-size-exempt"
BINARY_PEEK = 8000  # git's own rule: a NUL byte in the first 8,000 bytes
# Exempt in every repository. A pattern ending in / names a folder at any
# depth; any other pattern without a / matches the file name.
DEFAULT_EXEMPT = (
    # lock files
    "*.lock",
    "*.lockb",
    "*.lockfile",
    "*-lock.json",
    "*-lock.yaml",
    "npm-shrinkwrap.json",
    "packages.lock.json",
    "Package.resolved",
    "go.sum",
    # vendored code
    "vendor/",
    "vendored/",
    "third_party/",
    "third-party/",
    "node_modules/",
    # generated code
    "generated/",
    "__generated__/",
    "dist/",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.generated.*",
    "*.g.cs",
    "*.g.dart",
    "*.freezed.dart",
    "*.designer.cs",
    "*.Designer.cs",
    "*ModelSnapshot.cs",
    "*.pb.go",
    "*_pb2.py",
    "*_pb2.pyi",
    "*.snap",
    # data
    "*.json",
    "*.jsonl",
    "*.ndjson",
    "*.geojson",
    "*.csv",
    "*.tsv",
    "*.ipynb",
    "*.svg",
)
REGULAR = ("100644", "100755")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028-\u202e\u2066-\u2069]")


def git(*args: str, data: bytes | None = None) -> bytes:
    p = subprocess.run(
        ["git", *args], input=data, capture_output=True, check=False, timeout=60
    )
    if p.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed (exit {p.returncode})")
    return p.stdout


def shown(path: str) -> str:
    """The path as one printable line."""
    return CONTROL.sub("?", path)


# ---------------------------------------------------------------- patterns


def glob_regex(glob: str) -> str:
    """A glob as a regex: * and ? stay inside one folder, ** crosses folders."""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return "".join(out)


def compile_pattern(line: str) -> re.Pattern | None:
    """One line of an exempt list, gitignore style, as a regex for a path.

    `name` matches a file or folder of that name at any depth, `name/` only a
    folder, with everything in it; a pattern with a / in front or in the
    middle is anchored to the repository root. `#` starts a comment line.
    Negation (`!`) is not supported; such a line is skipped.
    """
    p = line.strip()
    if not p or p.startswith(("#", "!")):
        return None
    folder = p.endswith("/")
    anchored = "/" in p.rstrip("/")
    p = p.strip("/")
    if not p:
        return None
    head = "" if anchored else "(?:.*/)?"
    tail = "/.*" if folder else "(?:/.*)?"
    return re.compile(f"{head}{glob_regex(p)}{tail}", re.DOTALL)


def compile_patterns(lines) -> list[re.Pattern]:
    return [r for r in (compile_pattern(line) for line in lines) if r is not None]


def exempt(path: str, patterns: list[re.Pattern]) -> bool:
    return any(p.fullmatch(path) for p in patterns)


def repo_patterns() -> list[str]:
    """The lines of .file-size-exempt: the staged copy, else the working tree."""
    p = subprocess.run(
        ["git", "cat-file", "blob", f":{EXEMPT_FILE}"],
        capture_output=True,
        check=False,
    )
    if p.returncode == 0:
        return p.stdout.decode("utf-8", "replace").splitlines()
    top = git("rev-parse", "--show-toplevel").decode().strip()
    try:
        with open(os.path.join(top, EXEMPT_FILE), encoding="utf-8") as f:
            return f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []


# ---------------------------------------------------------------- sizes


def measure(blob: bytes | None) -> tuple[int, int] | None:
    """(lines, bytes) of a text blob; None for a binary or missing one."""
    if blob is None or b"\0" in blob[:BINARY_PEEK]:
        return None
    lines = blob.count(b"\n")
    if blob and not blob.endswith(b"\n"):
        lines += 1
    return lines, len(blob)


def over(size: tuple[int, int] | None) -> bool:
    return size is not None and (size[0] > MAX_LINES or size[1] > MAX_BYTES)


def describe(size: tuple[int, int]) -> str:
    return f"{size[0]:,} lines, {size[1]:,} bytes"


def read_blobs(names: list[str]) -> list[bytes | None]:
    """The content of each object name (a sha or rev:path); None when missing."""
    if not names:
        return []
    out = git("cat-file", "--batch", data="".join(f"{n}\n" for n in names).encode())
    blobs: list[bytes | None] = []
    pos = 0
    for _ in names:
        end = out.index(b"\n", pos)
        head = out[pos:end].split()
        pos = end + 1
        if len(head) != 3:  # "<name> missing" or "<name> ambiguous"
            blobs.append(None)
            continue
        size = int(head[2])
        blobs.append(out[pos : pos + size] if head[1] == b"blob" else None)
        pos += size + 1
    return blobs


# ---------------------------------------------------------------- the commit


def base() -> str:
    """HEAD, or the empty tree for the first commit."""
    p = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "HEAD^{commit}"],
        capture_output=True,
        check=False,
    )
    if p.returncode == 0:
        return p.stdout.decode().strip()
    return git("hash-object", "-t", "tree", "--stdin", data=b"").decode().strip()


def merge_heads() -> list[str]:
    """The other parents of a merge that this commit concludes."""
    path = git("rev-parse", "--git-path", "MERGE_HEAD").decode().strip()
    try:
        with open(path, encoding="ascii") as f:
            return [line.strip() for line in f if line.strip()]
    except (OSError, UnicodeDecodeError):
        return []


def staged() -> list[tuple[str, str | None, str]]:
    """(path, old blob or None, new blob) for every regular file the commit
    adds or changes. Deleted files, symlinks and submodules are left out; a
    renamed file keeps the blob it had under its old name."""
    raw = git(
        "diff-index", "--cached", "--raw", "-z", "-M", "--no-abbrev", base()
    ).split(b"\0")
    out = []
    i = 0
    while i < len(raw) and raw[i].startswith(b":"):
        old_mode, new_mode, old_sha, new_sha, status = raw[i][1:].decode().split()
        paths = 2 if status[0] in "RC" else 1
        path = raw[i + paths].decode("utf-8", "surrogateescape")
        i += 1 + paths
        if status[0] in "DU" or new_mode not in REGULAR:
            continue
        old = old_sha if status[0] in "MRT" and old_mode in REGULAR else None
        out.append((path, old, new_sha))
    return out


def attributes(paths: list[str]) -> dict[str, dict[str, str]]:
    """The diff and linguist attributes of each path."""
    if not paths:
        return {}
    names = ("diff", "linguist-generated", "linguist-vendored")
    data = "\0".join(paths).encode("utf-8", "surrogateescape") + b"\0"
    raw = git("check-attr", "-z", "--stdin", *names, data=data).split(b"\0")
    out: dict[str, dict[str, str]] = {}
    for j in range(0, len(raw) - 2, 3):
        path = raw[j].decode("utf-8", "surrogateescape")
        out.setdefault(path, {})[raw[j + 1].decode()] = raw[j + 2].decode()
    return out


def skipped(attrs: dict[str, str]) -> bool:
    """Binary by .gitattributes, or marked generated or vendored there."""
    if attrs.get("diff") == "unset":
        return True
    return any(
        attrs.get(a) in ("set", "true")
        for a in ("linguist-generated", "linguist-vendored")
    )


def findings() -> tuple[list[tuple], list[tuple]]:
    """(refused, warned): (path, size, what it was before) for each file
    over the limit; warned holds the files that were over it already."""
    patterns = compile_patterns(DEFAULT_EXEMPT) + compile_patterns(repo_patterns())
    files = [f for f in staged() if not exempt(f[0], patterns)]
    attrs = attributes([f[0] for f in files])
    files = [f for f in files if not skipped(attrs.get(f[0], {}))]
    sizes = [measure(b) for b in read_blobs([f[2] for f in files])]
    big = [(f, s) for f, s in zip(files, sizes, strict=True) if over(s)]
    if not big:
        return [], []
    parents = merge_heads()
    names: list[str] = []
    for (path, old, _), _ in big:
        names.append(old or "")
        names += ["" if "\n" in path else f"{p}:{path}" for p in parents]
    before = iter(measure(b) for b in read_blobs(names))
    refused, warned = [], []
    for (path, old, _), size in big:
        prior = [next(before) for _ in range(1 + len(parents))]
        if any(over(p) for p in prior):
            warned.append((path, size, prior[0]))
        elif old is not None and prior[0] is not None:
            refused.append((path, size, f"was {describe(prior[0])}"))
        else:
            refused.append((path, size, "new file"))
    return refused, warned


def report(refused: list[tuple], warned: list[tuple]) -> None:
    limit = f"{MAX_LINES:,} lines and {MAX_BYTES:,} bytes"
    for path, size, _ in warned:
        print(
            f"pre-commit: warning: {shown(path)} is {describe(size)}, over the "
            f"file size limit of {limit}. It was over the limit before this "
            f"commit, so the commit goes on; split it when you next work on it. "
            f"[{WARN_RULE}]",
            file=sys.stderr,
        )
    if not refused:
        return
    print(
        f"pre-commit: commit refused, over the file size limit of {limit}: [{RULE}]",
        file=sys.stderr,
    )
    for path, size, how in refused:
        print(f"  {shown(path)}: {describe(size)} ({how})", file=sys.stderr)
    print(
        "Split the file: new code that would take a file past the limit goes in "
        "a new file. A generated, vendored or data file can be listed in "
        f"{EXEMPT_FILE}.",
        file=sys.stderr,
    )
    path, size, _ = refused[0]
    reason = (
        f"{shown(path)}: {size[0]} lines, {size[1]} bytes; "
        f"limit {MAX_LINES} lines, {MAX_BYTES} bytes"
    )
    if len(refused) > 1:
        reason += f"; {len(refused) - 1} more file(s) over the limit"
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kitlog

        kitlog.log("pre-commit", "block", RULE, reason)
    except Exception:
        pass  # logging must not change what the hook decides


def main() -> int:
    try:
        refused, warned = findings()
    except Exception as e:
        print(f"pre-commit: file size check failed: {e}", file=sys.stderr)
        return 2
    report(refused, warned)
    return REFUSED if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
