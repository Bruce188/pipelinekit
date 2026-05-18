#!/usr/bin/env python3
"""Tests for validate-task-spec.py pre-commit hook.

Fixtures:
(a) spec.md with routing.worker_class: claude staged -> exit 0
(b) spec.md without routing block staged -> exit non-zero + stderr error
(c) spec.md with empty worker_class: staged -> exit non-zero
(d) no spec.md staged (other files only) -> exit 0
"""

import os
import subprocess
import sys
import tempfile
import textwrap

HOOK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "validate-task-spec.py",
)


def _run_hook(repo_dir: str, env: dict | None = None) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    merged_env["GIT_DIR"] = os.path.join(repo_dir, ".git")
    merged_env["GIT_WORK_TREE"] = repo_dir
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, HOOK_PATH],
        capture_output=True,
        text=True,
        cwd=repo_dir,
        env=merged_env,
    )


def _git(repo_dir: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args),
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t.com",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t.com"},
    )


def _setup_repo(tmp: str) -> str:
    """Initialize a bare git repo in tmp and return its path."""
    _git(tmp, "init", "-b", "main")
    _git(tmp, "config", "user.email", "t@t.com")
    _git(tmp, "config", "user.name", "test")
    # Create an initial commit so HEAD is valid
    open(os.path.join(tmp, "README.md"), "w").write("init")
    _git(tmp, "add", "README.md")
    _git(tmp, "commit", "-m", "init: empty base")
    return tmp


def _stage_spec(repo_dir: str, task_id: str, content: str) -> str:
    """Write a spec.md at .claude/tasks/<task_id>/spec.md and stage it."""
    task_dir = os.path.join(repo_dir, ".claude", "tasks", task_id)
    os.makedirs(task_dir, exist_ok=True)
    spec_path = os.path.join(task_dir, "spec.md")
    with open(spec_path, "w") as f:
        f.write(content)
    _git(repo_dir, "add", spec_path)
    return spec_path


def test_fixture_a_valid_worker_class():
    """Fixture (a): spec.md with routing.worker_class: claude -> exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        _setup_repo(tmp)
        content = textwrap.dedent("""\
            ---
            title: My Task
            routing:
              worker_class: claude
            ---
            Task body here.
        """)
        _stage_spec(tmp, "task-1.1", content)
        result = _run_hook(tmp)
        assert result.returncode == 0, (
            f"Fixture (a) FAIL: expected exit 0 for valid worker_class, got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
    print("PASS fixture (a): valid worker_class -> exit 0")


def test_fixture_b_no_routing_block():
    """Fixture (b): spec.md without routing block -> exit non-zero + stderr error."""
    with tempfile.TemporaryDirectory() as tmp:
        _setup_repo(tmp)
        content = textwrap.dedent("""\
            ---
            title: My Task
            ---
            Task body here. No routing block at all.
        """)
        _stage_spec(tmp, "task-1.2", content)
        result = _run_hook(tmp)
        assert result.returncode != 0, (
            f"Fixture (b) FAIL: expected non-zero exit for missing routing block, got {result.returncode}"
        )
        assert "routing.worker_class" in result.stderr, (
            f"Fixture (b) FAIL: expected 'routing.worker_class' in stderr, got: {result.stderr!r}"
        )
    print("PASS fixture (b): missing routing block -> non-zero exit + stderr error")


def test_fixture_c_empty_worker_class():
    """Fixture (c): spec.md with empty worker_class: -> exit non-zero."""
    with tempfile.TemporaryDirectory() as tmp:
        _setup_repo(tmp)
        content = textwrap.dedent("""\
            ---
            title: My Task
            routing:
              worker_class:
            ---
            Task body here.
        """)
        _stage_spec(tmp, "task-1.3", content)
        result = _run_hook(tmp)
        assert result.returncode != 0, (
            f"Fixture (c) FAIL: expected non-zero exit for empty worker_class, got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
    print("PASS fixture (c): empty worker_class -> non-zero exit")


def test_fixture_d_no_spec_staged():
    """Fixture (d): no spec.md staged (other files only) -> exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        _setup_repo(tmp)
        # Stage a non-spec file
        other_path = os.path.join(tmp, "other.txt")
        with open(other_path, "w") as f:
            f.write("not a spec")
        _git(tmp, "add", other_path)
        result = _run_hook(tmp)
        assert result.returncode == 0, (
            f"Fixture (d) FAIL: expected exit 0 when no spec.md staged, got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
    print("PASS fixture (d): no spec.md staged -> exit 0")


def main():
    failures: list[str] = []
    tests = [
        test_fixture_a_valid_worker_class,
        test_fixture_b_no_routing_block,
        test_fixture_c_empty_worker_class,
        test_fixture_d_no_spec_staged,
    ]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failures.append(str(e))
        except Exception as e:
            failures.append(f"{t.__name__} ERROR: {e}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        sys.exit(1)

    print("\nAll 4 fixtures passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
