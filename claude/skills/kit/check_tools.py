"""Checks of the tools the ship skill works with: gh's login and Playwright.

Part of the self-check (check.py). Each line is [pass] or [info]: these tools
are the user's, they talk to a network the check does not own, and none of
them makes the kit itself not work.
"""

from __future__ import annotations

import contextlib
import importlib.metadata
import os
import re
import signal
import subprocess
import sys
import tempfile

GH_TIMEOUT = 15  # seconds `gh auth status` gets; it asks the GitHub API
BROWSER_TIMEOUT = 30  # seconds Playwright gets to start chromium and close it
NPX_TIMEOUT = 30  # seconds `npx playwright --version` gets
NPX_VERSION = re.compile(r"Version (\d[0-9A-Za-z.+-]{0,39})")
# Run by the python3 of the check, in an empty folder. One word comes back.
BROWSER_PROBE = f"""
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        p.chromium.launch(timeout={(BROWSER_TIMEOUT - 5) * 1000}).close()
except Exception as exc:
    print("nobrowser" if "Executable doesn't exist" in str(exc) else "error")
else:
    print("ready")
"""
SHIP = "the ship skill tests web pages with it"


def outcome(
    argv: list[str],
    *,
    env: dict | None = None,
    cwd: str | None = None,
    timeout: int,
    keep: bool = True,
) -> tuple[int | None, str]:
    """(exit code, stdout) of a program and whatever it starts.

    It gets no terminal and no input, its errors are dropped, and with keep
    False so is its output. A timeout ends its children too. Exit code None:
    it did not start or did not finish in time.
    """
    try:
        p = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if keep else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            env=env,
            cwd=cwd,
            start_new_session=True,
        )
    except OSError:
        return None, ""
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return None, ""
    return p.returncode, out or ""


def check_gh_login(c) -> None:
    """Is gh logged in? Only the exit code of `gh auth status` is used: its
    output names the account, the token's start and its scopes, and none of
    that is read or shown."""
    env = dict(os.environ, GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
    rc, _ = outcome(["gh", "auth", "status"], env=env, timeout=GH_TIMEOUT, keep=False)
    fix = "gh auth login, then gh auth status to see what gh reports"
    if rc == 0:
        c.add("environment", "pass", "gh: logged in")
    elif rc is None:
        c.add(
            "environment",
            "info",
            f"gh auth status gave no answer within {GH_TIMEOUT} seconds "
            "(no network?): whether gh is logged in is not known",
            fix,
        )
    else:
        c.add(
            "environment",
            "info",
            "gh is not logged in, or cannot use its login here (gh auth status "
            "failed; it also fails without network): the ship skill needs it",
            fix,
        )


def python_playwright() -> str:
    """The version of Playwright for this python3, or "" without one."""
    try:
        return importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        return ""


def check_playwright(c, version: str) -> None:
    """Playwright for python3: not installed, no browser, or chromium starts."""
    if not version:
        c.add("environment", "info", f"playwright not installed for python3 ({SHIP})")
        return
    with tempfile.TemporaryDirectory() as empty:
        rc, out = outcome(
            [sys.executable, "-c", BROWSER_PROBE],
            cwd=empty,
            timeout=BROWSER_TIMEOUT,
        )
    word = out.strip().splitlines()[-1] if rc == 0 and out.strip() else ""
    if word == "ready":
        c.add(
            "environment", "pass", f"playwright: {version} (python3), chromium starts"
        )
    elif word == "nobrowser":
        c.add(
            "environment",
            "info",
            f"playwright {version} is installed for python3, but no browser is "
            f"downloaded: it cannot test web pages yet ({SHIP})",
            "python3 -m playwright install chromium",
        )
    else:
        why = (
            f"did not start within {BROWSER_TIMEOUT} seconds"
            if rc is None
            else "did not start (missing system libraries, or a sandbox)"
        )
        c.add(
            "environment",
            "info",
            f"playwright {version} is installed for python3, but chromium {why}",
            "python3 -m playwright install --with-deps chromium",
        )


def node_project(cwd: str, top: str) -> str:
    """The nearest folder from cwd up to top that has a package.json, or "".

    Without a top (not in a git repository) only cwd itself counts.
    """
    here = os.path.abspath(cwd)
    top = os.path.abspath(top) if top else here
    if os.path.commonpath([here, top]) != top:
        top = here
    while True:
        if os.path.isfile(os.path.join(here, "package.json")):
            return here
        if here == top or os.path.dirname(here) == here:
            return ""
        here = os.path.dirname(here)


def check_node_playwright(c, cwd: str, top: str, npx: str | None) -> None:
    """In a Node project: the Playwright that npx finds. Never installs one."""
    project = node_project(cwd, top)
    if not project:
        return
    if not npx:
        c.add(
            "environment",
            "info",
            "this is a Node project and npx is not on PATH: Playwright for Node "
            "not checked",
        )
        return
    env = dict(
        os.environ,
        npm_config_yes="false",
        npm_config_update_notifier="false",
        NO_UPDATE_NOTIFIER="1",
    )
    rc, out = outcome(
        [npx, "--no-install", "playwright", "--version"],
        env=env,
        cwd=project,
        timeout=NPX_TIMEOUT,
    )
    found = NPX_VERSION.search(out) if rc == 0 else None
    if found:
        c.add(
            "environment",
            "pass",
            f"playwright: {found.group(1)} (npx, this Node project)",
        )
        return
    c.add(
        "environment",
        "info",
        "this is a Node project and npx finds no Playwright that runs here "
        "(npx --no-install playwright --version gave no version)",
        "npm install --save-dev @playwright/test, then npx playwright install chromium",
    )
