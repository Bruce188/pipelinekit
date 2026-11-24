"""The never-stage check of the global pre-commit hook (bash-guard.py pre-commit).

Each case commits in a throwaway repository whose core.hooksPath is the kit's
claude/git-hooks, with gitleaks stubbed out, so only the kit's own checks
decide. The list is the repo's claude/config/never-stage.txt.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
KIT = HOOKS.parent
MARKER = "CONTENT-MARKER-91c2"  # file content that must never reach the log
RULE = "[pre-commit.never-stage]"


class Repo:
    def __init__(self, root: Path, env: dict, log: Path):
        self.root, self.env, self.log = root, env, log

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def write(self, rel: str, content: str = f"{MARKER}\n") -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def add(self, *args: str) -> None:
        p = self.git("add", *args)
        assert p.returncode == 0, p.stderr

    def commit(self, *args: str) -> subprocess.CompletedProcess:
        return self.git("commit", "-q", "-m", "feat: change", *args)

    def unchecked(self, rel: str) -> None:
        """A listed path committed before the hook held the list."""
        self.write(rel)
        self.add("-f", "--", rel)
        p = self.git("commit", "-q", "--no-verify", "-m", "chore: setup")
        assert p.returncode == 0, p.stderr

    def committed(self, rel: str) -> bool:
        return self.git("cat-file", "-e", f"HEAD:{rel}").returncode == 0

    def events(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


def make_repo(tmp_path: Path, kit: Path = KIT) -> Repo:
    stub = tmp_path / "stub"
    stub.mkdir()
    gitleaks = stub / "gitleaks"
    gitleaks.write_text('#!/bin/sh\n[ "$1" = version ] && echo 8.24.2\nexit 0\n')
    gitleaks.chmod(0o755)
    env = dict(
        os.environ,
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@e",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@e",
        PIPELINEKIT_STATE_DIR=str(tmp_path / "state"),
        PATH=f"{stub}{os.pathsep}{os.environ['PATH']}",
    )
    for k in ("PIPELINEKIT_LOG", "PIPELINEKIT_ALLOW_SECRET", "GIT_DIR"):
        env.pop(k, None)
    env.pop("GIT_INDEX_FILE", None)
    root = tmp_path / "repo"
    root.mkdir()
    r = Repo(root, env, tmp_path / "state" / "events.jsonl")
    assert r.git("init", "-q", "-b", "feat").returncode == 0
    hooks = str(kit / "git-hooks")
    assert r.git("config", "core.hooksPath", hooks).returncode == 0
    return r


def copied_kit(tmp_path: Path) -> Path:
    """The git hooks and the hooks they run, without config/."""
    kit = tmp_path / "kit"
    shutil.copytree(KIT / "git-hooks", kit / "git-hooks")
    (kit / "hooks").mkdir()
    for name in ("bash-guard.py", "kitlog.py", "filesize.py"):
        shutil.copy(HOOKS / name, kit / "hooks" / name)
    return kit


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return make_repo(tmp_path)


def refused(
    repo: Repo, p: subprocess.CompletedProcess, *paths: str, tracked: bool = False
) -> None:
    assert p.returncode != 0
    assert RULE in p.stderr
    assert "\nNext: " in "\n" + p.stderr
    for rel in paths:
        assert f"  {rel} (pattern " in p.stderr
        if tracked:  # the change stays out of HEAD
            assert repo.git("diff", "--quiet", "HEAD", "--", rel).returncode == 1
        else:
            assert not repo.committed(rel)
    events = [e for e in repo.events() if e["rule"] == "pre-commit.never-stage"]
    assert len(events) == 1
    assert events[0]["hook"] == "pre-commit" and events[0]["kind"] == "block"
    assert MARKER not in repo.log.read_text()


# ---------------------------------------------------------------- refused


def test_a_listed_path_is_refused_on_the_first_commit(repo):
    repo.write(".env")
    repo.write("src/app.py")
    repo.add("--", ".env", "src/app.py")
    p = repo.commit()
    refused(repo, p, ".env")
    assert "src/app.py" not in p.stderr
    assert "Next: git restore --staged -- .env" in p.stderr
    assert repo.git("rev-parse", "-q", "--verify", "HEAD").returncode != 0
    reason = repo.events()[0]["reason"]
    assert ".env" in reason and "'.env'" in reason


def test_a_forced_add_of_an_ignored_path_is_refused(repo):
    repo.write(".gitignore", "docs/loops/\n")
    repo.add(".gitignore")
    assert repo.commit().returncode == 0
    repo.write("docs/loops/x/state.json")
    assert repo.git("add", "docs/loops/x/state.json").returncode != 0  # ignored
    repo.add("-f", "docs/loops/x/state.json")
    p = repo.commit()
    refused(repo, p, "docs/loops/x/state.json")
    assert "pattern 'docs/loops/'" in p.stderr


def test_every_listed_path_is_named_and_the_log_counts_the_rest(repo):
    for rel in ("id_rsa", "deploy/site.pem", ".claude/settings.local.json"):
        repo.write(rel)
        repo.add("-f", "--", rel)
    p = repo.commit()
    refused(repo, p, "id_rsa", "deploy/site.pem", ".claude/settings.local.json")
    assert "2 more" in repo.events()[0]["reason"]


def test_commit_all_of_a_tracked_listed_path_is_refused(repo):
    repo.unchecked(".npmrc")
    repo.write(".npmrc", "changed\n")
    refused(repo, repo.commit("-a"), ".npmrc", tracked=True)


def test_commit_with_a_listed_pathspec_is_refused(repo):
    repo.unchecked("credentials.json")
    repo.write("credentials.json", "changed\n")
    refused(
        repo, repo.commit("--", "credentials.json"), "credentials.json", tracked=True
    )


def test_a_path_with_a_space_gets_a_quoted_next_command(repo):
    repo.write("keys/my site.key")
    repo.add("--", "keys/my site.key")
    p = repo.commit()
    refused(repo, p, "keys/my site.key")
    assert "Next: git restore --staged -- 'keys/my site.key'" in p.stderr


def test_a_refusal_leaves_no_bytecode_cache_beside_the_hooks(tmp_path):
    kit = copied_kit(tmp_path)
    shutil.copytree(KIT / "config", kit / "config")
    repo = make_repo(tmp_path, kit)
    repo.write(".env")
    repo.add(".env")
    refused(repo, repo.commit(), ".env")
    assert not (kit / "hooks" / "__pycache__").exists()


# ---------------------------------------------------------------- allowed


def test_a_commit_without_listed_paths_is_not_changed(repo):
    for rel in ("src/app.py", ".env.example", "id_rsa.pub", "docs/guide.md"):
        repo.write(rel)
        repo.add("--", rel)
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert p.stderr == ""
    assert repo.committed(".env.example") and repo.committed("id_rsa.pub")
    assert repo.events() == []


def test_removing_a_tracked_listed_path_is_allowed(repo):
    repo.unchecked(".env")
    repo.git("rm", "-q", "--cached", ".env")
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert not repo.committed(".env")


def test_an_untouched_tracked_listed_path_does_not_block_other_commits(repo):
    repo.unchecked(".env")
    repo.write("src/app.py")
    repo.add("src/app.py")
    p = repo.commit()
    assert p.returncode == 0, p.stderr


# ---------------------------------------------------------------- not checked


def test_a_missing_list_warns_and_lets_the_commit_through(tmp_path):
    repo = make_repo(tmp_path, copied_kit(tmp_path))
    repo.write(".env")
    repo.add(".env")
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "never-stage list missing" in p.stderr
    assert "[pre-commit.never-stage-failed]" in p.stderr
    rules = [(e["kind"], e["rule"]) for e in repo.events()]
    assert rules == [("error", "pre-commit.never-stage-failed")]
