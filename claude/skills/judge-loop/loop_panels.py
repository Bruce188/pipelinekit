"""The judges of each round: the full panel in round 1 and in the final round,
three combined judges in the rounds between, one judge for a small change."""

# ruff: noqa: F403, F405
from __future__ import annotations

from loop_text import *

# The middle rounds of a full-panel loop: each combined judge covers two roles.
PAIRS = (
    ("correctness", "tests"),
    ("security", "operations"),
    ("user-experience", "scope"),
)
COMBINED = tuple("+".join(pair) for pair in PAIRS)
JUDGES = ROLES + COMBINED
# What judged a round: the six roles, the combined judges, the one general judge,
# or the judges a Judges: line chose.
PANELS = ("full", "combined", "single", "chosen")


def covers(judge):
    """The roles a judge covers: its own one, or the two of a combined judge."""
    return tuple(judge.split("+"))


def is_combined(judge):
    return judge in COMBINED


def combines(st):
    """True for a loop of the full panel: its middle rounds run combined judges."""
    return set(st.get("panel", ())) == set(FULL_PANEL)


def panel_kind(judges):
    judges = list(judges)
    if judges == list(COMBINED):
        return "combined"
    if set(judges) == set(FULL_PANEL):
        return "full"
    if judges == ["general"]:
        return "single"
    return "chosen"


def judges_of(st, kind):
    """The judges of a panel kind in this loop; the loop's panel by default."""
    return list(COMBINED) if kind == "combined" else list(st["panel"])


def next_judges(st):
    """The judges of the next round: the loop's panel in round 1 and in the final
    round; the combined judges between them in a full-panel loop."""
    if combines(st) and st["rounds"] and not st.get("final"):
        return list(COMBINED)
    return list(st["panel"])


def round_judges(st):
    """The judges of the pending round, else of the next one."""
    if st["pending"]:
        return judges_of(st, st["pending"].get("panel"))
    return next_judges(st)


def panel_of(st, rnd):
    """The panel kind of a counted round or of the pending one."""
    return rnd.get("panel") or panel_kind(st.get("panel", ()))


def readers(rnd):
    """The judges of a counted round that read; a skipped judge did not."""
    modes = rnd.get("modes", {})
    return [judge for judge in rnd["scores"] if modes.get(judge) != "skipped"]


def seen_by(rnd, judge):
    """The judges of a counted round that read for a role of this judge."""
    mine = set(covers(judge))
    return [other for other in readers(rnd) if mine & set(covers(other))]


def last_seen(st, judge):
    """The latest round in which a judge read for every role of this judge,
    itself or another panel's; 0 if none."""
    mine = set(covers(judge))
    for rnd in reversed(st["rounds"]):
        read = set()
        for other in readers(rnd):
            read |= set(covers(other))
        if mine <= read:
            return rnd["n"]
    return 0
