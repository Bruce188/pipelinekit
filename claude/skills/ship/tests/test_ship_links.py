"""The linked gate and the follow-up of a merge for the issues a pull request closes."""

import json
from types import SimpleNamespace

import ship_links
from ship_fixtures import BRANCH, gates, last_line, ref, refused, ship

TEAM = "feat/2-base"  # a working branch other than the default one, main


def release(number=12, login="me", body="Release notes", cross=False):
    return {
        "number": number,
        "author": {"login": login},
        "body": body,
        "isCrossRepository": cross,
    }


def onto(sb, base, pr):
    """The pull request's fields, with its base pushed as a copy of main."""
    if not base:
        return pr or {}
    sb.git("push", "-q", "origin", f"main:{base}")
    return {"baseRefName": base, **(pr or {})}


def passed(sb, base=None):
    """A judge record and a passed test record against `base`."""
    if not base:
        return sb.passed()
    sb.judged(base=base, base_ref=f"refs/remotes/origin/{base}")
    done = sb.ship("record", "--result", "pass", "--release", "no")
    assert done.returncode == 0, done.stderr


def linked(sb, pr=None, base=None, **state):
    """The linked gate of `ship.py status`: (state, detail)."""
    sb.state(pr=sb.pr(**onto(sb, base, pr)), **state)
    done = sb.ship("status", "--json", "--exit-zero")
    assert done.returncode == 0, done.stdout + done.stderr
    found = gates(done)["linked"]
    return found["state"], found["detail"]


def merged(sb, pr=None, base=None, **state):
    """Merge #7 and return what ship printed, one line each."""
    over = {"isDraft": False, "mergeStateStatus": "CLEAN", **onto(sb, base, pr)}
    sb.state(pr=sb.pr(**over), **state)
    passed(sb, base)
    done = sb.ship("merge", "--stay")
    assert done.returncode == 0, done.stdout + done.stderr
    into = over.get("baseRefName", "main")
    assert last_line(done) == f"Merged #7 into {into} (squash) at {sb.head()[:7]}."
    assert [row[2] for row in sb.calls("pr merge")] == ["7"]
    assert sb.calls("pr ready") == []
    return done.stdout.strip().splitlines()


def fake_repo(answer=(0, "{}", ""), default="main", user="me"):
    info = {"nameWithOwner": "o/r", "defaultBranchRef": {"name": default}}
    return SimpleNamespace(
        info=lambda: info, user=lambda: user, gh=lambda *args, **more: answer
    )


# ---------------------------------------------------------------- reading the body


def test_named_tells_closing_listed_and_misspelt_issues_apart():
    found = ship_links.named(
        "Fixes #3 and #4\nCloses: #5\nResolves #6, #7 & #8\nClosing #9\n"
        "Refs #10, see issue #11, part of #12\n<!-- Closes #13 -->\nfixs #14"
    )
    assert found == {
        3: ("closes", "Fixes"),
        4: ("only", "Fixes", 3),
        5: ("closes", "Closes"),
        6: ("closes", "Resolves"),
        7: ("only", "Resolves", 6),
        8: ("only", "Resolves", 6),
        9: ("word", "Closing #9"),
        14: ("word", "fixs #14"),
    }
    assert ship_links.closed_by("Closes #1, #2\nfixed #3") == {1, 3}


def test_the_issue_of_the_branch_comes_first():
    assert ship_links.wanted("feat/260-issue-links", "Closes #4")[0] == [260, 4]
    assert ship_links.wanted("fix/12", "Closes #12")[0] == [12]
    for head in ("release/2.0", "feat/v2-thing", "260-thing", "main"):
        assert ship_links.wanted(head, "")[0] == []


# ------------------------------------------------------------ into the default branch


def test_linked_passes_when_github_lists_the_issue(sb):
    assert linked(sb) == ("pass", "closes #1 on the merge into main")


def test_linked_passes_for_one_keyword_per_issue(sb):
    pr = {
        "body": "Closes #1\nCloses #2\nFixes: #3",
        "closingIssuesReferences": [ref(1), ref(2), ref(3)],
    }
    assert linked(sb, pr) == ("pass", "closes #1, #2 and #3 on the merge into main")


def test_linked_fails_without_a_keyword(sb):
    pr = {"body": "Adds the thing.", "closingIssuesReferences": []}
    assert linked(sb, pr) == (
        "fail",
        "#1 is not linked: the branch names it, the body has no `Closes #1` line",
    )


def test_linked_fails_on_a_misspelt_keyword(sb):
    pr = {"body": "Closing #1", "closingIssuesReferences": []}
    assert linked(sb, pr) == (
        "fail",
        "#1 is not linked: `Closing #1` is not a closing keyword; write `Closes #1`",
    )


def test_linked_fails_when_one_keyword_lists_several_issues(sb):
    pr = {"body": "Closes #1, #2", "closingIssuesReferences": [ref(1)]}
    assert linked(sb, pr) == (
        "fail",
        "#2 is not linked: it follows `Closes #1`, which closes only #1; "
        "give #2 a `Closes #2` line of its own",
    )


def test_linked_names_every_issue_that_is_not_linked(sb):
    pr = {"body": "Fixes #1 and #2\nClosing #3", "closingIssuesReferences": [ref(1)]}
    assert linked(sb, pr) == (
        "fail",
        "#2 is not linked: it follows `Fixes #1`, which closes only #1; give #2 a "
        "`Closes #2` line of its own; #3 is not linked: `Closing #3` is not a "
        "closing keyword; write `Closes #3`",
    )


def test_linked_fails_when_github_does_not_list_a_named_issue(sb):
    want = (
        "fail",
        "#1 is not linked: the body says `Closes #1`, but GitHub does not list #1 "
        "among the issues it closes; check that it is an issue of this repository",
    )
    assert linked(sb, {"closingIssuesReferences": []}) == want
    assert linked(sb, {"closingIssuesReferences": [ref(1, "x/y")]}) == want


def test_linked_ignores_issues_in_html_comments(sb):
    pr = {"body": "<!-- Closes #9 -->\nCloses #1"}
    assert linked(sb, pr) == ("pass", "closes #1 on the merge into main")


def test_linked_passes_when_no_issue_is_named(sb):
    pr = {
        "headRefName": "chore/tidy",
        "body": "Tidies up.",
        "closingIssuesReferences": [],
    }
    assert linked(sb, pr) == (
        "pass",
        "no issue named: the branch name has no issue number "
        "(<type>/<issue#>-<slug>) and the body no `Closes #N` line",
    )


def test_linked_fails_with_the_reason_when_gh_cannot_answer(sb):
    assert linked(sb, links_error="HTTP 502: Bad Gateway") == (
        "fail",
        "cannot read the issues #7 closes: HTTP 502: Bad Gateway",
    )
    asked = [row for row in sb.calls("pr view") if "7" in row]
    assert asked == [["pr", "view", "7", "--json", "body,closingIssuesReferences"]]


def test_linked_fails_on_an_unreadable_answer():
    found = ship_links.linked_gate(fake_repo((0, "[]", "")), {"number": 7})
    assert (
        found["detail"]
        == "cannot read the issues #7 closes: unreadable answer from gh pr view"
    )


def test_merge_refuses_an_issue_that_is_not_linked(sb):
    sb.state(pr=sb.pr(body="Closes #2", closingIssuesReferences=[ref(2)]))
    sb.passed()
    done = refused(sb, "linked", 1)
    assert last_line(done) == (
        "Not merged: linked: #1 is not linked: the branch names it, the body has no "
        "`Closes #1` line."
    )


# ---------------------------------------------------------------- into another branch


def test_linked_names_the_release_pull_request_that_closes_the_issue(sb):
    assert linked(sb, base=TEAM, release_prs=[release()]) == (
        "pass",
        "GitHub does not close #1 on a merge into feat/2-base; the release pull "
        "request #12 (feat/2-base -> main) will: ship adds the `Closes` lines to it "
        "after the merge",
    )
    asked = sb.calls("pr list")[-1]
    assert asked[asked.index("--base") + 1] == "main"
    assert asked[asked.index("--head") + 1] == TEAM
    assert asked[asked.index("--state") + 1] == "open"


def test_linked_says_when_someone_else_opened_the_release_pull_request(sb):
    found = linked(sb, base=TEAM, release_prs=[release(login="them\x1b[2J")])
    assert found == (
        "pass",
        "GitHub does not close #1 on a merge into feat/2-base; the release pull "
        "request #12 (feat/2-base -> main) will: it was opened by them [2J, so ship "
        "prints the "
        "`Closes` lines to add after the merge",
    )


def test_linked_says_when_the_release_pull_request_already_closes_the_issue(sb):
    found = linked(sb, base=TEAM, release_prs=[release(body="Closes #1")])
    assert found == (
        "pass",
        "GitHub does not close #1 on a merge into feat/2-base; the release pull "
        "request #12 (feat/2-base -> main) already closes #1",
    )


def test_linked_says_what_to_do_when_no_release_pull_request_is_open(sb):
    other_repo = release(number=3, cross=True)
    for prs in ([], [other_repo]):
        assert linked(sb, base=TEAM, release_prs=prs) == (
            "pass",
            "GitHub does not close #1 on a merge into feat/2-base; no release pull "
            "request (feat/2-base -> main) is open: give it one `Closes #N` line per "
            "issue when you open it",
        )


def test_linked_takes_the_oldest_open_release_pull_request(sb):
    found = linked(sb, base=TEAM, release_prs=[release(20), release(12, "them")])
    assert (
        "the release pull request #12 (feat/2-base -> main) will: it was opened by them"
        in found[1]
    )


def test_merge_refuses_when_github_cannot_list_release_pull_requests(sb):
    sb.state(pr=sb.pr(**onto(sb, TEAM, {})), release_error="HTTP 502")
    passed(sb, TEAM)
    done = refused(sb, "linked", 1)
    assert last_line(done) == (
        "Not merged: linked: GitHub does not close #1 on a merge into feat/2-base, and "
        "cannot find the release pull request (feat/2-base -> main): HTTP 502."
    )


# ---------------------------------------------------------------- after the merge


def test_merge_into_the_default_branch_checks_the_issue_closed(sb):
    out = merged(sb)
    assert out[-2] == "Closed: #1."
    assert sb.calls("issue view") == [["issue", "view", "1", "--json", "state"]]


def test_merge_waits_a_moment_for_github_to_close_the_issue(sb):
    out = merged(sb, issues={"1": ["OPEN", "CLOSED"]})
    assert out[-2] == "Closed: #1."
    assert len(sb.calls("issue view")) == 2


def test_merge_says_which_issues_are_still_open(sb):
    pr = {"body": "Closes #1\nCloses #2", "closingIssuesReferences": [ref(1), ref(2)]}
    out = merged(sb, pr, issues={"1": "CLOSED", "2": "OPEN"})
    assert out[-3:-1] == [
        "Closed: #1.",
        "#2 is still open after the merge: GitHub did not close it. Close it with "
        "gh issue close 2 once its work is done.",
    ]
    assert [row[2] for row in sb.calls("issue view")] == ["1", "2", "2", "2"]


def test_merge_says_which_issues_it_could_not_read(sb):
    out = merged(sb, issues={})
    assert out[-2] == (
        "Could not read #1: GraphQL: Could not resolve to an issue or pull request "
        "with the number of 1."
    )


def test_merge_into_another_branch_adds_the_lines_to_the_release_pull_request(sb):
    body = "Release notes \u2014 caf\u00e9\n"
    out = merged(sb, base=TEAM, release_prs=[release(body=body)])
    assert (
        out[-2]
        == "Added to the release pull request #12 (feat/2-base -> main): Closes #1."
    )
    assert sb.edits() == [{"number": "12", "body": f"{body.rstrip()}\n\nCloses #1\n"}]
    edit = sb.calls("pr edit")[0]
    assert edit[:4] == ["pr", "edit", "12", "--body-file"]
    assert not any(row[:2] == ["pr", "merge"] and "12" in row for row in sb.all_calls())


def test_merge_adds_only_the_lines_the_release_pull_request_lacks(sb):
    pr = {"body": "Closes #1\nCloses #2"}
    out = merged(sb, pr, base=TEAM, release_prs=[release(body="Closes #1")])
    assert (
        out[-2]
        == "Added to the release pull request #12 (feat/2-base -> main): Closes #2."
    )
    assert sb.edits() == [{"number": "12", "body": "Closes #1\n\nCloses #2\n"}]


def test_merge_adds_one_line_per_issue_to_an_empty_body(sb):
    pr = {"body": "Closes #1, #2"}
    merged(sb, pr, base=TEAM, release_prs=[release(body="")])
    assert sb.edits() == [{"number": "12", "body": "Closes #1\nCloses #2\n"}]


def test_merge_leaves_a_release_pull_request_that_already_closes_the_issue(sb):
    out = merged(sb, base=TEAM, release_prs=[release(body="Fixes #1")])
    assert (
        out[-2]
        == "The release pull request #12 (feat/2-base -> main) already closes #1."
    )
    assert sb.calls("pr edit") == []


def test_merge_prints_the_lines_when_someone_else_opened_the_release(sb):
    out = merged(sb, base=TEAM, release_prs=[release(login="them")])
    assert out[-3:-1] == [
        "The release pull request #12 (feat/2-base -> main) was opened by them: add "
        "these lines to its body:",
        "  Closes #1",
    ]
    assert sb.calls("pr edit") == []


def test_merge_prints_the_lines_when_no_release_pull_request_is_open(sb):
    out = merged(sb, base=TEAM)
    assert out[-3:-1] == [
        "GitHub does not close #1 on a merge into feat/2-base, and no release pull "
        "request (feat/2-base -> main) is open. When you open it, put these lines in "
        "its body:",
        "  Closes #1",
    ]


def test_merge_prints_the_lines_when_the_edit_fails(sb):
    out = merged(sb, base=TEAM, release_prs=[release()], edit_error="HTTP 403")
    assert out[-3:-1] == [
        "Could not edit the release pull request #12 (feat/2-base -> main): HTTP 403. "
        "Add these lines to its body:",
        "  Closes #1",
    ]


def test_after_merge_never_raises():
    pr = {"number": 7, "baseRefName": "main", "headRefName": BRANCH}
    assert ship.after_merge(fake_repo((1, "", "HTTP 502")), pr) == [
        "Could not read the issues #7 closes: HTTP 502."
    ]

    def broken():
        raise ship.ToolError("gh repo view: HTTP 401")

    repo = SimpleNamespace(info=broken)
    assert ship.after_merge(repo, pr) == [
        "Could not follow up the issues of #7: gh repo view: HTTP 401."
    ]


def test_after_merge_says_when_it_cannot_find_the_release_pull_request():
    answers = iter([(0, json.dumps({"body": "Closes #1"}), ""), (1, "", "HTTP 502")])
    repo = fake_repo()
    repo.gh = lambda *args, **more: next(answers)
    pr = {"number": 7, "baseRefName": TEAM, "headRefName": BRANCH}
    assert ship.after_merge(repo, pr) == [
        "Could not find the release pull request (feat/2-base -> main): HTTP 502. Put "
        "these lines in its body:",
        "  Closes #1",
    ]
