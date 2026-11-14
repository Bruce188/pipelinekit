"""Every skill's tests folder runs in CI."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def runner_lines(text=None):
    """The lines that run pytest or bash, with YAML comments taken off."""
    if text is None:
        text = WORKFLOW.read_text(encoding="utf-8")
    code = (re.sub(r"(^|\s)#.*", "", line).rstrip() for line in text.splitlines())
    runs = (line for line in code if not re.match(r"\s*(-\s*)?name:", line))
    return [line for line in runs if re.search(r"\b(pytest|bash)\b", line)]


def test_a_comment_does_not_count_as_a_run():
    text = (
        "      # python -m pytest claude/skills/judge-loop/tests\n"
        "      - run: python -m pytest -q claude/skills/kit/tests  # the kit\n"
        "      - name: pytest of claude/skills/ship/tests\n"
        "        name: bash claude/skills/ship/tests\n"
    )
    assert runner_lines(text) == [
        "      - run: python -m pytest -q claude/skills/kit/tests"
    ]


def test_every_skill_tests_folder_runs_in_ci():
    folders = sorted((REPO / "claude" / "skills").glob("*/tests"))
    assert folders, "no claude/skills/*/tests folder found"
    lines = runner_lines()
    missing = []
    for folder in folders:
        rel = folder.relative_to(REPO).as_posix()
        pattern = re.compile(r"(?<![\w./-])" + re.escape(rel) + r"(?=/|\s|$)")
        if not any(pattern.search(line) for line in lines):
            missing.append(rel)
    assert not missing, (
        "tests folders no line of .github/workflows/ci.yml runs with pytest "
        f"or bash: {missing}"
    )
