"""The commands the kit's skills pre-approve (allowed-tools) name the
installed helper only.

Claude Code fills in ${CLAUDE_SKILL_DIR} in a skill's text and in the Bash
rules of its allowed-tools with the folder it loaded the skill from. A Bash
rule matches the whole command text; `*` stands for any text, and a trailing
` *` that is the rule's only wildcard also matches the bare command
(code.claude.com/docs/en/permissions, "Wildcard patterns").
"""

import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[2]
SKILL_NAMES = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
# The folders a skill is loaded from: a default install and another home.
HOMES = ("/home/u/.claude", "/opt/kit-home")


def skill_text(name):
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def allowed_tools(name):
    """The rules of a skill's allowed-tools, inline or as a YAML list."""
    head = re.match(r"---\n(.*?)\n---\n", skill_text(name), re.S).group(1)
    m = re.search(r"^allowed-tools:(.*(?:\n  - .*)*)", head, re.M)
    if not m:
        return []
    value = m.group(1).replace("\n  - ", ", ")
    return re.findall(r"[A-Za-z]+(?:\([^()]*\))?", value)


def bash_rules(name, skill_dir):
    return [
        r[5:-1].replace("${CLAUDE_SKILL_DIR}", skill_dir)
        for r in allowed_tools(name)
        if r.startswith("Bash(")
    ]


def matches(rule, command):
    """Whether a Bash allow rule covers one command, as the docs describe."""
    if "*" not in rule:
        return command == rule
    if rule.endswith(" *") and rule.count("*") == 1 and command == rule[:-2]:
        return True
    pattern = ".*".join(re.escape(part) for part in rule.split("*"))
    return re.fullmatch(pattern, command, re.S) is not None


def allowed(name, skill_dir, command):
    return any(matches(r, command) for r in bash_rules(name, skill_dir))


def preload(name, skill_dir):
    """The command a skill runs when it loads (its !`...` line)."""
    lines = re.findall(r"^!`(.*)`$", skill_text(name), re.M)
    assert len(lines) == 1, name
    return lines[0].replace("${CLAUDE_SKILL_DIR}", skill_dir)


def helper_calls(name, skill_dir):
    """Every `python3 ${CLAUDE_SKILL_DIR}/...` call in a skill's text."""
    calls = re.findall(r"`(python3 \$\{CLAUDE_SKILL_DIR\}/[^`]*)`", skill_text(name))
    return [c.strip().replace("${CLAUDE_SKILL_DIR}", skill_dir) for c in calls]


def test_the_matcher_follows_the_documented_examples():
    assert matches("npm run *", "npm run build")
    assert matches("npm run *", "npm run")
    assert not matches("npm run *", "npm install")
    assert matches("ls *", "ls -la")
    assert not matches("ls *", "lsof")
    assert matches("ls*", "lsof")
    assert matches("* --help *", "npm --help x")
    assert not matches("* --help *", "npm --help")
    assert matches("npm run build", "npm run build")
    assert not matches("npm run build", "npm run build --watch")


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_no_bash_rule_starts_with_a_wildcard_before_the_path(name):
    for rule in bash_rules(name, "${CLAUDE_SKILL_DIR}"):
        assert not rule.startswith("*"), (name, rule)
        program, _, rest = rule.partition(" ")
        path = rest.split(" ", 1)[0] if program == "python3" else program
        assert "*" not in path, (name, rule)
        # The one wildcard a rule may hold takes the arguments, after a space.
        assert rule.count("*") <= 1, (name, rule)
        assert "*" not in rule or rule.endswith(" *"), (name, rule)


def test_kit_and_ship_name_their_helper_by_the_skill_folder():
    assert allowed_tools("kit") == [
        "Bash(python3 ${CLAUDE_SKILL_DIR}/check.py *)",
        "Bash(python3 ${CLAUDE_SKILL_DIR}/update.py plan)",
    ]
    assert allowed_tools("ship") == [
        "Bash(python3 ${CLAUDE_SKILL_DIR}/ship.py *)",
        "Bash(python3 ~/.claude/skills/judge-loop/loop.py *)",
    ]


@pytest.mark.parametrize("home", HOMES)
@pytest.mark.parametrize("name", ["kit", "ship"])
def test_the_helper_runs_without_a_prompt_from_any_home(name, home):
    skill_dir = f"{home}/skills/{name}"
    assert allowed(name, skill_dir, preload(name, skill_dir)), preload(name, skill_dir)
    calls = helper_calls(name, skill_dir)
    assert len(calls) >= 6, calls
    for call in calls:
        assert allowed(name, skill_dir, call), call


@pytest.mark.parametrize("home", HOMES)
def test_the_update_itself_still_asks(home):
    skill_dir = f"{home}/skills/kit"
    assert "`update.py apply --to`" in skill_text("kit")
    for call in (
        f"python3 {skill_dir}/update.py apply --to {'0' * 40}",
        f"python3 {skill_dir}/update.py plan --to abc",
        f"python3 {skill_dir}/update.py planx",
        f"python3 {skill_dir}/update.py",
    ):
        assert not allowed("kit", skill_dir, call), call


@pytest.mark.parametrize("home", HOMES)
def test_a_lookalike_helper_in_a_project_asks(home):
    for name, script in (
        ("kit", "check.py"),
        ("kit", "update.py plan"),
        ("ship", "ship.py status"),
    ):
        skill_dir = f"{home}/skills/{name}"
        for command in (
            f"python3 /work/project/x/skills/{name}/{script}",
            f"python3 x/skills/{name}/{script}",
            f"python3 ./skills/{name}/{script}",
            f"python3 {skill_dir}/../../../work/x/skills/{name}/{script}",
            f"python3 {skill_dir}x/{script}",
            f"python3 {home}/skills/{name}-old/{script}",
        ):
            assert not allowed(name, skill_dir, command), command
    skill_dir = f"{home}/skills/kit"
    assert not allowed("kit", skill_dir, f"python3 {skill_dir}/check.pyc")
    assert not allowed("kit", skill_dir, f"python3 {skill_dir}/check_core.py")
