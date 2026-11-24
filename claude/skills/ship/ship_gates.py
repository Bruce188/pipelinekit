"""The merge gates of ship.py, and how a release is told from other work."""

# ruff: noqa: F403, F405
from __future__ import annotations

import configparser
import fnmatch
import json
import os
import plistlib
import re
import stat
from collections import Counter
from xml.etree import ElementTree

try:
    import tomllib
except ImportError:  # before Python 3.11
    tomllib = None

from ship_base import *
from ship_behind import base_gate
from ship_ci import RUNS_HERE
from ship_judged import MAX_TEXT_FILE, judged_gate, user_file
from ship_links import linked_gate

# ---------------------------------------------------------------- gates


def skipped(name):
    return gate(name, "skip", "needs an open pull request")


def sort_checks(rollup):
    """Split checks into passed, failed and still running.

    A check run counts as finished as soon as it has a conclusion: GitHub can
    leave `status` on IN_PROGRESS after the job is done.
    """
    passed, failed, pending = [], [], []
    for item in rollup or []:
        if item.get("__typename") == "StatusContext":
            word = (item.get("state") or "").upper()
            done = word in PASSING | FAILING
        else:
            word = (item.get("conclusion") or "").upper()
            done = bool(word)
        if not done:
            pending.append(item)
        elif word in PASSING:
            passed.append(item)
        else:
            failed.append(item)
    return passed, failed, pending


def check_names(items):
    return ", ".join(
        sorted({i.get("name") or i.get("context") or "check" for i in items})
    )


def log_hints(failed):
    ids = []
    for item in failed:
        m = re.search(r"/actions/runs/(\d+)", item.get("detailsUrl") or "")
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return [f"read the log: gh run view {i} --log-failed" for i in ids]


def pr_gate(repo, pr):
    if pr is None:
        return gate(
            "pr",
            "fail",
            f"no pull request for {repo.branch}: bring it up to date with its base "
            "(see up-to-date), push, then gh pr create --draft",
        )
    state = pr.get("state") or "UNKNOWN"
    if state != "OPEN":
        return gate("pr", "fail", f"#{pr.get('number')} is {state.lower()}")
    draft = ", draft" if pr.get("isDraft") else ""
    return gate(
        "pr", "pass", f"#{pr.get('number')} into {pr.get('baseRefName')}{draft}"
    )


def own_gate(repo, pr):
    user = repo.user()
    author = (pr.get("author") or {}).get("login") or ""
    if author.lower() != user.lower():
        who = author or "someone else"
        return gate("own", "fail", f"opened by {who}, not by {user}", stop=True)
    if pr.get("isCrossRepository"):
        return gate(
            "own", "fail", "comes from a fork: the maintainers merge it", stop=True
        )
    return gate("own", "pass", f"opened by {user}")


def opts_out(text):
    """True when one line of `text` is the opt-out line itself."""
    for line in text.lstrip("\ufeff").splitlines():
        cells = [
            re.sub(r"[*_]", "", LINE_LEAD.sub("", cell.strip(), count=1)).strip()
            for cell in line.split("|")
        ]
        # `| Merges | ask first |`: two cells of a table row read as one line.
        pairs = [f"{a}: {b}" for a, b in zip(cells, cells[1:], strict=False) if a and b]
        if any(OPT_OUT.match(cell) for cell in cells + pairs):
            return True
    return False


def read_policy(path, limit=MAX_TEXT_FILE):
    """(text, why) of a CLAUDE.md: text None and why '' when there is none.

    The file is opened without waiting, so a named pipe or a device at the path
    cannot hold the gate up; anything but a regular file gives the reason in
    `why`. A link is followed, as Claude Code follows it.
    """
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return None, ""
    except IsADirectoryError:
        return None, "a folder, not a file"
    except OSError as exc:
        return None, (exc.strerror or type(exc).__name__).lower()
    try:
        mode = os.fstat(fd).st_mode
        if stat.S_ISDIR(mode):
            return None, "a folder, not a file"
        if stat.S_ISFIFO(mode):
            return None, "a named pipe, not a regular file"
        if not stat.S_ISREG(mode):
            return None, "not a regular file"
        chunks, size = [], 0
        while size <= limit:
            chunk = os.read(fd, limit + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    except OSError as exc:
        return None, (exc.strerror or type(exc).__name__).lower()
    finally:
        os.close(fd)
    if size > limit:
        return None, f"larger than {limit // (1024 * 1024)} MB"
    return b"".join(chunks).decode("utf-8", "replace"), ""


def policy_texts(repo, base=""):
    """(label, text, why) of every CLAUDE.md that speaks for the project or the user.

    The project's files count in the checkout and on the base branch, so a
    branch cannot drop a line for its own pull request. A file that is there
    but cannot be read comes with text None and `why` naming it.
    """
    user, shown = user_file()
    for label, path, name in (
        ("CLAUDE.md", repo.root / "CLAUDE.md", "CLAUDE.md"),
        (".claude/CLAUDE.md", repo.root / ".claude" / "CLAUDE.md", ".claude/CLAUDE.md"),
        ("CLAUDE.local.md", repo.root / "CLAUDE.local.md", "CLAUDE.local.md"),
        ("your user-level CLAUDE.md", user, shown),
    ):
        text, why = read_policy(path)
        if why:
            yield label, None, f"cannot read {name} ({why})"
        elif text is not None:
            yield label, text, ""
    for name in ("CLAUDE.md", ".claude/CLAUDE.md") if base else ():
        rc, text, _ = repo.try_git("show", f"refs/remotes/{repo.remote}/{base}:{name}")
        if not rc:
            yield f"{name} on {base}", text, ""


def policy_gate(repo, pr=None):
    """The environment, the user or the project can ask for a question first."""
    asked = os.environ.get("PIPELINEKIT_MERGE", "").strip()
    if asked and asked.lower() != "auto":
        return gate("policy", "fail", f"PIPELINEKIT_MERGE={asked[:20]}", stop=True)
    for label, text, why in policy_texts(repo, (pr or {}).get("baseRefName") or ""):
        if why:
            # It may hold the opt-out line: only the user can tell.
            why += ": make it a readable regular file or remove it"
            return gate("policy", "fail", why, stop=True)
        if opts_out(text):
            why = f"{label} says `Merges: ask first`"
            return gate("policy", "fail", why, stop=True)
    return gate("policy", "pass", "no `Merges: ask first` line")


def words_of(text):
    """(versions, words) in a title or a branch name, in lower case."""
    versions, words = [], []
    for m in TOKEN.finditer(text.lower()):
        if m.group("version"):
            versions.append(m.group("version"))
        elif m.group("word"):
            words.append(m.group("word"))
    return versions, words


def own_words(info):
    """The words of the repository's own name."""
    name = (info.get("nameWithOwner") or "").rpartition("/")[2]
    return frozenset(w for w in words_of(name)[1] if w not in VOCABULARY)


def named_release(kind, scope, text, own=()):
    """True when the words after a type name a release or a version.

    A text made of release words alone names one: `chore: prepare 0.3.0`,
    `chore: version bump`, `chore: patch`. With one or two other words in it,
    it has to read like a release: start like one (`chore: release kit 1.2.0`,
    `chore: bump version in package.json`), be a name and a number
    (`chore: kit 1.2.0`) or be short and end in one (`chore: weekly release`).
    A title about a tool (`ci: bump python version to 3.12`) or about how
    releases are made (`chore: release script`) is ordinary. After `feat` and
    `fix` any other word makes it an ordinary change, and `docs`, `test`,
    `style`, `refactor` and `perf` never name a release. `own` holds the words
    of the repository's own name, which count as release words.
    """
    if kind in QUIET_TYPES:
        return False
    versions, words = words_of(SHORTCODE.sub(" ", text))
    words = [w for w in words if w not in own]
    unknown = [w for w in words if w not in VOCABULARY]
    spoken = [w for w in words if w not in FILLER]
    implied = "release" in (kind, scope)
    strong = implied or any(w in STRONG for w in words)
    names = RELEASE_NAMES | VERSION_WORDS
    first = spoken[0] if spoken else ""
    if TOOLCHAIN.intersection(words) and not implied and first not in RELEASE_NAMES:
        return False
    if not unknown:
        if kind in PLAIN_TYPES:
            return bool(versions) and (strong or not words)
        if versions or strong:
            return True
        # `chore: patch`, `chore: bump minor`; not `chore: minor update`.
        rest = spoken[1:] if first in ACTIONS and len(spoken) > 1 else spoken
        return bool(rest) and all(w in LEVELS for w in rest)
    if kind in PLAIN_TYPES or len(unknown) > 2:
        return False
    if versions:
        leads = first in RELEASE_NAMES or (
            first in ACTIONS and any(w in names for w in spoken[1:3])
        )
        named = kind != "ci" and all(w in unknown for w in spoken)
        ends = len(unknown) == 1 and len(spoken) <= 3 and spoken[-1] in RELEASE_NAMES
        return implied or leads or named or ends
    if len(unknown) > 1 or MACHINERY.intersection(words):
        return False
    if first in ACTIONS and len(spoken) > 1 and spoken[1] in names:
        return True
    return (len(spoken) <= 2 and first in RELEASE_NAMES) or (
        len(spoken) <= 3 and spoken[-1] in names
    )


def release_head(head, own=()):
    """True when a branch name says release, version or stage."""
    name = head.lower()
    kind, slash, text = name.partition("/")
    if RELEASE_HEAD.match(name) or name in STAGE_HEADS:
        return True
    if slash and kind in STAGE_PREFIXES:
        return True
    if not slash:
        kind, text = "", name
        parts = re.split(r"[-_.]+", name)
        if len(parts) <= 2 and parts[0] in STAGE_FIRST:
            return True
    text = re.sub(r"[-_/]+", " ", re.sub(r"^\d+[-_]", "", text))
    if kind in TOPIC_PREFIXES:
        # `feat/21-v2` is the second take of a feature, not version 2.
        text = re.sub(r"(?<![\w.])v\d+(?![\w.])", " ", text)
    return named_release(kind, "", text, own)


def release_title(title, default="", own=()):
    """True when a pull request title names a release, not a change about one."""
    title = " ".join(CI_TAG.sub(" ", title or "").split())
    kind, scope, rest = "", "", title
    m = TITLE_PREFIX.match(title)
    if m:
        kind, scope = m.group("type").lower(), (m.group("scope") or "").lower()
        rest = title[m.end() :]
    m = MERGE_TITLE.match(title) or MERGE_TITLE.match(rest)
    if m:
        into = {default.lower(), *MAINLINES}
        return m.group(2).lower() in into and release_head(m.group(1), own)
    return bool(RELEASE_MARK.search(rest)) or named_release(kind, scope, rest, own)


def deploy_base(base):
    """True when the name of a base branch says it is deployed or published."""
    low = base.lower()
    if low.split("/")[0] in ("env", "environment", "environments"):
        return True
    return bool(DEPLOY_WORDS & set(re.split(r"[^a-z]+", low)))


def work_base(base):
    """True for a base that ordinary work goes into besides the default branch."""
    low = base.lower()
    if low in WORK_BASES or RELEASE_LINE.match(low):
        return True
    first, slash, _ = low.partition("/")
    return bool(slash) and first in WORK_PREFIXES | TOPIC_PREFIXES


def release_branches(head, base, default="", own=()):
    """Why these two branches make a release, a deploy or a promotion; else ''."""
    low, main_name = base.lower(), default.lower()
    main = low == main_name if default else low in (*MAINLINES, "trunk")
    if default and main_name not in MAINLINES and low in MAINLINES:
        return (
            f"{base} is not the default branch ({default}): what goes into it "
            "is a release"
        )
    if not main and deploy_base(base):
        return f"{base} is a deploy branch"
    if default and head == default and not main:
        return f"{head} into {base} promotes the default branch"
    if release_head(head, own):
        if main:
            return f"{head} into {base} is a release"
        return f"{head} into {base} merges a release or stage branch"
    if not main and not work_base(base):
        return f"{base} is not the default branch or a known working branch"
    return ""


def shown(path):
    """A path as a message shows it: one line, plain characters, not too long."""
    return re.sub(r"[^\x21-\x7e]+", "?", path)[:120]


def stem_of(name):
    """`.bumpversion.cfg` -> `bumpversion`, `__version__.py` -> `version`."""
    return re.sub(r"[-_ ]", "", name.lstrip(".").partition(".")[0])


def ext_of(name):
    """`.json` for `package.json`; '' for `VERSION` and for `.nvmrc`."""
    bare = name.lstrip(".")
    dot = bare.rfind(".")
    return "" if dot < 0 else bare[dot:]


def place(path):
    """How a changed file is read for a version.

    '' = not at all, `whole` = any change counts, `notes` = release notes,
    `data` = a manifest or another file that is not source code, `code`.
    """
    low = path.lower()
    *dirs, name = low.split("/")
    if low.startswith(SKIP_ROOTS) or SKIP_DIRS.intersection(dirs):
        return ""
    if name in LOCK_FILES | TOOL_FILES or name.startswith(TOOL_STARTS):
        return ""
    if name.endswith(SKIP_ENDS + BINARY_ENDS):
        return ""
    stem, ext = stem_of(name), ext_of(name)
    if ext in CODE_ENDS:
        manifest = (
            name in MANIFEST_CODE
            or name.startswith(("assemblyinfo.", "build.gradle"))
            or stem in ("version", "about")
        )
        return "data" if manifest else "code"
    if stem in VERSION_STEMS:
        return "whole"
    if NOTES_DIRS.intersection(dirs) and NUMBER.search(name):
        return "whole"
    if stem in NOTES_STEMS:
        return "notes"
    if stem in DOC_STEMS or (ext in DOC_ENDS and name != "cmakelists.txt"):
        return ""
    return "data"


def tool_key(key):
    """True when a key names the version of a tool or of a file format."""
    low = key.lower().lstrip("_-.@$")
    words = {word.lower() for word in KEY_WORD.findall(key)}
    if words & TOOL_WORDS:
        return True
    return low.startswith(TOOL_KEY_STARTS) and not low.startswith("minor")


def version_key(key, value):
    """True when `key = value` sets a version of the project itself."""
    if "version" not in key.lower() or tool_key(key) or not VALUE.match(value):
        return False
    last = re.sub(r"[_@$-]", "", key.lower().rpartition(".")[2])
    # A bare `version: 2` is the version of a file format.
    return last != "version" or bool(DOTTED.match(value.lstrip(" \t\"'[({vV")))


def walk(node, trail, out):
    """Count the leaves of parsed JSON, TOML or a property list by their keys."""
    if isinstance(node, dict):
        for key, value in node.items():
            walk(value, (*trail, str(key)), out)
    elif isinstance(node, list):
        for value in node:
            walk(value, trail, out)
    elif isinstance(node, (str, int, float)) and not isinstance(node, bool):
        out[(trail, str(node))] += 1


def xml_leaves(text):
    """The leaves of an XML manifest, without what it pins for other things."""
    if "<!ENTITY" in text.upper():
        raise ValueError("entities are not expanded")
    out = Counter()

    def visit(node, trail):
        tag = node.tag.rpartition("}")[2] if isinstance(node.tag, str) else ""
        pins = {"Include", "Update"} & set(node.attrib)
        if not tag or pins or XML_DEPENDS.search(tag):
            return
        here = (*trail, tag)
        for name, value in node.attrib.items():
            out[((*here, "@" + name.rpartition("}")[2]), value)] += 1
        if len(node):
            for child in node:
                visit(child, here)
        elif (node.text or "").strip():
            out[(here, node.text.strip())] += 1

    visit(ElementTree.fromstring(text), ())
    return out


def yaml_leaves(text):
    """The `key: value` leaves of a YAML file, read by indentation."""
    out, stack = Counter(), []
    for raw in text.splitlines():
        line = raw.split(" #")[0].rstrip()
        body = line.lstrip(" ")
        if not body or body.startswith(("#", "---", "...")):
            continue
        while body.startswith("- "):
            body = body[2:].lstrip(" ")
        indent = len(line) - len(body)
        m = YAML_PAIR.match(body)
        if not m:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key, value = m.group(2), (m.group(3) or "").strip()
        if value[:1] in ("{", "[") and "version" in value.lower():
            raise ValueError("a flow mapping is read by line")
        if not value or value[0] in "|>&*!":
            stack.append((indent, key))
        else:
            out[((*(k for _, k in stack), key), value.strip("\"'"))] += 1
    return out


def table_leaves(text):
    """The leaves of a TOML file read by line, for a Python without tomllib."""
    out, trail = Counter(), ()
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"\[+\s*([^\]]+?)\s*\]+", line)
        if m:
            trail = tuple(part.strip("\"' ") for part in m.group(1).split("."))
            continue
        key, equals, value = line.partition("=")
        if equals and not line.startswith("#"):
            out[((*trail, key.strip("\"' ")), value.strip().strip("\"'"))] += 1
    return out


def leaves(name, text):
    """The leaves of a manifest; None for a format that is read by line."""
    if not text.strip():
        return Counter()
    out = Counter()
    try:
        if name.endswith(".json"):
            walk(json.loads(text), (), out)
        elif name.endswith(".toml"):
            if tomllib is None:
                return table_leaves(text)
            walk(tomllib.loads(text), (), out)
        elif name.endswith(".plist"):
            walk(plistlib.loads(text.encode("utf-8")), (), out)
        elif name.endswith(XML_ENDS):
            return xml_leaves(text)
        elif name.endswith((".cfg", ".ini")):
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read_string(text)
            for section in parser.sections():
                for key, value in parser.items(section, raw=True):
                    out[((section, key), value)] += 1
        elif name.endswith((".yaml", ".yml")):
            return yaml_leaves(text)
        else:
            return None
    except Exception:  # noqa: BLE001 - whatever the parser raises: read by line
        return None
    return out


def sets_version(trail, value):
    """True when the leaf at `trail` is a version of the project itself."""
    if not trail or any(DEPENDS.search(key) for key in trail[:-1]):
        return False
    return version_key(trail[-1].lstrip("@"), value)


def line_rule(old, new):
    """True when a line added to a file without a known format sets a version."""
    before = Counter(old.splitlines())
    after = Counter(new.splitlines())
    added = [line for line in after - before if len(line) <= MAX_LINE]
    removed = {
        MASK.sub("#", line)
        for line in before - after
        if len(line) <= MAX_LINE and MASK.search(line)
    }
    for line in added:
        if DEP_LINE.search(line):
            continue
        for m in DECLARES.finditer(line):
            key = m.group("key")
            if tool_key(key):
                continue
            last = re.sub(r"[_@$-]", "", key.lower().rpartition(".")[2])
            if last != "version" or DOTTED.match(line[m.end() - 1 :]):
                return True
        # The same line as before with another number: `#define VER "1.2.4"`.
        if (
            MASK.search(line)
            and MASK.sub("#", line) in removed
            and not TOOL_WORDS.intersection(re.findall(r"[a-z]+", line.lower()))
        ):
            return True
    return False


def notes_rule(old, new, own=()):
    """True when the release notes gain the heading of a version.

    A line with a number the file did not hold yet counts when it is a
    heading, a link definition, or nothing but the number, a date, the name of
    the project and words like `version`. A sentence that names the version of
    something else does not.
    """
    seen = {m.group(1) for m in NUMBER.finditer(old)}
    lines = new.splitlines()
    added = Counter(lines) - Counter(old.splitlines())
    for at, line in enumerate(lines):
        if added[line] <= 0:
            continue
        added[line] -= 1
        if len(line) > MAX_LINE:
            continue
        fresh = [m for m in NUMBER.finditer(line) if m.group(1) not in seen]
        if not fresh:
            continue
        body = line.strip()
        below = lines[at + 1] if at + 1 < len(lines) else ""
        if body.startswith(("#", "=")) or UNDERLINE.match(below):
            return True
        if LINK_DEF.match(line):
            return True
        versions, words = words_of(STRIP_NOTE.sub(" ", body))
        if versions and all(w in own or w in NOTE_WORDS | MONTHS for w in words):
            return True
    return False


def changed_files(repo, base):
    """(files, error): old mode, new mode, old blob, new blob and path of each."""
    span = f"refs/remotes/{repo.remote}/{base}...HEAD"
    rc, out, err = repo.try_git(
        "diff", "--raw", "--no-abbrev", "--no-renames", "-z", span
    )
    if rc:
        return [], said(err or out, rc)
    parts = [part for part in out.split("\0") if part]
    files = []
    for meta, path in zip(parts[::2], parts[1::2], strict=False):
        fields = meta.lstrip(":").split()
        if len(fields) >= 5:
            files.append((*fields[:4], path))
    return files, ""


def blob(repo, sha):
    """(text, error) of a blob; '' for the side of a diff that has no file."""
    if not sha.strip("0"):
        return "", ""
    rc, out, err = repo.try_git("cat-file", "blob", sha)
    return ("", said(err or out, rc)) if rc else (out, "")


def code_version(repo, base):
    """(path, error): a source file in which the diff sets a version; else ''."""
    rc, out, err = repo.try_git(
        "-c",
        "core.quotePath=false",
        "diff",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        "--no-renames",
        "-G[Vv][Ee][Rr][Ss][Ii][Oo][Nn]",
        f"refs/remotes/{repo.remote}/{base}...HEAD",
    )
    if rc:
        return "", said(err or out, rc)
    path, header = "", False
    for line in out.splitlines():
        if line.startswith("diff --git "):
            path, header = "", True
        elif header and line.startswith("+++ "):
            path = line[6:].rstrip("\t") if line.startswith("+++ b/") else ""
        elif line.startswith("@@"):
            header = False
        elif (
            not header
            and path
            and line.startswith("+")
            and place(path) == "code"
            and CODE_VERSION.match(line[1:])
        ):
            return path, ""
    return "", ""


def sets(name, old, new):
    """True when the change from `old` to `new` sets a version of the project."""
    after = leaves(name, new)
    before = leaves(name, old) if after is not None else None
    if after is None or before is None:
        return line_rule(old, new)
    return any(sets_version(trail, value) for trail, value in after - before)


def listed(patterns, value, names=False):
    """True when `value` matches one of the patterns of a project line.

    `dir/` is everything below a directory, anything else a glob on the whole
    value and, with `names`, on the file name alone.
    """
    low = value.lower()
    for pattern in patterns:
        if pattern.endswith("/"):
            hit = low.startswith(pattern)
        else:
            name = low.rpartition("/")[2]
            hit = fnmatch.fnmatchcase(low, pattern) or (
                names and fnmatch.fnmatchcase(name, pattern)
            )
        if hit:
            return True
    return False


def project_lines(texts):
    """(files, branches) that a `Release files:` or `Release branches:` line names."""
    found = {"file": [], "branch": []}
    for text in texts:
        for raw in text.lstrip("\ufeff").splitlines():
            line = LINE_LEAD.sub("", raw.strip(), count=1).replace("`", "")
            m = PROJECT_LINE.match(line)
            if not m:
                continue
            values = re.split(r"[,\s]+", m.group(2).lower())
            found[m.group(1).lower()] += [
                v for v in values if v and "<" not in v and v != "-->"
            ]
    return found["file"], found["branch"]


def version_change(repo, base, own=(), release_files=()):
    """(why, error): why the changes against `base` make a release; else ''.

    Fails closed: a version is ordinary in the places the lists above name,
    and held anywhere else.
    """
    files, error = changed_files(repo, base)
    if error:
        return "", error
    watched, code = [], False
    for old_mode, new_mode, old, new, path in files:
        if {"160000", "120000"} & {old_mode, new_mode}:
            continue
        if listed(release_files, path, names=True):
            return f"the diff changes {shown(path)}, a release file of this project", ""
        kind = place(path)
        if kind == "whole":
            return f"the diff changes {shown(path)}{NEW_VERSION}", ""
        if kind == "code":
            code = True
        elif kind and new.strip("0"):
            watched.append((kind, old, new, path))
    if len(watched) > MAX_VERSION_FILES:
        why = f"the diff changes {len(watched)} files that can hold a version"
        return why + NEW_VERSION, ""
    for kind, old, new, path in watched:
        before, error = blob(repo, old)
        after, failed = blob(repo, new)
        if error or failed:
            return "", error or failed
        if "\0" in after or len(after) > MAX_BLOB:
            continue
        if "\0" in before or len(before) > MAX_BLOB:
            before = ""
        if kind == "notes":
            if notes_rule(before, after, own):
                why = f"the diff adds a version heading to {shown(path)}"
                return why + NEW_VERSION, ""
        elif sets(path.lower(), before, after):
            return f"the diff sets a version in {shown(path)}{NEW_VERSION}", ""
    if code:
        path, error = code_version(repo, base)
        if error:
            return "", error
        if path:
            return f"the diff sets a version in {shown(path)}{NEW_VERSION}", ""
    return "", ""


def promoted(repo, head):
    """(why, error): pull requests were merged into the head, so it is a stage."""
    kind, slash, _ = head.lower().partition("/")
    if slash and kind in TOPIC_PREFIXES:
        return "", ""
    rc, out, err = repo.gh(
        "pr", "list", "--base", head, "--state", "merged", "--limit", "1",
        "--json", "number",
    )  # fmt: skip
    merged = []
    if not rc:
        try:
            merged = json.loads(out)
        except ValueError:
            merged = None
        if not isinstance(merged, list):
            rc, err = 1, "unreadable answer"
    if rc:
        return "", f"cannot ask GitHub what was merged into {head}: {said(err, rc)}"
    if merged:
        why = f"pull requests were merged into {head}: merging it on is a promotion"
        return why, ""
    return "", ""


def recorded_release(repo, head):
    """What the passed round on `head` says: 'yes', 'no', '' or None for no round."""
    try:
        rounds = load_record(repo.record_file)["rounds"]
    except RecordError:
        return None
    last = rounds[-1] if rounds else {}
    if last.get("result") != "pass" or last.get("commit") != head:
        return None
    answer = last.get("release")
    return answer if answer in ("yes", "no") else ""


def release_gate(repo, pr):
    """A release, a deploy or a promotion of the default branch stays the user's."""
    head, base = pr.get("headRefName") or "", pr.get("baseRefName") or ""
    info = repo.info()
    default = (info.get("defaultBranchRef") or {}).get("name") or ""
    own = own_words(info)

    def stop(why):
        return gate("release", "fail", why, stop=True)

    if release_title(pr.get("title"), default, own):
        return stop("the title reads like a release")
    why = release_branches(head, base, default, own)
    if why:
        return stop(why)
    texts = (text for _, text, _ in policy_texts(repo, base) if text is not None)
    files, branches = project_lines(texts)
    for name in (head, base):
        if listed(branches, name):
            return stop(f"{name} is a release branch of this project")
    why, error = promoted(repo, head)
    if error:
        return gate("release", "fail", error)
    if why:
        return stop(why)
    why, error = version_change(repo, base, own, files)
    if error:
        return gate(
            "release", "fail", f"cannot read what changes against {base}: {error}"
        )
    if why:
        return stop(why)
    answer = recorded_release(repo, pr.get("headRefOid") or "")
    if answer == "yes":
        return stop("the test record says this is a release")
    if answer == "":
        return gate(
            "release",
            "fail",
            "the test record does not say whether this is a release: record the "
            "round again with --release yes or no",
        )
    return gate("release", "pass", "not a release")


def review_gate(pr):
    decision = pr.get("reviewDecision") or ""
    if decision == "CHANGES_REQUESTED":
        return gate("review", "fail", "a reviewer requested changes", stop=True)
    if decision == "REVIEW_REQUIRED":
        return gate("review", "fail", "the base branch requires a review", stop=True)
    asked = [
        r.get("login") or r.get("name") or r.get("slug") or "a reviewer"
        for r in pr.get("reviewRequests") or []
    ]
    if asked:
        return gate(
            "review", "fail", f"review requested from {', '.join(asked)}", stop=True
        )
    _, failed, pending = sort_checks(pr.get("statusCheckRollup"))
    if pr.get("mergeStateStatus") == "BLOCKED" and not failed and not pending:
        return gate("review", "fail", "branch protection blocks the merge", stop=True)
    return gate("review", "pass", "approved" if decision else "no review required")


def current_gate(repo, pr):
    head = pr.get("headRefOid") or ""
    if head != repo.head:
        return gate(
            "current",
            "fail",
            f"local HEAD {short(repo.head)} is not the pull request's head "
            f"{short(head)}: push or pull first",
        )
    if repo.dirty():
        return gate("current", "fail", "tracked files have uncommitted changes")
    return gate("current", "pass", f"head {short(head)}, tracked files clean")


def tested_gate(repo, head):
    try:
        rounds = load_record(repo.record_file)["rounds"]
    except RecordError as exc:
        return gate("tested", "fail", str(exc))
    where = repo.record_file.relative_to(repo.root).as_posix()
    if not rounds:
        return gate(
            "tested",
            "fail",
            f"no test record ({where}): run the acceptance test, then ship.py record",
        )
    last, n = rounds[-1], len(rounds)
    if last.get("result") != "pass":
        stuck = stop_reason(rounds)
        if stuck:
            why = f"round {n} failed, {stuck}: tell the user what is stuck"
            return gate("tested", "fail", why, stop=True)
        left = ", ".join(open_ids(last).values()) or "not named"
        return gate("tested", "fail", f"round {n} failed, still open: {left}")
    if last.get("commit") != head:
        return gate(
            "tested",
            "fail",
            f"round {n} passed on {short(last.get('commit'))}, the head is now "
            f"{short(head)}: test again",
        )
    tester = last.get("tester") or "agent"
    return gate("tested", "pass", f"round {n} passed on {short(head)} ({tester})")


def ci_gate(pr, expected=False):
    """CI as it stands now.

    `expected`: a workflow here runs on the pull request or on pushes to its
    branch, so a pull request without a single check has not been picked up
    yet; that is not a pass.
    """
    passed, failed, pending = sort_checks(pr.get("statusCheckRollup"))
    if failed:
        return gate(
            "ci", "fail", f"failed: {check_names(failed)}", hints=log_hints(failed)
        )
    if pending:
        total = len(passed) + len(pending)
        return gate(
            "ci",
            "pending",
            f"{len(pending)} of {total} still running: {check_names(pending)}",
        )
    if not passed and expected:
        return gate(
            "ci",
            "pending",
            f"no check has shown up yet, and {RUNS_HERE}",
        )
    if not passed:
        return gate("ci", "pass", "no CI checks on this pull request")
    return gate("ci", "pass", f"{count(len(passed), 'check')} finished, none failed")


def evaluate(repo, pr, no_checks_ok=False, base=""):
    """Every gate for the current branch's pull request; CI as it stands now.

    `base`: the base to compare with while there is no pull request (--base).
    """
    first = pr_gate(repo, pr)
    if first["state"] != "pass":
        return [
            first,
            skipped("own"),
            policy_gate(repo),
            skipped("release"),
            skipped("linked"),
            skipped("review"),
            skipped("current"),
            base_gate(repo, pr, base),
            judged_gate(repo, repo.head, ""),
            tested_gate(repo, repo.head),
            skipped("ci"),
        ]
    # First, because it fetches the base branch, which the policy gate reads.
    up_to_date = base_gate(repo, pr, base)
    return [
        first,
        own_gate(repo, pr),
        policy_gate(repo, pr),
        release_gate(repo, pr),
        linked_gate(repo, pr),
        review_gate(pr),
        current_gate(repo, pr),
        up_to_date,
        judged_gate(repo, pr.get("headRefOid") or "", pr.get("baseRefName") or ""),
        tested_gate(repo, pr.get("headRefOid") or ""),
        ci_gate(pr, repo.expects_checks() and not no_checks_ok),
    ]


def verdict(gates):
    """Exit code for a list of gates: 0 all hold, 3 the user's call, 1 otherwise."""
    bad = [g for g in gates if g["state"] != "pass"]
    if not bad:
        return 0
    return EXIT_STOP if any(g["stop"] for g in bad) else EXIT_FAIL
