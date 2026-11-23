"""The Environment lines for gh's login and Playwright (check_tools.py).

The tools are stubs: a gh and an npx on PATH, and a fake playwright package
on PYTHONPATH, so the machine's own tools, logins and network play no part.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_tools", KIT / "check_tools.py")
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)

SECRET = "gho_NOTAREALTOKEN0123456789"
FAKE_SYNC_API = """
import os, time

class _Browser:
    def close(self):
        pass

class _Chromium:
    def launch(self, **kw):
        mode = os.environ.get("FAKE_PLAYWRIGHT", "ready")
        if mode == "nobrowser":
            raise Exception(
                "BrowserType.launch: Executable doesn't exist at /x/headless_shell"
                " Please run: playwright install"
            )
        if mode == "deps":
            raise Exception(
                "Host system is missing dependencies to run browsers."
                " Please run: sudo playwright install-deps"
            )
        return _Browser()

class _Playwright:
    chromium = _Chromium()

class _Context:
    def __enter__(self):
        return _Playwright()

    def __exit__(self, *exc):
        return False

def sync_playwright():
    return _Context()
"""


class Report:
    def __init__(self):
        self.items = []

    def add(self, section, level, msg, fix=""):
        self.items.append({"section": section, "level": level, "msg": msg, "fix": fix})

    def lines(self):
        return [f"[{i['level']}] {i['msg']}" for i in self.items]


def stub(bin_dir, name, body):
    bin_dir.mkdir(exist_ok=True)
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def gh(tmp_path, monkeypatch):
    """A gh whose `auth status` prints what the real one does, then exits with
    $FAKE_GH_AUTH (default 0), and records that it ran."""
    bin_dir = tmp_path / "bin"
    stub(
        bin_dir,
        "gh",
        'if [ "$1 $2" = "auth status" ]; then\n'
        f'  touch "{tmp_path}/asked"\n'
        "  echo 'github.com'\n"
        "  echo '  Logged in to github.com account someone (keyring)'\n"
        f"  echo '  - Token: {SECRET}'\n"
        "  echo \"  - Token scopes: 'repo', 'workflow'\" >&2\n"
        '  [ "${FAKE_GH_AUTH:-0}" = sleep ] && exec sleep 30\n'
        '  exit "${FAKE_GH_AUTH:-0}"\n'
        "fi\n"
        "echo 'gh version 2.0.0 (test)'\n",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return tmp_path


def test_gh_logged_in(gh):
    r = Report()
    tools.check_gh_login(r)
    assert (gh / "asked").exists()
    assert r.lines() == ["[pass] gh: logged in"]


@pytest.mark.parametrize("code", ["1", "4"])
def test_gh_not_logged_in_is_info(gh, monkeypatch, code):
    monkeypatch.setenv("FAKE_GH_AUTH", code)
    r = Report()
    tools.check_gh_login(r)
    [item] = r.items
    assert item["level"] == "info"
    assert item["msg"].startswith("gh is not logged in, or cannot use its login here")
    assert "gh auth login" in item["fix"]


def test_gh_that_does_not_answer_is_info(gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_AUTH", "sleep")
    monkeypatch.setattr(tools, "GH_TIMEOUT", 1)
    r = Report()
    tools.check_gh_login(r)
    [item] = r.items
    assert item["level"] == "info" and "no answer within 1 seconds" in item["msg"]


@pytest.mark.parametrize("code", ["0", "1"])
def test_gh_login_report_never_shows_the_token_or_scopes(gh, monkeypatch, code):
    monkeypatch.setenv("FAKE_GH_AUTH", code)
    r = Report()
    tools.check_gh_login(r)
    text = repr(r.items)
    for word in (SECRET, "gho_", "scopes", "workflow", "someone", "keyring"):
        assert word not in text


@pytest.fixture
def playwright(tmp_path, monkeypatch):
    """A playwright 9.9.9 for python3 that behaves as $FAKE_PLAYWRIGHT says."""
    site = tmp_path / "site"
    (site / "playwright").mkdir(parents=True)
    (site / "playwright" / "__init__.py").write_text("")
    (site / "playwright" / "sync_api.py").write_text(FAKE_SYNC_API)
    meta = site / "playwright-9.9.9.dist-info"
    meta.mkdir()
    (meta / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: playwright\nVersion: 9.9.9\n"
    )
    monkeypatch.syspath_prepend(str(site))
    monkeypatch.setenv("PYTHONPATH", str(site))
    return site


def test_python_playwright_version(playwright):
    assert tools.python_playwright() == "9.9.9"


def test_playwright_not_installed():
    r = Report()
    tools.check_playwright(r, "")
    assert r.lines() == [
        "[info] playwright not installed for python3 "
        "(the ship skill tests web pages with it)"
    ]


def test_playwright_ready(playwright):
    r = Report()
    tools.check_playwright(r, "9.9.9")
    assert r.lines() == ["[pass] playwright: 9.9.9 (python3), chromium starts"]


def test_playwright_without_a_browser_is_told_apart(playwright, monkeypatch):
    monkeypatch.setenv("FAKE_PLAYWRIGHT", "nobrowser")
    r = Report()
    tools.check_playwright(r, "9.9.9")
    [item] = r.items
    assert item["level"] == "info"
    assert item["msg"].startswith(
        "playwright 9.9.9 is installed for python3, but no browser is downloaded"
    )
    assert item["fix"] == "python3 -m playwright install chromium"


def test_playwright_whose_browser_cannot_start(playwright, monkeypatch):
    monkeypatch.setenv("FAKE_PLAYWRIGHT", "deps")
    r = Report()
    tools.check_playwright(r, "9.9.9")
    [item] = r.items
    assert item["level"] == "info"
    assert "no browser" not in item["msg"]
    assert item["msg"].endswith(
        "but chromium did not start (missing system libraries, or a sandbox)"
    )
    assert item["fix"] == "python3 -m playwright install --with-deps chromium"


def test_playwright_probe_ignores_the_current_folder(playwright, monkeypatch, tmp_path):
    # A playwright.py in the folder /kit runs from must not stand in for it.
    work = tmp_path / "work"
    work.mkdir()
    (work / "playwright.py").write_text("raise SystemExit('shadowed')\n")
    monkeypatch.chdir(work)
    r = Report()
    tools.check_playwright(r, "9.9.9")
    assert r.lines() == ["[pass] playwright: 9.9.9 (python3), chromium starts"]


@pytest.fixture
def npx(tmp_path):
    """An npx that finds playwright 1.2.3 and records how it was called."""
    return stub(
        tmp_path / "bin",
        "npx",
        f'echo "$PWD $*" >> "{tmp_path}/npx.log"\n'
        'if [ "$*" = "--no-install playwright --version" ] '
        '&& [ "${FAKE_NPX:-ok}" = ok ]; then\n'
        "  echo 'Version 1.2.3'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'npm ERR! could not determine executable to run' >&2\n"
        "exit 1\n",
    )


def project(tmp_path):
    root = tmp_path / "app"
    (root / "src" / "deep").mkdir(parents=True)
    (root / "package.json").write_text('{"name": "app"}\n')
    return root


def test_node_project_reports_the_playwright_npx_finds(tmp_path, npx):
    root = project(tmp_path)
    r = Report()
    tools.check_node_playwright(r, str(root / "src" / "deep"), str(root), npx)
    assert r.lines() == ["[pass] playwright: 1.2.3 (npx, this Node project)"]
    calls = (tmp_path / "npx.log").read_text().splitlines()
    assert calls == [f"{root} --no-install playwright --version"]


def test_node_project_without_playwright(tmp_path, npx, monkeypatch):
    monkeypatch.setenv("FAKE_NPX", "missing")
    root = project(tmp_path)
    r = Report()
    tools.check_node_playwright(r, str(root), str(root), npx)
    [item] = r.items
    assert item["level"] == "info"
    assert "npx finds no Playwright" in item["msg"]
    assert "npm ERR" not in item["msg"]


def test_node_project_without_npx(tmp_path):
    root = project(tmp_path)
    r = Report()
    tools.check_node_playwright(r, str(root), str(root), None)
    assert r.lines() == [
        "[info] this is a Node project and npx is not on PATH: "
        "Playwright for Node not checked"
    ]


def test_no_node_project_no_npx_call(tmp_path, npx):
    work = tmp_path / "work"
    work.mkdir()
    r = Report()
    tools.check_node_playwright(r, str(work), "", npx)
    assert r.items == [] and not (tmp_path / "npx.log").exists()


def test_package_json_above_the_repository_does_not_count(tmp_path, npx):
    (tmp_path / "package.json").write_text("{}\n")
    repo = tmp_path / "repo" / "sub"
    repo.mkdir(parents=True)
    assert tools.node_project(str(repo), str(tmp_path / "repo")) == ""
    assert tools.node_project(str(repo), "") == ""
    assert tools.node_project(str(repo), str(tmp_path)) == str(tmp_path)


def test_check_py_reports_the_new_lines(tmp_path, gh, playwright, npx):
    # The whole checker, run in a Node project, has all three lines; none of
    # them is a [fail] or [warn] even when every tool is missing a piece.
    root = project(tmp_path)
    env = dict(
        os.environ,
        CLAUDE_HOME=str(tmp_path / "nohome"),
        PIPELINEKIT_UPDATE_CHECK="0",
        FAKE_GH_AUTH="1",
        FAKE_PLAYWRIGHT="nobrowser",
        FAKE_NPX="missing",
    )
    p = subprocess.run(
        [sys.executable, str(KIT / "check.py"), "--verbose", "--exit-zero", "--json"],
        capture_output=True,
        text=True,
        env=env,
        cwd=root,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    env_items = [
        i for i in json.loads(p.stdout)["results"] if i["section"] == "environment"
    ]
    text = {i["msg"]: i["level"] for i in env_items}
    assert text["gh: 2.0.0 (test)"] == "pass"
    for start in (
        "gh is not logged in",
        "playwright 9.9.9 is installed for python3, but no browser",
        "this is a Node project and npx finds no Playwright",
    ):
        [level] = [lvl for msg, lvl in text.items() if msg.startswith(start)]
        assert level == "info"
    assert SECRET not in p.stdout
