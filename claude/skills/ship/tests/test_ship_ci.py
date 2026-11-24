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
