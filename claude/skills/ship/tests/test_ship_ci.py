"""Which workflows ship.py counts as CI for a pull request: the `on:` block decides."""

import pytest
import ship_ci
from ship_fixtures import gates, last_line

BRANCH = "feat/1-thing"


@pytest.mark.parametrize(
    "text",
    [
        "on: push\n",
        "on: [push]\n",
        "'on': [push, workflow_dispatch]\n",
        '"on":\n  push:\n',
        "on:\n  - push\n",
        "on:\n- push\n",
        "on: {push: {branches: ['feat/**']}}\n",
        "on:\n  push:\n    branches:\n      - main\n      - 'feat/*'\n",
        "on:\n  push:\n    branches: [main,\n      feat/**]\n",
        "on:\n  push:\n    branches-ignore: [main]\n",
        "on:\n  push:\n    paths: ['src/**']\n",
        "on:\n  push:\n    branches: ['**', '!main']\n",
        "name: ci\non:  # every push\n  push:\njobs:\n  test:\n    runs-on: x\n",
        "on: pull_request\n",
        "on:\n  pull_request_target:\n    branches: [main]\n",
        "on:\n  pull_request:\n    types: [opened]\n",
    ],
)
def test_a_workflow_that_runs_for_the_branch(text):
    assert ship_ci.runs_for(text, BRANCH)


@pytest.mark.parametrize(
    "text",
    [
        "# runs on pull_request and push some day\non: workflow_dispatch\n",
        "on: [workflow_dispatch]  # pull_request later\n",
        "on:\n  push:\n    branches: [main]\n",
        "on:\n  push:\n    branches: ['*']\n",  # * stays within one part
        "on:\n  push:\n    branches: ['feat/**', '!feat/1-*']\n",
        "on:\n  push:\n    branches-ignore: ['feat/**']\n",
        "on:\n  push:\n    tags: ['v*']\n",
        "on:\n  schedule:\n    - cron: '0 3 * * *'\n",
        "on: {workflow_dispatch: {inputs: {push: {type: string}}}}\n",
        "on:\n  workflow_dispatch:\n    inputs:\n      pull_request:\n"
        "        type: string\n",
        "on:\n  workflow_dispatch:\njobs:\n  push:\n    steps:\n"
        "      - run: git push\n",
        "name: no trigger at all\n",
        "",
    ],
)
def test_a_workflow_that_does_not_run_for_the_branch(text):
    assert not ship_ci.runs_for(text, BRANCH)


def test_a_block_that_cannot_be_read_counts_when_it_names_an_event():
    assert ship_ci.runs_for("on: [push, {\n", BRANCH)
    assert not ship_ci.runs_for("on: [schedule, {\n", BRANCH)
    assert not ship_ci.runs_for("on: [schedule, {  # push\n", BRANCH)


def test_ready_for_review_counts_only_in_the_types_of_a_pull_request_trigger():
    ready = "on:\n  pull_request:\n    types: [opened, ready_for_review]\n"
    assert ship_ci.starts_when_ready(ready)
    assert ship_ci.starts_when_ready("on: {pull_request: {types: ready_for_review}}")
    commented = "on:\n  pull_request:\n    # types: [ready_for_review]\n"
    assert not ship_ci.starts_when_ready(commented)
    assert not ship_ci.starts_when_ready("on: push\n# ready_for_review\n")


def test_a_push_only_workflow_is_expected_ci(sb):
    sb.workflow("on: [push]\n")
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[]))
    done = sb.ship("status")
    assert "ready to merge" not in done.stdout
    assert "pushes to this branch" in done.stdout
    assert gates(sb.ship("status", "--json"))["ci"]["state"] == "pending"
    done = sb.ship("wait", "--grace", "0")
    assert done.returncode == 1 and "no check has shown up" in done.stdout
    done = sb.ship("merge", "--grace", "0")
    assert done.returncode == 1 and sb.calls("pr merge") == []


def test_a_word_in_a_comment_is_not_a_trigger(sb):
    sb.workflow("# pull_request and push: later\non: workflow_dispatch\n")
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[]))
    assert last_line(sb.ship("status")) == "Result: ready to merge"
    # No first check to wait for: wait answers at once, as status does.
    done = sb.ship("wait", "--timeout", "5")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "no CI checks" in done.stdout


@pytest.mark.parametrize(
    "message, tag",
    [
        ("chore: bump to 1.2.4 [skip ci]", "[skip ci]"),
        ("docs: release titles\n\n- chore: 1.2.0 [ci skip]\n", "[ci skip]"),
        ("fix: thing [no ci]", "[no ci]"),
        ("fix: thing [skip actions]", "[skip actions]"),
        ("fix: thing [actions skip]", "[actions skip]"),
        ("fix: thing\n\nMore words.\n\nskip-checks: true\n", "skip-checks: true"),
        ("fix: thing\n\nskip-checks:true", "skip-checks: true"),
        ("fix: thing\r\n\r\nskip-checks: true\r\n", "skip-checks: true"),
        (
            "fix: thing\n\nSigned-off-by: A <a@example.com>\nskip-checks: true",
            "skip-checks: true",
        ),
    ],
)
def test_a_message_that_asks_github_to_skip_the_workflows(message, tag):
    assert ship_ci.skip_request(message) == tag


@pytest.mark.parametrize(
    "message",
    [
        "fix: skip ci on docs-only changes",
        "fix: thing [skip-ci]",
        "fix: thing\n\nskip-checks: true\n\nA paragraph after it.",
        "fix: thing\n\nskip-checks: false",
        "fix: thing\n\nWe do not use skip-checks: true here.",
        "",
    ],
)
def test_a_message_that_does_not_ask_github_to_skip_them(message):
    assert ship_ci.skip_request(message) == ""


def skip_tagged(sb, message="chore: notes for 1.2.0 [skip ci]"):
    """A head commit whose message holds a skip tag, and no check on it."""
    sb.workflow()
    sb.commit(message)
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[]))


def test_a_head_commit_that_asks_github_to_skip_the_checks(sb):
    skip_tagged(sb)
    ci = gates(sb.ship("status", "--json"))["ci"]
    assert ci["state"] == "fail", ci
    assert "[skip ci]" in ci["detail"]
    assert "push a commit without the tag" in ci["detail"]
    done = sb.ship("status")
    assert done.returncode == 1
    assert "push a commit without the tag" in done.stdout
    # No run will come: wait answers at once instead of after the grace time.
    done = sb.ship("wait", "--grace", "600", timeout=60)
    assert done.returncode == 1, done.stdout + done.stderr
    lines = done.stdout.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("CI FAIL: "), lines
    assert "[skip ci]" in lines[0] and "push a commit without the tag" in lines[0]
    assert "waiting" not in done.stderr
    done = sb.ship("merge", "--grace", "600", timeout=60)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "push a commit without the tag" in last_line(done)
    assert sb.calls("pr merge") == [] and sb.calls("pr ready") == []


def test_a_skip_checks_trailer_is_named_too(sb):
    skip_tagged(sb, "chore: thing\n\nskip-checks: true")
    ci = gates(sb.ship("status", "--json"))["ci"]
    assert ci["state"] == "fail" and "skip-checks: true" in ci["detail"]


def test_without_the_tag_on_the_head_nothing_changes(sb):
    sb.workflow()
    sb.commit("chore: bump [skip ci]")
    sb.commit("fix: after it")
    sb.passed()
    sb.state(pr=sb.pr(statusCheckRollup=[]))
    ci = gates(sb.ship("status", "--json"))["ci"]
    assert ci["state"] == "pending" and "no check has shown up yet" in ci["detail"]
    done = sb.ship("wait", "--grace", "0")
    assert done.returncode == 1 and "no check has shown up after" in done.stdout
    # A head GitHub names but the checkout does not hold: as before.
    sb.state(pr=sb.pr(headRefOid="0" * 40, statusCheckRollup=[]))
    ci = gates(sb.ship("status", "--json"))["ci"]
    assert ci["state"] == "pending" and "no check has shown up yet" in ci["detail"]


def test_checks_on_a_tagged_head_count_as_usual(sb):
    skip_tagged(sb)
    sb.state(pr=sb.pr())
    assert gates(sb.ship("status", "--json"))["ci"]["state"] == "pass"
    done = sb.ship("wait", "--grace", "600", timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    # --allow-no-checks: no workflow is expected, so no tag is looked for.
    sb.state(pr=sb.pr(statusCheckRollup=[]))
    done = sb.ship("status", "--json", "--allow-no-checks")
    assert gates(done)["ci"]["state"] == "pass"
    assert sb.ship("wait", "--allow-no-checks").returncode == 0
