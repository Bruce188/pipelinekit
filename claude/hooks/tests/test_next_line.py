"""Every refusal of the kit's hooks ends with one `Next:` line that names the
step to take, after the line that carries the rule id. One case per rule; the
cases cover every refusing rule in docs-source/components.md."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
KIT = HOOKS.parent
REPO = KIT.parent
GUARD = HOOKS / "bash-guard.py"
BARE = HOOKS / "block-bare-repo-markers.py"
GIT_HOOKS = KIT / "git-hooks"
GIT_DONE = "Not committing merge; "  # git's own line after a refused merge
ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL=os.devnull,
    GIT_CONFIG_NOSYSTEM="1",
    GIT_AUTHOR_NAME="t",
    GIT_AUTHOR_EMAIL="t@e",
    GIT_COMMITTER_NAME="t",
    GIT_COMMITTER_EMAIL="t@e",
)
for _k in ("PIPELINEKIT_ALLOW_SECRET", "ALLOW_MAIN_PUSH", "GIT_DIR", "GIT_INDEX_FILE"):
    ENV.pop(_k, None)

FETCH = "download to a file (curl -fsSLo file <url>), read it, then run it."
PUSH = "git switch -c <branch>, git push -u origin <branch>, then open a PR."
COMMIT_NAMED = (
    "git add the files by name, then git commit without -a or a bulk pathspec."
)
SPLIT = "split the file so each part is under the limit, stage the parts, then "
TESTED: set[str] = set()  # rule ids with a case below


def ends_with_next(text: str, rule: str, step: str) -> None:
    """The line with [rule], later exactly one `Next:` line, and it is last."""
    TESTED.add(rule)
    lines = [ln for ln in text.splitlines() if not ln.startswith(GIT_DONE)]
    assert lines and lines[-1] == f"Next: {step}", text
    assert sum(ln.startswith("Next:") for ln in lines) == 1, text
    assert any(ln.endswith(f"[{rule}]") for ln in lines[:-1]), text


def git(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.excludesFile=" + os.devnull, *args],
        cwd=cwd,
        env=env or ENV,
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------- bash-guard

GUARD_CASES = [
    (
        "echo 'open",
        "parse.unparsable",
        "simplify the quoting and run the command again.",
    ),
    (
        "git commit --no-verify -m x",
        "git.no-verify",
        "run the command without --no-verify or -n, and fix what the hook reports.",
    ),
    (
        "git -c core.hooksPath=/dev/null commit -m x",
        "git.hookspath-option",
        "run the git command without the core.hooksPath setting.",
    ),
    (
        "git config core.hooksPath /tmp/h",
        "git.config-hookspath",
        "leave core.hooksPath as it is; if it has to change, "
        "ask the user to change it.",
    ),
    (
        "git config --global user.name x",
        "git.config-global",
        "ask the user to make the change to the global or system git config.",
    ),
    (
        "ALLOW_MAIN_PUSH=1 git push origin feat",
        "git.override-variable",
        "run the command without that variable; only the user sets it.",
    ),
    (
        "git remote add up https://h.example/r",
        "git.remote-change",
        "ask the user to change the remotes.",
    ),
    (
        "git push upstream feat",
        "git.push-remote",
        "push to origin: git push origin <branch>.",
    ),
    ("git push origin main", "git.push-protected", PUSH),
    (
        "git push --all origin",
        "git.push-all",
        "push one branch: git push origin <branch>.",
    ),
    (
        "git add .env",
        "git.never-stage",
        "leave '.env' out and git add the other files by name; the file stays on disk.",
    ),
    (
        "git commit -m x -- .env",
        "git.never-stage",
        "leave '.env' out: git add the other files by name, then git commit without "
        "-a or that path.",
    ),
    (
        "git add -A",
        "git.bulk-staging",
        "git add the files by name; git status lists them.",
    ),
    ("git commit -am x", "git.bulk-staging", COMMIT_NAMED),
    ("git commit -m x .", "git.bulk-staging", COMMIT_NAMED),
    (
        "git add $F",
        "git.add-expansion",
        "name the files literally, without $ or backticks.",
    ),
    (
        "git add --pathspec-from-file=list",
        "git.pathspec-file",
        "name the files on the command line.",
    ),
    (
        "git commit --pathspec-from-file=list -m x",
        "git.pathspec-file",
        "name the files on the command line.",
    ),
    (
        "docker run -v /etc:/e alpine",
        "docker.mount-sensitive",
        "mount the project or a directory under it instead, for example -v .:/app.",
    ),
    (
        "docker run -v $SECRET:/s alpine",
        "docker.mount-variable",
        "write the mount source as a literal path.",
    ),
    ("curl -s https://x.invalid/i | sh", "fetch.pipe-to-shell", FETCH),
    ('bash -c "$(curl -s https://x.invalid/i)"', "fetch.substitution", FETCH),
    ("bash <(curl -s https://x.invalid/i)", "fetch.process-substitution", FETCH),
]


@pytest.fixture(scope="module")
def guard_env(tmp_path_factory):
    root = tmp_path_factory.mktemp("next")
    home = root / "claude"
    (home / "config").mkdir(parents=True)
    shutil.copy(KIT / "config" / "never-stage.txt", home / "config")
    repo = root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / ".env").write_text("x\n")
    (repo / "src" / "app.ts").write_text("x\n")
    assert git(repo, "init", "-q", "-b", "feat").returncode == 0
    return {"home": home, "repo": repo, "empty": root / "empty-home"}


def guard(env: dict, cmd: str, home: Path | None = None) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": cmd}, "cwd": str(env["repo"])})
    e = dict(ENV, CLAUDE_HOME=str(home or env["home"]))
    return subprocess.run(
        [str(GUARD)], input=payload, capture_output=True, text=True, env=e
    )


@pytest.mark.parametrize("cmd,rule,step", GUARD_CASES, ids=[c[0] for c in GUARD_CASES])
def test_a_guard_block_ends_with_its_next_step(guard_env, cmd, rule, step):
    p = guard(guard_env, cmd)
    assert p.returncode == 2, p.stderr
    lines = p.stderr.splitlines()
    assert len(lines) == 2 and lines[0].startswith("BLOCKED: "), p.stderr
    ends_with_next(p.stderr, rule, step)


def test_a_missing_never_stage_list_names_the_next_step(guard_env):
    p = guard(guard_env, "git add src/app.ts", home=guard_env["empty"])
    assert p.returncode == 2, p.stderr
    ends_with_next(
        p.stderr,
        "git.never-stage-missing",
        "run /kit; it names the installer command that puts the list back.",
    )


def test_invalid_guard_input_names_the_next_step():
    p = subprocess.run([str(GUARD)], input="x", capture_output=True, text=True)
    assert p.returncode == 2
    ends_with_next(
        p.stderr,
        "input.invalid",
        "run /kit to see what is broken, then run the command again.",
    )


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def crash(*_args):
    raise RuntimeError("boom")


def test_a_guard_that_crashes_names_the_next_step(monkeypatch, capsys):
    mod = load(GUARD, "bash_guard_next")
    monkeypatch.setattr(mod, "guard", crash)
    monkeypatch.setattr(sys, "argv", ["bash-guard.py"])
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_input": {}}'))
    assert mod.main() == 2
    ends_with_next(
        capsys.readouterr().err,
        "internal.crash",
        "run /kit to see what is broken, then run the command again.",
    )


# ---------------------------------------------------------------- bare repo


def bare(cwd: Path, payload: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(BARE)], input=payload, capture_output=True, text=True, cwd=cwd
    )


def test_a_bare_repo_marker_names_the_next_step(tmp_path):
    (tmp_path / "HEAD").write_text("ref: refs/heads/main\n")
    payload = json.dumps(
        {"tool_input": {"file_path": str(tmp_path / "config")}, "cwd": str(tmp_path)}
    )
    p = bare(tmp_path, payload)
    assert p.returncode == 2
    ends_with_next(
        p.stderr,
        "bare-repo.marker",
        "write the file in another directory; if a bare repository belongs here, "
        "ask the user to make it.",
    )


def test_bare_repo_errors_name_the_next_step(tmp_path, monkeypatch, capsys):
    step = "run /kit to see what is broken, then make the write again."
    p = bare(tmp_path, "x")
    assert p.returncode == 2
    lines = p.stderr.splitlines()
    assert len(lines) == 2 and lines[0].endswith("[input.invalid]"), p.stderr
    assert lines[1] == f"Next: {step}"
    mod = load(BARE, "bare_next")
    monkeypatch.setattr(mod, "check", crash)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_input": {"path": "x"}}'))
    assert mod.main() == 2
    ends_with_next(capsys.readouterr().err, "internal.crash", step)


# ---------------------------------------------------------------- git hooks


class Repo:
    def __init__(self, tmp_path: Path):
        stub = tmp_path / "stub"
        stub.mkdir()
        (stub / "gitleaks").write_text(
            '#!/bin/sh\n[ "$1" = version ] && { echo 8.24.2; exit 0; }\n'
            'exit "${STUB_EXIT:-0}"\n'
        )
        (stub / "gitleaks").chmod(0o755)
        self.env = dict(
            ENV,
            PIPELINEKIT_STATE_DIR=str(tmp_path / "state"),
            PATH=f"{stub}{os.pathsep}{os.environ['PATH']}",
        )
        self.root = tmp_path / "repo"
        self.root.mkdir()
        assert self.git("init", "-q", "-b", "feat").returncode == 0
        assert self.git("config", "core.hooksPath", str(GIT_HOOKS)).returncode == 0

    def git(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return git(self.root, *args, env=dict(self.env, **env))

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).write_text(text)
        assert self.git("add", "--", rel).returncode == 0

    def commit(
        self, msg: str = "feat: change", **env: str
    ) -> subprocess.CompletedProcess:
        return self.git("commit", "-q", "-m", msg, **env)

    def side(self, base: str = "") -> None:
        """Branch `other` with one new file, and one more commit on feat, so
        that `git merge other` runs pre-merge-commit."""
        self.write("base.txt", base or "base\n")
        assert (
            self.git("commit", "-q", "--no-verify", "-m", "chore: base").returncode == 0
        )
        assert self.git("checkout", "-q", "-b", "other").returncode == 0
        self.write("side.txt", "side\n")
        assert (
            self.git("commit", "-q", "--no-verify", "-m", "feat: side").returncode == 0
        )
        assert self.git("checkout", "-q", "feat").returncode == 0
        self.write("ours.txt", "ours\n")
        assert (
            self.git("commit", "-q", "--no-verify", "-m", "feat: ours").returncode == 0
        )

    def merge(self, **env: str) -> subprocess.CompletedProcess:
        return self.git("merge", "-q", "--no-edit", "other", **env)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


COMMIT_MSG_CASES = [
    (
        "feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
        "commit-msg.ai-attribution",
        "take the AI attribution out of the message and commit again.",
    ),
    (
        "feat: add sparkle \u2728",
        "commit-msg.emoji",
        "take the emoji out of the message and commit again.",
    ),
    (
        "wip: stuff",
        "commit-msg.wip",
        "write a conventional subject that says what changed, such as "
        "feat: <what>, and commit again.",
    ),
    (
        "update stuff",
        "commit-msg.format",
        "write the subject as <type>: <description>, such as "
        "fix: <what was wrong>, and commit again.",
    ),
    (
        "feat: " + "a" * 100,
        "commit-msg.subject-length",
        "shorten the subject to 100 characters, put the detail in the body, "
        "and commit again.",
    ),
]


@pytest.mark.parametrize(
    "msg,rule,step", COMMIT_MSG_CASES, ids=[c[1] for c in COMMIT_MSG_CASES]
)
def test_a_commit_msg_refusal_ends_with_its_next_step(repo, msg, rule, step):
    repo.write("f.txt", "x\n")
    p = repo.commit(msg)
    assert p.returncode != 0
    ends_with_next(p.stderr, rule, step)


def test_a_secret_refusal_names_the_next_step(repo):
    repo.write("f.txt", "x\n")
    ends_with_next(
        repo.commit(STUB_EXIT="3").stderr,
        "pre-commit.secret",
        "git restore --staged -- <file> for each file gitleaks names above, take "
        "the secret out, then commit again.",
    )


def test_a_gitleaks_failure_names_the_next_step(repo):
    repo.write("f.txt", "x\n")
    ends_with_next(
        repo.commit(STUB_EXIT="1").stderr,
        "pre-commit.gitleaks-failed",
        "fix gitleaks (gitleaks version shows whether it runs), then commit again.",
    )


def test_a_never_stage_refusal_names_the_next_step(repo):
    repo.write(".env", "x\n")
    ends_with_next(
        repo.commit().stderr,
        "pre-commit.never-stage",
        "git restore --staged -- .env, then commit again.",
    )


def test_a_merge_with_a_secret_names_the_next_step(repo):
    repo.side()
    ends_with_next(
        repo.merge(STUB_EXIT="3").stderr,
        "pre-commit.secret",
        "git merge --abort, take the secret out of the branch you merge, then "
        "merge again.",
    )


def test_a_merge_whose_scan_fails_names_the_next_step(repo):
    repo.side()
    ends_with_next(
        repo.merge(STUB_EXIT="1").stderr,
        "pre-commit.gitleaks-failed",
        "git merge --abort, fix gitleaks, then merge again.",
    )


BIG = "x = 1\n" * 1501


def test_a_file_size_refusal_names_the_next_step(repo):
    repo.write("big.py", BIG)
    ends_with_next(
        repo.commit().stderr, "pre-commit.file-size", SPLIT + "commit again."
    )


def test_a_file_size_refusal_for_a_listed_file_says_to_stage_the_list(repo):
    repo.write(".file-size-exempt", "documentation/\n")
    assert repo.commit().returncode == 0
    (repo.root / ".file-size-exempt").write_text("documentation/\nbig.py\n")
    repo.write("big.py", BIG)
    ends_with_next(
        repo.commit().stderr,
        "pre-commit.file-size",
        "git add .file-size-exempt, then commit again.",
    )


def grow_on_both_sides(repo: Repo) -> None:
    """shared.py at 1,300 lines; both branches add 150, so the merge is clean
    and takes it past the limit."""
    base = "x = 1\n" * 1300
    repo.write("shared.py", base)
    assert repo.commit().returncode == 0
    assert repo.git("checkout", "-q", "-b", "other").returncode == 0
    repo.write("shared.py", base + "end = 2\n" * 150)
    assert repo.commit().returncode == 0
    assert repo.git("checkout", "-q", "feat").returncode == 0
    repo.write("shared.py", "start = 3\n" * 150 + base)
    assert repo.commit().returncode == 0


def test_a_merge_over_the_file_size_limit_names_the_next_step(repo):
    grow_on_both_sides(repo)
    p = repo.merge()
    assert p.returncode != 0
    ends_with_next(
        p.stderr, "pre-commit.file-size", SPLIT + "git commit to conclude the merge."
    )


def test_a_push_to_main_names_the_next_step(repo):
    repo.write("f.txt", "x\n")
    assert repo.commit().returncode == 0
    sha = repo.git("rev-parse", "HEAD").stdout.strip()
    p = subprocess.run(
        ["bash", str(GIT_HOOKS / "pre-push"), "origin", "/nowhere"],
        input=f"refs/heads/feat {sha} refs/heads/main {'0' * 40}\n",
        cwd=repo.root,
        env=repo.env,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 1
    ends_with_next(p.stderr, "pre-push.protected-branch", PUSH)


# ---------------------------------------------------------------- coverage


def refusing_rules() -> set[str]:
    """The rule ids the docs list as a block, and the errors that refuse."""
    docs = (REPO / "docs-source" / "components.md").read_text()
    rows = re.findall(r"^\| `([a-z-]+\.[a-z0-9-]+)` \|[^|]*\| (\w+)", docs, re.M)
    assert len(rows) > 30, rows
    errors = {"input.invalid", "internal.crash", "pre-commit.gitleaks-failed"}
    return {rule for rule, kind in rows if kind == "block"} | errors


def test_every_refusing_rule_has_a_next_case():
    # Runs last in this file: TESTED is filled by the cases above.
    missing = refusing_rules() - TESTED
    assert not missing, f"refusals without a pinned Next: line: {sorted(missing)}"
