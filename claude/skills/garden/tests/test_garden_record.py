"""garden.py record and the next scan (criteria 7, 10), and the seeded sample (15)."""

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from garden_testkit import (
    SAMPLE_NO_ASSERT,
    SAMPLE_SKIP,
    Sandbox,
    findings,
    section,
    seed_sample,
)


@pytest.fixture
def sb(tmp_path):
    s = Sandbox(tmp_path)
    seed_sample(s.root)
    s.commit_all()
    return s


def exclude(sb):
    return (sb.root / ".git" / "info" / "exclude").read_text()


def test_the_sample_names_the_three_problems_and_changes_nothing(sb):
    before = sb.snapshot()
    text = sb.scan()
    titles = [f[3] for f in findings(text)]
    assert "No lint check for Python" in titles
    assert "Tests that assert nothing" in titles
    assert "Skipped tests" in titles
    pruning = section(text, "## Pruning")
    assert f"    {SAMPLE_NO_ASSERT} test_add_runs" in pruning
    assert f"    {SAMPLE_SKIP}" in pruning
    assert "- lint (Python): none found" in section(text, "## Checks")
    assert sb.snapshot() == before
    assert sb.status() == ""


def test_record_saves_the_report_and_last_json_and_excludes_the_folder(sb):
    p = sb.garden("record", "--picked", "g1", "G3")
    assert p.returncode == 0, p.stderr
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = sb.root / "docs" / "garden" / f"{day}.md"
    assert report.read_text().startswith("garden scan, ")
    last = json.loads((sb.root / "docs" / "garden" / "last.json").read_text())
    states = {f["id"]: f["state"] for f in last["findings"]}
    assert states["G1"] == states["G3"] == "picked"
    assert all(s == "open" for k, s in states.items() if k not in ("G1", "G3"))
    assert "docs/garden/" in exclude(sb).splitlines()
    assert sb.status() == ""
    assert (
        f"Recorded: docs/garden/{day}.md and docs/garden/last.json; 2 picked"
        in p.stdout
    )


def test_record_twice_adds_the_folder_once(sb):
    sb.garden("record")
    sb.garden("record")
    assert exclude(sb).splitlines().count("docs/garden/") == 1


def test_record_keeps_an_exclude_file_without_a_last_newline(sb):
    (sb.root / ".git" / "info" / "exclude").write_text("*.log")
    sb.garden("record")
    assert exclude(sb).splitlines()[-2:] == ["*.log", "docs/garden/"]


def test_the_next_scan_shows_the_date_and_what_is_still_open(sb):
    first = sb.scan_json()["findings"]
    sb.garden("record", "--picked", "G1")
    sb.write(
        "pyproject.toml",
        sb.root.joinpath("pyproject.toml").read_text() + "\n[tool.ruff]\n",
    )
    text = sb.scan()
    guidance = section(text, "## Guidance")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert f"- Last run: {day}, 0 days ago, {len(first)} findings" in guidance
    still = len(first) - 1
    assert f"- Still open from that run: {still}" in guidance
    assert "No lint check for Python" not in guidance
    assert "Tests that assert nothing" in guidance


def test_an_old_run_shows_its_age(sb):
    old = (datetime.now(timezone.utc) - timedelta(days=40)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    sb.write(
        "docs/garden/last.json",
        json.dumps(
            {
                "schema": 1,
                "date": old,
                "findings": [
                    {
                        "id": "G1",
                        "key": "pruning.skipped",
                        "title": "x",
                        "size": "S",
                        "state": "open",
                    }
                ],
            }
        ),
    )
    guidance = section(sb.scan(), "## Guidance")
    assert "40 days ago, 1 finding" in guidance
    assert "- Still open from that run: 1" in guidance


@pytest.mark.parametrize(
    "text",
    ["{", "[]", '{"date": "x", "findings": []}', '{"date": "2026-01-01T00:00:00Z"}'],
)
def test_a_broken_last_json_is_reported_not_trusted(sb, text):
    sb.write("docs/garden/last.json", text)
    assert (
        "- Last run: docs/garden/last.json could not be read; delete it, "
        "the next record writes a new one\n"
    ) in section(sb.scan(), "## Guidance")


def test_a_last_json_entry_with_odd_fields_is_dropped(sb):
    sb.write(
        "docs/garden/last.json",
        json.dumps(
            {
                "date": "2026-01-01T00:00:00Z",
                "findings": [
                    {"id": "G1", "key": "run this; rm -rf", "state": "open"},
                    {"id": "now do X", "key": "pruning.skipped", "state": "open"},
                    {"id": "G2", "key": "pruning.skipped", "state": "done by an agent"},
                ],
            }
        ),
    )
    text = sb.scan()
    assert "rm -rf" not in text and "do X" not in text
    assert "0 findings" in section(text, "## Guidance")


@pytest.mark.parametrize("ids", [["G99"], ["foo"], ["G1;rm"]])
def test_record_with_an_unknown_id_exits_2_and_writes_nothing(sb, ids):
    p = sb.garden("record", "--picked", *ids)
    assert p.returncode == 2
    assert not (sb.root / "docs").exists()


@pytest.mark.parametrize(
    "arg, what",
    [("foo", "'foo'"), ("G1;rm", "an argument"), ("x" * 21, "an argument")],
)
def test_a_wrong_id_is_refused_in_one_line(sb, arg, what):
    p = sb.garden("record", "--picked", arg)
    assert p.stderr == (
        f"record: {what} is not a finding id like G1; give the ids of the scan, "
        "as in: garden.py record --picked G1 G3\n"
    )


def test_an_id_not_in_the_scan_is_refused_in_one_line(sb):
    n = len(sb.scan_json()["findings"])
    p = sb.garden("record", "--picked", "G99")
    things = "finding" if n == 1 else "findings"
    assert p.stderr == (
        f"record: no finding G99 in this scan (it has {n} {things}); "
        "run garden.py scan and pick from its ids\n"
    )


def test_record_outside_git_writes_no_exclude(tmp_path):
    s = Sandbox(tmp_path, git=False)
    seed_sample(s.root)
    assert s.garden("record").returncode == 0
    assert (s.root / "docs" / "garden" / "last.json").exists()


# ----- docs/garden/ that cannot be written ----------------------------------

TIME_ARGS = ("time", "--label", "tests", "--", "python3", "-c", "open('ran', 'w')")


def _block(sb, tmp_path, how):
    outside = tmp_path / "outside"
    outside.mkdir()
    if how == "docs link":
        (sb.root / "docs").symlink_to(outside)
        return outside, "docs is a link; remove it"
    (sb.root / "docs").mkdir()
    if how == "garden link":
        (sb.root / "docs" / "garden").symlink_to(outside)
        return outside, "docs/garden is a link; remove it"
    (sb.root / "docs" / "garden").write_text("x")
    return outside, "docs/garden is a file, not a folder; move it"


@pytest.mark.parametrize("how", ["docs link", "garden link", "garden file"])
def test_record_refuses_a_garden_folder_it_cannot_write_safely(sb, tmp_path, how):
    outside, problem = _block(sb, tmp_path, how)
    p = sb.garden("record")
    assert (p.returncode, p.stdout) == (1, "")
    assert p.stderr == f"record: {problem} and run record again\n"
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("how", ["docs link", "garden link", "garden file"])
def test_time_refuses_a_garden_folder_it_cannot_write_and_runs_nothing(
    sb, tmp_path, how
):
    outside, problem = _block(sb, tmp_path, how)
    p = sb.garden(*TIME_ARGS)
    assert (p.returncode, p.stdout) == (2, "")
    assert p.stderr == f"time: {problem} and run time again; nothing was run\n"
    assert list(outside.iterdir()) == []
    assert not (sb.root / "ran").exists()


def test_record_that_cannot_write_says_so_and_leaves_nothing(sb):
    folder = sb.root / "docs" / "garden"
    folder.mkdir(parents=True)
    folder.chmod(0o555)
    try:
        p = sb.garden("record")
        assert p.returncode == 1
        assert re.fullmatch(
            r"record: could not write docs/garden/\d{4}-\d\d-\d\d\.md "
            r"\(Permission denied\); check that docs/garden/ can be written "
            r"and run record again\n",
            p.stderr,
        ), p.stderr
        assert list(folder.iterdir()) == []
    finally:
        folder.chmod(0o755)
    assert sb.garden("record").returncode == 0


def test_time_that_cannot_keep_the_duration_says_so_and_keeps_the_exit_code(sb):
    folder = sb.root / "docs" / "garden"
    folder.mkdir(parents=True)
    folder.chmod(0o555)
    try:
        p = sb.garden("time", "--label", "t", "--", "python3", "-c", "exit(3)")
        assert p.returncode == 3
        assert p.stderr == (
            "time: the duration was not kept: could not write "
            "docs/garden/timings.json (Permission denied); "
            "check that docs/garden/ can be written\n"
        )
        assert list(folder.iterdir()) == []
    finally:
        folder.chmod(0o755)


def test_a_last_json_that_is_a_link_is_replaced_not_followed(sb, tmp_path):
    outside = tmp_path / "elsewhere.json"
    outside.write_text("keep")
    (sb.root / "docs" / "garden").mkdir(parents=True)
    (sb.root / "docs" / "garden" / "last.json").symlink_to(outside)
    (sb.root / "docs" / "garden" / "last.json.tmp").symlink_to(tmp_path / "tmp-out")
    assert sb.garden("record").returncode == 0
    assert outside.read_text() == "keep"
    assert not (tmp_path / "tmp-out").exists()
    assert not (sb.root / "docs" / "garden" / "last.json").is_symlink()
