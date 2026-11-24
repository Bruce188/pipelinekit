"""Which GitHub workflows run for a branch: the `on:` block of a workflow file.

A small reader for the part of YAML that the block uses (block and flow
mappings and sequences, quoted and plain words, comments), so a word in a
comment or in a step does not count as a trigger. Standard library only.
"""

from __future__ import annotations

import re

PR_EVENTS = ("pull_request", "pull_request_target")
RUNS_HERE = "a workflow here runs on pull requests or on pushes to this branch"
# GitHub starts no push or pull_request run for a commit whose message holds
# one of these, so no check comes for it, also not when the pull request is
# reopened.
SKIP_TAGS = ("[skip ci]", "[ci skip]", "[no ci]", "[skip actions]", "[actions skip]")
SKIP_TRAILER = re.compile(r"^skip-checks: ?true$", re.M)
ON_KEY = re.compile(r"""^(?:on|"on"|'on')\s*:(?:\s+(.*))?$""")


class Line:
    def __init__(self, indent, text):
        self.indent, self.text = indent, text


def strip_comment(line):
    """`line` without its comment; a # inside quotes or a word stays."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'" and (i == 0 or line[i - 1] in " \t[{,:"):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def depth(text):
    """How many brackets `text` leaves open, outside quotes."""
    level, quote = 0, ""
    for ch in text:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            level += 1
        elif ch in "]}":
            level -= 1
    return level


def on_lines(text):
    """The lines of the `on:` block, the first one holding what follows `on:`.

    None when the file has no top-level `on:` key.
    """
    raw = [strip_comment(line.expandtabs()) for line in text.splitlines()]
    at = next((i for i, line in enumerate(raw) if ON_KEY.match(line)), None)
    if at is None:
        return None
    lines = [Line(-1, (ON_KEY.match(raw[at]).group(1) or "").strip())]
    for line in raw[at + 1 :]:
        body = line.lstrip()
        if not body:
            continue
        indent = len(line) - len(body)
        if indent == 0 and not is_item(body) and depth(lines[-1].text) <= 0:
            break
        if depth(lines[-1].text) > 0:  # a flow collection over several lines
            lines[-1].text += " " + body
        else:
            lines.append(Line(indent, body))
    return lines


def is_item(text):
    return text == "-" or text.startswith("- ")


def split_key(text):
    """(key, value) of a mapping line; (None, None) when it is not one."""
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'" and i == 0:
            quote = ch
        elif ch in "[{" and i == 0:
            return None, None
        elif ch == ":" and (i + 1 == len(text) or text[i + 1] in " \t"):
            return unquote(text[:i]), text[i + 1 :].strip()
    return None, None


def unquote(word):
    word = word.strip()
    if len(word) >= 2 and word[0] == word[-1] and word[0] in "\"'":
        return word[1:-1]
    return word


def parse_block(lines, i, indent):
    """The node that starts at lines[i]; returns (node, index after it)."""
    if is_item(lines[i].text):
        return parse_seq(lines, i, indent)
    return parse_map(lines, i, indent)


def skip_deeper(lines, i, indent):
    while i < len(lines) and lines[i].indent > indent:
        i += 1
    return i


def child(lines, i, indent):
    """The block under a key or item that has nothing after it on its line."""
    if i < len(lines) and (
        lines[i].indent > indent
        or (lines[i].indent == indent and is_item(lines[i].text))
    ):
        return parse_block(lines, i, lines[i].indent)
    return None, i


def parse_seq(lines, i, indent):
    items = []
    while i < len(lines) and lines[i].indent == indent and is_item(lines[i].text):
        text = lines[i].text
        rest = text[1:].lstrip()
        if rest and split_key(rest)[0] is not None:  # `- key: value`
            lines[i] = Line(indent + len(text) - len(rest), rest)
            node, i = parse_map(lines, i, lines[i].indent)
        elif rest:
            node, i = inline(rest), skip_deeper(lines, i + 1, indent)
        elif i + 1 < len(lines) and lines[i + 1].indent > indent:
            node, i = parse_block(lines, i + 1, lines[i + 1].indent)
        else:
            node, i = None, i + 1
        items.append(node)
    return items, i


def parse_map(lines, i, indent):
    out = {}
    while i < len(lines) and lines[i].indent == indent and not is_item(lines[i].text):
        key, value = split_key(lines[i].text)
        if key is None:
            raise ValueError(f"not a mapping line: {lines[i].text}")
        if value:
            out[key], i = inline(value), skip_deeper(lines, i + 1, indent)
        else:
            out[key], i = child(lines, i + 1, indent)
    return out, i


class Flow:
    """A flow collection such as `[push, pull_request]` or `{push: {...}}`."""

    def __init__(self, text):
        self.text, self.pos = text, 0

    def peek(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t":
            self.pos += 1
        if self.pos >= len(self.text):
            raise ValueError("a flow collection is not closed")
        return self.text[self.pos]

    def value(self, key=False):
        ch = self.peek()
        if ch in "[{":
            self.pos += 1
            return self.collection("]" if ch == "[" else "}")
        if ch in "\"'":
            end = self.text.find(ch, self.pos + 1)
            if end < 0:
                raise ValueError("a quote is not closed")
            word, self.pos = self.text[self.pos + 1 : end], end + 1
            return word
        start = self.pos
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            after = self.text[self.pos + 1 : self.pos + 2]
            if ch in ",[]{}" or (key and ch == ":" and after in ("", " ", ",", "}")):
                break
            self.pos += 1
        return self.text[start : self.pos].strip()

    def collection(self, close):
        out = [] if close == "]" else {}
        while self.peek() != close:
            if close == "]":
                out.append(self.value())
            else:
                key = self.value(key=True)
                if self.peek() == ":":
                    self.pos += 1
                    out[key] = None if self.peek() in ",}" else self.value()
                else:
                    out[key] = None
            if self.peek() == ",":
                self.pos += 1
            elif self.peek() != close:
                raise ValueError(f"unexpected {self.peek()!r} in a flow collection")
        self.pos += 1
        return out


def inline(text):
    text = text.strip()
    if text[:1] in ("[", "{"):
        return Flow(text).value()
    return unquote(text)


def read_on(text):
    """What the workflow's `on:` holds: a word, a list or a mapping; None if absent.

    Raises ValueError when the block cannot be read.
    """
    lines = on_lines(text)
    if lines is None:
        return None
    try:
        if lines[0].text:
            return inline(lines[0].text)
        node, _ = child(lines, 1, 0)
        return node
    except (IndexError, RecursionError) as exc:
        raise ValueError("the on: block cannot be read") from exc


def events(on):
    """{event: its settings or None} for what `on:` holds."""
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {item: None for item in on if isinstance(item, str)}
    if isinstance(on, dict):
        return {str(key): value for key, value in on.items()}
    return {}


def as_list(value):
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [] if value is None else [str(value)]


def pattern(glob):
    """GitHub's filter pattern as a regular expression.

    `*` matches within one path part, `**` across them; `?`, `+` and `[...]`
    work as in a regular expression; a backslash escapes the next character.
    """
    out, i = [], 0
    while i < len(glob):
        ch = glob[i]
        if glob.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if ch == "*":
            out.append("[^/]*")
        elif ch in "?+":
            out.append(ch)
        elif ch == "[" and "]" in glob[i + 1 :]:
            end = glob.index("]", i + 1)
            out.append(glob[i : end + 1])
            i = end + 1
            continue
        elif ch == "\\" and i + 1 < len(glob):
            out.append(re.escape(glob[i + 1]))
            i += 2
            continue
        else:
            out.append(re.escape(ch))
        i += 1
    try:
        return re.compile("".join(out))
    except re.error:
        return re.compile(re.escape(glob))


def matches(patterns, name):
    """GitHub's branch filter: the last pattern that matches decides; `!` negates."""
    hit = False
    for glob in patterns:
        negated = glob.startswith("!")
        if pattern(glob[1:] if negated else glob).fullmatch(name):
            hit = not negated
    return hit


def push_runs(settings, branch):
    """A `push:` trigger with these settings runs on a push to `branch`."""
    if not isinstance(settings, dict):
        return True
    if "branches" in settings:
        return matches(as_list(settings["branches"]), branch)
    if "branches-ignore" in settings:
        return not matches(as_list(settings["branches-ignore"]), branch)
    # Only tag filters: a push to a branch does not start it.
    return "tags" not in settings and "tags-ignore" not in settings


def runs_for(text, branch):
    """The workflow runs on the pull request of `branch` or on pushes to it.

    Either way its checks show on the pull request's head. A workflow whose
    `on:` block cannot be read counts when it names one of those events.
    """
    try:
        found = events(read_on(text))
    except ValueError:
        plain = "\n".join(strip_comment(line) for line in text.splitlines())
        return bool(re.search(r"\b(pull_request\w*|push)\b", plain))
    if any(event in found for event in PR_EVENTS):
        return True
    return "push" in found and push_runs(found["push"], branch)


def skip_request(message):
    """What in a commit message asks GitHub to skip its workflows; '' if nothing.

    One of GitHub's tags anywhere in the message, or a `skip-checks: true`
    line in its last paragraph, where trailers go.
    """
    for tag in SKIP_TAGS:
        if tag in message:
            return tag
    paragraphs = re.split(r"\n[ \t]*\n", message.replace("\r", "").strip())
    return "skip-checks: true" if SKIP_TRAILER.search(paragraphs[-1]) else ""


def starts_when_ready(text):
    """A pull request trigger of the workflow lists `ready_for_review`."""
    try:
        found = events(read_on(text))
    except ValueError:
        return False
    return any(
        isinstance(found.get(event), dict)
        and "ready_for_review" in as_list(found[event].get("types"))
        for event in PR_EVENTS
    )
