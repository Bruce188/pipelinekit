"""update.py: lists what origin has, and updates only to what it listed."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
REPO = KIT.parents[2]

sys.path.insert(0, str(KIT))
_spec = importlib.util.spec_from_file_location("kit_update", KIT / "update.py")
update_py = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(update_py)

SKIP = shutil.ignore_patterns(
    ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "docs"
)


def run_git(env, cwd, *args):
    p = subprocess.run(
        [
            "git",
            "-C",
            str(cwd),
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """A kit checkout with a local origin and an install made from it."""
    root = tmp_path_factory.mktemp("update")
    live = root / "live"
    user, work, origin = live / "home", live / "work", live / "origin.git"
    user.mkdir(parents=True)
    shutil.copytree(REPO, work, ignore=SKIP)
    env = dict(
        os.environ,
        HOME=str(user),
        CLAUDE_HOME=str(user / ".claude"),
        USER_NAME="Test User",
        USER_EMAIL="test@example.com",
        GIT_CONFIG_GLOBAL=str(user / ".gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        XDG_CONFIG_HOME=str(user / ".config"),
    )
    for k in (
        "ALLOW_MAIN_PUSH",
        "PIPELINEKIT_ALLOW_SECRET",
        "PIPELINEKIT_GIT_HOOKS",
        "PIPELINEKIT_STATE_DIR",
        "PIPELINEKIT_LOG",
        "PIPELINEKIT_SESSION_CHECK",
        "PIPELINEKIT_UPDATE_CHECK",
        "CLAUDE_INSTALL_SKIP_SERENA",
        "XDG_STATE_HOME",
        "GH_CONFIG_DIR",
    ):
        env.pop(k, None)
    run_git(env, live, "init", "-q", "--bare", "-b", "main", str(origin))
    run_git(env, work, "init", "-q", "-b", "main")
    run_git(env, work, "add", "-A")
    run_git(env, work, "commit", "-qm", "feat: the kit")
    run_git(env, work, "remote", "add", "origin", str(origin))
    run_git(env, work, "push", "-q", "origin", "main")
    p = subprocess.run(
        ["bash", str(work / "scripts" / "install.sh"), "--no-serena", "--git-hooks"],
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    shutil.copytree(live, root / "template", symlinks=True)
    return {"root": root, "live": live, "env": env}


class Kit:
    def __init__(self, template):
        self.env = template["env"]
        self.live = template["live"]
        self.work = self.live / "work"
        self.origin = self.live / "origin.git"
        self.home = self.live / "home" / ".claude"
        self.script = self.home / "skills" / "kit" / "update.py"

    def git(self, cwd, *args):
        return run_git(self.env, cwd, *args)

    def head(self):
        return self.git(self.work, "rev-parse", "HEAD")

    def manifest(self):
        return json.loads((self.home / "pipelinekit" / "manifest.json").read_text())

    def edit_manifest(self, **change):
        path = self.home / "pipelinekit" / "manifest.json"
        data = json.loads(path.read_text())
        data.update(change)
        path.write_text(json.dumps(data, indent=2))

    def update(self, *args, env=None):
        p = subprocess.run(
            [sys.executable, str(self.script), *args],
            capture_output=True,
            text=True,
            env=dict(self.env, **(env or {})),
            cwd=self.live,
        )
        out = p.stdout + p.stderr
        # The result line is the last line of stdout; the installer's warnings
        # (no gitleaks on this machine, say) arrive on stderr after it.
        said = p.stdout.strip().splitlines() or p.stderr.strip().splitlines()
        return p.returncode, out, (said or [""])[-1]

    def push(self, subject="feat: more", change=None):
        """Somebody else pushes a commit; `change(clone)` edits the kit."""
        other = self.live / "other"
        if not other.exists():
            self.git(self.live, "clone", "-q", str(self.origin), str(other))
        if change:
            change(other)
        else:
            n = len(list(other.iterdir()))
            (other / f"note{n}.txt").write_text("x\n")
        self.git(other, "add", "-A")
        self.git(other, "commit", "-qm", subject)
        self.git(other, "push", "-q", "origin", "main")
        return self.git(other, "rev-parse", "HEAD")

    def installed(self):
        return {
            str(p.relative_to(self.home)): p.read_bytes()
            for p in sorted(self.home.rglob("*"))
            if p.is_file()
        }


@pytest.fixture
def kit(template):
    shutil.rmtree(template["live"])
    shutil.copytree(template["root"] / "template", template["live"], symlinks=True)
    return Kit(template)


BY_HAND = "By hand: bash {work}/scripts/install.sh --git-hooks --no-serena"


def partly(old, new, installer, self_check):
    """The last line of an update whose checkout moved but whose install did
    not finish; `self_check` is a regular expression."""
    return (
        re.escape(
            f"Partly updated {old[:7]} -> {new[:7]}: the checkout is at {new[:7]} "
            "but the install did not finish; run the command on the By hand "
            f"line. Installer: {installer}. Self-check: "
        )
        + self_check
        + r"\."
    )


def bump_version(clone):
    (clone / "VERSION").write_text("9.9.9\n")


def test_plan_when_up_to_date(kit):
    rc, out, last = kit.update("plan")
    assert rc == 0, out
    assert last == f"Up to date: this install is at origin/main ({kit.head()[:7]})."


def test_plan_lists_the_new_commits_and_changes_nothing(kit):
    before, head = kit.installed(), kit.head()
    kit.push("feat: first new thing")
    new = kit.push("fix: second new thing")
    rc, out, last = kit.update("plan")
    assert rc == 0, out
    assert f"Installed: {head[:7]} (main)" in out
    assert f"Remote:    {new[:7]} (origin/main)" in out
    assert "feat: first new thing" in out and "fix: second new thing" in out
    assert last == (
        f"Update available: 2 commits. Apply with: python3 {kit.script} "
        f"apply --to {new}"
    )
    assert kit.head() == head and kit.installed() == before


def test_apply_updates_checkout_and_install(kit):
    old = kit.head()
    new = kit.push("feat: version nine", bump_version)
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 0, out
    assert last == f"Updated {old[:7]} -> {new[:7]}. Self-check: healthy."
    assert kit.head() == new
    m = kit.manifest()
    assert m["commit"] == new and m["version"] == "9.9.9"
    # What was chosen at install time stays: git hooks on, no serena.
    assert m["hooks_path"] == f"{kit.home}/git-hooks" and m["serena"] is False
    assert "serena: skipped" in out
    assert not (kit.live / "home" / ".claude.json").exists()
    rc, out, last = kit.update("plan")
    assert rc == 0 and last.startswith("Up to date: "), out


def test_apply_after_a_pull_by_hand(kit):
    old = kit.head()
    new = kit.push("feat: version nine", bump_version)
    kit.git(kit.work, "pull", "-q", "--ff-only", "origin", "main")
    rc, out, last = kit.update("plan")
    assert rc == 0 and f"Checkout:  {new[:7]}" in out, out
    assert last.startswith("Update available: 1 commit. Apply with: ")
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 0, out
    assert last == f"Updated {old[:7]} -> {new[:7]}. Self-check: healthy."
    assert kit.manifest()["version"] == "9.9.9"


def test_apply_refuses_when_origin_moved_on(kit):
    before, head = kit.installed(), kit.head()
    shown = kit.push("feat: shown in the plan")
    later = kit.push("feat: pushed after the plan")
    rc, out, last = kit.update("apply", "--to", shown)
    assert rc == 1, out
    assert last == (
        f"Not updated: origin/main is at {later[:7]} now, not at {shown[:7]}; "
        "run the plan again."
    )
    assert kit.head() == head and kit.installed() == before


def refused(kit, reason):
    """Plan and apply both refuse with `reason` and leave everything as it was."""
    before, head = kit.installed(), kit.head()
    new = kit.push()
    rc, out, last = kit.update("plan")
    assert rc == 1 and last == f"Cannot update: {reason}.", out
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 1 and last == f"Not updated: {reason}.", out
    assert kit.head() == head and kit.installed() == before


def test_refuses_uncommitted_changes(kit):
    with open(kit.work / "VERSION", "a") as f:
        f.write("mine\n")
    refused(kit, "the checkout has uncommitted changes")
    assert (kit.work / "VERSION").read_text().endswith("mine\n")


def test_refuses_another_branch(kit):
    kit.git(kit.work, "switch", "-q", "-c", "mine")
    refused(kit, "the checkout is on mine, this install was made from main")


def test_refuses_own_commits(kit):
    (kit.work / "mine.txt").write_text("x\n")
    kit.git(kit.work, "add", "mine.txt")
    kit.git(kit.work, "commit", "-qm", "feat: my own")
    refused(kit, "the checkout has commits that origin/main does not have")


def test_refuses_an_install_from_elsewhere(kit):
    kit.edit_manifest(commit="1" * 40)
    before = kit.installed()
    rc, out, last = kit.update("plan")
    assert rc == 1, out
    assert last == (
        "Cannot update: this install was made from 1111111, which is not part "
        "of origin/main."
    )
    assert kit.installed() == before


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"checkout": "/no/such"}, "the checkout this install was made from is not"),
        ({"commit": ""}, "the install manifest names no commit"),
        ({"branch": ""}, "a checkout that was on no branch"),
        ({"branch": "-x"}, "the branch in the install manifest is not a name the"),
    ],
)
def test_refuses_a_manifest_it_cannot_use(kit, change, reason):
    kit.edit_manifest(**change)
    rc, out, last = kit.update("plan")
    assert rc == 1 and last.startswith("Cannot update: ") and reason in last, out


def test_refuses_a_checkout_it_cannot_install_from(kit, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    kit.edit_manifest(checkout=str(plain))
    rc, out, last = kit.update("plan")
    assert rc == 1, out
    assert last == (
        "Cannot update: the folder this install was made from is not a git checkout."
    )
    (plain / ".git").mkdir()
    rc, out, last = kit.update("plan")
    assert rc == 1, out
    assert last == (
        "Cannot update: the checkout this install was made from has no "
        "scripts/install.sh."
    )


def test_refuses_without_a_manifest(kit):
    (kit.home / "pipelinekit" / "manifest.json").unlink()
    rc, out, last = kit.update("plan")
    assert rc == 1 and last.startswith("Cannot update: the install manifest is"), out


def test_origin_out_of_reach(kit):
    kit.git(kit.work, "remote", "set-url", "origin", str(kit.live / "gone.git"))
    rc, out, last = kit.update("plan")
    assert rc == 1 and last.startswith("Cannot update: origin could not be"), out


def test_subjects_are_single_cleaned_lines_and_capped(kit):
    for i in range(34):
        kit.push(f"feat: number {i}")
    kit.push("feat: colour \x1b[31mred\x1b[0m " + "long " * 60)
    rc, out, last = kit.update("plan")
    assert rc == 0 and "\x1b" not in out, out
    listed = [x for x in out.splitlines() if x.startswith("  ")]
    assert len(listed) == 31 and listed[-1] == "  and 5 more"
    assert all(len(x) <= 122 for x in listed)
    assert last.startswith("Update available: 35 commits. ")


SPLITS = "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"
STAYS = "\x9b", "\u202e", "\u200b", "\u2066", "\ufeff"


def test_no_character_in_a_subject_starts_a_new_line_or_hides(kit):
    for i, ch in enumerate(SPLITS + STAYS):
        kit.push(f"fix: number {i} before{ch}Up to date: after {i}")
    kit.push(b"fix: caf\xe9 in another encoding")
    rc, out, last = kit.update("plan")
    assert rc == 0, out
    listed = [x for x in out.splitlines() if x.startswith("  ")]
    assert len(listed) == len(SPLITS + STAYS) + 1, out
    assert sum("Up to date: after" in x for x in listed) == len(SPLITS + STAYS)
    assert any("fix: caf" in x for x in listed)
    assert not [ch for ch in out if not ch.isprintable() and ch != "\n"]
    assert last.startswith("Update available: 15 commits. ")


@pytest.mark.parametrize("checkout", ["", None, ".", "work"])
def test_a_checkout_that_is_no_full_path_is_never_the_current_directory(kit, checkout):
    kit.edit_manifest(checkout=checkout)
    new = kit.push()
    before = kit.installed()
    for args in (("plan",), ("apply", "--to", new)):
        p = subprocess.run(
            [sys.executable, str(kit.script), *args],
            capture_output=True,
            text=True,
            env=kit.env,
            cwd=kit.work if checkout != "work" else kit.live,
        )
        assert p.returncode == 1, p.stdout + p.stderr
        assert "the checkout this install was made from is not there" in p.stdout
    assert kit.git(kit.work, "rev-parse", "HEAD") != new
    assert not (kit.work / ".git" / "FETCH_HEAD").exists()
    assert kit.installed() == before


def test_an_install_that_went_in_but_fails_its_check_is_not_called_not_updated(kit):
    def open_guard(clone):
        guard = clone / "claude" / "hooks" / "bash-guard.py"
        guard.write_text("#!/usr/bin/env python3\nimport sys\n\nsys.exit(0)\n")

    old = kit.head()
    new = kit.push("feat: a guard that allows everything", open_guard)
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 1, out
    assert kit.manifest()["commit"] == new
    assert re.fullmatch(
        partly(old, new, "failed (exit 1)", r"\d+ problems?, run /kit"), last
    ), last
    assert BY_HAND.format(work=kit.work) in out.splitlines()


def test_an_installer_that_fails_after_its_work_is_not_called_a_clean_update(kit):
    def fail_late(clone):
        scripts = clone / "scripts"
        (scripts / "install.sh").rename(scripts / "install-real.sh")
        (scripts / "install.sh").write_text(
            '#!/bin/bash\nbash "$(dirname "$0")/install-real.sh" "$@"\nexit 7\n'
        )

    old = kit.head()
    new = kit.push("feat: an installer that fails at its end", fail_late)
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 1, out
    assert kit.manifest()["commit"] == new
    assert re.fullmatch(partly(old, new, "failed (exit 7)", "healthy"), last), last
    assert BY_HAND.format(work=kit.work) in out.splitlines()


def test_a_warning_in_the_new_install_is_not_called_healthy(kit, tmp_path):
    # The warning: the Bash sandbox is on while the kit denies the gh login
    # file. The self-check gives it only when gh is on PATH, so the test puts
    # one there instead of counting on the machine's (a sandboxed session may
    # not have it on PATH).
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/bin/sh\necho 'gh version 2.0.0 (test)'\n")
    (bin_dir / "gh").chmod(0o755)
    path = kit.home / "settings.json"
    settings = json.loads(path.read_text())
    settings["sandbox"] = {"enabled": True}
    path.write_text(json.dumps(settings, indent=2))
    old = kit.head()
    new = kit.push("feat: version nine", bump_version)
    rc, out, last = kit.update(
        "apply",
        "--to",
        new,
        env={"PATH": f"{bin_dir}{os.pathsep}{kit.env['PATH']}"},
    )
    assert rc == 0, out
    assert last == (
        f"Updated {old[:7]} -> {new[:7]}. Self-check: working, 1 warning, run /kit."
    )


def test_failed_installer_is_reported(kit):
    def break_installer(clone):
        (clone / "scripts" / "install.sh").write_text("#!/bin/sh\nexit 7\n")

    old = kit.head()
    new = kit.push("feat: broken installer", break_installer)
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 1, out
    assert kit.head() == new
    assert re.fullmatch(partly(old, new, "failed (exit 7)", ".+"), last), last
    # The command keeps what was chosen at install time and pastes as it is.
    assert BY_HAND.format(work=kit.work) in out.splitlines()


def test_an_installer_that_does_nothing_is_not_called_an_update(kit):
    def idle_installer(clone):
        (clone / "scripts" / "install.sh").write_text("#!/bin/sh\nexit 0\n")

    old = kit.head()
    new = kit.push("feat: an installer that does nothing", idle_installer)
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 1, out
    installer = f"exit 0, but the install manifest is not at {new[:7]}"
    assert re.fullmatch(partly(old, new, installer, ".+"), last), last
    assert BY_HAND.format(work=kit.work) in out.splitlines()


def test_a_self_check_that_does_not_run_is_not_called_an_update(kit):
    def check_without_json(clone):
        path = clone / "claude" / "skills" / "kit" / "check.py"
        text = path.read_text().replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nimport sys as _sys\n\n"
            'if _sys.argv[1:] == ["--json", "--no-remote"]:\n'
            "    raise SystemExit(3)\n",
            1,
        )
        path.write_text(text)

    old = kit.head()
    new = kit.push("feat: a check that cannot report", check_without_json)
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 1, out
    assert kit.manifest()["commit"] == new
    assert re.fullmatch(
        partly(old, new, "finished", re.escape("did not run (exit 3)")), last
    ), last
    assert BY_HAND.format(work=kit.work) in out.splitlines()


def test_a_check_py_that_does_not_load_says_how_to_recover(kit):
    def break_check(clone):
        path = clone / "claude" / "skills" / "kit" / "check.py"
        path.write_text(path.read_text() + "\ndef broken(:\n")

    def mend_check(clone):
        path = clone / "claude" / "skills" / "kit" / "check.py"
        path.write_text(path.read_text().replace("\ndef broken(:\n", ""))

    old = kit.head()
    broken = kit.push("feat: a check.py with a typo", break_check)
    rc, out, last = kit.update("apply", "--to", broken)
    assert rc == 1, out
    # The installer stops at the manifest, which it writes with check.py.
    did_not_run = re.escape("did not run (exit 1)")
    assert re.fullmatch(partly(old, broken, "failed (exit 1)", did_not_run), last), last
    by_hand = (
        f"By hand: git -C {kit.work} pull --ff-only origin main && "
        f"bash {kit.work}/scripts/install.sh --git-hooks --no-serena"
    )
    fixed = kit.push("fix: the typo", mend_check)
    for args, word in (
        (("plan",), "Cannot update"),
        (("apply", "--to", fixed), "Not updated"),
    ):
        rc, out, last = kit.update(*args)
        assert rc == 1, out
        assert re.fullmatch(
            rf"{word}: this install's check\.py could not be loaded "
            r"\(SyntaxError: .+\); run the By hand line: git pull --ff-only in "
            r"the checkout, then the installer\.",
            last,
        ), last
        assert by_hand in out.splitlines(), out
        assert kit.head() == broken
    # The line does what it says.
    p = subprocess.run(
        ["bash", "-c", by_hand.removeprefix("By hand: ")],
        capture_output=True,
        text=True,
        env=kit.env,
        stdin=subprocess.DEVNULL,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    rc, out, last = kit.update("plan")
    assert rc == 0 and last.startswith("Up to date: "), out
    assert kit.head() == fixed


def test_a_check_py_that_does_not_load_without_a_manifest(kit):
    path = kit.home / "skills" / "kit" / "check.py"
    path.write_text("raise SystemExit(2)\n")
    (kit.home / "pipelinekit" / "manifest.json").unlink()
    rc, out, last = kit.update("plan")
    assert rc == 1, out
    assert last == (
        "Cannot update: this install's check.py could not be loaded (SystemExit: 2); "
        "run git pull --ff-only in the checkout this install was made from, then "
        "its scripts/install.sh."
    )
    assert "By hand:" not in out


@pytest.mark.parametrize(
    "to", ["", "abc", "main", "g" * 40, "--help-me", "a" * 39, "a" * 41, "a" * 63]
)
def test_apply_wants_a_full_commit_id(kit, to):
    rc, out, _ = kit.update("apply", f"--to={to}")
    assert rc == 2, out
    assert out.strip() == (
        "Not updated: --to takes the full commit id the plan printed: 40 "
        "characters 0-9 and a-f (64 in a SHA-256 checkout)."
    ), out


def test_apply_wants_an_id_as_long_as_the_checkout_uses(kit):
    new = kit.push()
    before = kit.installed()
    rc, out, _ = kit.update("apply", "--to", new + "0" * 24)
    assert rc == 2, out
    assert out.strip() == (
        "Not updated: --to takes the full commit id the plan printed: 40 "
        "characters 0-9 and a-f."
    ), out
    assert kit.head() != new and kit.installed() == before
    assert not (kit.work / ".git" / "FETCH_HEAD").exists()


def test_a_refusal_names_ids_that_differ(kit):
    new = kit.push()
    other = new[:7] + ("0" if new[7] != "0" else "1") + new[8:]
    rc, out, last = kit.update("apply", "--to", other)
    assert rc == 1, out
    assert last == (
        f"Not updated: origin/main is at {new} now, not at {other}; run the plan again."
    )


def test_plan_gives_up_on_a_remote_that_does_not_answer(kit, monkeypatch, capsys):
    kit.git(kit.work, "config", "remote.origin.uploadpack", "sleep 30; git-upload-pack")
    for key in set(os.environ) - set(kit.env):
        monkeypatch.delenv(key)
    for key, value in kit.env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(update_py, "ANSWER_TIMEOUT", 1)
    started = time.monotonic()
    assert update_py.main(["plan"]) == 1
    assert time.monotonic() - started < 10
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == (
        "Cannot update: origin did not answer within 1 second; try again later."
    )


def test_usage_errors(kit):
    assert kit.update()[0] == 2
    assert kit.update("apply")[0] == 2
    assert kit.update("sideways")[0] == 2


def test_installer_options_keep_the_install_as_it_was(monkeypatch):
    args = update_py.installer_args
    monkeypatch.setattr(update_py.check, "git_value", lambda *a: "/h/git-hooks")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    kit = {"serena": True, "hooks_path": "/h/git-hooks"}
    assert args(kit, "/h") == ["--git-hooks"]
    assert args(dict(kit, serena=False), "/h") == ["--git-hooks", "--no-serena"]
    # A manifest from before the option was recorded: go by what is installed.
    assert args(dict(kit, serena=None), "/h") == ["--git-hooks", "--no-serena"]
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/serena")
    assert args(dict(kit, serena=None), "/h") == ["--git-hooks"]
    # The choice the manifest records counts, not what git says now ...
    assert args(dict(kit, hooks_path=""), "/h") == ["--no-git-hooks"]
    assert args(dict(kit, hooks_path="/other/hooks"), "/h") == ["--no-git-hooks"]
    home = os.path.expanduser("~/h")
    assert args(dict(kit, hooks_path="~/h/git-hooks"), home) == ["--git-hooks"]
    monkeypatch.setattr(update_py.check, "git_value", lambda *a: "")
    assert args(kit, "/h") == ["--git-hooks"]
    # ... and git only when the manifest has no record of it.
    assert args(dict(kit, hooks_path=None), "/h") == ["--no-git-hooks"]
    monkeypatch.setattr(update_py.check, "git_value", lambda *a: "/h/git-hooks")
    assert args(dict(kit, hooks_path=None), "/h") == ["--git-hooks"]
