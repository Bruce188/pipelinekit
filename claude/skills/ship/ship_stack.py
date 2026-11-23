"""Stacks in ship: a pull request of a judged stack merges bottom-up, once its
own items and those below it are cleared and nothing unjudged came on its
branch; after a merge, the pull requests based on the merged branch move to
the branch it merged into and are brought up to date by a merge."""

from __future__ import annotations

import json
from pathlib import Path

NAME = "stack"
MAX_STATE = 4 * 1024 * 1024
SHOWN = 5


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def first_line(text, rc):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return (lines[-1] if lines else f"exit {rc}").rstrip(".")[:200]


def worktrees(repo):
    """The folders of every worktree of the repository, this one first."""
    out = [Path(repo.root)]
    rc, text, _ = repo.try_git("worktree", "list", "--porcelain")
    if rc:
        return out
    for line in text.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree ") :])
            if path not in out:
                out.append(path)
    return out


def read_state(path):
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > MAX_STATE:
            return None
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(st, dict) or not isinstance(st.get("stack"), dict):
        return None
    prs = st["stack"].get("prs")
    if not isinstance(prs, list) or not all(isinstance(e, dict) for e in prs):
        return None
    return st


def find_stack(repo, number):
    """(path, state) of the newest stack loop, in any worktree, that holds this
    pull request; None when it is in none."""
    found = []
    for root in worktrees(repo):
        for path in sorted((root / "docs" / "loops").glob("*/build/state.json")):
            st = read_state(path)
            if st and any(e.get("pr") == number for e in st["stack"]["prs"]):
                try:
                    found.append((path.stat().st_mtime, str(path), path, st))
                except OSError:
                    continue
    if not found:
        return None
    found.sort(key=lambda entry: entry[:2])
    return found[-1][2], found[-1][3]


def open_at_or_below(st, below):
    """The open items on a pull request at or below this one; an item that
    names no pull request holds every pull request of the stack."""
    items = st.get("items") if isinstance(st.get("items"), dict) else {}
    out = []
    for key, it in items.items():
        if not isinstance(it, dict) or not it.get("open"):
            continue
        settled = it.get("settled")
        if isinstance(settled, dict) and settled and not settled.get("raised_again"):
            continue
        if "pr" not in it or it["pr"] in below:
            out.append(key)
    return out


def stack_gate(repo, pr, gate):
    """The stack gate of one pull request."""
    number = pr.get("number")
    found = find_stack(repo, number)
    if not found:
        return gate(NAME, "pass", "not in a judged stack")
    path, st = found
    entries = st["stack"]["prs"]
    numbers = [e.get("pr") for e in entries]
    k = numbers.index(number)
    where = path.parent.as_posix()
    rounds = [r for r in st.get("rounds") or [] if isinstance(r, dict)]
    again = f"judge the stack again (loop.py brief in {where})"
    if not rounds:
        return gate(NAME, "fail", f"the stack loop in {where} has no judged round yet")
    if st.get("outcome") != "accepted":
        left = open_at_or_below(st, set(numbers[: k + 1]))
        if left:
            shown = ", ".join(left[:SHOWN]) + (", ..." if len(left) > SHOWN else "")
            return gate(
                NAME,
                "fail",
                f"{plural(len(left), 'item')} open at or below #{number} ({shown}): "
                f"fix each on its pull request's branch, merge it up, then {again}",
            )
    base = pr.get("baseRefName") or ""
    lower = {e.get("branch"): e.get("pr") for e in entries[:k]}
    if base in lower:
        return gate(
            NAME,
            "fail",
            f"#{lower[base]} below it merges first: a stack merges bottom-up",
        )
    heads = rounds[-1].get("heads")
    judged = heads.get(str(number)) if isinstance(heads, dict) else None
    n = len(rounds)
    if not isinstance(judged, str) or not judged:
        return gate(NAME, "fail", f"round {n} of the stack has no head of #{number}")
    head = pr.get("headRefOid") or repo.head
    rc, out, _ = repo.try_git(
        "rev-list",
        "--no-merges",
        f"{judged}..{head}",
        f"^refs/remotes/{repo.remote}/{base}",
        "--",
    )
    if rc:
        return gate(
            NAME,
            "fail",
            f"cannot compare the head with the head judged in round {n}: fetch, "
            "then ship again",
        )
    new = [line for line in out.splitlines() if line.strip()]
    if new:
        return gate(
            NAME,
            "fail",
            f"{plural(len(new), 'commit')} on #{number} not judged since round {n}: "
            f"{again}",
        )
    return gate(
        NAME,
        "pass",
        f"judged in round {n} of the stack; no item open at or below #{number}",
    )


def retarget(repo, merged, into, login):
    """Move the open pull requests based on the merged branch to `into` and merge
    `into` into each of them. `login` gives the user's login, '' when unknown.
    The lines that say what was done; only the user's own pull requests move."""
    if not merged or not into:
        return []
    rc, out, err = repo.gh(
        "pr", "list", "--base", merged, "--state", "open",
        "--json", "number,author,isCrossRepository,headRefName",
    )  # fmt: skip
    by_hand = f"set the base of each pull request on {merged} to {into} by hand"
    if rc:
        return [
            f"Not moved: gh pr list failed ({first_line(err or out, rc)}); {by_hand}."
        ]
    try:
        found = json.loads(out or "[]")
    except ValueError:
        found = None
    if not isinstance(found, list):
        return [f"Not moved: gh pr list gave an unreadable answer; {by_hand}."]
    lines, me = [], None
    for entry in found:
        number = entry.get("number") if isinstance(entry, dict) else None
        if not isinstance(number, int) or isinstance(number, bool):
            continue
        if me is None:
            me = login()
        author = entry.get("author") if isinstance(entry.get("author"), dict) else {}
        if entry.get("isCrossRepository") or not me or author.get("login") != me:
            lines.append(
                f"Not moved: #{number} on {merged} is not yours; ask its author to "
                f"set its base to {into}."
            )
            continue
        rc, out, err = repo.gh("pr", "edit", str(number), "--base", into)
        if rc:
            why = first_line(err or out, rc)
            lines.append(
                f"Not moved: #{number}: gh pr edit failed ({why}); set its base to "
                f"{into} by hand."
            )
            continue
        rc, out, err = repo.gh("pr", "update-branch", str(number), timeout=120)
        if rc:
            why = first_line(err or out, rc)
            branch = entry.get("headRefName") or "its branch"
            lines.append(
                f"Moved #{number} to {into}, not updated: gh pr update-branch failed "
                f"({why}); merge {into} into {branch} by hand (never rebase)."
            )
            continue
        lines.append(f"Moved #{number} to {into} and merged {into} into its branch.")
    return lines
