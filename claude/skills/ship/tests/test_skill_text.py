"""Text checks for the ship skill: the brief a tester agent gets."""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
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


def tester_brief() -> str:
    text = SKILL.read_text(encoding="utf-8")
    return text.split("\n## Tester brief\n", 1)[1].split("\n## ", 1)[0]


def test_the_tester_brief_gives_the_rules_for_every_agent():
    brief = tester_brief()
    for words in EVERY_AGENT:
        assert words in brief, words
