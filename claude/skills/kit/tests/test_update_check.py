"""check.py's Updates section: is origin ahead of the install?

The install comes from test_check.py; origin is a local repository.
"""

import json
import os
import subprocess
import time

import pytest
import test_check as base
from test_check import check, check_py, edit_json, state

# The install of test_check.py, made once for this module too.
installed = base.installed
kit = base.kit


# ---------------------------------------------------------------- updates

ON = {"PIPELINEKIT_UPDATE_CHECK": "1"}


def git(kit, cwd, *args):
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
        env=kit["env"],
    )
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


@pytest.fixture
def tracked(kit, tmp_path):
    """The install says it came from a checkout whose origin is a local repo."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(kit, tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(kit, tmp_path, "init", "-q", "-b", "main", str(work))
    (work / "f0").write_text("0\n")
    git(kit, work, "add", "f0")
    git(kit, work, "commit", "-qm", "feat: start")
    git(kit, work, "remote", "add", "origin", str(origin))
    git(kit, work, "push", "-q", "origin", "main")
    head = git(kit, work, "rev-parse", "HEAD")
    edit_json(
        kit,
        "pipelinekit/manifest.json",
        lambda d: d.update(checkout=str(work), branch="main", commit=head),
    )
    return {"kit": kit, "work": work, "origin": origin, "head": head}


def commit_in(t, repo, subject="feat: more"):
    n = len(list(repo.iterdir()))
    (repo / f"f{n}").write_text("x\n")
    git(t["kit"], repo, "add", "-A")
    git(t["kit"], repo, "commit", "-qm", subject)
    return git(t["kit"], repo, "rev-parse", "HEAD")


def push_commit(t, subject="feat: more"):
    """Somebody else pushes to origin; the checkout does not know yet."""
    other = t["work"].parent / "other"
    if not other.exists():
        git(t["kit"], other.parent, "clone", "-q", str(t["origin"]), str(other))
    new = commit_in(t, other, subject)
    git(t["kit"], other, "push", "-q", "origin", "main")
    return new


def cache(kit):
    return state(kit) / "update.json"


def test_up_to_date(tracked):
    kit = tracked["kit"]
    rc, out = check(kit, "--verbose", env=ON)
    assert rc == 0, out
    line = (
        f"[pass] up to date with origin/main ({tracked['head'][:7]}, checked just now)"
    )
    assert "Updates\n" in out and line in out
    assert out.rstrip().endswith("Result: healthy")
    saved = json.loads(cache(kit).read_text())
    assert saved["state"] == "ok" and saved["commit"] == tracked["head"]
    assert cache(kit).stat().st_mode & 0o777 == 0o600


def test_update_available_is_information_not_a_problem(tracked):
    kit = tracked["kit"]
    new = push_commit(tracked)
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert (
        f"[info] update available: origin/main is at {new[:7]}, "
        f"this install is from {tracked['head'][:7]} (checked just now)"
    ) in out
    assert "fix: /kit update in a session, or from a shell: python3 " in out
    assert "[warn]" not in out and out.rstrip().endswith("Result: healthy")
    rc, out = check(kit, "--json", env=ON)
    d = json.loads(out)
    assert rc == 0 and d["healthy"] is True
    assert d["update"]["state"] == "available"
    assert d["update"]["remote"] == new and d["update"]["installed"] == tracked["head"]


def test_update_counts_the_commits_it_can_see(tracked):
    kit = tracked["kit"]
    push_commit(tracked)
    new = push_commit(tracked)
    git(kit, tracked["work"], "fetch", "-q", "origin")
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert f"origin/main is at {new[:7]}, 2 commits ahead, this install" in out


def test_remote_is_asked_once_a_day(tracked):
    kit = tracked["kit"]
    check(kit, env=ON)
    new = push_commit(tracked)
    rc, out = check(kit, "--verbose", env=ON)
    assert "[pass] up to date with origin/main" in out, out
    saved = json.loads(cache(kit).read_text())
    saved["checked_at"] -= 5 * 3600
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, "--verbose", env=ON)
    assert "up to date with origin/main" in out and "checked 5 hours ago" in out
    saved["checked_at"] -= 20 * 3600
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, env=ON)
    assert f"update available: origin/main is at {new[:7]}" in out, out


@pytest.mark.parametrize(
    "junk", ["", "not json", "[]", '{"state": "ok"}', '{"checked_at": true}']
)
def test_broken_cache_is_ignored(tracked, junk):
    kit = tracked["kit"]
    cache(kit).parent.mkdir(parents=True, exist_ok=True)
    cache(kit).write_text(junk)
    rc, out = check(kit, "--verbose", env=ON)
    assert rc == 0 and "[pass] up to date with origin/main" in out, out


def test_cache_of_another_checkout_is_not_used(tracked):
    kit = tracked["kit"]
    check(kit, env=ON)
    saved = json.loads(cache(kit).read_text())
    saved.update(checkout="/somewhere/else", commit="0" * 40)
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, "--verbose", env=ON)
    assert "[pass] up to date with origin/main" in out, out


def test_unreachable_origin_is_not_a_problem(tracked):
    kit = tracked["kit"]
    git(
        kit, tracked["work"], "remote", "set-url", "origin", str(tracked["work"] / "no")
    )
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert "[info] not checked: origin did not answer" in out
    assert out.rstrip().endswith("Result: healthy")
    assert json.loads(cache(kit).read_text())["state"] == "unreachable"
    # An hour later it is asked again; an answer would be kept for a day.
    git(kit, tracked["work"], "remote", "set-url", "origin", str(tracked["origin"]))
    rc, out = check(kit, env=ON)
    assert "not checked: origin did not answer" in out
    saved = json.loads(cache(kit).read_text())
    saved["checked_at"] -= 2 * 3600
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, "--verbose", env=ON)
    assert "[pass] up to date with origin/main" in out, out


def test_branch_gone_from_origin(tracked):
    kit = tracked["kit"]
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(branch="old"))
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert "[info] not checked: origin has no branch old, checked just now" in out


@pytest.mark.parametrize(
    "change, said",
    [
        ({"checkout": "/no/such/checkout"}, "the checkout this install was made from"),
        ({"checkout": ""}, "the checkout this install was made from"),
        ({"commit": "abc"}, "the install manifest names no commit"),
        ({"branch": ""}, "the install was made from a checkout that was on no branch"),
        (
            {"branch": "--upload-pack=touch pwned"},
            "the branch in the install manifest is not a name the kit takes",
        ),
    ],
)
def test_update_not_checked(tracked, change, said):
    kit = tracked["kit"]
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(change))
    rc, out = check(kit, env=ON, cwd=tracked["work"].parent)
    assert rc == 0, out
    assert f"[info] not checked: {said}" in out
    assert not cache(kit).exists()
    assert not (tracked["work"].parent / "pwned").exists()


def test_update_check_switched_off(tracked):
    kit = tracked["kit"]
    push_commit(tracked)
    rc, out = check(kit)
    assert rc == 0, out
    assert "[info] the update check is switched off (PIPELINEKIT_UPDATE_CHECK=0)" in out
    assert "update available" not in out and not cache(kit).exists()


def test_quick_has_no_update_check(tracked):
    kit = tracked["kit"]
    rc, out = check(kit, "--quick", "--verbose", env=ON)
    assert rc == 0 and "Updates" not in out and not cache(kit).exists(), out
    assert json.loads(check(kit, "--quick", "--json", env=ON)[1])["update"] == {}


NO_ANSWER = (
    "[info] not checked: no recent answer of origin, and --no-remote does not ask it"
)


def test_no_remote_uses_only_a_recent_answer(tracked):
    kit = tracked["kit"]
    rc, out = check(kit, "--no-remote", env=ON)
    assert rc == 0 and NO_ANSWER in out and not cache(kit).exists(), out
    assert out.rstrip().endswith("Result: healthy")
    check(kit, env=ON)
    rc, out = check(kit, "--no-remote", env=ON)
    assert "[pass] up to date with origin/main" in out, out
    saved = json.loads(cache(kit).read_text())
    saved["checked_at"] -= 25 * 3600
    cache(kit).write_text(json.dumps(saved))
    rc, out = check(kit, "--no-remote", "--json", env=ON)
    d = json.loads(out)
    assert d["update"] == {"state": "unknown"}
    assert [i["msg"] for i in d["results"] if i["section"] == "update"] == [
        NO_ANSWER.removeprefix("[info] ")
    ]


def test_checkout_ahead_of_the_install(tracked):
    kit = tracked["kit"]
    new = commit_in(tracked, tracked["work"])
    rc, out = check(kit, "--verbose", env=ON)
    assert rc == 0, out
    assert (
        f"[info] the checkout is at {new[:7]}, this install was made from "
        f"{tracked['head'][:7]}: the installer brings the install in line"
    ) in out
    assert "fix: bash " in out and "scripts/install.sh" in out
    assert "[pass] up to date with origin/main" in out


def test_install_ahead_of_origin(tracked):
    kit = tracked["kit"]
    new = commit_in(tracked, tracked["work"])
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(commit=new))
    rc, out = check(kit, "--verbose", env=ON)
    assert rc == 0, out
    assert f"[pass] ahead of origin/main: this install is from {new[:7]}" in out
    assert "update available" not in out


def test_remote_call_ends_with_its_children():
    start = time.time()
    rc, out = check_py.run_group(
        ["sh", "-c", "sleep 30 & sleep 30"], dict(os.environ), 1
    )
    assert (rc, out) == (None, "") and time.time() - start < 10
    assert check_py.run_group(["/no/such/program"], dict(os.environ), 1) == (None, "")
    assert check_py.run_group(["sh", "-c", "echo hi"], dict(os.environ), 5) == (
        0,
        "hi\n",
    )


def test_age_in_words():
    assert check_py.age(5) == "just now"
    assert check_py.age(600) == "10 minutes ago"
    assert check_py.age(3 * 3600) == "3 hours ago"


def test_updates_line_is_shown_without_verbose(tracked):
    # It says when origin was asked; a folded "[pass] 1 check" would hide that.
    kit = tracked["kit"]
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    updates = out.split("Updates\n")[1].splitlines()[0]
    head = tracked["head"][:7]
    assert updates == f"  [pass] up to date with origin/main ({head}, checked just now)"
    new = commit_in(tracked, tracked["work"])
    edit_json(kit, "pipelinekit/manifest.json", lambda d: d.update(commit=new))
    rc, out = check(kit, env=ON)
    assert f"[pass] ahead of origin/main: this install is from {new[:7]}" in out


def test_no_answer_says_when_it_was_asked_and_how_to_ask_again(tracked):
    kit = tracked["kit"]
    work = tracked["work"]
    git(kit, work, "remote", "set-url", "origin", str(work / "no"))
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert (
        "[info] not checked: origin did not answer (offline, no access or no such "
        "remote), checked just now"
    ) in out
    assert "fix: origin is asked again 1 hour after that; to ask now: python3 " in out
    assert "skills/kit/check.py --refresh" in out
    saved = json.loads(cache(kit).read_text())
    saved["checked_at"] -= 30 * 60
    cache(kit).write_text(json.dumps(saved))
    git(kit, work, "remote", "set-url", "origin", str(tracked["origin"]))
    rc, out = check(kit, env=ON)
    assert "did not answer (offline, no access or no such remote), checked 30 " in out
    rc, out = check(kit, "--refresh", env=ON)
    assert rc == 0 and "[pass] up to date with origin/main" in out, out
    assert json.loads(cache(kit).read_text())["state"] == "ok"


def test_refresh_asks_although_an_answer_is_stored(tracked):
    kit = tracked["kit"]
    check(kit, env=ON)
    new = push_commit(tracked)
    assert "up to date with origin/main" in check(kit, env=ON)[1]
    rc, out = check(kit, "--refresh", env=ON)
    assert rc == 0 and f"update available: origin/main is at {new[:7]}" in out, out


def test_refresh_and_no_remote_do_not_go_together(tracked):
    rc, out = check(tracked["kit"], "--refresh", "--no-remote", env=ON)
    assert rc == 2 and "not allowed with argument" in out, out


def test_a_folder_that_is_no_git_checkout_is_named_so(tracked):
    kit = tracked["kit"]
    folder = tracked["work"].parent / "plain"
    folder.mkdir()
    edit_json(
        kit, "pipelinekit/manifest.json", lambda d: d.update(checkout=str(folder))
    )
    rc, out = check(kit, env=ON)
    assert rc == 0, out
    assert (
        "[info] not checked: the folder this install was made from is not a git "
        "checkout"
    ) in out


def test_origin_is_asked_while_the_other_checks_run(tracked, monkeypatch, tmp_path):
    # A remote that does not answer costs no time of its own: it is asked
    # while the probes run, and they take seconds anyway.
    asked = []

    def slow_remote(checkout, branch):
        time.sleep(2)
        asked.append(branch)
        return {"state": "unreachable", "commit": ""}

    monkeypatch.setenv("PIPELINEKIT_UPDATE_CHECK", "1")
    monkeypatch.setenv("PIPELINEKIT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tracked["kit"]["user"]))
    monkeypatch.setattr(check_py, "ask_remote", slow_remote)
    monkeypatch.setattr(check_py, "probe", lambda c: time.sleep(2))
    monkeypatch.setattr(check_py, "check_environment", lambda c: None)
    start = time.time()
    c = check_py.run_checks(str(tracked["kit"]["home"]), False)
    took = time.time() - start
    assert asked == ["main"]
    assert took < 3.5, took
    msgs = [i["msg"] for i in c.items if i["section"] == "update"]
    assert msgs and msgs[0].startswith("not checked: origin did not answer"), msgs
    c = check_py.run_checks(str(tracked["kit"]["home"]), True)
    assert asked == ["main"] and c.update == {}


def test_no_remote_and_a_stored_answer_start_no_call(tracked, monkeypatch, tmp_path):
    def no_call(checkout, branch):
        raise AssertionError("origin was asked")

    monkeypatch.setenv("PIPELINEKIT_UPDATE_CHECK", "1")
    monkeypatch.setenv("PIPELINEKIT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(check_py, "ask_remote", no_call)
    c = check_py.Check(str(tracked["kit"]["home"]), False)
    c.remote = False
    check_py.start_update(c)
    assert c.asking is None
    check_py.store_answer(
        str(tracked["work"]),
        "main",
        {"state": "ok", "commit": tracked["head"], "checked_at": int(time.time())},
    )
    c.remote = True
    check_py.start_update(c)
    assert c.asking is None
