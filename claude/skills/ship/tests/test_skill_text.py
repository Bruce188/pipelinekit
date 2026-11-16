"""Text checks for the ship skill: the brief a tester agent gets, the issue links."""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
TEMPLATE = Path(__file__).resolve().parents[3] / "CLAUDE.md.template"
BUILDER = Path(__file__).resolve().parents[3] / "agents" / "kit-builder.md"
JUDGE_LOOP = Path(__file__).resolve().parents[2] / "judge-loop" / "SKILL.md"
# The rule for bringing a branch up to date with its base, word for word.
RULE = (
    "Before a PR is written up or updated: fetch, then bring the branch up to date "
    "with the base branch the PR targets (`origin/<base>`, not always `main`). "
    "Rebase onto it while the branch was never pushed; once it was pushed (a remote "
    "branch of that name exists), merge it in. Never force push. Then run the tests "
    "again."
)
# The rules for every agent, with the two file-reading rules, and the answer limit.
EVERY_AGENT = (
    "read it whole, once.",
    "search first, then read only those lines.",
    "Read nothing twice.",
    "Fewer, fuller tool calls",
    "Keep tool output short",
    "The same error after about 10 calls: stop and report it.",
    "Return at most 15 lines; the details go to the report.",
)


def read_tester_brief() -> str:
    text = SKILL.read_text(encoding="utf-8")
    return text.split("\n## Tester brief\n", 1)[1].split("\n## ", 1)[0]


def test_the_tester_brief_gives_the_rules_for_every_agent():
    brief = read_tester_brief()
    for words in EVERY_AGENT:
        assert words in brief, words


def test_the_skill_and_the_template_state_the_issue_link_rules():
    skill = SKILL.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    for text in (skill, template):
        assert "one `Closes #N` line per issue" in text
        assert "`Closes #1, #2` closes only #1" in text
        assert "a branch other than the default one does not close its issue" in text
        assert "carries the `Closes` lines" in text
    issue_links = skill.split("\n## Issue links\n", 1)[1].split("\n## ", 1)[0]
    assert "the number in its branch name (`<type>/<issue#>-<slug>`)" in issue_links
    assert "(`Closes`, `Fixes`, `Resolves` and their other forms)" in issue_links
    assert (
        "A keyword in an HTML comment or in code, inline or fenced, does not count."
        in (issue_links)
    )
    assert "says `Part of #N` (or `Refs #N`) instead of `Closes #N`" in issue_links


def test_every_place_states_the_up_to_date_rule_in_the_same_words():
    for path in (TEMPLATE, SKILL, BUILDER, JUDGE_LOOP):
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert RULE in text, path.name
        assert "--force" not in text, path.name
    template = TEMPLATE.read_text(encoding="utf-8").splitlines()
    assert f"- {RULE}" in template
    hand_over = JUDGE_LOOP.read_text(encoding="utf-8").split("**Hand-over.**", 1)[1]
    assert RULE in hand_over.split("\n", 1)[0]


def test_the_skill_holds_the_test_until_the_branch_is_up_to_date():
    skill = " ".join(SKILL.read_text(encoding="utf-8").split())
    assert (
        "4. **Test.** Run `status` first: while `up-to-date` fails, the test does "
        "not start; bring the branch up to date as its line says."
    ) in skill
    assert "`record --result pass` refuses while the gate fails" in skill
