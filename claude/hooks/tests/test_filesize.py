"""The file size limit of the global pre-commit hook (claude/hooks/filesize.py).

Each case commits in a throwaway repository whose core.hooksPath is the kit's
claude/git-hooks, with gitleaks stubbed out so only the size check decides.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
GIT_HOOKS = HOOKS.parent / "git-hooks"
REPO = HOOKS.parents[1]
sys.path.insert(0, str(HOOKS))
import filesize  # noqa: E402

LINE = "value = 1\n"  # 10 bytes
MARKER = "CONTENT-MARKER-7f3a"  # file content that must never reach the log
LIMIT = "1,500 lines and 50,000 bytes"


def text(n: int, line: str = LINE) -> str:
    return f"# {MARKER}\n" + line * (n - 1)


class Repo:
    def __init__(self, root: Path, env: dict, log: Path):
        self.root, self.env, self.log = root, env, log

    def git(self, *args: str, env: dict | None = None):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            env=env or self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def write(self, rel: str, content: str | bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        assert self.git("add", "--", rel).returncode == 0

    def commit(self, msg: str = "feat: change", **env: str):
        return self.git("commit", "-q", "-m", msg, env=dict(self.env, **env))

    def commit_unchecked(self, msg: str = "chore: setup") -> None:
        """A commit made before the limit existed."""
        assert self.git("commit", "-q", "--no-verify", "-m", msg).returncode == 0

    def committed(self, rel: str) -> bool:
        return self.git("cat-file", "-e", f"HEAD:{rel}").returncode == 0

    def events(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


def make_repo(tmp_path: Path, hooks: Path = GIT_HOOKS) -> Repo:
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
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
    for k in (
        "PIPELINEKIT_LOG",
        "PIPELINEKIT_ALLOW_SECRET",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "PYTHONDONTWRITEBYTECODE",
    ):
        env.pop(k, None)
    root = tmp_path / "repo"
    root.mkdir()
    r = Repo(root, env, tmp_path / "state" / "events.jsonl")
    assert r.git("init", "-q", "-b", "feat").returncode == 0
    assert r.git("config", "core.hooksPath", str(hooks)).returncode == 0
    return r


def copy_never_stage(kit: Path) -> None:
    """The never-stage list beside a copied kit, for pre-commit's first check."""
    (kit / "config").mkdir()
    shutil.copy(HOOKS.parent / "config" / "never-stage.txt", kit / "config")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return make_repo(tmp_path)


# ---------------------------------------------------------------- refused


def test_a_new_file_over_the_line_limit_is_refused(repo):
    repo.write("src/big.py", text(1501))
    p = repo.commit()
    assert p.returncode != 0
    assert not repo.committed("src/big.py")
    assert "src/big.py: 1,501 lines, 15,022 bytes (new file)" in p.stderr
    assert LIMIT in p.stderr and "[pre-commit.file-size]" in p.stderr


def test_the_whole_refusal(repo):
    repo.write("src/big.py", text(1501))
    p = repo.commit()
    assert p.returncode != 0
    assert p.stderr.splitlines() == [
        f"pre-commit: commit refused, over the file size limit of {LIMIT}:",
        "  src/big.py: 1,501 lines, 15,022 bytes (new file)",
        "Split the file: new code that would take a file past the limit goes in "
        "a new file. A generated, vendored or data file can be listed in "
        ".file-size-exempt at the top of the repository, one pattern per line. "
        "[pre-commit.file-size]",
        "Next: split the file so each part is under the limit, stage the parts, "
        "then commit again.",
    ]


def test_a_path_with_control_characters_is_shown_on_one_line(repo):
    repo.write("odd\nname\x1b[31m.py", text(1501))
    p = repo.commit()
    assert p.returncode != 0
    assert "  odd?name?[31m.py: 1,501 lines, 15,022 bytes (new file)" in p.stderr
    assert "\x1b" not in p.stderr


def commit_not_utf8(repo) -> tuple[int, str]:
    """Stage a file named caf\xe9.py over the limit and commit it."""
    (repo.root / os.fsdecode(b"caf\xe9.py")).write_text(text(1501))
    assert repo.git("add", "-A").returncode == 0
    p = subprocess.run(
        ["git", "commit", "-q", "-m", "feat: change"],
        cwd=repo.root,
        env=repo.env,
        capture_output=True,
        check=False,
    )
    return p.returncode, p.stderr.decode("utf-8", "replace")


NOT_UTF8 = "  caf\\udce9.py: 1,501 lines, 15,022 bytes (new file)"


def test_a_path_that_is_not_utf8_is_refused_and_shown(repo):
    rc, err = commit_not_utf8(repo)
    assert rc != 0, err
    assert NOT_UTF8 in err.splitlines()
    assert "file size check failed" not in err
    (e,) = repo.events()
    assert (e["kind"], e["rule"]) == ("block", "pre-commit.file-size")


def test_a_merge_with_a_path_that_is_not_utf8_is_refused(repo):
    repo.write("base.py", text(10))
    repo.commit_unchecked()
    other = branch_commit(repo, "side.py", text(10))
    (repo.root / ".git" / "MERGE_HEAD").write_text(other + "\n")
    rc, err = commit_not_utf8(repo)
    assert rc != 0, err
    assert NOT_UTF8 in err.splitlines()
    assert "file size check failed" not in err


def test_a_unicode_path_on_an_ascii_terminal_is_refused(repo):
    repo.write("café.py", text(1501))
    p = repo.commit(PYTHONIOENCODING="ascii")
    assert p.returncode != 0, p.stderr
    assert "  caf\\xe9.py: 1,501 lines, 15,022 bytes (new file)" in p.stderr


def test_a_new_file_over_the_byte_limit_is_refused(repo):
    repo.write("wide.md", text(20, "y" * 2999 + "\n"))
    p = repo.commit()
    assert p.returncode != 0
    assert "wide.md: 20 lines, 57,022 bytes (new file)" in p.stderr


def test_the_refusal_is_logged_with_its_rule_and_without_content(repo):
    repo.write("src/big.py", text(1501))
    repo.write("src/other.py", text(1600))
    assert repo.commit().returncode != 0
    (e,) = repo.events()
    assert (e["hook"], e["kind"], e["rule"]) == (
        "pre-commit",
        "block",
        "pre-commit.file-size",
    )
    assert "src/big.py: 1501 lines, 15022 bytes" in e["reason"]
    assert "limit 1500 lines, 50000 bytes" in e["reason"]
    assert "1 more file(s)" in e["reason"]
    assert MARKER not in repo.log.read_text()


def test_a_file_that_crosses_the_limit_is_refused(repo):
    repo.write("app.py", text(1400))
    assert repo.commit().returncode == 0
    repo.write("app.py", text(1501))
    p = repo.commit()
    assert p.returncode != 0
    assert (
        "app.py: 1,501 lines, 15,022 bytes (was 1,400 lines, 14,012 bytes)" in p.stderr
    )
    assert repo.events()[0]["rule"] == "pre-commit.file-size"


def test_a_file_that_grows_past_only_the_byte_limit_is_refused(repo):
    repo.write("notes.md", text(10, "z" * 4000 + "\n"))
    assert repo.commit().returncode == 0
    repo.write("notes.md", text(14, "z" * 4000 + "\n"))
    p = repo.commit()
    assert p.returncode != 0
    lines = p.stderr.splitlines()
    assert "  notes.md: 14 lines, 52,035 bytes (was 10 lines, 36,031 bytes)" in lines
    assert lines[-2].endswith("[pre-commit.file-size]")
    assert lines[-1].startswith("Next: split the file ")


def test_a_file_at_the_limit_passes(repo):
    repo.write("lines.py", text(1500))
    repo.write("bytes.md", "a" * 49_999 + "\n")
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "size limit" not in p.stderr
    assert repo.events() == []


def test_the_first_commit_of_a_repository_is_checked(repo):
    repo.write("big.py", text(2000))
    assert repo.git("rev-parse", "-q", "--verify", "HEAD").returncode != 0
    p = repo.commit()
    assert p.returncode != 0
    assert "  big.py: 2,000 lines, 20,012 bytes (new file)" in p.stderr.splitlines()
    (e,) = repo.events()
    assert (e["kind"], e["rule"]) == ("block", "pre-commit.file-size")


def test_a_new_copy_of_a_file_already_over_is_refused(repo):
    repo.write("old.py", text(1600))
    repo.commit_unchecked()
    repo.write("copy.py", text(1600))
    p = repo.commit()
    assert p.returncode != 0 and "copy.py" in p.stderr


def test_a_refusal_leaves_no_bytecode_cache_beside_the_hooks(tmp_path):
    kit = tmp_path / "kit"
    shutil.copytree(GIT_HOOKS, kit / "git-hooks")
    (kit / "hooks").mkdir()
    for name in ("filesize.py", "kitlog.py", "bash-guard.py"):
        shutil.copy(HOOKS / name, kit / "hooks" / name)
    copy_never_stage(kit)
    repo = make_repo(tmp_path, kit / "git-hooks")
    repo.write("big.py", text(2000))
    assert repo.commit().returncode != 0
    assert len(repo.events()) == 1
    assert not (kit / "hooks" / "__pycache__").exists()


@pytest.mark.parametrize("how", [["-a"], ["--", "app.py"]])
def test_a_commit_from_a_temporary_index_is_checked(repo, how):
    repo.write("app.py", text(10))
    assert repo.commit().returncode == 0
    (repo.root / "app.py").write_text(text(1501))
    p = repo.git("commit", "-q", "-m", "feat: change", *how)
    assert p.returncode != 0, p.stderr
    line = "  app.py: 1,501 lines, 15,022 bytes (was 10 lines, 112 bytes)"
    assert line in p.stderr.splitlines()
    assert repo.git("show", "HEAD:app.py").stdout == text(10)


def test_a_large_binary_is_never_read_whole(repo, monkeypatch):
    repo.write("blob.bin", b"\0" + b"x" * 3_000_000)
    repo.write("small.py", text(10))
    big = repo.git("rev-parse", ":blob.bin").stdout.strip()
    read = []
    real = filesize.read_sizes
    monkeypatch.setattr(filesize, "read_sizes", lambda n: read.extend(n) or real(n))
    monkeypatch.chdir(repo.root)
    for k in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        monkeypatch.delenv(k, raising=False)
    assert filesize.findings() == ([], [], [])
    assert big not in read
    p = repo.commit()
    assert p.returncode == 0 and p.stderr == ""


def test_a_large_text_file_is_counted_whole(repo):
    repo.write("huge.md", ("y" * 99 + "\n") * 30_000)
    p = repo.commit()
    assert p.returncode != 0
    line = "  huge.md: 30,000 lines, 3,000,000 bytes (new file)"
    assert line in p.stderr.splitlines()


def blobs(repo, tmp_path, contents: list[bytes]) -> list[str]:
    folder = tmp_path / "blobs"
    folder.mkdir()
    files = []
    for i, data in enumerate(contents):
        (folder / str(i)).write_bytes(data)
        files.append(str(folder / str(i)))
    p = subprocess.run(
        ["git", "hash-object", "-w", "--stdin-paths"],
        cwd=repo.root,
        env=repo.env,
        input="\n".join(files),
        capture_output=True,
        text=True,
        check=True,
    )
    return p.stdout.split()


def in_repo(repo, monkeypatch) -> None:
    monkeypatch.chdir(repo.root)
    for k in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        monkeypatch.delenv(k, raising=False)


def test_many_blobs_read_in_one_batch_are_measured_like_measure(
    repo, tmp_path, monkeypatch
):
    contents = []
    for i in range(2500):
        data = f"line {i}\n".encode() * (i % 13) + b"tail" * (i % 3)
        if i % 17 == 0:
            data = b"\0" + data
        if i % 500 == 0:
            data += b"x\n" * 30_000  # over MAX_BYTES: read in pieces
        contents.append(data)
    names = blobs(repo, tmp_path, contents)
    in_repo(repo, monkeypatch)
    assert filesize.sizes(names) == [filesize.measure(c) for c in contents]


def test_a_blob_too_small_to_be_over_is_never_read(repo, tmp_path, monkeypatch):
    (small,) = blobs(repo, tmp_path, [b"a\n" * 700])
    in_repo(repo, monkeypatch)
    read = []
    real = filesize.read_sizes
    monkeypatch.setattr(filesize, "read_sizes", lambda n: read.extend(n) or real(n))
    assert filesize.sizes([small], floor=filesize.MAX_LINES) == [(0, 1400)]
    assert read == []


def test_a_binary_stream_is_dropped_after_its_first_bytes():
    f = io.BytesIO(b"x" * 100 + b"\0" + b"x" * 1_000_000)
    assert filesize.count(f) is None
    assert f.tell() == filesize.BINARY_PEEK


@pytest.mark.parametrize(
    "data",
    [b"", b"a", b"a\nb", b"a\nb\n", b"y" * 100_000 + b"\nz", b"\n" * 9000],
    ids=["empty", "one-line", "no-last-newline", "two-lines", "long", "newlines"],
)
def test_a_text_stream_is_counted_like_a_blob(data):
    assert filesize.count(io.BytesIO(data)) == filesize.measure(data)


def test_the_refusal_stands_with_the_log_switched_off(repo):
    repo.write("big.py", text(1501))
    assert repo.commit(PIPELINEKIT_LOG="0").returncode != 0
    assert repo.events() == []


# ---------------------------------------------------------------- already over


def test_a_file_already_over_the_limit_only_warns(repo):
    repo.write("legacy.py", text(1600))
    repo.commit_unchecked()
    repo.write("legacy.py", text(1700))
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert repo.git("show", "HEAD:legacy.py").stdout.count("\n") == 1700
    assert p.stderr.splitlines() == [
        f"pre-commit: warning: legacy.py is 1,700 lines, 17,012 bytes, over the "
        f"file size limit of {LIMIT}. It was over the limit before this commit, "
        "so the commit goes on. New code goes in a new file; split this one only "
        "when asked. [pre-commit.file-size-over]"
    ]
    assert repo.events() == []


def test_a_file_already_over_that_shrinks_but_stays_over_only_warns(repo):
    repo.write("legacy.py", text(1900))
    repo.commit_unchecked()
    repo.write("legacy.py", text(1600))
    p = repo.commit()
    assert p.returncode == 0 and "[pre-commit.file-size-over]" in p.stderr


def test_a_renamed_file_keeps_the_size_it_had(repo):
    repo.write("old_name.py", text(1600))
    repo.commit_unchecked()
    assert repo.git("mv", "old_name.py", "new_name.py").returncode == 0
    repo.write("new_name.py", text(1610))
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "warning: new_name.py" in p.stderr


def branch_commit(repo, rel: str, content: str) -> str:
    """Commit rel on a new branch "other" and return to feat; the commit id."""
    assert repo.git("checkout", "-q", "-b", "other").returncode == 0
    repo.write(rel, content)
    repo.commit_unchecked("feat: change on the other branch")
    other = repo.git("rev-parse", "HEAD").stdout.strip()
    assert repo.git("checkout", "-q", "feat").returncode == 0
    return other


def test_concluding_a_merge_warns_for_a_file_over_in_the_other_parent(repo):
    repo.write("shared.py", text(1000))
    repo.commit_unchecked()
    other = branch_commit(repo, "shared.py", text(1600))
    repo.write("shared.py", text(1650))
    (repo.root / ".git" / "MERGE_HEAD").write_text(other + "\n")
    p = repo.commit("feat: merge other")
    assert p.returncode == 0, p.stderr
    assert "warning: shared.py" in p.stderr


def test_a_new_file_named_like_an_object_in_a_merge_is_a_new_file(repo):
    repo.write("legacy.py", text(1600))
    repo.commit_unchecked()
    blob = repo.git("rev-parse", "HEAD:legacy.py").stdout.strip()
    other = branch_commit(repo, "side.py", text(10))
    (repo.root / ".git" / "MERGE_HEAD").write_text(other + "\n")
    name = f"new-g{blob[:7]}"
    repo.write(name, text(2000))
    p = repo.commit("feat: merge other")
    assert p.returncode != 0, p.stderr
    assert f"  {name}: 2,000 lines, 20,012 bytes (new file)" in p.stderr.splitlines()


def grow_on_both_sides(repo, ours: int, theirs: int) -> None:
    """shared.py starts at 1,300 lines; the branch "other" adds `theirs` lines
    at its end and feat adds `ours` at its start, so the two merge cleanly."""
    repo.write("shared.py", text(1300))
    assert repo.commit().returncode == 0
    branch_commit(repo, "shared.py", text(1300) + "end = 2\n" * theirs)
    repo.write("shared.py", "start = 3\n" * ours + text(1300))
    assert repo.commit().returncode == 0


def merge(repo):
    return repo.git("merge", "-q", "--no-edit", "other")


def test_a_clean_merge_that_takes_a_file_past_the_limit_is_refused(repo):
    grow_on_both_sides(repo, 150, 150)
    p = merge(repo)
    assert p.returncode != 0
    lines = p.stderr.splitlines()
    assert (
        f"pre-merge-commit: merge refused, over the file size limit of {LIMIT}:"
    ) in lines
    assert any(x.endswith(" [pre-commit.file-size]") for x in lines)
    line = "  shared.py: 1,600 lines, 15,712 bytes (was 1,450 lines, 14,512 bytes)"
    assert line in lines
    assert repo.git("rev-parse", "-q", "--verify", "HEAD^2").returncode != 0
    (e,) = repo.events()
    assert (e["hook"], e["kind"], e["rule"]) == (
        "pre-merge-commit",
        "block",
        "pre-commit.file-size",
    )
    assert MARKER not in repo.log.read_text()
    # The merge is left for git commit, whose pre-commit refuses it again.
    assert repo.commit("feat: merge other").returncode != 0


def test_a_clean_merge_under_the_limit_goes_through(repo):
    grow_on_both_sides(repo, 50, 50)
    p = merge(repo)
    assert p.returncode == 0, p.stderr
    assert p.stderr == ""
    assert repo.git("rev-parse", "-q", "--verify", "HEAD^2").returncode == 0
    assert repo.git("show", "HEAD:shared.py").stdout.count("\n") == 1400


def test_merge_no_verify_skips_the_file_size_limit(repo):
    grow_on_both_sides(repo, 150, 150)
    p = repo.git("merge", "-q", "--no-edit", "--no-verify", "other")
    assert p.returncode == 0, p.stderr
    assert "[pre-commit.file-size]" not in p.stderr
    assert repo.git("rev-parse", "-q", "--verify", "HEAD^2").returncode == 0
    assert repo.events() == []


def test_a_clean_merge_warns_for_a_file_over_in_the_other_parent(repo):
    grow_on_both_sides(repo, 10, 300)
    p = merge(repo)
    assert p.returncode == 0, p.stderr
    assert "pre-merge-commit: warning: shared.py is 1,610 lines" in p.stderr
    assert "before this merge, so the merge goes on" in p.stderr
    assert "[pre-commit.file-size-over]" in p.stderr
    assert repo.events() == []


def test_a_clean_merge_runs_the_repositorys_own_pre_merge_commit(repo):
    grow_on_both_sides(repo, 50, 50)
    own = repo.root / ".git" / "hooks" / "pre-merge-commit"
    own.parent.mkdir(exist_ok=True)
    own.write_text("#!/bin/sh\necho own hook ran >&2\nexit 1\n")
    own.chmod(0o755)
    p = merge(repo)
    assert p.returncode != 0
    assert "own hook ran" in p.stderr
    assert repo.git("rev-parse", "-q", "--verify", "HEAD^2").returncode != 0


def add_own_hook(repo, marker: Path) -> None:
    hook = repo.root / ".githooks" / "pre-merge-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    hook.chmod(0o755)
    assert repo.git("add", ".githooks").returncode == 0


def test_a_clean_merge_does_not_run_a_pre_merge_commit_it_brings_in(repo, tmp_path):
    marker = tmp_path / "hook-ran"
    repo.write("base.py", text(10))
    repo.commit_unchecked()
    assert repo.git("checkout", "-q", "-b", "other").returncode == 0
    add_own_hook(repo, marker)
    repo.commit_unchecked("feat: add a hook")
    assert repo.git("checkout", "-q", "feat").returncode == 0
    repo.write("ours.py", text(10))
    repo.commit_unchecked()
    p = merge(repo)
    assert p.returncode == 0, p.stderr
    assert not marker.exists()
    assert (
        "pre-merge-commit: warning: .githooks/pre-merge-commit is not run: it is "
        "not the executable file the current commit has."
    ) in p.stderr.splitlines()


def test_a_clean_merge_runs_the_committed_githooks_pre_merge_commit(repo, tmp_path):
    marker = tmp_path / "hook-ran"
    grow_on_both_sides(repo, 50, 50)
    add_own_hook(repo, marker)
    repo.commit_unchecked("feat: add a hook")
    p = merge(repo)
    assert p.returncode == 0, p.stderr
    assert marker.exists()
    assert "is not run" not in p.stderr


# ---------------------------------------------------------------- not counted


def test_a_deleted_file_is_not_counted(repo):
    repo.write("legacy.py", text(1600))
    repo.commit_unchecked()
    assert repo.git("rm", "-q", "legacy.py").returncode == 0
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "size limit" not in p.stderr


def test_a_binary_file_is_not_counted(repo):
    repo.write("image.bin", b"\x89PNG\0" + b"\n" * 60_000)
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "size limit" not in p.stderr


def test_a_file_marked_binary_in_gitattributes_is_not_counted(repo):
    repo.write(".gitattributes", "*.dat binary\nraw.txt -diff\n")
    repo.write("table.dat", text(2000))
    repo.write("raw.txt", text(2000))
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "size limit" not in p.stderr


def test_a_symlink_is_not_counted(repo):
    (repo.root / "link.py").symlink_to("\n" * 1600)  # a 1,600-line target
    assert repo.git("add", "link.py").returncode == 0
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "size limit" not in p.stderr


def test_a_submodule_is_not_counted(repo, tmp_path):
    content = tmp_path / "content.txt"
    content.write_text(text(1600))
    sha = repo.git("hash-object", "-w", str(content)).stdout.strip()
    gitlink = f"160000,{sha},sub"
    assert repo.git("update-index", "--add", "--cacheinfo", gitlink).returncode == 0
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode != 0
    listed = [line for line in p.stderr.splitlines() if line.startswith("  ")]
    assert listed == ["  big.py: 2,000 lines, 20,012 bytes (new file)"]


def test_a_symlink_replaced_by_a_file_over_the_limit_is_a_new_file(repo):
    (repo.root / "link.py").symlink_to("target.py")
    assert repo.git("add", "link.py").returncode == 0
    assert repo.commit().returncode == 0
    (repo.root / "link.py").unlink()
    repo.write("link.py", text(1600))
    p = repo.commit()
    assert p.returncode != 0
    assert "  link.py: 1,600 lines, 16,012 bytes (new file)" in p.stderr.splitlines()


# ---------------------------------------------------------------- exempt


SAMPLES = {
    "*.lock": "Cargo.lock",
    "*.lockb": "bun.lockb",
    "*.lockfile": "gradle.lockfile",
    "*-lock.json": "package-lock.json",
    "*-lock.yaml": "web/pnpm-lock.yaml",
    "npm-shrinkwrap.json": "npm-shrinkwrap.json",
    "packages.lock.json": "src/App/packages.lock.json",
    "Package.resolved": "App.xcworkspace/swiftpm/Package.resolved",
    "go.sum": "go.sum",
    "vendor/": "vendor/lib/big.py",
    "vendored/": "pkg/vendored/x.py",
    "third_party/": "src/third_party/zlib.c",
    "third-party/": "third-party/a.js",
    "node_modules/": "node_modules/a/index.js",
    "generated/": "api/generated/client.py",
    "__generated__/": "web/__generated__/types.ts",
    "dist/": "dist/app.js",
    "*.min.js": "static/app.min.js",
    "*.min.css": "static/app.min.css",
    "*.map": "static/app.js.map",
    "*.generated.*": "src/api.generated.ts",
    "*.g.cs": "obj/View.g.cs",
    "*.g.dart": "lib/model.g.dart",
    "*.freezed.dart": "lib/model.freezed.dart",
    "*.designer.cs": "Forms/main.designer.cs",
    "*.Designer.cs": "Forms/Main.Designer.cs",
    "*ModelSnapshot.cs": "Data/Migrations/AppDbContextModelSnapshot.cs",
    "*.pb.go": "proto/model.pb.go",
    "*_pb2.py": "proto/model_pb2.py",
    "*_pb2.pyi": "proto/model_pb2.pyi",
    "*.snap": "tests/__snapshots__/view.test.js.snap",
    "*.pbxproj": "ios/App.xcodeproj/project.pbxproj",
    "*.xcstrings": "ios/App/Localizable.xcstrings",
    "*.storyboard": "ios/App/Base.lproj/Main.storyboard",
    "*.xib": "ios/App/Views/Cell.xib",
    "*.resx": "src/App/Properties/Resources.resx",
    "*.json": "fixtures/big.json",
    "*.jsonl": "events.jsonl",
    "*.ndjson": "logs/a.ndjson",
    "*.geojson": "maps/city.geojson",
    "*.csv": "data/table.csv",
    "*.tsv": "data/table.tsv",
    "*.ipynb": "notebooks/a.ipynb",
    "*.svg": "logo.svg",
}


def test_every_default_pattern_has_a_sample_it_matches():
    assert set(SAMPLES) == set(filesize.DEFAULT_EXEMPT)
    for pattern, rel in SAMPLES.items():
        assert filesize.exempt(rel, filesize.compile_patterns([pattern])), pattern


@pytest.mark.parametrize("rel", ["src/generated.py", "app.css", "lockfile.py"])
def test_names_close_to_a_default_pattern_are_counted(repo, rel):
    repo.write(rel, text(2000))
    p = repo.commit()
    assert p.returncode != 0
    assert f"  {rel}: 2,000 lines, 20,012 bytes (new file)" in p.stderr.splitlines()


@pytest.mark.parametrize(
    "rel",
    [
        *SAMPLES.values(),
        "package-lock.json",
        "web/pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.lock",
        "uv.lock",
        "go.sum",
        "gradle.lockfile",
        "vendor/lib/big.py",
        "src/third_party/zlib.c",
        "node_modules/a/index.js",
        "dist/app.js",
        "api/generated/client.py",
        "static/app.min.js",
        "static/app.js.map",
        "Data/Migrations/AppDbContextModelSnapshot.cs",
        "Forms/Main.Designer.cs",
        "proto/model_pb2.py",
        "tests/__snapshots__/view.test.js.snap",
        "data/table.csv",
        "fixtures/big.json",
        "events.jsonl",
        "logo.svg",
        "ios/App.xcodeproj/project.pbxproj",
        "ios/App/Localizable.xcstrings",
        "ios/App/Base.lproj/Main.storyboard",
        "ios/App/Views/Cell.xib",
        "src/App/Properties/Resources.resx",
    ],
)
def test_lock_vendored_generated_and_data_files_are_exempt(repo, rel):
    repo.write(rel, text(2000))
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "size limit" not in p.stderr


def test_linguist_generated_and_vendored_paths_are_exempt(repo):
    repo.write(
        ".gitattributes",
        "gen/*.py linguist-generated\nlib.py linguist-vendored=true\n",
    )
    repo.write("gen/client.py", text(2000))
    repo.write("lib.py", text(2000))
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert "size limit" not in p.stderr


def test_an_unstaged_gitattributes_does_not_exempt(repo):
    (repo.root / ".gitattributes").write_text("big.py linguist-generated\n")
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode != 0
    assert "  big.py: 2,000 lines, 20,012 bytes (new file)" in p.stderr.splitlines()


def test_the_repository_exempt_list(repo):
    repo.write(
        ".file-size-exempt",
        "# rendered pages\ndocumentation/\n*.out\n/top.txt\nsnap/**/*.txt\n",
    )
    for rel in (
        "documentation/components.html",
        "a/b/run.out",
        "top.txt",
        "snap/x/y/z.txt",
    ):
        repo.write(rel, text(2000))
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    repo.write("sub/top.txt", text(2000))
    p = repo.commit()
    assert p.returncode != 0 and "sub/top.txt" in p.stderr


def test_a_listed_file_is_exempt_in_the_same_commit_that_lists_it(repo):
    repo.write("report.html", text(1400))
    assert repo.commit().returncode == 0
    repo.write("report.html", text(2000))
    repo.write(".file-size-exempt", "report.html\n")
    p = repo.commit()
    assert p.returncode == 0 and p.stderr == ""
    assert repo.events() == []


UNUSED = (
    "pre-commit: warning: .file-size-exempt at the top of the repository {}, "
    "so its patterns are not used. Make it a plain UTF-8 text file."
)


def test_an_exempt_list_that_is_not_utf8_is_not_used(repo):
    repo.write(".file-size-exempt", b"big.py\n\xff\n")
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode != 0
    assert UNUSED.format("is not UTF-8 text") in p.stderr.splitlines()


def test_an_exempt_list_staged_as_a_link_is_not_used(repo):
    (repo.root / "list.txt").write_text("big.py\n")
    (repo.root / ".file-size-exempt").symlink_to("list.txt")
    repo.write("big.py", text(2000))
    assert repo.git("add", ".file-size-exempt").returncode == 0
    p = repo.commit()
    assert p.returncode != 0
    line = UNUSED.format("is staged as a link or a submodule")
    assert line in p.stderr.splitlines()


def test_an_exempt_list_staged_as_a_folder_is_not_used(repo):
    repo.write(".file-size-exempt/list.txt", "big.py\n")
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode != 0
    lines = p.stderr.splitlines()
    assert "  big.py: 2,000 lines, 20,012 bytes (new file)" in lines
    assert UNUSED.format("is staged as a folder") in lines


def test_an_untracked_exempt_list_is_not_used(repo):
    (repo.root / ".file-size-exempt").write_text("big.py\n")
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode != 0
    lines = p.stderr.splitlines()
    assert "  big.py: 2,000 lines, 20,012 bytes (new file)" in lines
    assert "stage the list" not in p.stderr
    (e,) = repo.events()
    assert (e["kind"], e["rule"]) == ("block", "pre-commit.file-size")


def test_unstaged_changes_to_a_tracked_exempt_list_are_named(repo):
    repo.write(".file-size-exempt", "documentation/\n")
    assert repo.commit().returncode == 0
    (repo.root / ".file-size-exempt").write_text("documentation/\nbig.py\n")
    repo.write("big.py", text(2000))
    repo.write("other.py", text(1600))
    p = repo.commit()
    assert p.returncode != 0
    lines = p.stderr.splitlines()
    assert "  big.py: 2,000 lines, 20,012 bytes (new file)" in lines
    assert (
        "The unstaged changes of .file-size-exempt list big.py; stage the list "
        "(`git add .file-size-exempt`)."
    ) in lines
    assert lines[-2].endswith("[pre-commit.file-size]")
    assert lines[-1] == (
        "Next: git add .file-size-exempt, split the other file so each part is "
        "under the limit, stage the parts, then commit again."
    )
    assert repo.git("add", ".file-size-exempt").returncode == 0
    p = repo.commit()
    assert p.returncode != 0
    assert "  other.py: 1,600 lines" in p.stderr
    assert "big.py" not in p.stderr and "stage the list" not in p.stderr


def test_bad_lines_in_the_exempt_list_are_skipped_with_a_warning(repo):
    repo.write(".file-size-exempt", "[z-a]\n!keep.py\ndocs/\n")
    repo.write("big.py", text(2000))
    repo.write("docs/page.md", text(2000))
    p = repo.commit()
    assert p.returncode != 0
    lines = p.stderr.splitlines()
    assert (
        "pre-commit: warning: .file-size-exempt line 1: `[z-a]` is skipped: "
        "the range z-a is reversed."
    ) in lines
    assert (
        "pre-commit: warning: .file-size-exempt line 2: `!keep.py` is skipped: "
        "negation (!) is not supported."
    ) in lines
    assert "  big.py: 2,000 lines, 20,012 bytes (new file)" in lines
    assert "docs/page.md" not in p.stderr
    assert "file size check failed" not in p.stderr


def test_a_reversed_range_does_not_stop_the_other_patterns():
    rx = filesize.compile_patterns(["[z-a]", "a.py"])
    assert len(rx) == 1 and filesize.exempt("x/a.py", rx)


@pytest.mark.parametrize(
    "pattern, path",
    [("*a" * 30 + "b", "a" * 200), ("**?" * 30 + "b", "a/" * 49 + "aa")],
    ids=["stars", "double-stars"],
)
def test_a_pattern_cannot_make_the_check_slow(pattern, path):
    rx = filesize.compile_patterns([pattern])
    start = time.monotonic()
    assert not filesize.exempt(path, rx)
    assert time.monotonic() - start < 1


@pytest.mark.parametrize(
    "content, used",
    [("# padding\n" * 1000 + "big.py\n", "1,000"), ("x" * 70_000 + "\nbig.py\n", "0")],
    ids=["lines", "bytes"],
)
def test_an_oversized_exempt_list_is_cut_with_a_warning(repo, content, used):
    repo.write(".file-size-exempt", content)
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode != 0
    lines = p.stderr.splitlines()
    assert (
        "pre-commit: warning: .file-size-exempt is over 1,000 lines or 64,000 "
        f"bytes; only its first {used} lines are used."
    ) in lines
    assert "  big.py: 2,000 lines, 20,012 bytes (new file)" in lines


@pytest.mark.parametrize("staged_attributes", [True, False], ids=["staged", "none"])
@pytest.mark.parametrize("where", ["info", "config"])
def test_attributes_from_outside_the_commit_do_not_exempt(
    repo, tmp_path, where, staged_attributes
):
    if staged_attributes:
        repo.write(".gitattributes", "*.dat binary\n")
    rule = "big.py linguist-generated\n"
    if where == "info":
        info = repo.root / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text(rule)
    else:
        (tmp_path / "attributes").write_text(rule)
        attrs = str(tmp_path / "attributes")
        assert repo.git("config", "core.attributesFile", attrs).returncode == 0
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode != 0, p.stderr
    assert "  big.py: 2,000 lines, 20,012 bytes (new file)" in p.stderr.splitlines()


def test_a_missing_exempt_list_says_nothing(repo):
    repo.write("small.py", text(10))
    p = repo.commit()
    assert p.returncode == 0 and p.stderr == ""


@pytest.mark.parametrize(
    "pattern, yes, no",
    [
        ("big.py", ["big.py", "a/big.py"], ["big.pyc", "abig.py"]),
        ("docs/", ["docs/a.md", "x/docs/b/c.md"], ["docs", "docs.md"]),
        ("/top.txt", ["top.txt"], ["a/top.txt"]),
        ("a/*.md", ["a/x.md"], ["a/b/x.md", "b/a/x.md"]),
        ("a/**/*.md", ["a/x.md", "a/b/c/x.md"], ["b/x.md"]),
        ("*.g?.cs", ["x.gx.cs", "d/x.gy.cs"], ["x.g.cs"]),
        ("build", ["build", "build/x.py", "a/build/y"], ["builds/x"]),
        ("*.[ch]", ["a.c", "b/x.h"], ["a.cc", "a.[ch]"]),
        ("[!a]*.py", ["b.py", "d/c.py"], ["a.py"]),
        ("x[^0-9].md", ["xa.md"], ["x1.md", "x/.md"]),
        ("a[/b]c", ["abc"], ["a/c"]),
        ("v[]]", ["v]"], ["v"]),
        ("[.md", ["[.md"], ["a.md"]),
        ("a/**", ["a/x", "a/b/c"], ["a", "b/a/x"]),
        ("**/foo", ["foo", "x/y/foo", "foo/z"], ["foox", "xfoo"]),
        ("a/**/b", ["a/b", "a/x/y/b"], ["a/xb", "b"]),
        ("*", ["a", "b/c"], []),
        ("a**b", ["ab", "axxb", "d/ab"], ["a/b"]),
    ],
)
def test_exempt_patterns(pattern, yes, no):
    rx = filesize.compile_patterns([pattern])
    assert all(filesize.exempt(p, rx) for p in yes)
    assert not any(filesize.exempt(p, rx) for p in no)


def test_comments_blank_lines_and_negations_are_skipped():
    assert filesize.compile_patterns(["", "  ", "# note", "!keep.py", "/"]) == []


# ---------------------------------------------------------------- the check failing


@pytest.mark.parametrize("hook", ["pre-commit", "pre-merge-commit"])
def test_a_failing_check_lets_the_commit_through_and_is_logged(tmp_path, hook):
    kit = tmp_path / "kit"
    shutil.copytree(GIT_HOOKS, kit / "git-hooks")
    (kit / "hooks").mkdir()
    for name in ("kitlog.py", "bash-guard.py"):
        shutil.copy(HOOKS / name, kit / "hooks" / name)
    copy_never_stage(kit)
    (kit / "hooks" / "filesize.py").write_text("raise SystemExit(5)\n")
    repo = make_repo(tmp_path, kit / "git-hooks")
    if hook == "pre-commit":
        repo.write("big.py", text(2000))
        p = repo.commit()
    else:
        grow_on_both_sides(repo, 150, 150)
        repo.log.unlink(missing_ok=True)
        p = merge(repo)
        assert repo.git("rev-parse", "-q", "--verify", "HEAD^2").returncode == 0
    assert p.returncode == 0, p.stderr
    assert (
        f"{hook}: warning: file size check failed (exit 5), file sizes NOT "
        "checked; run /kit to see what is broken [pre-commit.file-size-failed]"
    ) in p.stderr.splitlines()
    (e,) = repo.events()
    assert (e["hook"], e["kind"], e["rule"]) == (
        hook,
        "error",
        "pre-commit.file-size-failed",
    )


@pytest.mark.parametrize("args", [[], ["pre-push"], ["pre-commit", "extra"]])
def test_a_wrong_argument_is_a_usage_error(repo, args):
    p = subprocess.run(
        [sys.executable, str(HOOKS / "filesize.py"), *args],
        cwd=repo.root,
        env=repo.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 2
    assert p.stderr == "usage: filesize.py pre-commit|pre-merge-commit\n"
    assert repo.events() == []


@pytest.mark.parametrize(
    "says, shown",
    [
        ("", ""),
        ("printf 'fatal: bad\\033 index\\nmore\\n' >&2; ", ": fatal: bad? index"),
    ],
    ids=["silent", "with-stderr"],
)
def test_a_failing_git_is_reported_and_lets_the_commit_through(
    repo, tmp_path, says, shown
):
    real = shutil.which("git", path=repo.env["PATH"])
    stub = tmp_path / "failing-git"
    stub.mkdir()
    (stub / "git").write_text(
        "#!/bin/sh\n"
        f'for a in "$@"; do [ "$a" = diff-index ] && {{ {says}exit 128; }}; done\n'
        f'exec "{real}" "$@"\n'
    )
    (stub / "git").chmod(0o755)
    repo.write("big.py", text(2000))
    env = dict(repo.env, PATH=f"{stub}{os.pathsep}{repo.env['PATH']}")
    # Run the hook itself: git puts its own folder first on a hook's PATH.
    p = subprocess.run(
        [str(GIT_HOOKS / "pre-commit")],
        cwd=repo.root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    assert p.stderr.splitlines() == [
        f"pre-commit: file size check failed: git diff-index failed (exit 128){shown}",
        "pre-commit: warning: file size check failed (exit 2), file sizes NOT "
        "checked; run /kit to see what is broken [pre-commit.file-size-failed]",
    ]
    (e,) = repo.events()
    assert (e["hook"], e["kind"], e["rule"]) == (
        "pre-commit",
        "error",
        "pre-commit.file-size-failed",
    )


def test_measure_counts_a_last_line_without_a_newline():
    assert filesize.measure(b"") == (0, 0)
    assert filesize.measure(b"a\nb") == (2, 3)
    assert filesize.measure(b"a\nb\n") == (2, 4)
    assert filesize.measure(b"a\0b") is None


# ---------------------------------------------------------------- docs


def test_the_docs_name_the_limit_and_every_default_pattern():
    docs = (REPO / "docs-source" / "file-size.md").read_text()
    assert "1,500 lines" in docs and "50,000 bytes" in docs
    missing = [p for p in filesize.DEFAULT_EXEMPT if f"`{p}`" not in docs]
    assert not missing, f"default exemptions missing from file-size.md: {missing}"
    assert "`pre-merge-commit`" in docs
    assert f"`{filesize.EXEMPT_FILE}`" in docs


def test_the_upgrade_page_notes_the_file_size_refusal():
    note = upgrade_note()
    for words in (
        "refuses a commit",
        "1,500 lines or 50,000 bytes",
        "already over the limit only warns",
        "`.file-size-exempt`",
        "file-size.html",
        "`pre-merge-commit`",
    ):
        assert words in note, words


CATEGORIES = (
    "generated, vendored, lock and data files, and the project and designer "
    "files an IDE writes"
)
NOT_CHECKED = (
    "`git rebase`",
    "`git cherry-pick`",
    "`git revert`",
    "`git am`",
    "`git stash`",
)


def upgrade_note() -> str:
    page = (REPO / "docs-source" / "upgrading.md").read_text()
    note = page[page.index("## File size limit") :]
    return note[: note.index("\n## ")]


def test_the_docs_name_the_commands_that_are_not_checked():
    for text in ((REPO / "docs-source" / "file-size.md").read_text(), upgrade_note()):
        missing = [c for c in NOT_CHECKED if c not in text]
        assert not missing, missing


def test_the_exempt_kinds_have_one_name_everywhere():
    for text in (
        (REPO / "docs-source" / "file-size.md").read_text(),
        (REPO / "docs-source" / "components.md").read_text(),
        upgrade_note(),
        filesize.__doc__,
    ):
        assert CATEGORIES in " ".join(text.split())


# ---------------------------------------------------------------- CLAUDE.md template


def test_the_claude_md_template_states_the_limit():
    text = (REPO / "claude" / "CLAUDE.md.template").read_text()
    assert "at most 1,500 lines and 50,000 bytes" in text
    assert "New code that would take a file past that goes in a new file" in text
    assert "2,000 lines" not in text


def test_the_warning_and_the_template_agree_on_splitting():
    template = (REPO / "claude" / "CLAUDE.md.template").read_text()
    assert "do not split an existing longer file unless asked" in template
    assert "split this one only when asked" in filesize.ALREADY_OVER
    assert "when you next work on it" not in filesize.ALREADY_OVER
