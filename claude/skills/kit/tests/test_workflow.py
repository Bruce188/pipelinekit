"""Every skill's tests folder runs in CI."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def runner_lines():
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if re.search(r"\b(pytest|bash)\b", line)]


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
