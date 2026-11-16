"""Fixtures of the kit tests: one real install per test file, and a copy per test."""

import os
import shutil
import subprocess

import pytest
from check_fixtures import (
    REPO,
)


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """One real install into a throwaway HOME, kept as a template."""
    root = tmp_path_factory.mktemp("kit")
    user = root / "home"
    user.mkdir()
    env = dict(
        os.environ,
        HOME=str(user),
        CLAUDE_HOME=str(user / ".claude"),
        USER_NAME="Test User",
        USER_EMAIL="test@example.com",
        GIT_CONFIG_GLOBAL=str(user / ".gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        XDG_CONFIG_HOME=str(user / ".config"),
        PIPELINEKIT_GIT_HOOKS="1",
        # The real remote is none of a test's business; the update tests switch
        # the check on against a local origin.
        PIPELINEKIT_UPDATE_CHECK="0",
    )
    # The event log then sits below the throwaway HOME, as on a real machine.
    for k in (
        "ALLOW_MAIN_PUSH",
        "PIPELINEKIT_ALLOW_SECRET",
        "PIPELINEKIT_STATE_DIR",
        "PIPELINEKIT_LOG",
        "PIPELINEKIT_SESSION_CHECK",
        "XDG_STATE_HOME",
    ):
        env.pop(k, None)
    p = subprocess.run(
        ["bash", str(REPO / "scripts" / "install.sh"), "--no-serena"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    shutil.copytree(user, root / "template", symlinks=True)
    return {"root": root, "user": user, "home": user / ".claude", "env": env}


@pytest.fixture
def kit(installed):
    """A fresh copy of the install at the same path (settings hold that path)."""
    shutil.rmtree(installed["user"])
    shutil.copytree(installed["root"] / "template", installed["user"], symlinks=True)
    return installed
