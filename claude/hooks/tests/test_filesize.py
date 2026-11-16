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
        f"pre-commit: commit refused, over the file size limit of {LIMIT}: "
        "[pre-commit.file-size]",
        "  src/big.py: 1,501 lines, 15,022 bytes (new file)",
        "Split the file: new code that would take a file past the limit goes in "
        "a new file. A generated, vendored or data file can be listed in "
        ".file-size-exempt.",
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
    assert repo.commit().returncode != 0


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
    assert repo.commit().returncode != 0


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
    for name in ("filesize.py", "kitlog.py"):
        shutil.copy(HOOKS / name, kit / "hooks" / name)
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
    real = filesize.read_blobs
    monkeypatch.setattr(filesize, "read_blobs", lambda n: read.extend(n) or real(n))
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


# ---------------------------------------------------------------- exempt


@pytest.mark.parametrize(
    "rel",
    [
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


LOCAL_NOTE = (
    "pre-commit: note: {} is {}, over the file size limit of "
    f"{LIMIT}; the commit goes on because .file-size-exempt in the working "
    "tree lists it, and that list is not staged. "
    "[pre-commit.file-size-exempt-local]"
)


def test_an_exempt_list_in_the_working_tree_counts_with_a_note(repo):
    (repo.root / ".file-size-exempt").write_text("big.py\nother.py\n")
    repo.write("big.py", text(2000))
    repo.write("other.py", text(1600))
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert p.stderr.splitlines() == [
        LOCAL_NOTE.format("big.py", "2,000 lines, 20,012 bytes"),
        LOCAL_NOTE.format("other.py", "1,600 lines, 16,012 bytes"),
    ]
    (e,) = repo.events()
    assert (e["hook"], e["kind"], e["rule"]) == (
        "pre-commit",
        "override",
        "pre-commit.file-size-exempt-local",
    )
    assert e["reason"] == (
        "big.py: 2000 lines, 20012 bytes; exempt only by the unstaged "
        ".file-size-exempt; 1 more file(s)"
    )
    assert MARKER not in repo.log.read_text()


def test_a_working_tree_exempt_list_says_nothing_for_files_under_the_limit(repo):
    (repo.root / ".file-size-exempt").write_text("small.py\nlegacy.py\n")
    repo.write("small.py", text(10))
    repo.write("legacy.py", text(1600))
    repo.commit_unchecked()
    repo.write("legacy.py", text(1700))
    p = repo.commit()
    assert p.returncode == 0 and p.stderr == ""
    assert repo.events() == []


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


@pytest.mark.parametrize("kind", ["link", "folder"])
def test_an_exempt_list_in_the_working_tree_that_is_no_file_is_not_used(repo, kind):
    target = repo.root / ".file-size-exempt"
    if kind == "link":
        (repo.root / "list.txt").write_text("big.py\n")
        target.symlink_to("list.txt")
    else:
        target.mkdir()
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode != 0
    assert UNUSED.format("is a link or a folder") in p.stderr.splitlines()


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
    ],
)
def test_exempt_patterns(pattern, yes, no):
    rx = filesize.compile_patterns([pattern])
    assert all(filesize.exempt(p, rx) for p in yes)
    assert not any(filesize.exempt(p, rx) for p in no)


def test_comments_blank_lines_and_negations_are_skipped():
    assert filesize.compile_patterns(["", "  ", "# note", "!keep.py", "/"]) == []


# ---------------------------------------------------------------- the check failing


def test_a_failing_check_lets_the_commit_through_and_is_logged(tmp_path):
    kit = tmp_path / "kit"
    shutil.copytree(GIT_HOOKS, kit / "git-hooks")
    (kit / "hooks").mkdir()
    shutil.copy(HOOKS / "kitlog.py", kit / "hooks" / "kitlog.py")
    (kit / "hooks" / "filesize.py").write_text("raise SystemExit(5)\n")
    repo = make_repo(tmp_path, kit / "git-hooks")
    repo.write("big.py", text(2000))
    p = repo.commit()
    assert p.returncode == 0, p.stderr
    assert (
        "pre-commit: warning: file size check failed (exit 5), file sizes NOT "
        "checked; run /kit to see what is broken [pre-commit.file-size-failed]"
    ) in p.stderr.splitlines()
    (e,) = repo.events()
    assert (e["kind"], e["rule"]) == ("error", "pre-commit.file-size-failed")


def test_measure_counts_a_last_line_without_a_newline():
    assert filesize.measure(b"") == (0, 0)
    assert filesize.measure(b"a\nb") == (2, 3)
    assert filesize.measure(b"a\nb\n") == (2, 4)
    assert filesize.measure(b"a\0b") is None


# ---------------------------------------------------------------- docs


def test_the_docs_name_the_limit_and_every_default_pattern():
    docs = (REPO / "docs-source" / "components.md").read_text()
    assert "1,500 lines" in docs and "50,000 bytes" in docs
    missing = [p for p in filesize.DEFAULT_EXEMPT if f"`{p}`" not in docs]
    assert not missing, f"default exemptions missing from components.md: {missing}"
    assert f"`{filesize.EXEMPT_FILE}`" in docs


def test_the_upgrade_page_notes_the_file_size_refusal():
    page = (REPO / "docs-source" / "upgrading.md").read_text()
    note = page[page.index("## File size limit") :]
    note = note[: note.index("\n## ")]
    for words in (
        "refuses a commit",
        "1,500 lines or 50,000 bytes",
        "already over the limit only warns",
        "`.file-size-exempt`",
        ".git/info/exclude",
        "components.html#file-size-limit",
    ):
        assert words in note, words


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
