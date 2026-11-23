"""The changed hunks of a build round (hunks.patch) and the brief that names them."""

from __future__ import annotations

import re
import subprocess
import time

import pytest
from loop_fixtures import brief_of, item, loop, nine, result

ALPHA = (
    "def alpha(values):\n"
    "    total_of_values = sum(values)\n"
    "    return total_of_values * 2\n"
)
BETA = (
    "def beta(names):\n"
    "    joined_names = ', '.join(sorted(names))\n"
    "    message_text = 'names: ' + joined_names\n"
    "    print_to_screen = print(message_text)\n"
    "    return message_text\n"
)
GAMMA = (
    "def gamma(count):\n"
    "    doubled_count = count + count\n"
    "    return doubled_count - 1\n"
)
HEAD = "import os\nimport sys\n\n\n"


def unmoved(tmp_path, old, new):
    """The patch of old -> new (each {name: text}) after the move filter."""
    for side, files in (("old", old), ("new", new)):
        folder = tmp_path / side
        folder.mkdir()
        for name, text in files.items():
            (folder / name).write_text(text)
    proc = subprocess.run(
        ["git", "diff", "--no-index", "--no-renames", "-U5", "old", "new"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stderr
    body, kept, total = loop.unmoved(proc.stdout)
    return body.decode(), kept, total


def changed(text):
    """The added and removed lines of a patch, without the file headers."""
    return [
        line
        for line in text.splitlines()
        if line[:1] in "+-" and not line.startswith(("+++ ", "--- "))
    ]


def headers_hold(text):
    """Every hunk header counts the lines under it."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        hit = re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", line)
        if not hit:
            continue
        old = new = 0
        for body in lines[i + 1 :]:
            if body.startswith(("@@", "diff --git ")):
                break
            if body[:1] in (" ", "-"):
                old += 1
            if body[:1] in (" ", "+"):
                new += 1
        assert (old, new) == (int(hit[2]), int(hit[4])), line


def test_a_function_moved_unchanged_is_left_out(tmp_path):
    text, kept, total = unmoved(
        tmp_path,
        {"a.py": HEAD + ALPHA + "\n\n" + BETA, "b.py": HEAD + GAMMA},
        {"a.py": HEAD + ALPHA, "b.py": HEAD + GAMMA + "\n\n" + BETA},
    )
    assert kept == 0 and total > 10
    assert "beta" not in text and "joined_names" not in text
    assert changed(text) == []


def test_a_changed_line_inside_a_moved_block_stays(tmp_path):
    moved = BETA.replace("'names: '", "'all names: '")
    text, kept, _ = unmoved(
        tmp_path,
        {"a.py": HEAD + ALPHA + "\n\n" + BETA, "b.py": HEAD + GAMMA},
        {"a.py": HEAD + ALPHA, "b.py": HEAD + GAMMA + "\n\n" + moved},
    )
    assert changed(text) == [
        "-    message_text = 'names: ' + joined_names",
        "+    message_text = 'all names: ' + joined_names",
    ]
    assert kept == 2
    assert "def beta" not in text and "print_to_screen" not in text
    headers_hold(text)


def test_a_plain_change_stays_with_five_lines_of_context(tmp_path):
    lines = [f"value_number_{i} = {i}\n" for i in range(20)]
    edited = list(lines)
    edited[10] = "value_number_10 = 1000\n"
    text, kept, total = unmoved(
        tmp_path, {"c.py": "".join(lines)}, {"c.py": "".join(edited)}
    )
    assert changed(text) == ["-value_number_10 = 10", "+value_number_10 = 1000"]
    assert (kept, total) == (2, 2)
    context = [line for line in text.splitlines() if line.startswith(" ")]
    assert context == [
        f" value_number_{i} = {i}" for i in (*range(5, 10), *range(11, 16))
    ]
    assert "@@ -6,11 +6,11 @@" in text
    headers_hold(text)


def test_a_short_line_found_elsewhere_still_counts_as_changed(tmp_path):
    text, kept, _ = unmoved(
        tmp_path,
        {"d.py": HEAD + ALPHA + "    pass\n\n\n" + GAMMA},
        {"d.py": HEAD + ALPHA + "\n\n" + GAMMA + "    pass\n"},
    )
    assert "-    pass" in changed(text) and "+    pass" in changed(text)
    assert kept >= 2


def test_a_file_without_hunks_stays():
    patch = (
        b"diff --git a/x.bin b/x.bin\n"
        b"new file mode 100644\n"
        b"index 0000000..1111111\n"
        b"Binary files /dev/null and b/x.bin differ\n"
    )
    body, kept, total = loop.unmoved(patch)
    assert body == patch and (kept, total) == (0, 0)


def test_a_removed_line_that_looks_like_a_header_is_a_line():
    patch = (
        b"diff --git a/n.md b/n.md\n"
        b"--- a/n.md\n"
        b"+++ b/n.md\n"
        b"@@ -1,2 +1,2 @@\n"
        b"---- old rule of the notes\n"
        b"+--- new rule of the notes\n"
        b" end\n"
    )
    body, kept, total = loop.unmoved(patch)
    assert (kept, total) == (2, 2)
    assert b"---- old rule of the notes\n" in body


def test_an_indent_change_in_place_stays(tmp_path):
    body = "".join(f"    total_value_{i} = compute_something(i)\n" for i in range(3))
    deeper = body.replace("    ", "        ")
    text, kept, total = unmoved(
        tmp_path,
        {"e.py": "def f():\n" + body + "    return 1\n"},
        {"e.py": "def f():\n    if ok:\n" + deeper + "    return 1\n"},
    )
    assert (kept, total) == (7, 7)
    assert "+        total_value_2 = compute_something(i)" in changed(text)
    headers_hold(text)


@pytest.mark.parametrize(
    "old, new",
    [
        (
            "x = 1\nreturn compute_the_total_value(x)",
            "x = 1\nreturn compute_the_total_value(x)\n",
        ),
        (
            "".join(f"line_number_{i} = value_{i}\n" for i in range(5)),
            "".join(f"line_number_{i} = value_{i}\r\n" for i in range(5)),
        ),
    ],
    ids=["final newline", "line ends"],
)
def test_a_whitespace_edit_in_place_stays(tmp_path, old, new):
    text, kept, total = unmoved(tmp_path, {"f.py": old}, {"f.py": new})
    assert kept == total > 0
    assert len(changed(text)) == total


def test_a_file_whose_lines_all_moved_keeps_its_header(tmp_path):
    text, kept, _ = unmoved(
        tmp_path,
        {"g.py": BETA, "h.py": HEAD + GAMMA},
        {"h.py": HEAD + GAMMA + "\n\n" + BETA},
    )
    assert kept == 0 and changed(text) == []
    assert "g.py" in text and "deleted file mode" in text
    assert "joined_names" not in text


def test_a_long_run_is_filtered_in_linear_time():
    count = 40000
    lines = [b"+" if i % 2 else b"+value_%d = %d" % (i, i) for i in range(count)]
    patch = (
        b"diff --git a/y.py b/y.py\nnew file mode 100644\n--- /dev/null\n"
        b"+++ b/y.py\n@@ -0,0 +1,%d @@\n" % count + b"\n".join(lines) + b"\n"
    )
    start = time.monotonic()
    _, kept, total = loop.unmoved(patch)
    assert time.monotonic() - start < 10
    assert kept == total == count


# The file a build round writes ---------------------------------------------------

REL = "docs/loops/feat-1-x/build"


def test_every_build_round_writes_hunks_patch(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    patch = (sb.loopdir() / "hunks.patch").read_text()
    first, rest = patch.split("\n", 1)
    assert first.startswith("# ") and first.endswith(
        f"The full diff: {REL}/judge/r1.diff"
    )
    assert "Moved lines are left out" in first
    assert "+line 0" in rest and rest.startswith("diff --git ")
    assert sb.save("general", nine("I1")).code == 0
    assert sb.run("round").code == 1
    sb.change("app.py", 5, tag="r2")
    assert sb.run("brief").code == 0
    patch = (sb.loopdir() / "hunks.patch").read_text()
    assert patch.split("\n", 1)[0].endswith(f"The full diff: {REL}/judge/r2.diff")
    assert "+r2 4" in patch


def test_a_plan_round_writes_no_hunks(sb):
    sb.start_plan()
    assert sb.run("brief").code == 0
    assert not (sb.loopdir("plan", "p1") / "hunks.patch").exists()


# The brief --------------------------------------------------------------------


def in_order(prompt, *parts):
    """The index of the first line holding each part; they rise."""
    at = [next(i for i, line in enumerate(prompt) if part in line) for part in parts]
    assert at == sorted(at), list(zip(parts, at, strict=True))


def test_a_normal_round_reads_the_hunks_first(sb):
    sb.start_build()
    (sb.loopdir() / "map.md").write_text("app | app.py | all\n")
    run = sb.run("brief")
    _, prompt = brief_of(run, "general", 1)
    text = "\n".join(prompt)
    assert loop.READ_ORDER in prompt
    in_order(
        prompt,
        loop.READ_ORDER,
        f"{REL}/hunks.patch",
        f"{REL}/map.md",
        "there is no result of yours before it",
        f"{REL}/criteria.md",
    )
    for name in ("READ_HUNKS", "TEN_READ_WHOLE", "READ_CAP"):
        assert getattr(loop, name) in text, name
    assert loop.READ_FULL not in text and loop.READ_TOUCHED not in text
    assert f"{REL}/judge/r1.diff" in text
    assert sb.save("general", nine("I1")).code == 0
    assert sb.run("round").code == 1
    sb.change("app.py", 4)
    _, prompt = brief_of(sb.run("brief"), "general", 2)
    text = "\n".join(prompt)
    in_order(
        prompt,
        f"{REL}/hunks.patch",
        f"{REL}/map.md",
        f"Your last counted result (round 1): {REL}/judge/r1_general.json",
        f"{REL}/criteria.md",
    )
    assert loop.START_FROM_LAST in text and loop.READ_CAP in text
    assert loop.READ_TOUCHED not in text


def test_a_brief_without_map_md_says_so(sb):
    sb.start_build()
    _, prompt = brief_of(sb.run("brief"), "general", 1)
    assert f"The areas of the change: {REL}/map.md (not written; skip it)" in prompt



def test_the_final_round_asks_for_every_touched_file_whole(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    assert sb.save("general", nine("I1")).code == 0
    assert sb.run("round").code == 1
    sb.change("app.py", 4)
    sb.set_state(final=True)
    _, prompt = brief_of(sb.run("brief"), "general", 2)
    text = "\n".join(prompt)
    in_order(prompt, f"{REL}/hunks.patch", f"{REL}/map.md", f"{REL}/criteria.md")
    assert loop.READ_FULL in text and loop.READ_TOUCHED in text
    assert loop.READ_HUNKS not in text and loop.READ_CAP not in text


def test_a_plan_brief_keeps_the_full_read(sb):
    sb.start_plan()
    _, prompt = brief_of(sb.run("brief"), "general", 1)
    text = "\n".join(prompt)
    assert loop.READ_FULL in text and "hunks.patch" not in text


# A read that stopped at the cap -----------------------------------------------


def test_a_part_read_counts_below_10_and_brings_a_full_brief(sb):
    sb.start_build()
    assert sb.run("brief").code == 0
    answer = result(9, improvements=[item("I1")], read="part", unread="app.py")
    assert sb.save("general", answer).code == 0
    run = sb.run("round")
    assert run.code == 1 and "general 9 full, read part" in run.out, run
    sb.change("app.py", 4)
    _, prompt = brief_of(sb.run("brief"), "general", 2)
    assert loop.START_FROM_LAST not in "\n".join(prompt)


@pytest.mark.parametrize(
    "data, field",
    [
        ({"read": "part"}, "overall"),
        ({"read": "full", "unread": 3}, "unread"),
        ({"read": "part", "unread": " "}, "unread"),
    ],
)
def test_the_part_read_fields(data, field):
    raw = result(10, **data)
    with pytest.raises(loop.NoScore) as caught:
        loop.check_result(raw, "general")
    assert caught.value.field == field
