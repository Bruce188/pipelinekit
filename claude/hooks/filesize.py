#!/usr/bin/env python3
"""File size limit for the global pre-commit and pre-merge-commit hooks.

  filesize.py pre-commit|pre-merge-commit
      (each hook runs it inside the repo with its own name; `git merge` runs
      pre-merge-commit before it records a merge it made without conflicts)

A hand-written text file has at most 1,500 lines and 50,000 bytes, so that a
person or an agent can read it whole in one go. The check refuses a commit
that adds a file over the limit, or that takes a file from under the limit to
over it. A file that was already over the limit before the commit gets a
warning and the commit goes through. Git runs neither hook for rebase,
cherry-pick, revert, am or stash, so what those commands record is not
checked.

Never counted: binary files (a NUL byte in the first 8,000 bytes, or `-diff`
or `binary` in a staged .gitattributes), deleted files, symlinks and
submodules. Exempt: generated, vendored, lock and data files, and the project
and designer files an IDE writes (DEFAULT_EXEMPT below); paths marked
`linguist-generated` or `linguist-vendored` in a staged .gitattributes; and
the patterns in the staged `.file-size-exempt` at the top of the repository.
Only what the commit carries exempts a file: $GIT_DIR/info/attributes,
core.attributesFile and the system attributes file are not read, and an
unstaged edit to .gitattributes or to the exempt list exempts nothing. When
the unstaged changes of a tracked exempt list name a refused file, the
refusal says to stage the list.

Exit 0 = the commit or merge may go on, 3 = refused; anything else (2 for a
wrong argument or a check that failed) means the sizes were not checked, and
the hook lets the commit through with a warning. A refusal is logged through
kitlog.py with the path and its size, never the content. Stdlib only.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import tempfile
import threading

MAX_LINES = 1500
MAX_BYTES = 50_000
REFUSED = 3
RULE = "pre-commit.file-size"
WARN_RULE = "pre-commit.file-size-over"
EXEMPT_FILE = ".file-size-exempt"
LIST_LINES = 1000  # an exempt list is read up to this many lines
LIST_BYTES = 64_000  # and this many bytes; the rest is not used
HOOK_NAMES = ("pre-commit", "pre-merge-commit")
HOOK = HOOK_NAMES[0]  # the hook that runs the check; main() sets it
# While `git merge` runs pre-merge-commit, MERGE_HEAD is not written yet; git
# names each commit it merges in a GITHEAD_<sha> variable instead.
MERGED_VAR = re.compile(r"GITHEAD_([0-9a-f]{40}|[0-9a-f]{64})")
BINARY_PEEK = 8000  # git's own rule: a NUL byte in the first 8,000 bytes
CHUNK = 1 << 16  # a blob over MAX_BYTES is read in pieces of this size
PATHS_PER_CALL = 200  # paths per `git ls-tree` call
ALREADY_OVER = "New code goes in a new file; split this one only when asked."
# Exempt in every repository: generated, vendored, lock and data files, and
# the project and designer files an IDE writes. A pattern ending in / names a
# folder at any depth; any other pattern without a / matches the file name.
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
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f -‮⁦-⁩]")
# Kept for the temporary repository that reads the staged .gitattributes;
# every other GIT_* variable belongs to the commit in progress.
KEPT_GIT_VARS = (
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def git(
    *args: str,
    data: bytes | None = None,
    env: dict | None = None,
    cwd: str | None = None,
) -> bytes:
    p = subprocess.run(
        ["git", *args],
        input=data,
        capture_output=True,
        check=False,
        timeout=60,
        env=env,
        cwd=cwd,
    )
    if p.returncode != 0:
        name = next((a for a in args if a[:1] != "-" and "=" not in a), "")
        why = p.stderr.decode("utf-8", "replace").strip().splitlines()
        tail = f": {why[0].strip()}" if why else ""
        raise RuntimeError(f"git {name} failed (exit {p.returncode}){tail}")
    return p.stdout


def shown(path: str) -> str:
    """The path as one printable line."""
    return CONTROL.sub("?", path)


def encoded(text: str) -> bytes:
    """A path or object name as git has it; a byte that is not UTF-8 came in
    as a surrogate escape and goes back out as that byte."""
    return text.encode("utf-8", "surrogateescape")


def decoded(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


def warn(text: str) -> None:
    print(f"{HOOK}: warning: {text}", file=sys.stderr)


# ---------------------------------------------------------------- patterns
#
# Patterns are matched without regular expressions, so that no line of an
# exempt list can make the check slow. A folder name is matched against one
# folder glob, and the folder names of a path against the folder globs, each
# with a greedy match that goes back at most to the last star: the time grows
# with the length of the pattern times the length of the path, never faster.

STAR = object()  # `*`: any run of characters inside one folder name
ANY = object()  # `?`: one character
GLOBSTAR = object()  # a folder glob that is just `**`: any run of folders


def char_class(glob: str, i: int) -> tuple[tuple, int] | None:
    """The `[...]` class that starts at glob[i] as (negated, ranges), and the
    index past it; None when no `]` closes it. `[!...]` and `[^...]` match any
    other character, and a `]` right after the opening bracket is part of the
    set. A reversed range such as `[z-a]` raises ValueError."""
    j = i + 1
    negate = j < len(glob) and glob[j] in "!^"
    j += negate
    end = glob.find("]", j + 1 if glob[j : j + 1] == "]" else j)
    if end < 0:
        return None
    body, ranges, k = glob[j:end], [], 0
    while k < len(body):
        if k + 2 < len(body) and body[k + 1] == "-":
            lo, hi = body[k], body[k + 2]
            if lo > hi:
                raise ValueError(f"the range {lo}-{hi} is reversed")
            ranges.append((lo, hi))
            k += 3
        else:
            ranges.append((body[k], body[k]))
            k += 1
    return (negate, tuple(ranges)), end + 1


def one(token, ch: str) -> bool:
    """Whether one token of a folder glob matches the character ch."""
    if token is ANY:
        return True
    if isinstance(token, str):
        return token == ch
    negate, ranges = token
    return any(lo <= ch <= hi for lo, hi in ranges) != negate


def wild(pattern, items, star, unit) -> bool:
    """Whether items match pattern: `star` takes any run of items, and every
    other token one item that unit(token, item) accepts."""
    p = i = 0
    back_p, back_i = -1, 0
    while i < len(items):
        if p < len(pattern) and pattern[p] is star:
            back_p, back_i = p, i
            p += 1
        elif p < len(pattern) and unit(pattern[p], items[i]):
            p += 1
            i += 1
        elif back_p >= 0:
            back_i += 1
            p, i = back_p + 1, back_i
        else:
            return False
    return all(t is star for t in pattern[p:])


def name_match(glob: tuple, name: str) -> bool:
    return wild(glob, name, STAR, one)


def split_folders(glob: str) -> list[str]:
    """The glob split at each `/` that is not inside a `[...]` class."""
    out, start, i = [], 0, 0
    while i < len(glob):
        cls = char_class(glob, i) if glob[i] == "[" else None
        if cls:
            i = cls[1]
            continue
        if glob[i] == "/":
            out.append(glob[start:i])
            start = i + 1
        i += 1
    out.append(glob[start:])
    return out


def folder_glob(text: str):
    """One folder name of a pattern as its tokens; GLOBSTAR for `**`."""
    if text == "**":
        return GLOBSTAR
    tokens: list = []
    i = 0
    while i < len(text):
        c = text[i]
        cls = char_class(text, i) if c == "[" else None
        if cls:
            tokens.append(cls[0])
            i = cls[1]
            continue
        if c == "*":
            if not (tokens and tokens[-1] is STAR):  # a run of stars is one
                tokens.append(STAR)
        else:
            tokens.append(ANY if c == "?" else c)
        i += 1
    return tuple(tokens)


def compile_pattern(line: str) -> tuple | None:
    """One line of an exempt list, gitignore style, as a matcher for a path.

    `name` matches a file or folder of that name at any depth, `name/` only a
    folder, with everything in it; a pattern with a / in front or in the
    middle is anchored to the repository root. `*`, `?` and `[...]` stay
    inside one folder name, and a folder name that is just `**` stands for
    any number of folders. A blank line, a `#` comment and a `!` line give
    None; a reversed range raises ValueError.
    """
    p = line.strip()
    if not p or p.startswith(("#", "!")):
        return None
    folder = p.endswith("/")
    anchored = "/" in p.rstrip("/")
    globs = [folder_glob(t) for t in split_folders(p) if t]
    if not globs:
        return None
    if len(globs) > 1 and globs[-1] is GLOBSTAR:  # `a/**`: everything in a
        globs.pop()
        folder = True
    head = [] if anchored else [GLOBSTAR]
    tail = [(STAR,), GLOBSTAR] if folder else [GLOBSTAR]
    return tuple(head + globs + tail)


def compile_patterns(lines, where: str | None = None) -> list[tuple]:
    """The matchers of an exempt list. A line that cannot be used is skipped,
    with a warning naming `where` and the line when `where` is given."""
    out = []
    for n, line in enumerate(lines, 1):
        why = ""
        if line.strip().startswith("!"):
            why = "negation (!) is not supported"
        else:
            try:
                rx = compile_pattern(line)
            except ValueError as e:
                why = str(e)
            else:
                if rx is not None:
                    out.append(rx)
        if why and where:
            warn(f"{where} line {n}: `{shown(line.strip())}` is skipped: {why}.")
    return out


def exempt(path: str, patterns: list[tuple]) -> bool:
    names = path.split("/")
    return any(wild(p, names, GLOBSTAR, name_match) for p in patterns)


def capped(lines: list[str], quiet: bool = False) -> list[str]:
    """The first LIST_LINES lines of an exempt list, within LIST_BYTES."""
    used = total = 0
    for line in lines:
        total += len(encoded(line)) + 1
        if used == LIST_LINES or total > LIST_BYTES:
            break
        used += 1
    if used < len(lines) and not quiet:
        warn(
            f"{EXEMPT_FILE} is over {LIST_LINES:,} lines or {LIST_BYTES:,} "
            f"bytes; only its first {used:,} lines are used."
        )
    return lines[:used]


def unused(why: str) -> tuple[list[str], None]:
    warn(
        f"{EXEMPT_FILE} at the top of the repository {why}, so its patterns "
        "are not used. Make it a plain UTF-8 text file."
    )
    return [], None


def repo_patterns() -> tuple[list[str], bytes | None]:
    """The lines of the staged .file-size-exempt, and its content (None when
    no regular file is staged there). A list staged as a link, a submodule or
    a folder, or that is not UTF-8 text, is not used, with a warning; a
    missing one is the usual case and says nothing."""
    # The pathspec also matches files in a folder of that name: only an
    # entry for the path itself is the list.
    env = dict(os.environ, GIT_LITERAL_PATHSPECS="1")
    entries = [
        e.split(b"\t", 1)
        for e in git("ls-files", "-s", "-z", "--", EXEMPT_FILE, env=env).split(b"\0")
        if e
    ]
    entry = next((h for h, path in entries if path == encoded(EXEMPT_FILE)), b"")
    if entries and not entry:
        return unused("is staged as a folder")
    if not entry:
        return [], None
    mode, sha = entry.split()[:2]
    if mode.decode() not in REGULAR:
        return unused("is staged as a link or a submodule")
    data = git("cat-file", "blob", sha.decode())
    try:
        return capped(data.decode("utf-8").splitlines()), data
    except UnicodeDecodeError:
        return unused("is not UTF-8 text")[0], data


def stage_hint(staged_list: bytes | None, refused: list[str]) -> list[str]:
    """The refused paths that the unstaged changes of a tracked exempt list
    name, so the refusal can say to stage the list. Never fails."""
    if staged_list is None or not refused:
        return []
    try:
        top = git("rev-parse", "--show-toplevel").rstrip(b"\n")
        path = os.path.join(os.fsdecode(top), EXEMPT_FILE)
        if os.path.islink(path) or not os.path.isfile(path):
            return []
        with open(path, "rb") as f:
            data = f.read()
        if data == staged_list:
            return []
        patterns = compile_patterns(capped(data.decode("utf-8").splitlines(), True))
        return [p for p in refused if exempt(p, patterns)]
    except Exception:
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


def paired(keys: list, values: list) -> list[tuple]:
    """zip() that insists on lists of one length, also on Python 3.9, which
    has no zip(strict=True)."""
    if len(keys) != len(values):
        raise RuntimeError(f"{len(keys)} names gave {len(values)} answers")
    return list(zip(keys, values))  # noqa: B905


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
    """The byte size of each object name that is a blob; None when missing or
    not a blob. Nothing is read but the headers."""
    if not names:
        return []
    out = git("cat-file", "--batch-check", data=batch_input(names))
    heads = [batch_head(line) for line in out.split(b"\n")[: len(names)]]
    return [h[1] if h and h[0] == b"blob" else None for h in heads]


def read_sizes(names: list[str]) -> list[tuple[int, int] | None]:
    """measure() of each blob named, read from one `git cat-file --batch` one
    blob at a time, so only one blob is ever held."""
    if not names:
        return []
    with subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as p:

        def feed() -> None:  # in its own thread, so neither pipe can fill up
            try:
                p.stdin.write(batch_input(names))
                p.stdin.close()
            except OSError:
                pass

        writer = threading.Thread(target=feed, daemon=True)
        writer.start()
        out: list[tuple[int, int] | None] = []
        try:
            for _ in names:
                line = p.stdout.readline()
                if not line.endswith(b"\n"):
                    raise RuntimeError("git cat-file stopped early")
                head = batch_head(line[:-1])
                if head is None:  # "<name> missing" or "<name> ambiguous"
                    out.append(None)
                    continue
                blob = p.stdout.read(head[1] + 1)
                if len(blob) != head[1] + 1:
                    raise RuntimeError("git cat-file stopped early")
                out.append(measure(blob[:-1]) if head[0] == b"blob" else None)
        except BaseException:
            p.kill()
            raise
        writer.join()
        if p.wait(timeout=60) != 0:
            raise RuntimeError(f"git cat-file failed (exit {p.returncode})")
    return out


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


def sizes(names: list[str], floor: int = 0) -> list[tuple[int, int] | None]:
    """(lines, bytes) of each blob named (a sha); None for a binary, missing
    or empty name. Each blob is measured once. A blob of at most `floor`
    bytes is not read and comes back as (0, bytes): with a floor up to
    MAX_LINES it cannot be over the limit. Blobs up to MAX_BYTES are read one
    by one from a single batch; a larger one is read in pieces and dropped
    once its first bytes show a binary."""
    named = sorted({n for n in names if n})
    known = dict(paired(named, blob_sizes(named)))
    small = [n for n in named if known[n] is not None and floor < known[n] <= MAX_BYTES]
    found = dict(paired(small, read_sizes(small)))
    for n in named:
        if known[n] is None:
            found[n] = None
        elif known[n] <= floor:
            found[n] = (0, known[n])
        elif n not in found:
            found[n] = stream_size(n)
    return [found[n] if n else None for n in names]


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
        path = decoded(raw[i + paths])
        i += 1 + paths
        if status[0] in "DU" or new_mode not in REGULAR:
            continue
        old = old_sha if status[0] in "MRT" and old_mode in REGULAR else None
        out.append((path, old, new_sha))
    return out


def parent_blobs(parent: str, paths: list[str]) -> dict[str, str]:
    """The blob of each path that is a regular file in the commit `parent`.
    Paths are looked up in its tree, never parsed as revision names."""
    env = dict(os.environ, GIT_LITERAL_PATHSPECS="1")
    out: dict[str, str] = {}
    for i in range(0, len(paths), PATHS_PER_CALL):
        chunk = paths[i : i + PATHS_PER_CALL]
        raw = git("ls-tree", "-r", "-z", "--full-tree", parent, "--", *chunk, env=env)
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            head, path = entry.split(b"\t", 1)
            mode, kind, sha = head.decode().split()
            if kind == "blob" and mode in REGULAR:
                out[decoded(path)] = sha
    return out


def attributes(paths: list[str]) -> dict[str, dict[str, str]]:
    """The diff and linguist attributes of each path, from the staged
    .gitattributes files alone. They are read in a temporary repository whose
    index holds just those files, with the system and global attribute files
    switched off, so $GIT_DIR/info/attributes, core.attributesFile and an
    unstaged edit exempt nothing."""
    if not paths:
        return {}
    env = dict(os.environ)
    for k in ("GIT_LITERAL_PATHSPECS", "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS"):
        env.pop(k, None)
    raw = git(
        "ls-files", "-s", "-z", "--",
        ":(glob).gitattributes", ":(glob)**/.gitattributes",
        env=env,
    )  # fmt: skip
    entries = []
    for entry in raw.split(b"\0"):
        head, _, path = entry.partition(b"\t")
        fields = head.split()
        if (
            len(fields) == 3
            and fields[2] == b"0"
            and fields[0].decode() in REGULAR
            and path.rsplit(b"/", 1)[-1] == b".gitattributes"
        ):
            entries.append(entry + b"\0")
    if not entries:
        return {}
    sha256 = len(entries[0].split()[1]) == 64
    objects = os.path.abspath(
        os.fsdecode(git("rev-parse", "--git-path", "objects").rstrip(b"\n"))
    )
    names = ("diff", "linguist-generated", "linguist-vendored")
    data = b"".join(encoded(p) + b"\0" for p in paths)
    clean = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") or k in KEPT_GIT_VARS
    }
    with tempfile.TemporaryDirectory(prefix="filesize-") as tmp:
        init = ["init", "-q", "--template="]
        git(*init, *(["--object-format=sha256"] if sha256 else []), tmp, env=clean)
        env = dict(clean, GIT_OBJECT_DIRECTORY=objects, GIT_ATTR_NOSYSTEM="1")
        git(
            "update-index",
            "-z",
            "--index-info",
            data=b"".join(entries),
            env=env,
            cwd=tmp,
        )
        raw = git(
            "-c", f"core.attributesFile={os.devnull}",
            "check-attr", "--cached", "-z", "--stdin", *names,
            data=data, env=env, cwd=tmp,
        )  # fmt: skip
    fields = raw.split(b"\0")
    out: dict[str, dict[str, str]] = {}
    for j in range(0, len(fields) - 2, 3):
        attrs = out.setdefault(decoded(fields[j]), {})
        attrs[fields[j + 1].decode()] = fields[j + 2].decode()
    return out


def skipped(attrs: dict[str, str]) -> bool:
    """Binary by .gitattributes, or marked generated or vendored there."""
    if attrs.get("diff") == "unset":
        return True
    return any(
        attrs.get(a) in ("set", "true")
        for a in ("linguist-generated", "linguist-vendored")
    )


def findings() -> tuple[list[tuple], list[tuple], list[str]]:
    """(refused, warned, hints). refused and warned hold (path, size, what it
    was before) for each file over the limit, warned the files that were over
    it already; hints the refused paths that an unstaged exempt list names.

    Sizes come first: only a file over the limit is matched against the
    exempt patterns and its attributes, and a blob too small to be over the
    limit is never read."""
    files = staged()
    new = sizes([f[2] for f in files], floor=MAX_LINES)
    big = [(f, s) for f, s in paired(files, new) if over(s)]
    if not big:
        return [], [], []
    lines, staged_list = repo_patterns()
    patterns = compile_patterns(DEFAULT_EXEMPT) + compile_patterns(lines, EXEMPT_FILE)
    big = [b for b in big if not exempt(b[0][0], patterns)]
    attrs = attributes([b[0][0] for b in big])
    big = [b for b in big if not skipped(attrs.get(b[0][0], {}))]
    if not big:
        return [], [], []
    paths = [b[0][0] for b in big]
    trees = [parent_blobs(p, paths) for p in merge_heads()]
    names: list[str] = []
    for (path, old, _), _ in big:
        names.append(old or "")
        names += [t.get(path, "") for t in trees]
    before = iter(sizes(names))
    refused, warned = [], []
    for (path, old, _), size in big:
        prior = [next(before) for _ in range(1 + len(trees))]
        if any(over(p) for p in prior):
            warned.append((path, size, prior[0]))
        elif old is not None and prior[0] is not None:
            refused.append((path, size, f"was {describe(prior[0])}"))
        else:
            refused.append((path, size, "new file"))
    return refused, warned, stage_hint(staged_list, [r[0] for r in refused])


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


def report(refused: list[tuple], warned: list[tuple], hints: list[str]) -> None:
    limit = f"{MAX_LINES:,} lines and {MAX_BYTES:,} bytes"
    what = "merge" if HOOK == "pre-merge-commit" else "commit"
    for path, size, _ in warned:
        warn(
            f"{shown(path)} is {describe(size)}, over the file size limit of "
            f"{limit}. It was over the limit before this {what}, so the {what} "
            f"goes on. {ALREADY_OVER} [{WARN_RULE}]"
        )
    if not refused:
        return
    print(
        f"{HOOK}: {what} refused, over the file size limit of {limit}:", file=sys.stderr
    )
    for path, size, how in refused:
        print(f"  {shown(path)}: {describe(size)} ({how})", file=sys.stderr)
    if hints:
        print(
            f"The unstaged changes of {EXEMPT_FILE} list "
            f"{', '.join(shown(p) for p in hints)}; stage the list "
            f"(`git add {EXEMPT_FILE}`).",
            file=sys.stderr,
        )
    print(
        "Split the file: new code that would take a file past the limit goes in "
        "a new file. A generated, vendored or data file can be listed in "
        f"{EXEMPT_FILE} at the top of the repository, one pattern per line. "
        f"[{RULE}]",
        file=sys.stderr,
    )
    log("block", RULE, refused, f"limit {MAX_LINES} lines, {MAX_BYTES} bytes")


def main(argv: list[str]) -> int:
    global HOOK
    if len(argv) != 1 or argv[0] not in HOOK_NAMES:
        print(f"usage: filesize.py {'|'.join(HOOK_NAMES)}", file=sys.stderr)
        return 2
    HOOK = argv[0]
    # A path that is not UTF-8, or a terminal that is not, must not stop the
    # report half-way: such characters are printed as escapes instead.
    sys.stderr.reconfigure(errors="backslashreplace")
    try:
        refused, warned, hints = findings()
    except Exception as e:
        print(f"{HOOK}: file size check failed: {shown(str(e))}", file=sys.stderr)
        return 2
    code = REFUSED if refused else 0
    try:
        report(refused, warned, hints)
    except Exception:
        if refused:  # the decision stands even when the report cannot be printed
            with contextlib.suppress(Exception):
                print(
                    f"{HOOK}: refused, over the file size limit [{RULE}]",
                    file=sys.stderr,
                )
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
