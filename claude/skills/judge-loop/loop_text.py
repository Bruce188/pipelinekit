"""Messages, printing and small text helpers of loop.py."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import unicodedata

SCHEMA = 1
ROLES = (
    "general",
    "correctness",
    "security",
    "tests",
    "operations",
    "user-experience",
    "scope",
)
FULL_PANEL = ROLES[1:]
KINDS = ("plan", "build")
UNFINISHED = ("open", "stalled", "ask", "blocked")
FINISHED = ("done", "budget", "accepted", "abandoned", "skip")
OUTCOMES = UNFINISHED + FINISHED
OUTCOME_WORDS = {
    "ask": "waiting for the user",
    "blocked": "waiting for the user on blocking items",
    "budget": "out of rounds",
    "accepted": "accepted by the user",
    "skip": "skipped without a judge",
}
AGENT_NAMES = ("kit-planner", "kit-builder", "kit-judge")
FALLBACK_SENTENCE = "fallback: the judge is not limited to reading by its tools"

DEFAULT_BUDGET = 5
MAX_SWITCH_ROUNDS = 20
MAX_RESUME_ROUNDS = 5
MAX_RESULT = 200 * 1024
MAX_AGENT_FILE = 64 * 1024
MAX_STATE = 5 * 1024 * 1024
MAX_TEXT_FILE = 1024 * 1024
MAX_DIFF = 2 * 1024 * 1024
MAX_FIELD = 2000
MAX_ITEMS = 50
MAX_DIMENSIONS = 20
FULL_LINES = 400
FULL_FILES = 15
EXEMPT_LINES = 10
GH_TIMEOUT = 10
LIMIT = 300
REFUSED_SHOWN = 40
MAX_PATH_SHOWN = 120
MAX_TOKENS = 1_000_000_000
MAX_AREA_FILE = 200 * 1024
MAX_AREA_PATH = 120
MODES = ("full", "changes", "skipped")
READS = ("full", "changes")
CUT_MARK = " [cut]"

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
ITEM_ID = re.compile(r"[A-Z][A-Za-z0-9_-]{0,19}")
SHA = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")
PLAIN_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+@-]{0,79}")
SAFE_REL = re.compile(r"[A-Za-z0-9._@+-]+(/[A-Za-z0-9._@+-]+)*")
REMOTE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
BLANK = frozenset("\u115f\u1160\u3164\uffa0\u2800")
BOM = b"\xef\xbb\xbf"

# Sizes of change (the table of the skill).
DOC_EXTENSIONS = (".md", ".mdx", ".rst", ".adoc")
SENSITIVE_WORDS = frozenset(
    (
        "auth",
        "authn",
        "authz",
        "security",
        "payment",
        "payments",
        "billing",
        "migration",
        "migrations",
        "hook",
        "hooks",
        "deploy",
        "deployment",
        "install",
        "installer",
        "secrets",
        "credentials",
        "permissions",
    )
)
STEERING_FILES = frozenset(
    ("claude.md", "claude.local.md", "agents.md", "skill.md", ".mcp.json")
)
STEERING_FOLDERS = frozenset((".claude", "agents", "skills", "commands", "roles"))

# Why a result is no score: a field and a phrase, all of them the helper's own
# words. Nothing from the answer file is ever part of the reason.
MISSING = "missing"
WRONG_TYPE = "wrong type"
NOT_A_NUMBER = "not a number"
OUT_OF_RANGE = "outside 0 to 10"
NOT_A_STRING = "not a string"
EMPTY = "empty"
TOO_LONG = "too long"
TOO_MANY = "too many"
NOT_UNIQUE = "not unique"
NOT_AN_ID = "not a valid id"
NOT_OPEN_ID = "not an open id"
NOT_THE_ROLE = "not the role"
TEN_WITH_OPEN = "a 10 with open items"
NOT_ONE_OBJECT = "not one JSON object"
NOT_UTF8 = "not UTF-8"
OVER_SIZE = "over 200 kB"
NOT_HALF_STEP = "not a step of 0.5"
BELOW_NO_ITEM = "below 10 without an item"
TEN_NOT_FULL = "a 10 without a full read"
WHY_PHRASES = (
    MISSING,
    WRONG_TYPE,
    NOT_A_NUMBER,
    OUT_OF_RANGE,
    NOT_A_STRING,
    EMPTY,
    TOO_LONG,
    TOO_MANY,
    NOT_UNIQUE,
    NOT_AN_ID,
    NOT_OPEN_ID,
    NOT_THE_ROLE,
    TEN_WITH_OPEN,
    NOT_ONE_OBJECT,
    NOT_UTF8,
    OVER_SIZE,
    NOT_HALF_STEP,
    BELOW_NO_ITEM,
    TEN_NOT_FULL,
)
# The reasons of `round` that name no field.
NO_RESULT = "no result saved"
SAVE_UNFINISHED = "the save did not finish"
RESULT_CHANGED = "the result changed after it was saved"
OTHER_WORK = "other work"

# The sentences of every judge brief, word for word.
TEN_MINUS = (
    "Your score is 10 minus named items: each lost point needs an item that says "
    "where, what is wrong, the smallest fix and the check that proves it. No item, "
    "no deduction."
)
EVERY_GAP = "List every gap you can find in this round, not the top few."
NO_MARK_DOWN = (
    "Do not mark down for what waits on the user, needs the host, or stands in "
    "settled.md."
)
NO_RAISE_AGAIN = (
    "Do not raise a closed item again without showing where it is still wrong."
)
HALF_STEPS = "Score in steps of 0.5."
READ_FULL = (
    "Read a file you judge whole, once. For a single fact, search first and read "
    "those lines. Read nothing twice."
)
START_FROM_LAST = (
    "Start from your last result and the delta. Read only what changed and what it "
    'touches. Before you give a 10, read the whole work again and answer "read": '
    '"full".'
)
READ_CHANGES = (
    "Read the delta once. For a single fact outside it, search first and read those "
    "lines. The full read before a 10 is the one second read."
)
ONE_OBJECT = "Answer with one compact JSON object and nothing else."
REAL_DEFECT = (
    "From this round on a new item must be a real defect or a gap against "
    "criteria.md or the plan, not something that could be nicer."
)
CHANGE_LOG = (
    "The author's change log holds claims, not proof. Use only its rows marked "
    "r{m} or later: check a `fixed` row in the work, weigh the evidence of an "
    "`answered` row, and do not mark down what an `owner` row leaves to the user."
)

NOT_A_REPO = (
    "Refused: not in a git repository. "
    "Next: work without the judge loop and say so in one line."
)

# The commands, filled in by the sections below: name -> (configure, run).
COMMANDS: dict = {}


class Exit(Exception):
    """The last line of a run and its exit code."""

    def __init__(self, code, line):
        super().__init__(line)
        self.code = code
        self.line = line


class GitFailed(Exception):
    """A git call that ended with a code the helper did not expect."""

    def __init__(self, subcommand, code, said):
        super().__init__(subcommand)
        self.subcommand = subcommand
        self.code = code
        self.said = said


class NoScore(Exception):
    """A result that is not a score: the field and the phrase."""

    def __init__(self, field, why):
        super().__init__(f"{field}: {why}")
        self.field = field
        self.why = why

    @property
    def reason(self):
        return f"{self.field}: {self.why}"


# Printing -------------------------------------------------------------------


def clean(text: object, limit: int = LIMIT) -> str:
    """One line of characters that show (the rule of clean() in check.py)."""
    out = []
    for ch in unicodedata.normalize("NFC", str(text)[: limit * 8]):
        kind = unicodedata.category(ch)
        if kind[0] in "CZ" or ch in BLANK:
            out.append(" ")
        elif kind not in ("Mn", "Me"):
            out.append(ch)
    return " ".join("".join(out).split())[:limit]


def show_path(rel) -> str:
    rel = str(rel)
    if len(rel) <= MAX_PATH_SHOWN and SAFE_REL.fullmatch(rel):
        return rel
    return "a file"


def show_branch(name) -> str:
    return name if PLAIN_BRANCH.fullmatch(name or "") else "another branch"


def show_name(name, other="a file") -> str:
    return name if NAME.fullmatch(name or "") else other


def shown_value(value) -> str:
    """A refused command-line value: cut, and every odd character a '?'."""
    return re.sub(r"[^A-Za-z0-9._/-]", "?", str(value)[:REFUSED_SHOWN])


def short(sha) -> str:
    return sha[:7] if SHA.fullmatch(sha or "") else "none"


def count(n, word) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def score_text(value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:g}" if isinstance(value, float) else str(value)


def average_text(value) -> str:
    return f"{value:.1f}"


def slug(branch):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-") or "branch"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def outcome_words(outcome) -> str:
    """An outcome as plain words: "the loop is <words>"."""
    return OUTCOME_WORDS.get(outcome, outcome)


def quiet_stdout():
    """Send the rest of the output to the null device: its reader is gone."""
    try:
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, sys.stdout.fileno())
        os.close(null)
    except (OSError, ValueError, AttributeError):
        pass


def say(line=""):
    """Print one line; a reader that went away does not stop the command."""
    try:
        print(line, flush=True)
    except BrokenPipeError:
        quiet_stdout()
