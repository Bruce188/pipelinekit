"""check.py: a healthy install passes and each way it can break is reported."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from check_fixtures import (
    CHECK,
    REPO,
    check,
    check_py,
    edit_json,
    replace_script,
    snapshot,
)

# ---------------------------------------------------------------- healthy


def test_healthy_install(kit):
    rc, out = check(kit)
    assert rc == 0, out
    assert out.startswith("pipelinekit ")
    assert "[fail]" not in out and "[warn]" not in out
    assert "Live probe" in out
    assert out.rstrip().endswith("Result: healthy")


def test_verbose_lists_every_probe(kit):
    rc, out = check(kit, "--verbose")
    assert rc == 0, out
    for line in (
        "[pass] bash-guard.py: 5 probes as expected",
        "[pass] block-bare-repo-markers.py: 2 probes as expected",
        "[pass] post-edit-format.sh: 1 probe as expected",
        "[pass] session-check.py: 2 probes as expected",
        "[pass] commit-msg: 2 probes as expected",
        "[pass] pre-commit: 2 probes as expected",
        "[pass] pre-merge-commit: 2 probes as expected",
        "[pass] pre-push: 2 probes as expected",
        "[pass] event log: 6 refusals recorded",
        "[pass] hook helper: kitlog.py",
        "[pass] hook helper: filesize.py",
        "[pass] kit files within the file size limit of 1,500 lines and 50,000 bytes",
        "[pass] git: global core.hooksPath set",
        "[pass] settings.json: 12 kit hook entries wired",
    ):
        assert line in out, out


def test_quick_skips_the_probes(kit):
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert "(quick check)" in out and "Live probe" not in out


def test_check_changes_nothing(kit):
    before = snapshot(kit["user"])
    check(kit)
    check(kit, "--quick")
    assert snapshot(kit["user"]) == before


# ---------------------------------------------------------------- files


def test_missing_hook_is_reported_once(kit):
    (kit["home"] / "hooks" / "bash-guard.py").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] hook missing: bash-guard.py" in out
    assert "settings.json: hook command not found" in out
    assert "missing: hooks/bash-guard.py" not in out
    assert "bash-guard.py does not start" not in out
    assert "Repair: bash " in out


def test_hook_not_executable(kit):
    (kit["home"] / "hooks" / "block-bare-repo-markers.py").chmod(0o644)
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] hook not executable: block-bare-repo-markers.py" in out


@pytest.mark.parametrize("mode", [(), ("--quick",)])
def test_crlf_hook(kit, mode):
    guard = kit["home"] / "hooks" / "bash-guard.py"
    guard.write_bytes(guard.read_bytes().replace(b"\n", b"\r\n"))
    rc, out = check(kit, *mode)
    assert rc == 1
    assert "hook has CRLF line endings and cannot start: bash-guard.py" in out


def test_missing_git_hook(kit):
    (kit["home"] / "git-hooks" / "pre-push").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] git hook missing: pre-push" in out


def test_removed_skill_is_one_line(kit):
    shutil.rmtree(kit["home"] / "skills" / "mobile")
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] skill missing: mobile" in out
    assert out.count("mobile") == 1, out


def test_removed_skill_file(kit):
    (kit["home"] / "skills" / "kit" / "check.py").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] missing: skills/kit/check.py" in out


def test_edited_skill_file_is_only_a_warning(kit):
    with open(kit["home"] / "skills" / "deploy" / "SKILL.md", "a") as f:
        f.write("\nmy own note\n")
    rc, out = check(kit)
    assert rc == 0, out
    assert "[warn] changed since install: skills/deploy/SKILL.md" in out
    assert "Result: working, 1 warning" in out


def test_removed_frontend_design_skill_file(kit):
    (kit["home"] / "skills" / "frontend-design" / "SKILL.md").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] skill missing: frontend-design" in out


def test_edited_frontend_design_is_only_a_warning(kit):
    with open(kit["home"] / "skills" / "frontend-design" / "SKILL.md", "a") as f:
        f.write("\nmy own note\n")
    rc, out = check(kit)
    assert rc == 0, out
    assert "[warn] changed since install: skills/frontend-design/SKILL.md" in out


# ---------------------------------------------------------------- file sizes

LIMIT = "file size limit of 1,500 lines and 50,000 bytes"


def oversize(path):
    path.write_text("x = 1\n" * 1501)


def test_kit_file_over_the_size_limit_warns(kit):
    oversize(kit["home"] / "skills" / "deploy" / "SKILL.md")
    rc, out = check(kit)
    assert rc == 0, out
    lines = out.splitlines()
    assert (
        f"[warn] 1 kit file over the {LIMIT}: "
        "skills/deploy/SKILL.md (1,501 lines, 9,006 bytes)"
    ) in out, out
    i = next(n for n, line in enumerate(lines) if f"over the {LIMIT}" in line)
    assert lines[i + 1] == "         fix: open an issue on the kit's repository"
    assert "Result: working, 2 warnings" in out


NOT_CHECKED = "[warn] kit file sizes not checked: hooks/filesize.py "


def test_a_size_check_that_does_not_load_says_so(kit):
    (kit["home"] / "hooks" / "filesize.py").write_text("raise SystemExit(5)\n")
    rc, out = check(kit)
    assert f"{NOT_CHECKED}does not load (SystemExit: 5)" in out, out
    assert LIMIT not in out


def test_a_size_check_that_fails_says_so(kit):
    with open(kit["home"] / "hooks" / "filesize.py", "a") as f:
        f.write("\n\ndef measure(blob):\n    raise ValueError('cannot measure')\n")
    rc, out = check(kit)
    assert f"{NOT_CHECKED}failed (ValueError: cannot measure)" in out, out
    assert f"[pass] kit files within the {LIMIT}" not in out


def test_vendored_and_data_files_are_not_counted(kit):
    oversize(kit["home"] / "skills" / "frontend-design" / "SKILL.md")
    files = json.loads((kit["home"] / "pipelinekit" / "manifest.json").read_text())
    data = next(r for r in sorted(files["files"]) if r.endswith(".json"))
    (kit["home"] / data).write_text(json.dumps(list(range(3000)), indent=1))
    rc, out = check(kit, "--verbose")
    assert rc == 0, out
    assert "over the file size limit" not in out
    assert f"[pass] kit files within the {LIMIT}" in out


def test_quick_does_not_measure_kit_files(kit):
    oversize(kit["home"] / "skills" / "deploy" / "SKILL.md")
    rc, out = check(kit, "--quick", "--verbose")
    assert rc == 0, out
    assert LIMIT not in out


def test_missing_size_helper(kit):
    (kit["home"] / "hooks" / "filesize.py").unlink()
    rc, out = check(kit, "--verbose")
    assert rc == 1
    assert (
        "[fail] hook helper missing: filesize.py "
        "(pre-commit and pre-merge-commit let commits and merges through "
        "without the file size limit)"
    ) in out
    assert "[pass] pre-commit: 1 probe as expected" in out
    assert "[pass] pre-merge-commit: 1 probe as expected" in out
    assert "[pass] event log: 4 refusals recorded" in out
    assert LIMIT not in out


def test_size_helper_that_lets_everything_through(kit):
    replace_script(kit, "hooks/filesize.py", "import sys\nsys.exit(0)\n")
    rc, out = check(kit)
    assert rc == 1
    for n in ("pre-commit", "pre-merge-commit"):
        assert (
            f"[fail] {n}: a file over the size limit gave 'accept', expected 'reject'"
        ) in out, out
    assert LIMIT not in out and "Result:" in out


def test_a_size_refusal_without_its_rule_id_fails(kit):
    replace_script(
        kit,
        "hooks/filesize.py",
        "import subprocess, sys\n"
        "staged = subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode\n"
        "sys.exit(3 if staged else 0)\n",
    )
    rc, out = check(kit)
    assert rc == 1, out
    for n in ("pre-commit", "pre-merge-commit"):
        assert (
            f"[fail] {n}: a file over the size limit gave "
            "'reject without [pre-commit.file-size]', expected 'reject'"
        ) in out, out


def test_the_probe_never_stages_in_the_calling_repository(kit, tmp_path):
    caller = tmp_path / "caller"
    subprocess.run(["git", "init", "-q", "--template=", str(caller)], check=True)
    index = caller / ".git" / "index"
    rc, out = check(
        kit,
        "--verbose",
        env={
            "GIT_DIR": str(caller / ".git"),
            "GIT_INDEX_FILE": str(index),
        },
    )
    assert not index.exists(), out
    assert "[pass] pre-commit: 2 probes as expected" in out, out
    assert "[pass] pre-merge-commit: 2 probes as expected" in out, out


def test_a_missing_module_stops_the_check_with_one_line(tmp_path):
    shutil.copy(CHECK, tmp_path / "check.py")
    p = subprocess.run(
        [sys.executable, str(tmp_path / "check.py")], capture_output=True, text=True
    )
    assert p.returncode == 2, p.stderr
    assert p.stdout == "" and len(p.stderr.splitlines()) == 1, p.stderr
    assert p.stderr.startswith("check.py: cannot load its modules ("), p.stderr


# ---------------------------------------------------------------- agents


def test_installed_agents_pass(kit):
    rc, out = check(kit, "--verbose")
    assert rc == 0, out
    for name in check_py.KIT_AGENTS:
        assert f"[pass] agent: {name}" in out
    assert "[pass] kit-judge.md only reads" in out


@pytest.mark.parametrize("mode", [(), ("--quick",)])
def test_removed_agent_is_one_line(kit, mode):
    (kit["home"] / "agents" / "kit-builder.md").unlink()
    rc, out = check(kit, *mode)
    assert rc == 1
    assert "[fail] agent missing: kit-builder.md: run the installer" in out
    assert out.count("kit-builder") == 1, out


def test_removed_judge_is_not_also_a_tools_problem(kit):
    (kit["home"] / "agents" / "kit-judge.md").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] agent missing: kit-judge.md: run the installer" in out
    assert "allows more than reading" not in out


def test_edited_agent_is_a_change_since_install(kit):
    with open(kit["home"] / "agents" / "kit-planner.md", "a") as f:
        f.write("\nmy own note\n")
    rc, out = check(kit)
    assert rc == 0, out
    assert (
        "Changes since install\n  [warn] changed since install: agents/kit-planner.md"
    ) in out


def test_other_agents_of_the_user_are_not_reported(kit):
    (kit["home"] / "agents" / "mine.md").write_text("my own agent\n")
    rc, out = check(kit)
    assert rc == 0, out
    assert "mine.md" not in out


JUDGE_TOOLS_LINE = "tools: Read, Grep, Glob\n"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (JUDGE_TOOLS_LINE, "tools: Read, Grep, Glob, Write\n"),
        (JUDGE_TOOLS_LINE, "tools: Read, Grep, Glob, Bash\n"),
        (JUDGE_TOOLS_LINE, "tools: Read, Grep, Glob\ntools: Edit\n"),
        (JUDGE_TOOLS_LINE, "tools:\n  - Read\n"),
        (JUDGE_TOOLS_LINE, ""),  # no tools line: every tool
        # An indented tools line is not the key: the real one is missing.
        (JUDGE_TOOLS_LINE, "description: |\n  tools: Read, Grep, Glob\n"),
        (JUDGE_TOOLS_LINE, "x:\n  tools: Read, Grep, Glob\n"),
        (JUDGE_TOOLS_LINE, JUDGE_TOOLS_LINE + '"tools": Bash\n'),
        (JUDGE_TOOLS_LINE, JUDGE_TOOLS_LINE + "  tools: Bash\n"),
        # YAML joins an indented line to the value above it, empty lines or not.
        (JUDGE_TOOLS_LINE, JUDGE_TOOLS_LINE + "  , Bash\n"),
        (JUDGE_TOOLS_LINE, JUDGE_TOOLS_LINE + "\n  , Bash\n"),
        # An indented --- closes no frontmatter either.
        ("tools: Read, Grep, Glob\n---\n", "tools: Read, Grep, Glob\n ---\n"),
        # An indented --- opens no frontmatter.
        ("---\nname: kit-judge\n", " ---\nname: kit-judge\n"),
    ],
)
def test_judge_that_may_do_more_than_read(kit, old, new):
    judge = kit["home"] / "agents" / "kit-judge.md"
    text = judge.read_text()
    assert text.count(JUDGE_TOOLS_LINE) == 1
    assert text.count(old) == 1
    judge.write_text(text.replace(old, new))
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "[fail] kit-judge.md allows more than reading: run the installer" in out


def test_judge_tools_line_outside_the_frontmatter_does_not_count(kit):
    judge = kit["home"] / "agents" / "kit-judge.md"
    text = judge.read_text().replace("tools: Read, Grep, Glob\n", "")
    judge.write_text(text + "\ntools: Read, Grep, Glob\n")
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "kit-judge.md allows more than reading" in out


def test_judge_with_crlf_line_endings_still_only_reads(kit):
    judge = kit["home"] / "agents" / "kit-judge.md"
    judge.write_bytes(judge.read_bytes().replace(b"\n", b"\r\n"))
    rc, out = check(kit, "--quick", "--verbose")
    assert rc == 0, out
    assert "[pass] kit-judge.md only reads" in out


def test_missing_manifest(kit):
    (kit["home"] / "pipelinekit" / "manifest.json").unlink()
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] install manifest not found: run the installer once" in out


def test_damaged_manifest_does_not_crash_the_checker(kit):
    (kit["home"] / "pipelinekit" / "manifest.json").write_text(
        '{"files": [], "commit": 5, "hooks_path": 7, "skills": 3,'
        ' "settings": "x", "checkout": 1}'
    )
    rc, out = check(kit)
    assert rc == 1, out
    assert (
        "[fail] install manifest damaged (commit is not text): run the installer once"
        in out
    )
    assert "check failed" not in out


# ---------------------------------------------------------------- probes


def test_guard_that_allows_everything(kit):
    replace_script(kit, "hooks/bash-guard.py", "#!/usr/bin/env python3\n")
    rc, out = check(kit)
    assert rc == 1
    assert "bash-guard.py: commit --no-verify gave 'allow', expected 'block'" in out
    assert "DROP TABLE through psql gave 'allow', expected 'ask'" in out
    assert "[warn] changed since install: hooks/bash-guard.py" in out
    # Without the probes the same install only shows a changed file.
    rc, out = check(kit, "--quick")
    assert rc == 0, out


def test_guard_that_blocks_everything(kit):
    replace_script(
        kit, "hooks/bash-guard.py", "#!/usr/bin/env python3\nraise SystemExit(2)\n"
    )
    rc, out = check(kit)
    assert rc == 1
    assert "a harmless git command gave 'block', expected 'allow'" in out


def test_guard_that_crashes(kit):
    replace_script(
        kit, "hooks/bash-guard.py", "#!/usr/bin/env python3\nraise RuntimeError\n"
    )
    rc, out = check(kit)
    assert rc == 1
    assert "a harmless git command gave 'exit 1', expected 'allow'" in out


def test_bare_repo_hook_that_allows_everything(kit):
    replace_script(kit, "hooks/block-bare-repo-markers.py", "#!/bin/sh\nexit 0\n")
    rc, out = check(kit)
    assert rc == 1
    assert "HEAD next to refs/ gave 'allow', expected 'block'" in out


def test_commit_msg_that_accepts_everything(kit):
    replace_script(kit, "git-hooks/commit-msg", "#!/bin/sh\nexit 0\n")
    rc, out = check(kit)
    assert rc == 1
    assert (
        "commit-msg: a non-conventional message gave 'accept', expected 'reject'" in out
    )


def test_pre_push_that_accepts_main(kit):
    replace_script(kit, "git-hooks/pre-push", "#!/bin/sh\nexit 0\n")
    rc, out = check(kit)
    assert rc == 1
    assert "pre-push: push to main gave 'accept', expected 'reject'" in out


# ---------------------------------------------------------------- settings


def test_hook_entry_removed_from_settings(kit):
    def drop(d):
        for g in d["hooks"]["PreToolUse"]:
            g["hooks"] = [
                h
                for h in g["hooks"]
                if not h["command"].endswith("block-bare-repo-markers.py")
                and h.get("args") != ["fetch", "curl"]
            ]

    edit_json(kit, "settings.json", drop)
    rc, out = check(kit, "--quick")
    assert rc == 1
    wired = "kit hook no longer wired: PreToolUse"
    assert f"{wired} Edit|Write -> block-bare-repo-markers.py" in out
    assert f"{wired} Bash -> bash-guard.py fetch curl" in out


def test_deny_rule_removed(kit):
    rule = "Read(.env.*)"
    edit_json(kit, "settings.json", lambda d: d["permissions"]["deny"].remove(rule))
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert f"[fail] settings.json: 1 kit deny rule missing: {rule}" in out


def test_ask_rule_removed_is_a_warning(kit):
    edit_json(kit, "settings.json", lambda d: d["permissions"]["ask"].pop())
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert "[warn] settings.json: 1 kit ask rule missing" in out


def test_attribution_switched_back_on(kit):
    edit_json(kit, "settings.json", lambda d: d.pop("attribution"))
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "[fail] settings.json: attribution not disabled" in out


def test_invalid_settings_json(kit):
    (kit["home"] / "settings.json").write_text("{not json")
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] settings.json: unreadable" in out


def test_missing_settings_json(kit):
    (kit["home"] / "settings.json").unlink()
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "[fail] settings.json: missing" in out


# ---------------------------------------------------------------- git


def git_config(kit, *args, cwd=None):
    subprocess.run(
        ["git", "config", *args], check=True, env=kit["env"], cwd=cwd or kit["root"]
    )


def test_hooks_path_changed_since_install(kit):
    git_config(kit, "--global", "core.hooksPath", "/elsewhere")
    rc, out = check(kit, "--quick")
    assert rc == 1
    assert "pointed at the kit when it was installed, now '/elsewhere'" in out
    assert f"fix: git config --global core.hooksPath {kit['home']}/git-hooks" in out


def test_hooks_path_never_enabled_is_not_a_problem(kit):
    git_config(kit, "--global", "--unset", "core.hooksPath")
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(hooks_path=""))
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert "[info] global core.hooksPath is 'unset' (kit git hooks inactive)" in out


def test_repository_with_its_own_hooks_path(kit, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=kit["env"])
    git_config(kit, "core.hooksPath", ".husky", cwd=tmp_path)
    rc, out = check(kit, cwd=tmp_path)
    assert rc == 0, out
    assert "[warn] this repository sets its own core.hooksPath (.husky)" in out


# ---------------------------------------------------------------- output


def test_json_report(kit):
    rc, out = check(kit, "--json")
    assert rc == 0, out
    d = json.loads(out)
    assert set(d) == {
        "schema",
        "home",
        "mode",
        "kit",
        "healthy",
        "counts",
        "repair",
        "results",
        "update",
        "activity",
    }
    assert d["update"] == {"state": "off"}
    assert d["healthy"] is True and d["mode"] == "full"
    assert d["counts"]["fail"] == 0 and d["counts"]["pass"] > 20
    assert d["kit"]["checkout"] == str(REPO)
    assert re.fullmatch(r"[0-9a-f]{40}", d["kit"]["commit"])
    assert all({"section", "level", "msg"} <= set(r) for r in d["results"])
    assert {r["section"] for r in d["results"]} == {
        "install",
        "drift",
        "probe",
        "environment",
        "update",
        "activity",
    }


def test_json_report_of_a_broken_install(kit):
    (kit["home"] / "hooks" / "post-edit-format.sh").unlink()
    rc, out = check(kit, "--json", "--quick")
    d = json.loads(out)
    assert rc == 1 and d["healthy"] is False and d["mode"] == "quick"
    assert d["counts"]["fail"] >= 1
    assert not any(r["section"] == "probe" for r in d["results"])


def test_exit_zero_still_reports_the_problem(kit):
    (kit["home"] / "hooks" / "bash-guard.py").unlink()
    rc, out = check(kit, "--exit-zero")
    assert rc == 0
    assert "[fail] hook missing: bash-guard.py" in out


def test_messages_are_one_printable_line():
    assert check_py.clean("a\x1b[31mb\nc\td") == "a [31mb c d"
    assert len(check_py.clean("x" * 999)) == 300


def test_remote_url_loses_its_credentials():
    strip = check_py.without_credentials
    assert (
        strip("https://user:token@example.com/o/r.git") == "https://example.com/o/r.git"
    )
    assert strip("https://example.com/o/r.git") == "https://example.com/o/r.git"
    assert strip("git@example.com:o/r.git") == "git@example.com:o/r.git"


# ---------------------------------------------------------------- manifest


def test_manifest_describes_the_install(kit):
    m = json.loads((kit["home"] / "pipelinekit" / "manifest.json").read_text())
    assert m["schema"] == check_py.SCHEMA
    assert m["checkout"] == str(REPO)
    assert m["hooks_path"] == f"{kit['home']}/git-hooks"
    assert m["skills"] == sorted(check_py.KIT_SKILLS)
    files = m["files"]
    for rel in (
        "hooks/bash-guard.py",
        "git-hooks/pre-push",
        "git-hooks/pre-merge-commit",
        "skills/kit/check.py",
        "skills/kit/SKILL.md",
        "config/never-stage.txt",
        "CLAUDE.md",
        "agents/kit-planner.md",
        "agents/kit-builder.md",
        "agents/kit-judge.md",
    ):
        assert rel in files
    assert all(files.values()), "a file was listed but not installed"
    assert not any(
        "__pycache__" in rel or "/tests/" in rel
        for rel in files
        if rel.startswith("hooks/")
    )
    assert len(m["settings"]["hooks"]) == 12
    assert "Read(.env)" in m["settings"]["deny"]


def test_skill_list_matches_the_repo_and_the_installer():
    in_repo = sorted(
        p.name
        for p in (REPO / "claude" / "skills").iterdir()
        if (p / "SKILL.md").is_file()
    )
    assert list(check_py.KIT_SKILLS) == in_repo
    text = (REPO / "scripts" / "install.sh").read_text()
    listed = re.search(r"^KIT_SKILLS=\(([^)]*)\)", text, re.M).group(1).split()
    assert sorted(listed) == in_repo


def test_only_a_folder_with_skill_md_counts_as_a_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    src = tmp_path / "repo" / "claude"
    for d in ("hooks", "git-hooks", "config", "skills/kept", "skills/bare"):
        (src / d).mkdir(parents=True)
    (src / "config" / "settings.template.json").write_text("{}\n")
    (src / "skills" / "kept" / "SKILL.md").write_text("kept\n")
    (src / "skills" / "kept" / "tool.py").write_text("")
    (src / "skills" / "bare" / "tool.py").write_text("")
    repo = str(tmp_path / "repo")
    assert check_py.skill_dirs(repo) == ["kept"]
    skills = [f for f in check_py.kit_files(repo) if f.startswith("skills/")]
    assert skills == ["skills/kept/SKILL.md", "skills/kept/tool.py"]
    m = json.loads(
        Path(check_py.write_manifest(repo, str(tmp_path / "home"))).read_text()
    )
    assert m["skills"] == ["kept"]
    assert [f for f in m["files"] if f.startswith("skills/")] == skills


def test_agent_list_matches_the_repo_and_the_installer():
    in_repo = sorted(p.name for p in (REPO / "claude" / "agents").iterdir())
    assert sorted(check_py.KIT_AGENTS) == in_repo
    text = (REPO / "scripts" / "install.sh").read_text()
    listed = re.search(r"^KIT_AGENTS=\(([^)]*)\)", text, re.M).group(1).split()
    assert sorted(listed) == in_repo
    assert len(set(listed)) == len(listed)


def test_hook_lists_match_the_repo():
    hooks = sorted(
        p.name
        for p in (REPO / "claude" / "hooks").iterdir()
        if p.is_file() and p.suffix in (".py", ".sh")
    )
    assert sorted(check_py.HOOKS + check_py.HELPERS) == hooks
    git_hooks = sorted(p.name for p in (REPO / "claude" / "git-hooks").iterdir())
    assert sorted(check_py.GIT_HOOKS) == git_hooks


def test_environment_covers_what_the_ship_skill_needs(kit):
    rc, out = check(kit, "--verbose")
    assert rc == 0, out
    assert re.search(r"\[pass\] gh: \S|\[info\] gh not installed", out)
    assert re.search(r"\[pass\] playwright: \S|\[info\] playwright not installed", out)
    rc, out = check(kit, "--verbose", "--quick")
    assert rc == 0 and "playwright" not in out


PLUGIN_LINE = "frontend-design is also enabled"


def plugin_lines(out):
    return [ln for ln in out.splitlines() if PLUGIN_LINE in ln]


def enable_plugins(kit, plugins):
    edit_json(kit, "settings.json", lambda d: d.update(enabledPlugins=plugins))


def test_duplicate_frontend_design_plugin_is_one_info_line(kit):
    key = "frontend-design@claude-plugins-official"
    enable_plugins(kit, {key: True})
    for args in ((), ("--quick",)):
        rc, out = check(kit, *args)
        assert rc == 0, out
        (line,) = plugin_lines(out)
        assert line.startswith("  [info] ") and "/plugin" in line
        assert line.endswith(f"Plugin: {key}")
    rc, out = check(kit, "--json")
    d = json.loads(out)
    assert rc == 0 and d["healthy"] is True
    (item,) = [r for r in d["results"] if PLUGIN_LINE in r["msg"]]
    assert item["level"] == "info" and item["section"] == "environment"
    assert len(item["msg"]) <= 300
    # The fixed text and the longest line it can make stay below clean()'s limit.
    note = check_py.DESIGN_PLUGIN_NOTE
    assert item["msg"] == f"{note} Plugin: {key}"
    assert len(note) == 221 and len(f"{note} Plugin: ") == 230
    assert len(f"{note} Plugin: {'x' * 40} and 9999 more") == 284

    enable_plugins(kit, {"frontend-design@y": True, "frontend-design@x": True})
    (line,) = plugin_lines(check(kit, "--quick")[1])
    assert line.endswith("Plugin: frontend-design@x and 1 more")

    # A key that is not exactly name@marketplace is not counted, nor repeated.
    odd = "frontend-design@x PLANTED words"
    enable_plugins(kit, {odd: True})
    for args in (("--quick",), ("--quick", "--json")):
        rc, out = check(kit, *args)
        assert rc == 0 and "PLANTED" not in out, out
        assert not plugin_lines(out)

    enable_plugins(kit, {odd: True, "frontend-design@x": True})
    rc, out = check(kit, "--quick")
    assert "PLANTED" not in out
    (line,) = plugin_lines(out)
    assert line.endswith("Plugin: frontend-design@x")

    # A valid key too long to repeat is counted.
    enable_plugins(kit, {"frontend-design@" + "a" * 25: True})
    (line,) = plugin_lines(check(kit, "--quick")[1])
    assert "/plugin" in line
    assert line.endswith("Plugin entries: 1") and "a" * 25 not in line

    longest = "frontend-design@" + "a" * 24
    assert len(longest) == 40
    enable_plugins(kit, {longest: True})
    (line,) = plugin_lines(check(kit, "--quick")[1])
    assert line.endswith(f"Plugin: {longest}")


@pytest.mark.parametrize(
    "plugins",
    [
        {"other@x": True},
        {"frontend-design@x": False},
        {"frontend-design@x": "true"},
        {"frontend-design@x": 1},
        ["frontend-design@x"],
        "frontend-design@x",
        {"frontend-design-system@x": True},
        {"my-frontend-design@x": True},
        {"frontend-design@claude-plugins-official ": True},
        {"frontend-design@": True},
        {"frontend-design": True},
        {"frontend-design@x\n": True},
        {"frontend-design@x/y": True},
    ],
    ids=[
        "absent",
        "false",
        "string",
        "one",
        "list",
        "text",
        "longer-name",
        "prefixed-name",
        "trailing-space",
        "no-marketplace",
        "bare-name",
        "trailing-newline",
        "slash",
    ],
)
def test_no_plugin_line_otherwise(kit, plugins):
    enable_plugins(kit, plugins)
    rc, out = check(kit, "--quick")
    assert rc == 0, out
    assert not plugin_lines(out)


def test_no_plugin_line_without_the_kit_copy(kit):
    enable_plugins(kit, {"frontend-design@claude-plugins-official": True})
    (kit["home"] / "skills" / "frontend-design" / "SKILL.md").unlink()
    for args in ((), ("--quick",)):
        rc, out = check(kit, *args)
        assert rc == 1
        assert "[fail] skill missing: frontend-design" in out
        assert not plugin_lines(out)
        assert "two copies" not in out


def test_no_plugin_line_with_unreadable_settings(kit):
    (kit["home"] / "settings.json").write_text("{not json")
    rc, out = check(kit)
    assert rc == 1
    assert "[fail] settings.json: unreadable" in out
    assert not plugin_lines(out)
