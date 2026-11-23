#!/usr/bin/env python3
"""File size limit for the global pre-commit and pre-merge-commit hooks.

  filesize.py [pre-commit|pre-merge-commit]
      (claude/git-hooks/pre-commit runs it inside the repo; pre-merge-commit,
      which `git merge` runs before it records a merge, passes its own name)

A hand-written text file has at most 1,500 lines and 50,000 bytes, so that a
person or an agent can read it whole in one go. The check refuses a commit
that adds a file over the limit, or that takes a file from under the limit to
over it. A file that was already over the limit before the commit gets a
warning and the commit goes through.

Never counted: binary files (a NUL byte in the first 8,000 bytes, or `-diff`
or `binary` in the staged .gitattributes), deleted files, symlinks and
submodules. Exempt: the default patterns below (lock, vendored, generated,
IDE and data files), paths marked `linguist-generated` or `linguist-vendored`
in the staged .gitattributes, and the patterns in the repository's
`.file-size-exempt`. A file that passes only because an unstaged
`.file-size-exempt` in the working tree lists it gets a note and an override
event, so a local exemption is never silent.

Exit 0 = the commit or merge may go on, 3 = refused; anything else means the check
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
LOCAL_RULE = "pre-commit.file-size-exempt-local"
EXEMPT_FILE = ".file-size-exempt"
HOOK_NAMES = ("pre-commit", "pre-merge-commit")
HOOK = HOOK_NAMES[0]  # the hook that runs the check; main() sets it
# While `git merge` runs pre-merge-commit, MERGE_HEAD is not written yet; git
# names each commit it merges in a GITHEAD_<sha> variable instead.
MERGED_VAR = re.compile(r"GITHEAD_([0-9a-f]{40}|[0-9a-f]{64})")
BINARY_PEEK = 8000  # git's own rule: a NUL byte in the first 8,000 bytes
CHUNK = 1 << 16  # a blob over MAX_BYTES is read in pieces of this size
ALREADY_OVER = "New code goes in a new file; split this one only when asked."
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
    # project and designer files an IDE writes
    "*.pbxproj",
    "*.xcstrings",
    "*.storyboard",
    "*.xib",
    "*.resx",
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


def encoded(text: str) -> bytes:
    """A path or object name as git has it; a byte that is not UTF-8 came in
    as a surrogate escape and goes back out as that byte."""
    return text.encode("utf-8", "surrogateescape")


# ---------------------------------------------------------------- patterns


def char_class(glob: str, i: int) -> tuple[str, int] | None:
    """The `[...]` class that starts at glob[i] as a regex, and the index past
    it; None when no `]` closes it. `[!...]` and `[^...]` match any other
    character, and a `]` right after the opening bracket is part of the set.
    A class never matches the / between folders."""
    j = i + 1
    negate = j < len(glob) and glob[j] in "!^"
    j += negate
    end = glob.find("]", j + 1 if glob[j : j + 1] == "]" else j)
    if end < 0:
        return None
    body = "".join(c if c == "-" else re.escape(c) for c in glob[j:end])
    return ("[^/" + body + "]" if negate else "(?!/)[" + body + "]"), end + 1


def glob_regex(glob: str) -> str:
    """A glob as a regex: *, ? and [...] stay inside one folder, ** crosses
    folders."""
    out, i = [], 0
    while i < len(glob):
        cls = char_class(glob, i) if glob[i] == "[" else None
        if cls:
            out.append(cls[0])
            i = cls[1]
        elif glob.startswith("**/", i):
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


def exempt_list_unused(
    why: str, step: str = "Make it a plain UTF-8 text file."
) -> list[str]:
    print(
        f"{HOOK}: warning: {EXEMPT_FILE} at the top of the repository {why}, "
        f"so its patterns are not used. {step}",
        file=sys.stderr,
    )
    return []


def repo_patterns() -> tuple[list[str], bool]:
    """The lines of .file-size-exempt, and whether they come from the index.

    The staged copy counts, else the one in the working tree. A list that is
    a link, a folder, unreadable or not UTF-8 text is not used, with a warning;
    a missing one is the usual case and says nothing.
    """
    # The pathspec also matches files in a folder of that name: only an
    # entry for the path itself is the list.
    entries = [
        e.split(b"\t", 1)
        for e in git("ls-files", "-s", "-z", "--", EXEMPT_FILE).split(b"\0")
        if e
    ]
    entry = next((head for head, path in entries if path == encoded(EXEMPT_FILE)), b"")
    if entries and not entry:
        return exempt_list_unused("is staged as a folder"), True
    if entry:
        mode, sha = entry.split()[:2]
        if mode.decode() not in REGULAR:
            return exempt_list_unused("is staged as a link or a submodule"), True
        data = read_blobs([sha.decode()])[0] or b""
        staged_list = True
    else:
        staged_list = False
        path = os.path.join(
            git("rev-parse", "--show-toplevel").decode().strip(), EXEMPT_FILE
        )
        if not os.path.lexists(path):
            return [], False
        if os.path.islink(path) or not os.path.isfile(path):
            return exempt_list_unused("is a link or a folder"), False
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            why = f"cannot be read ({e.strerror})"
            return exempt_list_unused(why, "Make it a readable file."), False
    try:
        return data.decode("utf-8").splitlines(), staged_list
    except UnicodeDecodeError:
        return exempt_list_unused("is not UTF-8 text"), staged_list


# ---------------------------------------------------------------- sizes


def measure(blob: bytes | None) -> tuple[int, int] | None:
    """(lines, bytes) of a text blob; None for a binary or missing one."""
    if blob is None or b"\0" in blob[:BINARY_PEEK]:
        return None
    lines = blob.count(b"\n")
    if blob and not blob.endswith(b"\n"):
        lines += 1
    return lines, len(blob)


def count(stream) -> tuple[int, int] | None:
    """measure() for a stream read in pieces: None as soon as the first
    BINARY_PEEK bytes show a binary, so a large binary is never read whole."""
    head = stream.read(BINARY_PEEK)
    if b"\0" in head:
        return None
    lines, size, last = head.count(b"\n"), len(head), head[-1:]
    while chunk := stream.read(CHUNK):
        lines += chunk.count(b"\n")
        size += len(chunk)
        last = chunk[-1:]
    if size and last != b"\n":
        lines += 1
    return lines, size


def over(size: tuple[int, int] | None) -> bool:
    return size is not None and (size[0] > MAX_LINES or size[1] > MAX_BYTES)


def describe(size: tuple[int, int]) -> str:
    return f"{size[0]:,} lines, {size[1]:,} bytes"


def batch_head(line: bytes) -> tuple[bytes, int] | None:
    """(type, size) from a `git cat-file --batch` header; None when the object
    is missing. A missing name may hold spaces, so the line is read from the
    right: "<sha> <type> <size>" or "<name> missing"."""
    parts = line.rsplit(b" ", 2)
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return parts[1], int(parts[2])


def batch_input(names: list[str]) -> bytes:
    return b"".join(encoded(n) + b"\n" for n in names)


def blob_sizes(names: list[str]) -> list[int | None]:
    """The byte size of each object name (a sha or rev:path) that is a blob;
    None when missing or not a blob. Nothing is read but the headers."""
    if not names:
        return []
    out = git("cat-file", "--batch-check", data=batch_input(names))
    heads = [batch_head(line) for line in out.split(b"\n")[: len(names)]]
    return [h[1] if h and h[0] == b"blob" else None for h in heads]


def read_blobs(names: list[str]) -> list[bytes | None]:
    """The whole content of each object name; None when missing."""
    if not names:
        return []
    out = git("cat-file", "--batch", data=batch_input(names))
    blobs: list[bytes | None] = []
    pos = 0
    for _ in names:
        end = out.index(b"\n", pos)
        head = batch_head(out[pos:end])
        pos = end + 1
        if head is None:  # "<name> missing" or "<name> ambiguous"
            blobs.append(None)
            continue
        kind, size = head
        blobs.append(out[pos : pos + size] if kind == b"blob" else None)
        pos += size + 1
    return blobs


def stream_size(name: str) -> tuple[int, int] | None:
    """count() of one blob straight from git, for a blob over MAX_BYTES."""
    with subprocess.Popen(
        ["git", "cat-file", "blob", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as p:
        size = count(p.stdout)
        if size is None:
            p.kill()  # a binary: the rest is never read
            return None
        if p.wait(timeout=60) != 0:
            raise RuntimeError(f"git cat-file failed (exit {p.returncode})")
    return size


def sizes(names: list[str]) -> list[tuple[int, int] | None]:
    """(lines, bytes) of each text blob named; None for a binary, missing or
    empty name. Blobs up to MAX_BYTES are read whole in one batch; a larger
    one is read in pieces and dropped once its first bytes show a binary."""
    named = sorted({n for n in names if n})
    known = dict(zip(named, blob_sizes(named), strict=True))
    small = [n for n in named if known[n] is not None and known[n] <= MAX_BYTES]
    content = dict(zip(small, read_blobs(small), strict=True))
    out = []
    for n in names:
        if not n or known[n] is None:
            out.append(None)
        elif n in content:
            out.append(measure(content[n]))
        else:
            out.append(stream_size(n))
    return out


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
    """The other parents of a merge that this commit concludes, or that `git
    merge` is about to record."""
    if HOOK == "pre-merge-commit":
        return sorted(m[1] for k in os.environ if (m := MERGED_VAR.fullmatch(k)))
    path = git("rev-parse", "--git-path", "MERGE_HEAD").decode().strip()
    try:
        with open(path, encoding="ascii") as f:
            return [line.strip() for line in f if line.strip()]
    except (OSError, UnicodeDecodeError):
        return []


def staged() -> list[tuple[str, str | None, str]]:
    """(path, old blob or None, new blob) for every regular file the commit
    adds or changes. Deleted files, symlinks and submodules are left out; a
    renamed file keeps the blob it had under its old name. The index is the
    one git commit uses, so `commit -a` and `commit -- <path>` are checked."""
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
    """The diff and linguist attributes of each path, from the staged
    .gitattributes only: an unstaged edit there exempts nothing."""
    if not paths:
        return {}
    names = ("diff", "linguist-generated", "linguist-vendored")
    data = b"".join(encoded(p) + b"\0" for p in paths)
    raw = git("check-attr", "--cached", "-z", "--stdin", *names, data=data)
    raw = raw.split(b"\0")
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


def findings() -> tuple[list[tuple], list[tuple], list[tuple]]:
    """(refused, warned, local): (path, size, what it was before) for each
    file over the limit. warned holds the files that were over it already,
    local the ones that would be refused but for an unstaged exempt list."""
    patterns = compile_patterns(DEFAULT_EXEMPT)
    lines, from_index = repo_patterns()
    listed = compile_patterns(lines)
    if from_index:
        patterns, listed = patterns + listed, []
    files = [f for f in staged() if not exempt(f[0], patterns)]
    attrs = attributes([f[0] for f in files])
    files = [f for f in files if not skipped(attrs.get(f[0], {}))]
    big = [
        (f, s)
        for f, s in zip(files, sizes([f[2] for f in files]), strict=True)
        if over(s)
    ]
    if not big:
        return [], [], []
    parents = merge_heads()
    names: list[str] = []
    for (path, old, _), _ in big:
        names.append(old or "")
        names += ["" if "\n" in path else f"{p}:{path}" for p in parents]
    before = iter(sizes(names))
    refused, warned, local = [], [], []
    for (path, old, _), size in big:
        prior = [next(before) for _ in range(1 + len(parents))]
        if any(over(p) for p in prior):
            if not exempt(path, listed):
                warned.append((path, size, prior[0]))
        elif exempt(path, listed):
            local.append((path, size, ""))
        elif old is not None and prior[0] is not None:
            refused.append((path, size, f"was {describe(prior[0])}"))
        else:
            refused.append((path, size, "new file"))
    return refused, warned, local


def log(kind: str, rule: str, entries: list[tuple], what: str) -> None:
    """One event for the first entry, with a count of the rest; never the
    content. Logging must not change what the hook decides."""
    path, size, _ = entries[0]
    reason = f"{shown(path)}: {size[0]} lines, {size[1]} bytes; {what}"
    if len(entries) > 1:
        reason += f"; {len(entries) - 1} more file(s)"
    try:
        sys.dont_write_bytecode = True  # leave no __pycache__ beside the hooks
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kitlog

        kitlog.log(HOOK, kind, rule, reason)
    except Exception:
        pass


def report(refused: list[tuple], warned: list[tuple], local: list[tuple]) -> None:
    limit = f"{MAX_LINES:,} lines and {MAX_BYTES:,} bytes"
    for path, size, _ in warned:
        print(
            f"{HOOK}: warning: {shown(path)} is {describe(size)}, over the "
            f"file size limit of {limit}. It was over the limit before this "
            f"commit, so the commit goes on. {ALREADY_OVER} [{WARN_RULE}]",
            file=sys.stderr,
        )
    for path, size, _ in local:
        print(
            f"{HOOK}: note: {shown(path)} is {describe(size)}, over the file "
            f"size limit of {limit}; the commit goes on because {EXEMPT_FILE} in "
            f"the working tree lists it, and that list is not staged. "
            f"[{LOCAL_RULE}]",
            file=sys.stderr,
        )
    if local:
        log("override", LOCAL_RULE, local, f"exempt only by the unstaged {EXEMPT_FILE}")
    if not refused:
        return
    what = "merge" if HOOK == "pre-merge-commit" else "commit"
    print(
        f"{HOOK}: {what} refused, over the file size limit of {limit}: [{RULE}]",
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
    log("block", RULE, refused, f"limit {MAX_LINES} lines, {MAX_BYTES} bytes")


def main(argv: list[str]) -> int:
    global HOOK
    if len(argv) > 1 or (argv and argv[0] not in HOOK_NAMES):
        print(f"usage: filesize.py [{'|'.join(HOOK_NAMES)}]", file=sys.stderr)
        return 2
    HOOK = argv[0] if argv else HOOK_NAMES[0]
    # A path that is not UTF-8, or a terminal that is not, must not stop the
    # report half-way: such characters are printed as escapes instead.
    sys.stderr.reconfigure(errors="backslashreplace")
    try:
        refused, warned, local = findings()
    except Exception as e:
        print(f"{HOOK}: file size check failed: {e}", file=sys.stderr)
        return 2
    report(refused, warned, local)
    return REFUSED if refused else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
