"""Tests of check.py: an event log that is damaged, too big, not rotated or
dated wrong, and the values --days and --session take."""

import json

import pytest
from check_fixtures import check
from test_check_activity import activity_rules, ev, state, write_events


def test_lines_that_are_no_events_are_counted(kit):
    write_events(kit, "not json", "[]", ev(kind="shout"), "")
    rc, out = check(kit)
    assert rc == 0, out
    assert "[info] 3 lines of the event log skipped: " in out
    assert "no blocks, asks or hook errors" not in out


def test_an_event_of_an_unknown_kind_is_counted(kit):
    write_events(kit, ev(kind="shout"), ev("sql.destructive", "ask"))
    rc, out = check(kit)
    assert rc == 0 and activity_rules(out) == ["sql.destructive"], out
    assert "[info] 1 line of the event log skipped: " in out


def big_log(kit, size, last):
    """events.jsonl of at least `size` bytes; `last` is its newest event."""
    line = json.dumps(ev("git.old-rule", reason="x" * 200)) + "\n"
    state(kit).mkdir(parents=True, exist_ok=True)
    with open(state(kit) / "events.jsonl", "w") as f:
        f.write(line * (size // len(line) + 1))
        f.write(json.dumps(last) + "\n")


def test_a_log_that_was_not_rotated_is_a_warning(kit):
    big_log(kit, 1_100_000, ev("sql.destructive", "ask"))
    rc, out = check(kit)
    assert rc == 0, out
    assert "[warn] the event log was not rotated at 1 MB: " in out
    assert "sql.destructive" in out
    assert out.rstrip().endswith("Result: working, 1 warning")


def test_a_log_at_the_rotation_size_is_no_warning(kit):
    big_log(kit, 990_000, ev())
    rc, out = check(kit)
    assert rc == 0 and "[warn]" not in out, out


def test_a_log_too_big_to_read_whole_is_read_from_its_end(kit):
    big_log(kit, 4_500_000, ev("sql.destructive", "ask"))
    rc, out = check(kit)
    assert rc == 0, out
    assert "sql.destructive (bash-guard): asked once" in out
    assert "[info] events.jsonl: only its newest 4 MB were read" in out
    assert "lines of the event log skipped" not in out  # not the cut line


def test_events_from_the_future_are_shown_and_named(kit):
    write_events(kit, ev(age_days=-1), ev("sql.destructive", "ask", age_days=1))
    rc, out = check(kit)
    assert rc == 0, out
    assert activity_rules(out) == ["git.no-verify", "sql.destructive"]
    assert "[info] 1 event is dated after now" in out


@pytest.mark.parametrize("value", [" 7 ", "+7", "7.0", "1e1", "\u0667", ""])
def test_days_takes_plain_digits_only(kit, value):
    rc, out = check(kit, "--days", value)
    assert rc == 2 and "--days takes a whole number from 1 to 365" in out, out


def test_an_empty_session_is_refused(kit):
    rc, out = check(kit, "--session", "")
    assert rc == 2 and "--session takes a session id" in out, out
