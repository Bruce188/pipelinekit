"""Tests of stacks: planning them, a stack loop, items per pull request, waiting."""

from __future__ import annotations

import json

from loop_fixtures import brief_of, ends, item, loop, result

# planning ---------------------------------------------------------------------


def issue(n, files, lines=100, after=(), kind="feat"):
    return {
        "issue": n,
        "type": kind,
        "slug": f"i{n}",
        "files": list(files),
        "after": list(after),
        "lines": lines,
    }


def plan(sb, issues, *flags):
    path = sb.tmp / "issues.json"
    path.write_text(json.dumps(issues))
    return sb.run("stacks", "--issues", path, "--base", "main", *flags)


def test_issues_that_touch_the_same_files_form_one_stack(sb):
    run = plan(
        sb,
        [
            issue(1, ["a.py"]),
            issue(2, ["b.py"]),
            issue(3, ["./a.py", "c.py"]),
            issue(4, ["src/"]),
            issue(5, ["src/x.py"], kind="fix"),
        ],
    )
    assert run.code == 0, run
    assert run.lines[:3] == [
        "Stack 1 of 3: base main, 2 pull requests, about 200 changed lines",
        "  1. #1 feat/1-i1 on main",
        "  2. #3 feat/3-i3 on feat/1-i1",
    ]
    assert (
        "Stack 2 of 3: base main, 1 pull request, about 100 changed lines" in run.lines
    )
    assert "  2. #5 fix/5-i5 on feat/4-i4" in run.lines
    assert "Cap: 5 pull requests and 2500 changed lines per stack" in run.lines
    ends(run, 0, "Planned: 3 stacks for 5 issues. Next: build each stack bottom-up")


def test_an_issue_comes_after_the_issues_it_waits_on(sb):
    run = plan(sb, [issue(1, ["a.py"], after=[2]), issue(2, ["b.py"])])
    assert run.code == 0, run
    assert run.lines[1:3] == [
        "  1. #2 feat/2-i2 on main",
        "  2. #1 feat/1-i1 on feat/2-i2",
    ]


def test_issues_that_wait_on_each_other_are_refused(sb):
    run = plan(sb, [issue(1, ["a.py"], after=[2]), issue(2, ["b.py"], after=[1])])
    ends(run, 2, "Refused: issues #1, #2 wait on each other.")


def test_an_issues_file_without_a_slug_is_refused(sb):
    run = plan(sb, [{"issue": 1, "files": ["a.py"]}])
    ends(run, 2, "Refused: issues[1].slug is not lower-case letters, digits and -.")


def test_a_stack_over_the_cap_splits_onto_the_part_below(sb):
    run = plan(sb, [issue(n, ["a.py"], lines=400) for n in range(1, 9)])
    assert run.code == 0, run
    assert (
        "Stack 1 of 2: base main, 5 pull requests, about 2000 changed lines"
        in run.lines
    )
    assert (
        "Stack 2 of 2: base feat/5-i5, 3 pull requests, about 1200 changed lines, "
        "the part above the stack before it" in run.lines
    )
    assert "  1. #6 feat/6-i6 on feat/5-i5" in run.lines


def test_the_line_cap_splits_a_stack_too(sb):
    run = plan(sb, [issue(1, ["a.py"], lines=1500), issue(2, ["a.py"], lines=1500)])
    assert run.code == 0, run
    assert (
        "Stack 2 of 2: base feat/1-i1, 1 pull request, about 1500 changed lines, "
        "the part above the stack before it" in run.lines
    )


def test_stacks_off_plans_one_pull_request_per_issue(sb):
    sb.on_base("CLAUDE.md", "Stacks: off\n")
    run = plan(sb, [issue(1, ["a.py"]), issue(2, ["a.py"])])
    assert run.code == 0, run
    assert run.lines[0] == (
        "Stacks: off, by CLAUDE.md:1 on main: one loop per pull request, each on main"
    )
    assert (
        "Stack 2 of 2: base main, 1 pull request, about 100 changed lines" in run.lines
    )
    ends(run, 0, "Planned: 2 stacks for 2 issues. Next: build each issue on its own")


def test_stacks_off_in_the_users_own_claude_md(sb):
    (sb.claude_home / "CLAUDE.md").write_text("Stacks: off\n")
    run = plan(sb, [issue(1, ["a.py"]), issue(2, ["a.py"])])
    assert run.lines[0].startswith("Stacks: off, by "), run
    assert run.last.startswith("Planned: 2 stacks"), run


def test_the_form_without_stacks_keeps_the_order_of_waiting(sb):
    issues = loop.read_issues([issue(1, ["a.py"], after=[2]), issue(2, ["b.py"])])
    stacks = loop.form_stacks(issues, "main", stacked=False)
    assert [s["issues"][0]["issue"] for s in stacks] == [2, 1]
    assert {s["base"] for s in stacks} == {"main"}


# a stack loop -----------------------------------------------------------------

STACK = ((21, 11, "feat/11-a", "a.py"), (22, 12, "feat/12-b", "b.py"))
CRITERIA = "## #11\n\n- a works\n\n## #12\n\n- b works\n"
ROOT = "docs/loops/feat-12-b/build"
ROLE = loop.FULL_PANEL[0]


def stack_file(sb, prs=STACK, base="main"):
    path = sb.tmp / "stack.json"
    entries = [{"pr": p, "issue": i, "branch": b} for p, i, b, _ in prs]
    path.write_text(json.dumps({"base": base, "prs": entries}))
    return path


def build_stack(sb, prs=STACK, base="main"):
    below = base
    for _, _, branch, rel in prs:
        sb.git("checkout", "-q", "-b", branch, below)
        sb.change(rel, 3, tag=branch)
        below = branch
    return stack_file(sb, prs, base)


def start_stack(sb):
    run = sb.run("start", "build", "--stack", build_stack(sb))
    assert run.code == 0, run
    sb.criteria(text=CRITERIA)
    return run


def tens(**others):
    scores = {role: 10 for role in loop.FULL_PANEL}
    scores.update(others)
    return scores


def nine_on(pr, x="I1"):
    return result(9, improvements=[item(x, pr=pr)])


def test_a_stack_loop_has_the_full_panel_and_at_most_five_rounds(sb):
    sb.on_base("CLAUDE.md", "Judge rounds: 8\n")
    run = start_stack(sb)
    st = sb.state()
    assert st["panel"] == list(loop.FULL_PANEL)
    assert st["budget"] == 5
    assert [e["pr"] for e in st["stack"]["prs"]] == [21, 22]
    assert "Stack: #21 feat/11-a, #22 feat/12-b, bottom first, on main" in run.lines
    assert run.last.endswith(
        "Next: write criteria.md, one section per issue (## #N), then loop.py brief."
    )


def test_a_stack_runs_combined_judges_between_its_full_rounds(sb):
    start_stack(sb)
    sb.judge(tens(**{ROLE: nine_on(21)}))
    sb.change("b.py", 5, tag="fixed")
    run = sb.run("brief")
    assert run.code == 0, run
    judges = ", ".join(loop.COMBINED)
    assert f"Panel of round 2: combined ({judges})" in run.lines
    first = loop.COMBINED[0]
    run = sb.save(first, result(9, improvements=["tests:I2"]))
    assert run.code == 3, run
    assert sb.save(first, result(9, improvements=[item("tests:I2", pr=22)])).code == 0
    for judge in loop.COMBINED[1:]:
        assert sb.save(judge, result(10)).code == 0
    run = sb.run("round")
    assert run.code == 1, run
    assert sb.state()["items"]["tests:I2"]["pr"] == 22
    assert any(line.startswith("  [tests I2 on #22] ") for line in run.lines), run


def test_a_stack_starts_on_its_top_branch(sb):
    path = build_stack(sb)
    sb.git("checkout", "-q", "feat/11-a")
    run = sb.run("start", "build", "--stack", path)
    ends(
        run,
        2,
        "Refused: the top of the stack is feat/12-b, the checkout is on feat/11-a.",
    )


def test_a_stack_on_its_base_branch_names_its_top_branch(sb):
    path = build_stack(sb)
    sb.git("checkout", "-q", "main")
    run = sb.run("start", "build", "--stack", path)
    ends(
        run,
        2,
        "Refused: main is the base branch. Next: git switch feat/12-b (the top of "
        "the stack), then the same command.",
    )
    assert not (sb.root / "docs" / "loops").exists()


def test_each_branch_of_a_stack_holds_the_one_below(sb):
    path = build_stack(sb)
    sb.git("checkout", "-q", "feat/11-a")
    sb.change("a.py", 5, tag="later")
    sb.git("checkout", "-q", "feat/12-b")
    run = sb.run("start", "build", "--stack", path)
    ends(run, 2, "Refused: feat/12-b does not hold feat/11-a, the branch below it.")
    assert "merge feat/11-a into feat/12-b (never rebase)" in run.last


def test_a_stack_file_over_the_cap_is_refused(sb):
    prs = [(20 + k, 10 + k, f"feat/{10 + k}-x", "a.py") for k in range(1, 7)]
    run = sb.run("start", "build", "--stack", stack_file(sb, prs))
    ends(run, 2, "Refused: the stack holds 6 pull requests, over the cap of 5.")


def test_a_branch_that_does_not_name_its_issue_is_refused(sb):
    prs = [(21, 11, "feat/12-a", "a.py")]
    run = sb.run("start", "build", "--stack", stack_file(sb, prs))
    ends(run, 2, "Refused: prs[1].branch is not <type>/11-<slug>.")


def test_stacks_off_refuses_a_stack_loop(sb):
    sb.on_base("CLAUDE.md", "Stacks: off\n")
    run = sb.run("start", "build", "--stack", build_stack(sb))
    ends(run, 2, "Refused: stacks are switched off by CLAUDE.md:1 on main.")


def test_the_brief_maps_the_stack(sb):
    start_stack(sb)
    run = sb.run("brief")
    assert run.code == 0, run
    text = (sb.root / ROOT / "stack.md").read_text()
    assert (
        f"| 1 | #21 | #11 | feat/11-a | main | {ROOT}/stack/pr21.patch | new |" in text
    )
    assert (
        f"| 2 | #22 | #12 | feat/12-b | feat/11-a | {ROOT}/stack/pr22.patch | new |"
        in text
    )
    first = (sb.root / ROOT / "stack" / "pr21.patch").read_text()
    second = (sb.root / ROOT / "stack" / "pr22.patch").read_text()
    assert "a.py" in first and "b.py" not in first
    assert "b.py" in second and "/a.py" not in second
    _, prompt = brief_of(run, ROLE, 1)
    assert any(f"{ROOT}/stack.md" in line for line in prompt)
    assert any('"pr", one of #21, #22' in line for line in prompt)
    assert any("A full brief reads the whole change" in line for line in prompt)


def test_the_criteria_name_each_issue(sb):
    start_stack(sb)
    sb.criteria(text="## #11\n\n- a works\n")
    run = sb.run("brief")
    ends(run, 2, "Refused: criteria.md names no criteria for #12.")


def test_an_item_without_its_pull_request_is_no_score(sb):
    start_stack(sb)
    assert sb.run("brief").code == 0
    run = sb.save(ROLE, result(9, improvements=[item("I1")]))
    assert run.code == 3, run
    assert "improvements[1].pr" in run.last


def test_an_item_on_a_pull_request_outside_the_stack_is_no_score(sb):
    start_stack(sb)
    assert sb.run("brief").code == 0
    run = sb.save(ROLE, nine_on(99))
    assert run.code == 3, run
    assert loop.NOT_IN_STACK in run.last


def test_an_item_keeps_its_pull_request_and_the_fix_names_it(sb):
    start_stack(sb)
    run = sb.judge(tens(**{ROLE: nine_on(21)}))
    assert run.code == 1, run
    assert sb.state()["items"][f"{ROLE}:I1"]["pr"] == 21
    assert any(line.startswith(f"  [{ROLE} I1 on #21] ") for line in run.lines), run
    assert "fix each item on its pull request's branch" in run.last


def test_a_pull_request_judged_before_shows_its_changes_since(sb):
    start_stack(sb)
    sb.judge(tens(**{ROLE: nine_on(21)}))
    sb.git("checkout", "-q", "feat/11-a")
    sb.write("a.py", "fixed\n")
    sb.commit("fix: a")
    sb.git("checkout", "-q", "feat/12-b")
    sb.git("merge", "-q", "--no-edit", "feat/11-a")
    run = sb.run("brief")
    assert run.code == 0, run
    text = (sb.root / ROOT / "stack.md").read_text()
    assert (
        f"| #21 | #11 | feat/11-a | main | {ROOT}/stack/pr21.patch | changes since "
        "round 1 |" in text
    )
    assert "### #21, changes since round 1" in text
    assert f"- [{ROLE} I1] open: problem I1 | fix: fix I1" in text
    first = (sb.root / ROOT / "stack" / "pr21.patch").read_text()
    second = (sb.root / ROOT / "stack" / "pr22.patch").read_text()
    assert first.startswith("# Its own commits since round 1")
    assert "+fixed" in first and "b.py" not in first
    assert second.startswith("# No commit of its own since round 1")
    assert sb.state()["pending"]["heads"]["21"] == sb.git("rev-parse", "feat/11-a")


def test_a_pull_request_not_changed_since_is_not_read_again(sb):
    start_stack(sb)
    sb.judge(tens(**{ROLE: nine_on(22)}))
    sb.change("b.py", 5, tag="fixed")
    assert sb.run("brief").code == 0
    text = (sb.root / ROOT / "stack.md").read_text()
    assert "| unchanged since round 1 |" in text
    first = (sb.root / ROOT / "stack" / "pr21.patch").read_text()
    assert "nothing new to read" in first
    assert sb.state()["rounds"][0]["heads"]["22"] != sb.head()


def test_the_base_merged_into_a_pull_request_above_is_not_its_own(sb):
    start_stack(sb)
    sb.judge(tens(**{ROLE: nine_on(22)}))
    sb.on_base("c.py", "from the base\n")
    sb.git("merge", "-q", "--no-edit", "origin/main")
    assert sb.run("brief").code == 0
    second = (sb.root / ROOT / "stack" / "pr22.patch").read_text()
    assert second.startswith("# No commit of its own since round 1"), second
    assert "c.py" not in second


def test_a_stack_of_one_pull_request(sb):
    one = STACK[:1]
    run = sb.run("start", "build", "--stack", build_stack(sb, one))
    assert run.code == 0, run
    sb.criteria(text="## #11\n\n- a works\n")
    run = sb.judge(tens())
    assert run.code == 0, run
    text = (sb.root / "docs/loops/feat-11-a/build/stack.md").read_text()
    assert "| 1 | #21 | #11 | feat/11-a | main |" in text


# waiting ----------------------------------------------------------------------


def test_a_stack_waits_for_its_judges(sb):
    start_stack(sb)
    run = sb.run("wait", "--note", "the model limit")
    ends(run, 0, "Waiting: the stack feat-12-b waits for its judges (the model limit).")
    assert sb.state()["waiting"]["note"] == "the model limit"
    status = sb.run("status")
    assert any(
        line.startswith("Waiting since ") and line.endswith(": the model limit")
        for line in status.lines
    ), status
    assert "loop.py brief once the judges can run again" in status.last
    assert sb.run("brief").code == 0
    assert "waiting" not in sb.state()


def test_a_damaged_stack_field_is_a_damaged_state(sb):
    start_stack(sb)
    sb.set_state(stack={"base": "main", "prs": "x"})
    run = sb.run("brief")
    assert run.code != 0, run
