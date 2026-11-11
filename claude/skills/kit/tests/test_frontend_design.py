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
