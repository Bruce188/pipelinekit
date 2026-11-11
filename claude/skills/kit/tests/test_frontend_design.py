"""The vendored frontend-design skill, the rules that load it and the docs."""

import hashlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SKILL = REPO / "claude" / "skills" / "frontend-design"
VENDORED = ("SKILL.md", "LICENSE.txt")


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def recorded():
    """{file: (blob, sha256)} from the table in SOURCE.md."""
    rows = re.findall(
        r"^\| `([^`]+)` \| `([0-9a-f]{40})` \| `([0-9a-f]{64})` \|$",
        (SKILL / "SOURCE.md").read_text(encoding="utf-8"),
        re.M,
    )
    return {name: (blob, digest) for name, blob, digest in rows}


# ---------------------------------------------------------------- vendored


def test_source_note_lists_both_files():
    assert sorted(recorded()) == sorted(VENDORED)


def test_vendored_files_match_their_checksums():
    for name, (_, digest) in recorded().items():
        data = (SKILL / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name


def test_vendored_files_match_their_git_blobs():
    for name, (blob, _) in recorded().items():
        data = (SKILL / name).read_bytes()
        header = f"blob {len(data)}\0".encode()
        assert hashlib.sha1(header + data).hexdigest() == blob, name


def test_vendored_files_have_no_carriage_returns():
    for name in VENDORED:
        assert b"\r" not in (SKILL / name).read_bytes(), name


def test_source_note_names_the_upstream():
    text = (SKILL / "SOURCE.md").read_text(encoding="utf-8")
    assert re.search(r"^- Commit: `[0-9a-f]{40}`$", text, re.M)
    assert "https://github.com/anthropics/skills" in text
    assert "`skills/frontend-design`" in text
    assert "Apache License 2.0" in text
    assert "Both files are unchanged." in text
    assert re.search(r"^## Moving to a newer commit$", text, re.M)


def test_skill_name():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    front = text.split("---")[1]
    assert re.search(r"^name: frontend-design$", front, re.M)


def test_vendored_files_keep_their_bytes_in_a_checkout():
    attrs = read(".gitattributes").splitlines()
    for name in VENDORED:
        assert f"claude/skills/frontend-design/{name} -text" in attrs, name


# ---------------------------------------------------------------- texts


def section(text, heading):
    """The body of a `## heading` section, up to the next `## ` heading."""
    match = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, heading
    return match.group(1)


def test_template_rule_names_when_to_load_the_skill():
    rule = section(read("claude/CLAUDE.md.template"), "Design")
    assert "load the `frontend-design` skill" in rule
    for case in (
        "app or site UI",
        "an HTML page or Artifact",
        "a new `docs-writer` snippet or a change to its template",
        "a chart or dashboard",
    ):
        assert case in rule, case


def test_template_rule_names_who_decides_what():
    rule = section(read("claude/CLAUDE.md.template"), "Design")
    order = (
        "the project's own design system or brand",
        "then the host's rules for the output (an Artifact's page contract "
        "and theme tokens)",
        "then `frontend-design`",
    )
    places = [rule.find(step) for step in order]
    assert -1 not in places and places == sorted(places), places
    assert "the `dataviz` skill, when the session has it, decides chart form" in rule
    assert "`frontend-design` decides the page around the chart" in rule
    assert "`docs-writer` pages keep the template's CSS variables" in rule


def test_template_rule_says_when_to_skip_it():
    rule = section(read("claude/CLAUDE.md.template"), "Design")
    assert "Skip it for work with no visual output" in rule
    assert "small fixes inside an existing design: follow what is there" in rule


def test_docs_writer_points_at_the_skill():
    text = read("claude/skills/docs-writer/SKILL.md")
    part = section(text, "Design")
    assert "Load the `frontend-design` skill before adding a snippet" in part
    assert "restyling `template.html`" in part
    assert "raw HTML in a page's markdown source" in part
    assert "the template's CSS variables" in part and "`--accent`" in part
    assert "No remote assets" in part
    assert text.index("## Design") < text.index("## When to use something else")


def test_kit_answer_relays_the_plugin_line():
    text = read("claude/skills/kit/SKILL.md")
    steps = section(text, "How to answer")
    first = re.search(r"^1\. (.*)$", steps, re.M).group(1)
    assert first.startswith("Lead with the `Result:` line. If it says healthy")
    assert "`update available`" in first and "`frontend-design`" in first
    assert first.endswith("and stop.")
    fourth = re.search(r"^4\. (.*)$", steps, re.M).group(1)
    assert fourth.startswith(
        "Mention `[info]` lines only when they explain a problem. Two exceptions:"
    )
    assert "`/kit update` applies it" in fourth
    assert "always mention the line about a `frontend-design` plugin" in fourth
    row = re.search(r"^\| Environment \|.*$", text, re.M).group(0)
    assert "a `frontend-design` plugin enabled next to the kit's copy" in row
