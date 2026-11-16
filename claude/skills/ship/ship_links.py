"""The linked gate of ship.py, and what follows a merge for the issues it closes.

GitHub closes an issue when a pull request that says `Closes #N` merges into
the default branch, and only then. A pull request into any other branch merges
without closing its issue; the release pull request that later brings that
branch into the default one has to carry the keywords instead.

The issues of a pull request are the number in its branch name
(`<type>/<issue#>-<slug>`) and every issue its body names after a closing
keyword (`Closes`, `Fixes`, `Resolves` and their other forms) or after a word
that looks like a misspelt one. GitHub's own list, `closingIssuesReferences`,
decides whether a pull request into the default branch closes them.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import contextlib
import difflib
import json
import os
import re
import tempfile
import time

from ship_base import *
from ship_judged import clean

KEYWORDS = (
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
)
STEMS = ("clos", "fix", "resol")
ISSUE = r"#(?P<n>\d{1,9})(?![\w-])"
# `Closes #4` and the issues listed after it, which GitHub does not close:
# `Closes #4, #5` and `Fixes #4 and #5` close #4 alone.
CLOSING = re.compile(
    r"(?<![\w-])(?P<word>close[sd]?|fix(?:e[sd])?|resolve[sd]?)(?:[ \t]*:)?[ \t]+"
    + ISSUE
    + r"(?P<more>(?:[ \t]*(?:,|&|\band\b)[ \t]*#\d{1,9}(?![\w-]))*)",
    re.I,
)
# Any word right before an issue, to find a keyword that is misspelt.
WORD_ISSUE = re.compile(r"(?<![\w-])(?P<word>[A-Za-z]{3,12})(?:[ \t]*:)?[ \t]+" + ISSUE)
BRANCH_ISSUE = re.compile(r"[A-Za-z]+/(\d{1,9})(?:[-_]|$)")
COMMENT = re.compile(r"<!--.*?(?:-->|$)", re.S)
NONE_NAMED = (
    "no issue named: the branch name has no issue number "
    "(<type>/<issue#>-<slug>) and the body no `Closes #N` line"
)
CLOSE_LOOKS = 3  # reads of an issue after the merge before it counts as open


def answer(text, rc):
    """What a failed command said, on one line, without its closing full stop."""
    return clean(said(text, rc)).rstrip(".")


def looks_like_keyword(word):
    """`Closing #4`, `fixs #4`: a word meant as a closing keyword."""
    return word.startswith(STEMS) or bool(
        difflib.get_close_matches(word, KEYWORDS, 1, 0.75)
    )


def numbers(issues):
    """`#1`, `#1 and #2`, `#1, #2 and #3`."""
    names = [f"#{n}" for n in issues]
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def named(body):
    """{issue: how the body names it}, in the order the body names them.

    ('closes', word): right after a keyword; ('only', word, first): listed
    after the issue a keyword closes; ('word', text): after a misspelt keyword.
    """
    text = COMMENT.sub(" ", body or "")
    found = {}
    for m in CLOSING.finditer(text):
        first = int(m["n"])
        found[first] = ("closes", m["word"])
        for extra in re.findall(r"#(\d{1,9})", m["more"]):
            found.setdefault(int(extra), ("only", m["word"], first))
    for m in WORD_ISSUE.finditer(text):
        n, word = int(m["n"]), m["word"].lower()
        if n not in found and looks_like_keyword(word):
            found[n] = ("word", " ".join(m.group(0).split()))
    return found


def wanted(head, body):
    """(issues, how): the issues a pull request is for, and how its body names them."""
    how = named(body)
    issues = []
    m = BRANCH_ISSUE.match(head or "")
    if m:
        issues.append(int(m.group(1)))
    issues += [n for n in how if n not in issues]
    return issues, how


def closed_by(body):
    """The issues a body closes: each one right after a keyword."""
    return {n for n, how in named(body).items() if how[0] == "closes"}


def github_closes(data, name_with_owner):
    """The issues of this repository GitHub will close, as numbers."""
    out = []
    for item in data.get("closingIssuesReferences") or []:
        if not isinstance(item, dict):
            continue
        n = item.get("number")
        where = item.get("repository")
        where = where if isinstance(where, dict) else {}
        owner = (where.get("owner") or {}).get("login") or ""
        full = f"{owner}/{where.get('name') or ''}" if owner else ""
        here = not full or full.lower() == name_with_owner.lower()
        if type(n) is int and here and n not in out:
            out.append(n)
    return out


def links(repo, number):
    """(data, error): the body of a pull request and the issues GitHub links."""
    rc, out, err = repo.gh(
        "pr", "view", str(number), "--json", "body,closingIssuesReferences"
    )
    if rc:
        return {}, answer(err or out, rc)
    try:
        data = json.loads(out)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return {}, "unreadable answer from gh pr view"
    return data, ""


def release_pr(repo, base, default):
    """(pull request, error): the open one from `base` into the default branch."""
    rc, out, err = repo.gh(
        "pr", "list", "--base", default, "--head", base, "--state", "open",
        "--limit", "10", "--json", "number,author,body,isCrossRepository",
    )  # fmt: skip
    if rc:
        return None, answer(err or out, rc)
    try:
        found = json.loads(out)
    except ValueError:
        found = None
    if not isinstance(found, list):
        return None, "unreadable answer from gh pr list"
    found = [
        p
        for p in found
        if isinstance(p, dict)
        and type(p.get("number")) is int
        and not p.get("isCrossRepository")
    ]
    return (min(found, key=lambda p: p["number"]) if found else None), ""


def why_not(n, how):
    """Why GitHub does not list issue `n` among those a pull request closes."""
    lead = f"#{n} is not linked:"
    if how is None:
        return f"{lead} the branch names it, the body has no `Closes #{n}` line"
    if how[0] == "only":
        word, first = how[1], how[2]
        return (
            f"{lead} it follows `{word} #{first}`, which closes only #{first}; "
            f"give #{n} a `Closes #{n}` line of its own"
        )
    if how[0] == "word":
        return f"{lead} `{clean(how[1])}` is not a closing keyword; write `Closes #{n}`"
    return (
        f"{lead} the body says `{how[1]} #{n}`, but GitHub does not list #{n} "
        "among the issues it closes; check that it is an issue of this repository"
    )


def default_of(repo):
    return (repo.info().get("defaultBranchRef") or {}).get("name") or ""


def pair(base, default):
    return f"({clean(base)} -> {clean(default)})"


def linked_gate(repo, pr):
    """The pull request closes its issues when it merges, or says what will."""
    number = pr.get("number")
    base, default = pr.get("baseRefName") or "", default_of(repo)
    if not default:
        return gate("linked", "fail", "gh repo view did not name the default branch")
    data, error = links(repo, number)
    if error:
        return gate(
            "linked", "fail", f"cannot read the issues #{number} closes: {error}"
        )
    issues, how = wanted(pr.get("headRefName"), data.get("body"))
    if base == default:
        closes = github_closes(data, repo.info().get("nameWithOwner") or "")
        missing = [n for n in issues if n not in closes]
        if missing:
            why = "; ".join(why_not(n, how.get(n)) for n in missing)
            return gate("linked", "fail", why)
        if not closes:
            return gate("linked", "pass", NONE_NAMED)
        return gate(
            "linked", "pass", f"closes {numbers(closes)} on the merge into {default}"
        )
    if not issues:
        return gate("linked", "pass", NONE_NAMED)
    lead = f"GitHub does not close {numbers(issues)} on a merge into {clean(base)}"
    other, error = release_pr(repo, base, default)
    if error:
        return gate(
            "linked",
            "fail",
            f"{lead}, and cannot find the release pull request "
            f"{pair(base, default)}: {error}",
        )
    if other is None:
        return gate(
            "linked",
            "pass",
            f"{lead}; no release pull request {pair(base, default)} is open: "
            "give it one `Closes #N` line per issue when you open it",
        )
    them = f"the release pull request #{other['number']} {pair(base, default)}"
    if set(issues) <= closed_by(other.get("body")):
        return gate(
            "linked", "pass", f"{lead}; {them} already closes {numbers(issues)}"
        )
    author = clean((other.get("author") or {}).get("login") or "")
    if author and author.lower() == repo.user().lower():
        return gate(
            "linked",
            "pass",
            f"{lead}; {them} will: ship adds the `Closes` lines to it after the merge",
        )
    return gate(
        "linked",
        "pass",
        f"{lead}; {them} will: it was opened by {author or 'someone else'}, so "
        "ship prints the `Closes` lines to add after the merge",
    )


# ---------------------------------------------------------------- after the merge


def issue_open(repo, n):
    """(True when issue `n` is open, error)."""
    rc, out, err = repo.gh("issue", "view", str(n), "--json", "state")
    if rc:
        return False, answer(err or out, rc)
    try:
        state = json.loads(out).get("state")
    except (ValueError, AttributeError):
        state = None
    if not isinstance(state, str):
        return False, "unreadable answer from gh issue view"
    return state.upper() != "CLOSED", ""


def check_closed(repo, issues):
    """Lines on the issues a merge into the default branch should have closed.

    GitHub can take a moment to close an issue, so an open one is read again.
    """
    left, failed = list(issues), {}
    for look in range(CLOSE_LOOKS):
        if look:
            time.sleep(min(poll_seconds(), 2))
        now = []
        for n in left:
            is_open, error = issue_open(repo, n)
            if error:
                failed[n] = error
            elif is_open:
                now.append(n)
        left = now
        if not left:
            break
    closed = [n for n in issues if n not in left and n not in failed]
    lines = [f"Closed: {numbers(closed)}."] if closed else []
    lines += [
        f"#{n} is still open after the merge: GitHub did not close it. Close it "
        f"with gh issue close {n} once its work is done."
        for n in left
    ]
    lines += [f"Could not read #{n}: {why}." for n, why in failed.items()]
    return lines


def edit_body(repo, number, body):
    """Replace the body of pull request `number`; return an error or ''."""
    try:
        fd, path = tempfile.mkstemp(prefix="ship-body-", suffix=".md")
    except OSError as exc:
        return clean(f"cannot write the new body: {exc}")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        rc, out, err = repo.gh("pr", "edit", str(number), "--body-file", path)
    except OSError as exc:
        return clean(f"cannot write the new body: {exc}")
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)
    return answer(err or out, rc) if rc else ""


def carry(repo, base, default, issues):
    """Put a `Closes` line per issue on the release pull request, or print them."""
    where = pair(base, default)
    other, error = release_pr(repo, base, default)
    if error:
        lines = [f"Closes #{n}" for n in issues]
        head = f"Could not find the release pull request {where}: {error}."
        return [f"{head} Put these lines in its body:", *(f"  {x}" for x in lines)]
    if other is None:
        lines = [f"Closes #{n}" for n in issues]
        return [
            f"GitHub does not close {numbers(issues)} on a merge into "
            f"{clean(base)}, and no release pull request {where} is open. "
            "When you open it, put these lines in its body:",
            *(f"  {x}" for x in lines),
        ]
    number, body = other["number"], other.get("body") or ""
    there = closed_by(body)
    lines = [f"Closes #{n}" for n in issues if n not in there]
    them = f"the release pull request #{number} {where}"
    if not lines:
        return [f"{them[0].upper()}{them[1:]} already closes {numbers(issues)}."]
    author = clean((other.get("author") or {}).get("login") or "")
    if not author or author.lower() != repo.user().lower():
        return [
            f"{them[0].upper()}{them[1:]} was opened by {author or 'someone else'}: "
            "add these lines to its body:",
            *(f"  {x}" for x in lines),
        ]
    gap = "\n\n" if body.strip() else ""
    error = edit_body(repo, number, body.rstrip() + gap + "\n".join(lines) + "\n")
    if error:
        return [
            f"Could not edit {them}: {error}. Add these lines to its body:",
            *(f"  {x}" for x in lines),
        ]
    return [f"Added to {them}: {'; '.join(lines)}."]


def after_merge(repo, pr):
    """Lines on the issues of a pull request that was just merged; never raises.

    Into the default branch: which of its issues GitHub closed. Into another
    branch: the `Closes` lines go to the release pull request, which ship
    edits but never merges.
    """
    number, base = pr.get("number"), pr.get("baseRefName") or ""
    try:
        default = default_of(repo)
        data, error = links(repo, number)
        if error:
            return [f"Could not read the issues #{number} closes: {error}."]
        issues, _ = wanted(pr.get("headRefName"), data.get("body"))
        if default and base == default:
            closes = github_closes(data, repo.info().get("nameWithOwner") or "")
            issues = closes + [n for n in issues if n not in closes]
            return check_closed(repo, issues) if issues else []
        if not default or not issues:
            return []
        return carry(repo, base, default, issues)
    except ToolError as exc:
        return [f"Could not follow up the issues of #{number}: {answer(str(exc), 1)}."]
