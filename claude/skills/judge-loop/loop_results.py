"""The result check, the items and the closing lines of loop.py."""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
import math

from loop_start import *

# The result rules -----------------------------------------------------------


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NoScore(field, NOT_A_NUMBER)
    if isinstance(value, float) and not math.isfinite(value):
        raise NoScore(field, NOT_A_NUMBER)
    if not 0 <= value <= 10:
        raise NoScore(field, OUT_OF_RANGE)
    if (value * 2) % 1:
        raise NoScore(field, NOT_HALF_STEP)
    return value


def _text(item, key, field):
    if key not in item:
        raise NoScore(f"{field}.{key}", MISSING)
    value = item[key]
    if not isinstance(value, str):
        raise NoScore(f"{field}.{key}", NOT_A_STRING)
    if not value.strip():
        raise NoScore(f"{field}.{key}", EMPTY)
    if len(value) > MAX_FIELD:
        raise NoScore(f"{field}.{key}", TOO_LONG)
    return value


def check_result(raw: bytes, role: str, open_ids=(), mode="full") -> dict:
    """The result of one judge as a score, or NoScore with its reason.

    `open_ids` are the ids that were open in this judge's last counted result;
    a `still_open` entry must be one of them. `mode` is the read of the brief,
    which holds when the answer names none.
    """
    if len(raw) > MAX_RESULT:
        raise NoScore("size", OVER_SIZE)
    if raw.startswith(BOM):
        raise NoScore("json", NOT_ONE_OBJECT)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise NoScore("encoding", NOT_UTF8) from None
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        raise NoScore("json", NOT_ONE_OBJECT) from None
    if not isinstance(data, dict):
        raise NoScore("json", NOT_ONE_OBJECT)

    if "overall" not in data:
        raise NoScore("overall", MISSING)
    overall = _number(data["overall"], "overall")

    if "dimensions" not in data:
        raise NoScore("dimensions", MISSING)
    dimensions = data["dimensions"]
    if not isinstance(dimensions, dict):
        raise NoScore("dimensions", WRONG_TYPE)
    if len(dimensions) > MAX_DIMENSIONS:
        raise NoScore("dimensions", TOO_MANY)
    for i, (name, value) in enumerate(dimensions.items(), 1):
        shown = f".{name}" if NAME.fullmatch(name) else f"[{i}]"
        _number(value, f"dimensions{shown}")

    lists = {}
    for name in ("blocking", "improvements"):
        if name not in data:
            raise NoScore(name, MISSING)
        if not isinstance(data[name], list):
            raise NoScore(name, WRONG_TYPE)
        lists[name] = data[name]
    if len(lists["blocking"]) + len(lists["improvements"]) > MAX_ITEMS:
        raise NoScore("improvements", TOO_MANY)

    seen = {}
    items = {"blocking": [], "improvements": []}
    for name, entries in lists.items():
        for i, item in enumerate(entries, 1):
            field = f"{name}[{i}]"
            if not isinstance(item, dict):
                raise NoScore(field, WRONG_TYPE)
            if "id" not in item:
                raise NoScore(f"{field}.id", MISSING)
            item_id = item["id"]
            if not isinstance(item_id, str):
                raise NoScore(f"{field}.id", NOT_A_STRING)
            if not ITEM_ID.fullmatch(item_id):
                raise NoScore(f"{field}.id", NOT_AN_ID)
            if item_id in seen:
                raise NoScore(f"{field}.id", NOT_UNIQUE)
            entry = {
                "id": item_id,
                "kind": "blocking" if name == "blocking" else "improvement",
                "problem": _text(item, "problem", field),
                "evidence": _text(item, "evidence", field),
                "fix": _text(item, "fix", field),
                "check": _text(item, "check", field),
            }
            if "needed_for_10" in item:
                if not isinstance(item["needed_for_10"], bool):
                    raise NoScore(f"{field}.needed_for_10", WRONG_TYPE)
                entry["needed_for_10"] = item["needed_for_10"]
            seen[item_id] = entry
            items[name].append(entry)

    still_open = []
    if "still_open" in data:
        entries = data["still_open"]
        if not isinstance(entries, list):
            raise NoScore("still_open", WRONG_TYPE)
        for i, item_id in enumerate(entries, 1):
            if not isinstance(item_id, str):
                raise NoScore(f"still_open[{i}]", WRONG_TYPE)
            if item_id not in open_ids or item_id not in seen:
                raise NoScore(f"still_open[{i}]", NOT_OPEN_ID)
            still_open.append(item_id)

    read = mode if mode in READS else "full"
    if "read" in data:
        if data["read"] not in READS:
            raise NoScore("read", WRONG_TYPE)
        read = data["read"]

    if "judge" in data:
        if not isinstance(data["judge"], str):
            raise NoScore("judge", NOT_A_STRING)
        if data["judge"] != role:
            raise NoScore("judge", NOT_THE_ROLE)

    named = items["blocking"] + [
        e for e in items["improvements"] if e.get("needed_for_10") is not False
    ]
    if overall < 10 and not named:
        raise NoScore("overall", BELOW_NO_ITEM)

    if overall == 10:
        if items["blocking"]:
            raise NoScore("overall", TEN_WITH_OPEN)
        for item_id in still_open:
            entry = seen[item_id]
            if (
                entry["kind"] == "improvement"
                and entry.get("needed_for_10") is not False
            ):
                raise NoScore("overall", TEN_WITH_OPEN)
        if read != "full":
            raise NoScore("overall", TEN_NOT_FULL)

    return {
        "overall": overall,
        "blocking": items["blocking"],
        "improvements": items["improvements"],
        "still_open": still_open,
        "read": read,
    }


def open_ids(st, role):
    return {
        key.partition(":")[2]
        for key, item in st["items"].items()
        if key.startswith(f"{role}:") and item["open"]
    }


# Items and the Fix list -------------------------------------------------------


def effective_open(item):
    return item["open"] and (
        not item["settled"] or bool(item["settled"]["raised_again"])
    )


def settled_counts(st):
    settled = [
        it
        for it in st["items"].values()
        if it["settled"] and not it["settled"]["raised_again"]
    ]
    return len(settled), sum(1 for it in settled if it["kind"] == "blocking")


def settled_suffix(st):
    n, b = settled_counts(st)
    return f", {n} settled ({b} blocking)" if n else ""


def ordered_open(st):
    """The open items: blocking, carried, new; each as (key, item).

    Carried items were first raised before the last round; an item of a skipped
    judge carries over unchanged, so it is listed as carried though no judge
    raised it again.

    Within a group the order is the panel's, then the round an item was first
    raised, then its id, so the list does not depend on how the state was saved.
    """
    last = len(st["rounds"])
    panel = list(st["panel"])

    def place(entry):
        role, _, item_id = entry[0].partition(":")
        where = panel.index(role) if role in panel else len(panel)
        return where, entry[1]["first"], item_id

    items = sorted(
        ((k, it) for k, it in st["items"].items() if effective_open(it)), key=place
    )
    blocking = [x for x in items if x[1]["kind"] == "blocking"]
    carried = [x for x in items if x[1]["kind"] != "blocking" and x[1]["first"] < last]
    new = [x for x in items if x[1]["kind"] != "blocking" and x[1]["first"] >= last]
    return blocking + carried + new


def field_text(text):
    """One field of a Fix line: cut at LIMIT characters with a mark."""
    shown = clean(text, MAX_FIELD)
    if len(shown) > LIMIT:
        return shown[: LIMIT - len(CUT_MARK)] + CUT_MARK
    return shown


def is_cut(item):
    fields = ("problem", "evidence", "fix", "check")
    return any(len(clean(item.get(f, ""), MAX_FIELD)) > LIMIT for f in fields)


def item_line(key, item):
    role, _, item_id = key.partition(":")
    line = (
        f"  [{role} {item_id}] {field_text(item['problem'])} | evidence: "
        f"{field_text(item['evidence'])} | fix: {field_text(item['fix'])}"
    )
    if item.get("check"):
        line += f" | check: {field_text(item['check'])}"
    if item["settled"] and item["settled"]["raised_again"]:
        line += (
            " (raised again after being settled: fix it only if the judge gives new "
            "evidence, else ask the user)"
        )
    return line


def questions_sha(loop):
    data = loop.read("questions.md")
    return sha256(data) if data else ""


def print_items(loop, questions_since=None):
    """The Fix list, under its helper line; returns (items, blocking)."""
    st = loop.st
    items = ordered_open(st)
    lines = []
    if questions_since:
        lines.append(
            f"  New answers: questions.md changed since round {questions_since}; read "
            "it first"
        )
    lines += [item_line(k, it) for k, it in items]
    if lines:
        finished = st["outcome"] not in UNFINISHED
        say("Items left:" if finished else "Items to fix, in this order:")
        for line in lines:
            say(line)
    for key, it in items:
        if is_cut(it):
            role = key.partition(":")[0]
            say(f"  full text: {loop.rel}/judge/r{it['last']}_{role}.json")
    return len(items), sum(1 for _, it in items if it["kind"] == "blocking")


def fix_next(st):
    agents = st.get("agents", "kit")
    if st["kind"] == "plan":
        who = agent_word(agents, "kit-planner")
        return f"have {who} fix in this order, then loop.py brief."
    who = agent_word(agents, "kit-builder")
    return f"have {who} fix in this order and commit, then loop.py brief."


def plan_handover(st):
    n = len(st["rounds"])
    who = agent_word(st.get("agents", "kit"), "kit-builder")
    return (
        f"check out a work branch, have {who} build docs/loops/{st['name']}/plan/"
        f"plan.r{n}.md and commit, then loop.py start build --plan-loop {st['name']}."
    )


def averages_line(st):
    return "Averages: " + ", ".join(
        f"round {r['n']} {average_text(r['average'])}" for r in st["rounds"]
    )


def below_ten(st):
    last = st["rounds"][-1]["scores"] if st["rounds"] else {}
    low = [f"{role} {score_text(s)}" for role, s in last.items() if s != 10]
    return "Judges below 10: " + (", ".join(low) if low else "none")


def judge_mode(rnd, role):
    """A judge's mode in a round; a changes judge that read in full says so."""
    mode = rnd.get("modes", {}).get(role, "full")
    if mode == "changes" and rnd.get("read", {}).get(role) == "full":
        return "changes, read full"
    return mode


def progress_line(st):
    r = st["rounds"][-1]
    text = f"Round {r['n']} of {st['budget']}: average {average_text(r['average'])}"
    if len(st["rounds"]) > 1:
        text += f" (round before: {average_text(st['rounds'][-2]['average'])})"
    scores = ", ".join(
        f"{role} {score_text(r['scores'][role])} {judge_mode(r, role)}"
        for role in st["panel"]
        if role in r["scores"]
    )
    return f"{text}; {scores}"


# Closing lines ----------------------------------------------------------------

STALLED_WAIT = (
    "STOP: the loop is stalled. Next: find the cause; when it needs the user, ask "
    "(the skill's options for a stalled build); then loop.py diagnosed --note."
)
USER_WAIT = (
    "STOP: waiting for the user's answer. "
    "Next: ask the user, then loop.py resume, accept or abandon."
)
STALLED = (
    "STOP: stalled, less than 0.2 gain in two rounds. Next: read the judge items and "
    "find the cause (judges disagree, a fix trades one gap for another, or a decision "
    "of the user is missing); when it needs the user, ask (the skill's options for a "
    "stalled build); then loop.py diagnosed --note."
)
ASK = (
    "STOP: ask the user, less than 0.2 gain in two rounds. Next: explain what holds "
    "the score back and ask how to go on (the skill's options for ask); then loop.py "
    "resume, accept or abandon."
)
BLOCKED = (
    "STOP: blocking items left after the last round. Next: ask the user (the skill's "
    "options for blocked); then loop.py resume --rounds N, accept or abandon."
)
ABANDONED = (
    "Abandoned: nothing counts as judged. "
    "Next: loop.py start when the work is to be judged again."
)


def open_counts(st):
    items = [it for it in st["items"].values() if effective_open(it)]
    return len(items), sum(1 for it in items if it["kind"] == "blocking")


def after_next(st):
    """What comes after a finished loop: the build, or the acceptance test."""
    return plan_handover(st) if st["kind"] == "plan" else "the acceptance test."


def done_line(st):
    n = len(st["rounds"])
    k, _ = open_counts(st)
    head = f"Done: 10 from every judge in {count(n, 'round')}"
    if k:
        head += f", {count(k, 'improvement')} left"
    head += settled_suffix(st)
    if k:
        return (
            f"{head}. Next: loop.py leftovers, file each as an issue, "
            f"then {after_next(st)}"
        )
    return f"{head}. Next: {after_next(st)}"


def leftovers_next(st):
    if st["kind"] == "plan":
        return f"loop.py leftovers, file each as an issue, {plan_handover(st)}"
    return "loop.py leftovers, file each as an issue, then the acceptance test."


def budget_line(st):
    k, _ = open_counts(st)
    avg = average_text(st["rounds"][-1]["average"])
    return (
        f"Budget used: {count(len(st['rounds']), 'round')}, average {avg}, "
        f"{count(k, 'item')} left{settled_suffix(st)}. Next: {leftovers_next(st)}"
    )


def accepted_line(st):
    k, b = open_counts(st)
    return (
        f"Accepted: by the user in round {len(st['rounds'])} of {st['budget']} with "
        f"{count(k, 'item')} left ({b} blocking). Next: {leftovers_next(st)}"
    )


def skipped_line(st):
    skip = st["skip"]
    return (
        f"Skipped: {short(st['commit'])} ({count(skip.get('files', 0), 'file')}, "
        f"{count(skip.get('lines', 0), 'line')}) is recorded as not judged. "
        "Next: the acceptance test."
    )


def state_exit(loop):
    """The line `round` gives for a loop that is not open."""
    outcome = loop.st["outcome"]
    if outcome == "stalled":
        return Exit(3, STALLED_WAIT)
    if outcome in ("ask", "blocked"):
        return Exit(3, USER_WAIT)
    return Exit(
        2,
        f"Refused: this loop ended ({outcome_words(outcome)}). Next: loop.py status.",
    )


def closing_line(loop):
    st = loop.st
    lines = {
        "done": done_line,
        "budget": budget_line,
        "accepted": accepted_line,
        "skip": skipped_line,
    }
    if st["outcome"] in lines:
        return lines[st["outcome"]](st)
    return {
        "abandoned": ABANDONED,
        "stalled": STALLED,
        "ask": ASK,
        "blocked": BLOCKED,
    }[st["outcome"]]
