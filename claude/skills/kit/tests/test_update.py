"""update.py: lists what origin has, and updates only to what it listed."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
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

    def update(self, *args):
        p = subprocess.run(
            [sys.executable, str(self.script), *args],
            capture_output=True,
            text=True,
            env=self.env,
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
        ({"branch": "-x"}, "a checkout that was on no branch"),
    ],
)
def test_refuses_a_manifest_it_cannot_use(kit, change, reason):
    kit.edit_manifest(**change)
    rc, out, last = kit.update("plan")
    assert rc == 1 and last.startswith("Cannot update: ") and reason in last, out


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
        rf"Partly updated {old[:7]} -> {new[:7]}: the installer failed \(exit 1\) "
        r"after it had replaced the files; its command is on the By hand line\. "
        r"Self-check: \d+ problems?, run /kit\.",
        last,
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
    assert last == (
        f"Partly updated {old[:7]} -> {new[:7]}: the installer failed (exit 7) "
        "after it had replaced the files; its command is on the By hand line. "
        "Self-check: healthy."
    )
    assert BY_HAND.format(work=kit.work) in out.splitlines()


def test_a_warning_in_the_new_install_is_not_called_healthy(kit):
    path = kit.home / "settings.json"
    settings = json.loads(path.read_text())
    settings["sandbox"] = {"enabled": True}
    path.write_text(json.dumps(settings, indent=2))
    old = kit.head()
    new = kit.push("feat: version nine", bump_version)
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 0, out
    assert last == (
        f"Updated {old[:7]} -> {new[:7]}. Self-check: working, 1 warning, run /kit."
    )


def test_failed_installer_is_reported(kit):
    def break_installer(clone):
        (clone / "scripts" / "install.sh").write_text("#!/bin/sh\nexit 7\n")

    new = kit.push("feat: broken installer", break_installer)
    rc, out, last = kit.update("apply", "--to", new)
    assert rc == 1, out
    assert last == (
        f"Not updated: the checkout is at {new[:7]} but the installer failed "
        "(exit 7) and may have replaced some files; its command is on the By "
        "hand line."
    )
    # The command keeps what was chosen at install time and pastes as it is.
    assert BY_HAND.format(work=kit.work) in out.splitlines()


@pytest.mark.parametrize(
    "to", ["", "abc", "main", "g" * 40, "--help-me", "a" * 39, "a" * 41, "a" * 63]
)
def test_apply_wants_a_full_commit_id(kit, to):
    rc, out, _ = kit.update("apply", f"--to={to}")
    assert rc == 2 and "full commit id" in out, out


def test_usage_errors(kit):
    assert kit.update()[0] == 2
    assert kit.update("apply")[0] == 2
    assert kit.update("sideways")[0] == 2


def test_installer_options_keep_the_install_as_it_was(monkeypatch):
    args = update_py.installer_args
    monkeypatch.setattr(update_py.check, "git_value", lambda *a: "/h/git-hooks")
    monkeypatch.setattr(update_py.shutil, "which", lambda name: None)
    assert args({"serena": True}, "/h") == ["--git-hooks"]
    assert args({"serena": False}, "/h") == ["--git-hooks", "--no-serena"]
    # A manifest from before the option was recorded: go by what is installed.
    assert args({"serena": None}, "/h") == ["--git-hooks", "--no-serena"]
    monkeypatch.setattr(update_py.shutil, "which", lambda name: "/bin/serena")
    assert args({"serena": None}, "/h") == ["--git-hooks"]
    monkeypatch.setattr(update_py.check, "git_value", lambda *a: "/other/hooks")
    assert args({"serena": True}, "/h") == ["--no-git-hooks"]
    monkeypatch.setattr(update_py.check, "git_value", lambda *a: "")
    assert args({"serena": True}, "/h") == ["--no-git-hooks"]
