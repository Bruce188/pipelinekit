"""Text checks for the ship skill: the brief a tester agent gets, the issue links."""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
TEMPLATE = Path(__file__).resolve().parents[3] / "CLAUDE.md.template"
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
