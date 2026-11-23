#!/usr/bin/env python3
"""Finish a pull request you opened: test record, CI wait, gated merge.

  ship.py status [--json] [--exit-zero]    every merge gate and why it holds or not
  ship.py record --result pass|fail ...    store one round of the acceptance test
  ship.py wait [--timeout S] [--grace S]   return when CI on the head commit is done
  ship.py merge [--dry-run] [--stay]       check the gates, wait for CI, merge

Exit codes: 0 ok; 1 a gate or a check failed; 2 usage or tool error; 3 stop and
ask the user (a review, a release, someone else's pull request, a project that
asks first, or a test loop that does not converge). A passed round says
whether the pull request is a release: `record --result pass --release no`.

Standard library only. Needs git and a signed-in gh.
"""

from __future__ import annotations

import argparse
import configparser
import fnmatch
import json
import math
import os
import plistlib
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

try:
    import tomllib
except ImportError:  # before Python 3.11
    tomllib = None

SCHEMA = 1
PR_FIELDS = (
    "number,url,title,state,isDraft,isCrossRepository,baseRefName,headRefName,"
    "headRefOid,author,reviewDecision,reviewRequests,mergeable,mergeStateStatus,"
    "statusCheckRollup"
)
REPO_FIELDS = (
    "nameWithOwner,defaultBranchRef,mergeCommitAllowed,squashMergeAllowed,"
    "rebaseMergeAllowed"
)
METHODS = {
    "merge": "mergeCommitAllowed",
    "squash": "squashMergeAllowed",
    "rebase": "rebaseMergeAllowed",
}
PASSING = {"SUCCESS", "NEUTRAL", "SKIPPED"}
FAILING = {"FAILURE", "ERROR"}


def wordset(text):
    """The words of `text` as a set."""
    return frozenset(text.split())


# The line that opts a project out: plain, as a list or task item, a heading,
# a table cell, quoted, bold, inside an HTML comment, or as code alone on its
# line. A sentence that only mentions the line does not count.
LINE_LEAD = re.compile(
    r"^(?:<!--\s*)?(?:>\s*)*(?:#{1,6}\s+)?(?:(?:[-*+]|\d{1,9}[.)])\s+)?"
    r"(?:\[[ xX]\]\s+)?"
)
OPT_OUT = re.compile(
    r"^(?:(?:pipelinekit\s*:\s*)?merg(?:es?|ing)\s*(?::|-|\u2013|\u2014)\s*"
    r"(?:always\s+)?(?:ask|never|off|manual(?:ly)?)\b"
    r"|`merges?\s*:\s*ask(?:\s+first)?`[\s.]*(?:-->)?$)",
    re.I,
)

# Releases stay with the user. A release is recognised by its branches, by its
# title and by what it changes: a version number, or a version heading in the
# changelog. A miss here merges something the user wanted to decide, so the
# rules lean towards asking.
VERSION = r"v?\d+\.\d+(?:\.\d+)?(?:[-+.][0-9A-Za-z.-]+)?"
RELEASE_HEAD = re.compile(
    r"^(?:"
    r"(?:pre-?)?releases?(?:/.*|[-_]v?\d.*)?"
    r"|release-please--.*|changeset-release/.*"
    r"|(?:rel|rc|hotfix)[/-]v?\d+\.\d.*"
    rf"|{VERSION}"
    r")$",
    re.I,
)
# A stage on the way to a release, as a whole branch name and as the first
# part of one (`staging/eu`).
STAGE_HEADS = wordset(
    "develop development dev integration staging stage next beta alpha rc "
    "canary preview nightly edge uat qa preprod test testing stable "
    "main master trunk snapshot"
)
STAGE_PREFIXES = wordset("integration staging stage uat qa preprod env deploy")
MAINLINES = ("main", "master")
# One of these words anywhere in the name of a base branch makes it a deploy
# branch: `production-eu`, `aws-prod`, `gh-pages`.
DEPLOY_WORDS = wordset(
    "production prod prd live stable deploy deployment deployments deployed "
    "pages publish published released latest heroku netlify vercel"
)
# The branches besides the default one that ordinary work goes into: a shared
# working branch, a release line, another topic branch. Any other base is held.
WORK_BASES = wordset(
    "develop development dev integration staging stage next beta alpha "
    "canary preview nightly edge uat qa preprod test testing trunk"
)
WORK_PREFIXES = wordset("integration staging stage uat qa preprod")
TOPIC_PREFIXES = wordset(
    "feat feature fix bugfix chore docs doc refactor test tests perf ci build "
    "style revert task spike"
)
RELEASE_LINE = re.compile(
    r"^(?:(?:pre-?)?releases?[/_-].+|(?:rel|rc|hotfix|support|maint|maintenance)"
    r"[/-].+|v?\d+(?:\.(?:\d+|x))*)$"
)
TITLE_PREFIX = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?!?\s*:\s*", re.I)
# `[skip ci]` and its relatives say nothing about what a pull request is.
CI_TAG = re.compile(
    r"\[\s*(?:skip[ -][a-z]+|[a-z]+[ -]skip|no[ -]ci)\s*\]|\*{3}NO_CI\*{3}", re.I
)
MERGE_TITLE = re.compile(
    r"^merge\s+(?:remote-tracking\s+)?(?:branch\s+)?'?([\w./-]+)'?\s+into\s+"
    r"'?([\w./-]+)'?$",
    re.I,
)
RELEASE_MARK = re.compile(
    r"\[[^\]]*\b(?:pre-?)?releases?\b[^\]]*\]"
    r"|\(\s*(?:pre-?)?release(?:\s+v?\d[\w.+-]*)?\s*\)",
    re.I,
)
TOKEN = re.compile(
    r"(?P<version>(?<![\w.])v?\d+(?:\.(?:\d+|x))+(?:[-+][0-9a-z][0-9a-z.]*)*"
    r"|(?<![\w.])v\d+(?![\w.])"
    r"|(?<![\w.])(?:rc|beta|alpha)[ .-]?\d+(?![\w.]))"
    r"|(?P<word>[a-z][a-z0-9]*)"
    r"|(?P<number>\d+)"
)
# The words a release title is made of. A title with other words in it is
# about something else: `fix: release the lock before retrying`.
RELEASE_NAMES = wordset("release releases releasing released prerelease")
STRONG = RELEASE_NAMES | wordset(
    "version versions publish production prod hotfix deploy"
)
ACTIONS = wordset(
    "bump bumps bumped bumping cut tag ship deploy prepare prepared preparing "
    "prep finalize finalise finish finishing increment increase raise set "
    "update upgrade new publish create creating promote promoting do make start"
)
FILLER = wordset("for to the of and a an from in on with into")
VOCABULARY = (
    STRONG
    | ACTIONS
    | FILLER
    | wordset(
        "candidate rc changelog notes package packages npm pypi pre beta alpha "
        "patch minor major number numbers initial first final stable lts ga rel re"
    )
)
# What a pull request changes decides too. The lists below name the places
# where a version is ordinary: lock files, tool versions, dependencies, tests.
# A version anywhere else is held, whatever the file format.
NUMBER = re.compile(r"(?<![\w.])v?(\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.]+)*)")
LOCK_FILES = wordset(
    "package-lock.json npm-shrinkwrap.json yarn.lock pnpm-lock.yaml cargo.lock "
    "poetry.lock uv.lock pdm.lock pipfile.lock gemfile.lock composer.lock go.sum "
    "go.mod packages.lock.json flake.lock mix.lock pubspec.lock podfile.lock "
    "bun.lock bun.lockb deno.lock gradle.lockfile"
)
TOOL_FILES = wordset(
    ".python-version .nvmrc .node-version .ruby-version .tool-versions "
    ".java-version .terraform-version .sdkmanrc rust-toolchain "
    "rust-toolchain.toml global.json gemfile pipfile .pre-commit-config.yaml "
    "dependabot.yml renovate.json .mise.toml mise.toml gradle-wrapper.properties "
    "libs.versions.toml directory.packages.props .gitlab-ci.yml "
    "azure-pipelines.yml .travis.yml packages.config paket.dependencies "
    "paket.lock deps.edn"
)
TOOL_STARTS = (
    "requirements",
    "constraints",
    "dockerfile",
    "docker-compose",
    "compose.",
)
SKIP_ENDS = (
    ".lock",
    ".tf",
    ".hcl",
    ".tfvars",
    ".nix",
    ".snap",
    ".svg",
    ".map",
    ".ipynb",
    ".min.js",
    ".min.css",
)
SKIP_ROOTS = (
    ".github/",
    ".circleci/",
    ".devcontainer/",
    ".vscode/",
    ".idea/",
    ".husky/",
)
SKIP_DIRS = wordset(
    "test tests testing __tests__ spec specs fixtures fixture testdata vendor "
    "node_modules third_party thirdparty examples example samples sample "
    "__mocks__ __snapshots__"
)
CODE_ENDS = wordset(
    ".py .pyi .js .mjs .cjs .ts .mts .cts .tsx .jsx .rb .go .rs .java .kt .kts "
    ".swift .c .h .cc .cpp .cxx .hpp .cs .fs .vb .php .pl .pm .sh .bash .zsh "
    ".fish .ps1 .psm1 .bat .cmd .lua .ex .exs .erl .scala .clj .dart .m .mm .r "
    ".jl .hs .ml .sql .vue .svelte .css .scss .less"
)
# Source files that are a manifest all the same.
MANIFEST_CODE = wordset(
    "setup.py mix.exs build.gradle.kts settings.gradle.kts package.swift "
    "conanfile.py app.config.js app.config.ts app.config.mjs app.config.cjs"
)
DOC_ENDS = wordset(".md .markdown .mdx .rst .adoc .txt .html .htm .tex .org")
NOTES_STEMS = wordset("changelog changes history news releases releasenotes")
NOTES_DIRS = wordset(
    "changelog changelogs releases release-notes release_notes releasenotes"
)
VERSION_STEMS = wordset(
    "version bumpversion releasepleasemanifest appversion versioninfo"
)
XML_ENDS = (".xml", ".csproj", ".fsproj", ".vbproj", ".nuspec", ".props", ".targets")
# A table or element of these names holds the versions of other things.
DEPENDS = re.compile(
    r"depend|require|reference|engine|resolution|override|peer|build-?system"
    r"|toolchain|catalog",
    re.I,
)
XML_DEPENDS = re.compile(
    r"^(?:plugin|parent$|extension|properties$|profile)|depend|reference", re.I
)
KEY_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")
# A key with one of these words in it is the version of a tool or a format.
TOOL_WORDS = wordset(
    "python node nodejs ruby java jdk jvm go golang rust php sdk api schema "
    "manifest lockfile lang language framework tool tools gradle kotlin swift "
    "min minimum max maximum target compile required requires object format "
    "protocol runtime dotnet terraform compiler ecma jsx config npm yarn pnpm "
    "pip cargo maven scala clang gcc cmake xcode ndk typescript docker helm "
    "kube kubernetes wrapper bundler engine plugin provider ansible os "
    "platform model dictionary"
)
TOOL_KEY_STARTS = (
    "min",
    "max",
    "python",
    "node",
    "java",
    "php",
    "ruby",
    "rust",
    "api",
    "sdk",
    "schema",
    "lockfile",
    "required",
    "target",
    "compile",
    "format",
    "ecma",
    "lang",
    "golang",
)
VALUE = re.compile(r"\s*[\"'\[({]*v?\d")
# `version = "1.2.3"` and its relatives anywhere on a line of a manifest.
DECLARES = re.compile(
    r"(?<![\w.-])(?P<key>[\w.-]*version\w*)[\"']?\s*"
    r"(?:[:?+]?=(?!=)|:(?!:)|\(|>|\s)\s*[\"'\[({]*v?\d",
    re.I,
)
# The same at the start of a line of source code, with a quoted number: an
# assignment, a key of an object, a struct or a dictionary, a `#define`.
VERSION_NAME = (
    r"(?:__version__|(?:(?:app|package|pkg|project)_?)?version"
    r"(?:_?(?:name|code|string|number))?)"
)
CODE_VERSION = re.compile(
    r"^\s*(?:"
    r"(?:(?:export|pub|public|private|protected|internal|static|final|const"
    r"|constexpr|readonly|override|inline|extern|let|var|val|def|local|our|my"
    r"|string|std::string|int|char)(?:\s+|\s*\*\s*))*(?:[\w.]+\.|@|\$)?"
    + VERSION_NAME
    + r"\s*(?:\[\d*\]\s*)?(?:\{[^{}]*\}\s*)?(?::\s*[\w&' ]+?\s*)?:?=>?"
    r"|[\"']?" + VERSION_NAME + r"[\"']?\s*(?::|=>)(?=\s*[\"'`]v?\d+\.\d)"
    r"|#\s*define\s+" + VERSION_NAME + r"(?=\s)"
    r"|define\(\s*[\"']" + VERSION_NAME + r"[\"']\s*,"
    r"|@version(?=\s)"
    r")\s*[\"'`]v?\d",
    re.I,
)
# A line that pins something else: a dependency, a plugin, an image, a range.
DEP_LINE = re.compile(
    r"depend|require|plugin|classpath|implementation|\buses\s*:|\bimage\s*:"
    r"|^\s*from\s|\brev\s*:|^\s*(?:gem|pod|id)\s|cmake_minimum|bazel_dep"
    r"|\.package\("
    r"|[\"')]\s+version\s+[\"']|^\s*<\?xml|[=~^<>]=|~>|\w@v?\d"
    r"|[\w.-]+:[\w.-]+:v?\d",
    re.I,
)
# Three numbers, so not an IP address.
MASK = re.compile(r"(?<![\d.])\d+\.\d+\.\d+(?!\.?\d)(?:[-+][\w.]+)?")
UNDERLINE = re.compile(r"^\s*([=\-~^\"*+#])\1{2,}\s*$")
LINK_DEF = re.compile(r"^\s*\[v?\d[^\]]*\]\s*:")
NOTE_WORDS = wordset("version release released v")
PROJECT_LINE = re.compile(
    r"^[*_]*release\s+(file|branch)(?:e?s)?[*_]*\s*:[*_]*\s*(.+)$", re.I
)
BINARY_ENDS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".pdf",
    ".zip",
    ".gz",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".jar",
    ".dll",
    ".exe",
    ".so",
    ".bin",
)
DOC_STEMS = wordset(
    "readme license licence copying notice authors contributing contributors "
    "codeowners security todo"
)
DOTTED = re.compile(r"\d+[.,]\d")
YAML_PAIR = re.compile(r"([\"']?)([\w.@/$-]+)\1\s*:(?:\s+(.*))?$")
# What a line of release notes may hold besides the number and still be the
# heading of a version: `Version 1.2.4`, `1.2.4 - November 10, 2026`.
MONTHS = wordset(
    "jan january feb february mar march apr april may jun june jul july aug "
    "august sep sept september oct october nov november dec december"
)
STRIP_NOTE = re.compile(
    r"\([^)]*\)|<[^>]*>|https?://\S+|\d{4}-\d{2}-\d{2}|:[a-z0-9_+-]+:", re.I
)
SHORTCODE = re.compile(r":[a-z0-9_+-]+:")
LEVELS = wordset("patch minor major")
VERSION_WORDS = wordset("version versions")
# A title about one of these is about a tool, not about the project's version.
TOOLCHAIN = wordset(
    "python node nodejs ruby java go golang rust php dotnet net sdk gradle "
    "kotlin swift docker typescript yarn pnpm terraform deps dependency "
    "dependencies ubuntu debian alpine macos windows xcode android ios"
)
# And a title about one of these is about how releases are made.
MACHINERY = wordset(
    "workflow job script pipeline action docs config process checklist "
    "template step gate check test tests guide automation ci"
)
# The first word of a stage branch with a region or a number: `staging-eu`.
STAGE_FIRST = wordset(
    "integration staging stage uat qa preprod snapshot canary nightly"
)
NEW_VERSION = ": a new version is a release"
MAX_VERSION_FILES = 200
MAX_BLOB = 1_000_000
MAX_LINE = 500
QUIET_TYPES = wordset("docs test style refactor perf")
PLAIN_TYPES = wordset("feat feature fix bugfix revert")

CONVENTIONAL = re.compile(r"^[a-z]+(?:\([^)]*\))?!?: ")
MAX_FAILED_ROUNDS = 5
MAX_ROUNDS_OPEN = 3
# A draft that was marked ready has to stay mergeable this long, and on two
# reads at least, before it is merged: checks, review requests and branch
# protection that start with "ready for review" take a while to show up.
SETTLE = 30
FIRST_CHECK = 90  # how long a first check may take to show up
UNKNOWN_LOOKS = 20  # how long GitHub may take to say whether it can be merged
EXIT_FAIL, EXIT_TOOL, EXIT_STOP = 1, 2, 3
WORD = {"pass": "ok", "fail": "FAIL", "pending": "wait", "skip": "-"}


class ToolError(Exception):
    """git or gh is missing, timed out or answered with an error."""


class RecordError(ToolError):
    """The test record is there but cannot be read."""


def run(cmd, cwd=None, timeout=60):
    """Run a command; return (exit code, stdout, stderr) and never raise."""
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} gave no answer within {timeout} s"
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def slug(branch):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-") or "branch"


def short(sha):
    return (sha or "")[:7] or "none"


def count(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def said(text, rc):
    """What a failed command answered, on one line."""
    return " ".join((text or "").split())[:300] or f"exit {rc}"


def git_said(text, rc):
    """Why a git command failed: its error line, without the hints around it."""
    lines = [line.strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line and not line.startswith("hint:")]
    errors = [line for line in lines if line.startswith(("fatal:", "error:"))]
    return said((errors or lines or [""])[0], rc)


def poll_seconds():
    try:
        return max(0.01, float(os.environ.get("SHIP_POLL_SECONDS", "15")))
    except ValueError:
        return 15.0


class Repo:
    """The checkout ship.py runs in, with its git and gh calls."""

    def __init__(self):
        rc, out, _ = run(["git", "rev-parse", "--show-toplevel"])
        if rc:
            raise ToolError("not inside a git repository")
        self.root = Path(out)
        self.branch = self.git("branch", "--show-current")
        if not self.branch:
            raise ToolError("no branch is checked out")
        self.head = self.git("rev-parse", "HEAD")
        remote = self.try_git("config", f"branch.{self.branch}.remote")[1]
        self.remote = remote if remote and remote != "." else "origin"
        self._info = None
        self._user = None
        self._workflows = None

    def try_git(self, *args):
        return run(["git", *args], cwd=self.root)

    def git(self, *args):
        rc, out, err = self.try_git(*args)
        if rc:
            raise ToolError(f"git {' '.join(args)}: {err or out or f'exit {rc}'}")
        return out

    def gh(self, *args, timeout=30):
        return run(["gh", *args], cwd=self.root, timeout=timeout)

    def gh_json(self, *args):
        rc, out, err = self.gh(*args)
        what = "gh " + " ".join(args[:2])
        if rc:
            raise ToolError(f"{what}: {said(err or out, rc)}")
        try:
            data = json.loads(out)
        except ValueError as exc:
            raise ToolError(f"{what}: unreadable answer") from exc
        if not isinstance(data, dict):
            raise ToolError(f"{what}: unreadable answer")
        return data

    def pr(self):
        """The pull request of the current branch, or None when there is none."""
        rc, out, err = self.gh("pr", "view", "--json", PR_FIELDS)
        if rc and "no pull requests found" in err.lower():
            return None
        if rc:
            raise ToolError(f"gh pr view: {said(err or out, rc)}")
        try:
            data = json.loads(out)
        except ValueError as exc:
            raise ToolError("gh pr view: unreadable answer") from exc
        if not isinstance(data, dict):
            raise ToolError("gh pr view: unreadable answer")
        return data

    def default_branch(self):
        """The default branch as the remote names it; '' when git does not know."""
        rc, out, _ = self.try_git(
            "symbolic-ref", "-q", f"refs/remotes/{self.remote}/HEAD"
        )
        return "" if rc else out.removeprefix(f"refs/remotes/{self.remote}/")

    def info(self):
        if self._info is None:
            self._info = self.gh_json("repo", "view", "--json", REPO_FIELDS)
        return self._info

    def user(self):
        if self._user is None:
            rc, out, err = self.gh("api", "user", "--jq", ".login")
            if rc or not out:
                raise ToolError(f"gh api user: {err or 'no login'}")
            self._user = out
        return self._user

    def dirty(self):
        return bool(self.git("status", "--porcelain", "--untracked-files=no"))

    @property
    def record_file(self):
        return self.root / "docs" / "uat" / f"{slug(self.branch)}.json"

    def workflows(self):
        """The text of every GitHub workflow file in the checkout."""
        if self._workflows is None:
            texts = []
            for path in sorted((self.root / ".github" / "workflows").glob("*.y*ml")):
                try:
                    texts.append(path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    texts.append("")
            self._workflows = texts
        return self._workflows

    def has_workflows(self):
        return bool(self.workflows())

    def expects_checks(self):
        """A workflow here runs on pull requests, so a check should show up."""
        return any("pull_request" in text for text in self.workflows())

    def starts_on_ready(self):
        return any("ready_for_review" in text for text in self.workflows())


# ---------------------------------------------------------------- test record


def load_record(path):
    """The stored rounds; none when there is no file yet.

    A file that is there but unreadable is an error: reading it as empty would
    drop the earlier rounds on the next write.
    """
    problem = (
        f"docs/uat/{path.name} is not a readable test record: move it away, "
        "then record the test again"
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": SCHEMA, "rounds": []}
    except (OSError, ValueError) as exc:
        raise RecordError(problem) from exc
    rounds = data.get("rounds") if isinstance(data, dict) else None
    if not isinstance(rounds, list):
        raise RecordError(problem)
    data["rounds"] = [r for r in rounds if isinstance(r, dict)]
    return data


def ensure_ignored(repo):
    """Test records are local working notes: keep them out of commits."""
    if repo.try_git("check-ignore", "-q", "docs/uat/record.json")[0] == 0:
        return
    rc, out, _ = repo.try_git("rev-parse", "--git-path", "info/exclude")
    if rc:
        return
    exclude = repo.root / out
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        old = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        gap = "" if not old or old.endswith("\n") else "\n"
        exclude.write_text(f"{old}{gap}docs/uat/\n", encoding="utf-8")
    except OSError:
        return


def finding_ids(values):
    """Finding ids without blanks, and without repeats that differ only in case.

    `F1,F2` and `F1 F2` name the same two findings.
    """
    seen = {}
    for value in values:
        for name in re.split(r"[,;\s]+", value):
            if name:
                seen.setdefault(name.casefold(), name)
    return sorted(seen.values())


def open_ids(entry):
    """{id in lower case: id as written} for the findings a round left open."""
    found = entry.get("open") or []
    return {i.strip().casefold(): i.strip() for i in found if isinstance(i, str)}


def stop_reason(rounds):
    """Why the test loop should go back to the user, or an empty string."""
    tail = []
    for entry in reversed(rounds):
        if entry.get("result") != "fail":
            break
        tail.append(entry)
    if len(tail) >= MAX_FAILED_ROUNDS:
        return f"{len(tail)} failed rounds in a row"
    attempts = []  # newest first; a fix attempt is a new commit
    for entry in tail:
        if attempts and attempts[-1].get("commit") == entry.get("commit"):
            continue
        attempts.append(entry)
    if len(attempts) >= MAX_ROUNDS_OPEN:
        names = open_ids(attempts[0])
        stuck = set(names)
        for entry in attempts[1:MAX_ROUNDS_OPEN]:
            stuck &= set(open_ids(entry))
        if stuck:
            left = ", ".join(sorted(names[key] for key in stuck))
            return f"{left} still open after two fix attempts"
    return ""


def cmd_record(args, repo):
    if repo.branch in {repo.default_branch(), "main", "master"}:
        raise ToolError(
            f"{repo.branch} is not the branch of a pull request: record the test "
            "on the branch that was tested"
        )
    if args.result == "pass" and repo.dirty():
        print(
            "ship: tracked files have uncommitted changes; commit first, "
            "a passed round is tied to a commit",
            file=sys.stderr,
        )
        return EXIT_FAIL
    path = repo.record_file
    data = load_record(path)
    rounds = data["rounds"]
    rounds.append(
        {
            "round": len(rounds) + 1,
            "commit": repo.head,
            "result": args.result,
            "tester": args.tester,
            "open": args.open,
            "notes": args.notes,
            "release": args.release,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    data.update(schema=SCHEMA, branch=repo.branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    ensure_ignored(repo)
    left = f", open: {', '.join(args.open)}" if args.open else ""
    print(
        f"Round {len(rounds)}: {args.result} on {short(repo.head)} "
        f"({args.tester}){left}"
    )
    print(f"Record: {path.relative_to(repo.root).as_posix()}")
    reason = stop_reason(rounds)
    if reason:
        print(f"STOP: {reason}. Tell the user what is stuck instead of trying again.")
        return EXIT_STOP
    return 0


# ---------------------------------------------------------------- gates


def gate(name, state, detail, stop=False, hints=()):
    return {
        "gate": name,
        "state": state,
        "detail": detail,
        "stop": bool(stop and state == "fail"),
        "hints": list(hints),
    }


def skipped(name):
    return gate(name, "skip", "needs an open pull request")


def sort_checks(rollup):
    """Split checks into passed, failed and still running.

    A check run counts as finished as soon as it has a conclusion: GitHub can
    leave `status` on IN_PROGRESS after the job is done.
    """
    passed, failed, pending = [], [], []
    for item in rollup or []:
        if item.get("__typename") == "StatusContext":
            word = (item.get("state") or "").upper()
            done = word in PASSING | FAILING
        else:
            word = (item.get("conclusion") or "").upper()
            done = bool(word)
        if not done:
            pending.append(item)
        elif word in PASSING:
            passed.append(item)
        else:
            failed.append(item)
    return passed, failed, pending


def check_names(items):
    return ", ".join(
        sorted({i.get("name") or i.get("context") or "check" for i in items})
    )


def log_hints(failed):
    ids = []
    for item in failed:
        m = re.search(r"/actions/runs/(\d+)", item.get("detailsUrl") or "")
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return [f"read the log: gh run view {i} --log-failed" for i in ids]


def pr_gate(repo, pr):
    if pr is None:
        return gate(
            "pr",
            "fail",
            f"no pull request for {repo.branch}: push, then gh pr create --draft",
        )
    state = pr.get("state") or "UNKNOWN"
    if state != "OPEN":
        return gate("pr", "fail", f"#{pr.get('number')} is {state.lower()}")
    draft = ", draft" if pr.get("isDraft") else ""
    return gate(
        "pr", "pass", f"#{pr.get('number')} into {pr.get('baseRefName')}{draft}"
    )


def own_gate(repo, pr):
    user = repo.user()
    author = (pr.get("author") or {}).get("login") or ""
    if author.lower() != user.lower():
        who = author or "someone else"
        return gate("own", "fail", f"opened by {who}, not by {user}", stop=True)
    if pr.get("isCrossRepository"):
        return gate(
            "own", "fail", "comes from a fork: the maintainers merge it", stop=True
        )
    return gate("own", "pass", f"opened by {user}")


def opts_out(text):
    """True when one line of `text` is the opt-out line itself."""
    for line in text.lstrip("\ufeff").splitlines():
        cells = [
            re.sub(r"[*_]", "", LINE_LEAD.sub("", cell.strip(), count=1)).strip()
            for cell in line.split("|")
        ]
        # `| Merges | ask first |`: two cells of a table row read as one line.
        pairs = [f"{a}: {b}" for a, b in zip(cells, cells[1:], strict=False) if a and b]
        if any(OPT_OUT.match(cell) for cell in cells + pairs):
            return True
    return False


def policy_texts(repo, base=""):
    """(label, text) of every CLAUDE.md that speaks for the project or the user.

    The project's files count in the checkout and on the base branch, so a
    branch cannot drop a line for its own pull request.
    """
    home = Path(os.environ.get("CLAUDE_HOME") or Path.home() / ".claude")
    for label, path in (
        ("CLAUDE.md", repo.root / "CLAUDE.md"),
        (".claude/CLAUDE.md", repo.root / ".claude" / "CLAUDE.md"),
        ("CLAUDE.local.md", repo.root / "CLAUDE.local.md"),
        ("your user-level CLAUDE.md", home / "CLAUDE.md"),
    ):
        try:
            yield label, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    for name in ("CLAUDE.md", ".claude/CLAUDE.md") if base else ():
        rc, text, _ = repo.try_git("show", f"refs/remotes/{repo.remote}/{base}:{name}")
        if not rc:
            yield f"{name} on {base}", text


def policy_gate(repo, pr=None):
    """The environment, the user or the project can ask for a question first."""
    asked = os.environ.get("PIPELINEKIT_MERGE", "").strip()
    if asked and asked.lower() != "auto":
        return gate("policy", "fail", f"PIPELINEKIT_MERGE={asked[:20]}", stop=True)
    for label, text in policy_texts(repo, (pr or {}).get("baseRefName") or ""):
        if opts_out(text):
            why = f"{label} says `Merges: ask first`"
            return gate("policy", "fail", why, stop=True)
    return gate("policy", "pass", "no `Merges: ask first` line")


def words_of(text):
    """(versions, words) in a title or a branch name, in lower case."""
    versions, words = [], []
    for m in TOKEN.finditer(text.lower()):
        if m.group("version"):
            versions.append(m.group("version"))
        elif m.group("word"):
            words.append(m.group("word"))
    return versions, words


def own_words(info):
    """The words of the repository's own name."""
    name = (info.get("nameWithOwner") or "").rpartition("/")[2]
    return frozenset(w for w in words_of(name)[1] if w not in VOCABULARY)


def named_release(kind, scope, text, own=()):
    """True when the words after a type name a release or a version.

    A text made of release words alone names one: `chore: prepare 0.3.0`,
    `chore: version bump`, `chore: patch`. With one or two other words in it,
    it has to read like a release: start like one (`chore: release kit 1.2.0`,
    `chore: bump version in package.json`), be a name and a number
    (`chore: kit 1.2.0`) or be short and end in one (`chore: weekly release`).
    A title about a tool (`ci: bump python version to 3.12`) or about how
    releases are made (`chore: release script`) is ordinary. After `feat` and
    `fix` any other word makes it an ordinary change, and `docs`, `test`,
    `style`, `refactor` and `perf` never name a release. `own` holds the words
    of the repository's own name, which count as release words.
    """
    if kind in QUIET_TYPES:
        return False
    versions, words = words_of(SHORTCODE.sub(" ", text))
    words = [w for w in words if w not in own]
    unknown = [w for w in words if w not in VOCABULARY]
    spoken = [w for w in words if w not in FILLER]
    implied = "release" in (kind, scope)
    strong = implied or any(w in STRONG for w in words)
    names = RELEASE_NAMES | VERSION_WORDS
    first = spoken[0] if spoken else ""
    if TOOLCHAIN.intersection(words) and not implied and first not in RELEASE_NAMES:
        return False
    if not unknown:
        if kind in PLAIN_TYPES:
            return bool(versions) and (strong or not words)
        if versions or strong:
            return True
        # `chore: patch`, `chore: bump minor`; not `chore: minor update`.
        rest = spoken[1:] if first in ACTIONS and len(spoken) > 1 else spoken
        return bool(rest) and all(w in LEVELS for w in rest)
    if kind in PLAIN_TYPES or len(unknown) > 2:
        return False
    if versions:
        leads = first in RELEASE_NAMES or (
            first in ACTIONS and any(w in names for w in spoken[1:3])
        )
        named = kind != "ci" and all(w in unknown for w in spoken)
        ends = len(unknown) == 1 and len(spoken) <= 3 and spoken[-1] in RELEASE_NAMES
        return implied or leads or named or ends
    if len(unknown) > 1 or MACHINERY.intersection(words):
        return False
    if first in ACTIONS and len(spoken) > 1 and spoken[1] in names:
        return True
    return (len(spoken) <= 2 and first in RELEASE_NAMES) or (
        len(spoken) <= 3 and spoken[-1] in names
    )


def release_head(head, own=()):
    """True when a branch name says release, version or stage."""
    name = head.lower()
    kind, slash, text = name.partition("/")
    if RELEASE_HEAD.match(name) or name in STAGE_HEADS:
        return True
    if slash and kind in STAGE_PREFIXES:
        return True
    if not slash:
        kind, text = "", name
        parts = re.split(r"[-_.]+", name)
        if len(parts) <= 2 and parts[0] in STAGE_FIRST:
            return True
    text = re.sub(r"[-_/]+", " ", re.sub(r"^\d+[-_]", "", text))
    if kind in TOPIC_PREFIXES:
        # `feat/21-v2` is the second take of a feature, not version 2.
        text = re.sub(r"(?<![\w.])v\d+(?![\w.])", " ", text)
    return named_release(kind, "", text, own)


def release_title(title, default="", own=()):
    """True when a pull request title names a release, not a change about one."""
    title = " ".join(CI_TAG.sub(" ", title or "").split())
    kind, scope, rest = "", "", title
    m = TITLE_PREFIX.match(title)
    if m:
        kind, scope = m.group("type").lower(), (m.group("scope") or "").lower()
        rest = title[m.end() :]
    m = MERGE_TITLE.match(title) or MERGE_TITLE.match(rest)
    if m:
        into = {default.lower(), *MAINLINES}
        return m.group(2).lower() in into and release_head(m.group(1), own)
    return bool(RELEASE_MARK.search(rest)) or named_release(kind, scope, rest, own)


def deploy_base(base):
    """True when the name of a base branch says it is deployed or published."""
    low = base.lower()
    if low.split("/")[0] in ("env", "environment", "environments"):
        return True
    return bool(DEPLOY_WORDS & set(re.split(r"[^a-z]+", low)))


def work_base(base):
    """True for a base that ordinary work goes into besides the default branch."""
    low = base.lower()
    if low in WORK_BASES or RELEASE_LINE.match(low):
        return True
    first, slash, _ = low.partition("/")
    return bool(slash) and first in WORK_PREFIXES | TOPIC_PREFIXES


def release_branches(head, base, default="", own=()):
    """Why these two branches make a release, a deploy or a promotion; else ''."""
    low, main_name = base.lower(), default.lower()
    main = low == main_name if default else low in (*MAINLINES, "trunk")
    if default and main_name not in MAINLINES and low in MAINLINES:
        return (
            f"{base} is not the default branch ({default}): what goes into it "
            "is a release"
        )
    if not main and deploy_base(base):
        return f"{base} is a deploy branch"
    if default and head == default and not main:
        return f"{head} into {base} promotes the default branch"
    if release_head(head, own):
        if main:
            return f"{head} into {base} is a release"
        return f"{head} into {base} merges a release or stage branch"
    if not main and not work_base(base):
        return f"{base} is not the default branch or a known working branch"
    return ""


def shown(path):
    """A path as a message shows it: one line, plain characters, not too long."""
    return re.sub(r"[^\x21-\x7e]+", "?", path)[:120]


def stem_of(name):
    """`.bumpversion.cfg` -> `bumpversion`, `__version__.py` -> `version`."""
    return re.sub(r"[-_ ]", "", name.lstrip(".").partition(".")[0])


def ext_of(name):
    """`.json` for `package.json`; '' for `VERSION` and for `.nvmrc`."""
    bare = name.lstrip(".")
    dot = bare.rfind(".")
    return "" if dot < 0 else bare[dot:]


def place(path):
    """How a changed file is read for a version.

    '' = not at all, `whole` = any change counts, `notes` = release notes,
    `data` = a manifest or another file that is not source code, `code`.
    """
    low = path.lower()
    *dirs, name = low.split("/")
    if low.startswith(SKIP_ROOTS) or SKIP_DIRS.intersection(dirs):
        return ""
    if name in LOCK_FILES | TOOL_FILES or name.startswith(TOOL_STARTS):
        return ""
    if name.endswith(SKIP_ENDS + BINARY_ENDS):
        return ""
    stem, ext = stem_of(name), ext_of(name)
    if ext in CODE_ENDS:
        manifest = (
            name in MANIFEST_CODE
            or name.startswith(("assemblyinfo.", "build.gradle"))
            or stem in ("version", "about")
        )
        return "data" if manifest else "code"
    if stem in VERSION_STEMS:
        return "whole"
    if NOTES_DIRS.intersection(dirs) and NUMBER.search(name):
        return "whole"
    if stem in NOTES_STEMS:
        return "notes"
    if stem in DOC_STEMS or (ext in DOC_ENDS and name != "cmakelists.txt"):
        return ""
    return "data"


def tool_key(key):
    """True when a key names the version of a tool or of a file format."""
    low = key.lower().lstrip("_-.@$")
    words = {word.lower() for word in KEY_WORD.findall(key)}
    if words & TOOL_WORDS:
        return True
    return low.startswith(TOOL_KEY_STARTS) and not low.startswith("minor")


def version_key(key, value):
    """True when `key = value` sets a version of the project itself."""
    if "version" not in key.lower() or tool_key(key) or not VALUE.match(value):
        return False
    last = re.sub(r"[_@$-]", "", key.lower().rpartition(".")[2])
    # A bare `version: 2` is the version of a file format.
    return last != "version" or bool(DOTTED.match(value.lstrip(" \t\"'[({vV")))


def walk(node, trail, out):
    """Count the leaves of parsed JSON, TOML or a property list by their keys."""
    if isinstance(node, dict):
        for key, value in node.items():
            walk(value, (*trail, str(key)), out)
    elif isinstance(node, list):
        for value in node:
            walk(value, trail, out)
    elif isinstance(node, (str, int, float)) and not isinstance(node, bool):
        out[(trail, str(node))] += 1


def xml_leaves(text):
    """The leaves of an XML manifest, without what it pins for other things."""
    if "<!ENTITY" in text.upper():
        raise ValueError("entities are not expanded")
    out = Counter()

    def visit(node, trail):
        tag = node.tag.rpartition("}")[2] if isinstance(node.tag, str) else ""
        pins = {"Include", "Update"} & set(node.attrib)
        if not tag or pins or XML_DEPENDS.search(tag):
            return
        here = (*trail, tag)
        for name, value in node.attrib.items():
            out[((*here, "@" + name.rpartition("}")[2]), value)] += 1
        if len(node):
            for child in node:
                visit(child, here)
        elif (node.text or "").strip():
            out[(here, node.text.strip())] += 1

    visit(ElementTree.fromstring(text), ())
    return out


def yaml_leaves(text):
    """The `key: value` leaves of a YAML file, read by indentation."""
    out, stack = Counter(), []
    for raw in text.splitlines():
        line = raw.split(" #")[0].rstrip()
        body = line.lstrip(" ")
        if not body or body.startswith(("#", "---", "...")):
            continue
        while body.startswith("- "):
            body = body[2:].lstrip(" ")
        indent = len(line) - len(body)
        m = YAML_PAIR.match(body)
        if not m:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key, value = m.group(2), (m.group(3) or "").strip()
        if value[:1] in ("{", "[") and "version" in value.lower():
            raise ValueError("a flow mapping is read by line")
        if not value or value[0] in "|>&*!":
            stack.append((indent, key))
        else:
            out[((*(k for _, k in stack), key), value.strip("\"'"))] += 1
    return out


def table_leaves(text):
    """The leaves of a TOML file read by line, for a Python without tomllib."""
    out, trail = Counter(), ()
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"\[+\s*([^\]]+?)\s*\]+", line)
        if m:
            trail = tuple(part.strip("\"' ") for part in m.group(1).split("."))
            continue
        key, equals, value = line.partition("=")
        if equals and not line.startswith("#"):
            out[((*trail, key.strip("\"' ")), value.strip().strip("\"'"))] += 1
    return out


def leaves(name, text):
    """The leaves of a manifest; None for a format that is read by line."""
    if not text.strip():
        return Counter()
    out = Counter()
    try:
        if name.endswith(".json"):
            walk(json.loads(text), (), out)
        elif name.endswith(".toml"):
            if tomllib is None:
                return table_leaves(text)
            walk(tomllib.loads(text), (), out)
        elif name.endswith(".plist"):
            walk(plistlib.loads(text.encode("utf-8")), (), out)
        elif name.endswith(XML_ENDS):
            return xml_leaves(text)
        elif name.endswith((".cfg", ".ini")):
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read_string(text)
            for section in parser.sections():
                for key, value in parser.items(section, raw=True):
                    out[((section, key), value)] += 1
        elif name.endswith((".yaml", ".yml")):
            return yaml_leaves(text)
        else:
            return None
    except Exception:  # noqa: BLE001 - whatever the parser raises: read by line
        return None
    return out


def sets_version(trail, value):
    """True when the leaf at `trail` is a version of the project itself."""
    if not trail or any(DEPENDS.search(key) for key in trail[:-1]):
        return False
    return version_key(trail[-1].lstrip("@"), value)


def line_rule(old, new):
    """True when a line added to a file without a known format sets a version."""
    before = Counter(old.splitlines())
    after = Counter(new.splitlines())
    added = [line for line in after - before if len(line) <= MAX_LINE]
    removed = {
        MASK.sub("#", line)
        for line in before - after
        if len(line) <= MAX_LINE and MASK.search(line)
    }
    for line in added:
        if DEP_LINE.search(line):
            continue
        for m in DECLARES.finditer(line):
            key = m.group("key")
            if tool_key(key):
                continue
            last = re.sub(r"[_@$-]", "", key.lower().rpartition(".")[2])
            if last != "version" or DOTTED.match(line[m.end() - 1 :]):
                return True
        # The same line as before with another number: `#define VER "1.2.4"`.
        if (
            MASK.search(line)
            and MASK.sub("#", line) in removed
            and not TOOL_WORDS.intersection(re.findall(r"[a-z]+", line.lower()))
        ):
            return True
    return False


def notes_rule(old, new, own=()):
    """True when the release notes gain the heading of a version.

    A line with a number the file did not hold yet counts when it is a
    heading, a link definition, or nothing but the number, a date, the name of
    the project and words like `version`. A sentence that names the version of
    something else does not.
    """
    seen = {m.group(1) for m in NUMBER.finditer(old)}
    lines = new.splitlines()
    added = Counter(lines) - Counter(old.splitlines())
    for at, line in enumerate(lines):
        if added[line] <= 0:
            continue
        added[line] -= 1
        if len(line) > MAX_LINE:
            continue
        fresh = [m for m in NUMBER.finditer(line) if m.group(1) not in seen]
        if not fresh:
            continue
        body = line.strip()
        below = lines[at + 1] if at + 1 < len(lines) else ""
        if body.startswith(("#", "=")) or UNDERLINE.match(below):
            return True
        if LINK_DEF.match(line):
            return True
        versions, words = words_of(STRIP_NOTE.sub(" ", body))
        if versions and all(w in own or w in NOTE_WORDS | MONTHS for w in words):
            return True
    return False


def changed_files(repo, base):
    """(files, error): old mode, new mode, old blob, new blob and path of each."""
    span = f"refs/remotes/{repo.remote}/{base}...HEAD"
    rc, out, err = repo.try_git(
        "diff", "--raw", "--no-abbrev", "--no-renames", "-z", span
    )
    if rc:
        return [], said(err or out, rc)
    parts = [part for part in out.split("\0") if part]
    files = []
    for meta, path in zip(parts[::2], parts[1::2], strict=False):
        fields = meta.lstrip(":").split()
        if len(fields) >= 5:
            files.append((*fields[:4], path))
    return files, ""


def blob(repo, sha):
    """(text, error) of a blob; '' for the side of a diff that has no file."""
    if not sha.strip("0"):
        return "", ""
    rc, out, err = repo.try_git("cat-file", "blob", sha)
    return ("", said(err or out, rc)) if rc else (out, "")


def code_version(repo, base):
    """(path, error): a source file in which the diff sets a version; else ''."""
    rc, out, err = repo.try_git(
        "-c",
        "core.quotePath=false",
        "diff",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        "--no-renames",
        "-G[Vv][Ee][Rr][Ss][Ii][Oo][Nn]",
        f"refs/remotes/{repo.remote}/{base}...HEAD",
    )
    if rc:
        return "", said(err or out, rc)
    path, header = "", False
    for line in out.splitlines():
        if line.startswith("diff --git "):
            path, header = "", True
        elif header and line.startswith("+++ "):
            path = line[6:].rstrip("\t") if line.startswith("+++ b/") else ""
        elif line.startswith("@@"):
            header = False
        elif (
            not header
            and path
            and line.startswith("+")
            and place(path) == "code"
            and CODE_VERSION.match(line[1:])
        ):
            return path, ""
    return "", ""


def sets(name, old, new):
    """True when the change from `old` to `new` sets a version of the project."""
    after = leaves(name, new)
    before = leaves(name, old) if after is not None else None
    if after is None or before is None:
        return line_rule(old, new)
    return any(sets_version(trail, value) for trail, value in after - before)


def listed(patterns, value, names=False):
    """True when `value` matches one of the patterns of a project line.

    `dir/` is everything below a directory, anything else a glob on the whole
    value and, with `names`, on the file name alone.
    """
    low = value.lower()
    for pattern in patterns:
        if pattern.endswith("/"):
            hit = low.startswith(pattern)
        else:
            name = low.rpartition("/")[2]
            hit = fnmatch.fnmatchcase(low, pattern) or (
                names and fnmatch.fnmatchcase(name, pattern)
            )
        if hit:
            return True
    return False


def project_lines(texts):
    """(files, branches) that a `Release files:` or `Release branches:` line names."""
    found = {"file": [], "branch": []}
    for text in texts:
        for raw in text.lstrip("\ufeff").splitlines():
            line = LINE_LEAD.sub("", raw.strip(), count=1).replace("`", "")
            m = PROJECT_LINE.match(line)
            if not m:
                continue
            values = re.split(r"[,\s]+", m.group(2).lower())
            found[m.group(1).lower()] += [
                v for v in values if v and "<" not in v and v != "-->"
            ]
    return found["file"], found["branch"]


def version_change(repo, base, own=(), release_files=()):
    """(why, error): why the changes against `base` make a release; else ''.

    Fails closed: a version is ordinary in the places the lists above name,
    and held anywhere else.
    """
    files, error = changed_files(repo, base)
    if error:
        return "", error
    watched, code = [], False
    for old_mode, new_mode, old, new, path in files:
        if {"160000", "120000"} & {old_mode, new_mode}:
            continue
        if listed(release_files, path, names=True):
            return f"the diff changes {shown(path)}, a release file of this project", ""
        kind = place(path)
        if kind == "whole":
            return f"the diff changes {shown(path)}{NEW_VERSION}", ""
        if kind == "code":
            code = True
        elif kind and new.strip("0"):
            watched.append((kind, old, new, path))
    if len(watched) > MAX_VERSION_FILES:
        why = f"the diff changes {len(watched)} files that can hold a version"
        return why + NEW_VERSION, ""
    for kind, old, new, path in watched:
        before, error = blob(repo, old)
        after, failed = blob(repo, new)
        if error or failed:
            return "", error or failed
        if "\0" in after or len(after) > MAX_BLOB:
            continue
        if "\0" in before or len(before) > MAX_BLOB:
            before = ""
        if kind == "notes":
            if notes_rule(before, after, own):
                why = f"the diff adds a version heading to {shown(path)}"
                return why + NEW_VERSION, ""
        elif sets(path.lower(), before, after):
            return f"the diff sets a version in {shown(path)}{NEW_VERSION}", ""
    if code:
        path, error = code_version(repo, base)
        if error:
            return "", error
        if path:
            return f"the diff sets a version in {shown(path)}{NEW_VERSION}", ""
    return "", ""


def promoted(repo, head):
    """(why, error): pull requests were merged into the head, so it is a stage."""
    kind, slash, _ = head.lower().partition("/")
    if slash and kind in TOPIC_PREFIXES:
        return "", ""
    rc, out, err = repo.gh(
        "pr", "list", "--base", head, "--state", "merged", "--limit", "1",
        "--json", "number",
    )  # fmt: skip
    merged = []
    if not rc:
        try:
            merged = json.loads(out)
        except ValueError:
            merged = None
        if not isinstance(merged, list):
            rc, err = 1, "unreadable answer"
    if rc:
        return "", f"cannot ask GitHub what was merged into {head}: {said(err, rc)}"
    if merged:
        why = f"pull requests were merged into {head}: merging it on is a promotion"
        return why, ""
    return "", ""


def recorded_release(repo, head):
    """What the passed round on `head` says: 'yes', 'no', '' or None for no round."""
    try:
        rounds = load_record(repo.record_file)["rounds"]
    except RecordError:
        return None
    last = rounds[-1] if rounds else {}
    if last.get("result") != "pass" or last.get("commit") != head:
        return None
    answer = last.get("release")
    return answer if answer in ("yes", "no") else ""


def release_gate(repo, pr):
    """A release, a deploy or a promotion of the default branch stays the user's."""
    head, base = pr.get("headRefName") or "", pr.get("baseRefName") or ""
    info = repo.info()
    default = (info.get("defaultBranchRef") or {}).get("name") or ""
    own = own_words(info)

    def stop(why):
        return gate("release", "fail", why, stop=True)

    if release_title(pr.get("title"), default, own):
        return stop("the title reads like a release")
    why = release_branches(head, base, default, own)
    if why:
        return stop(why)
    files, branches = project_lines(text for _, text in policy_texts(repo, base))
    for name in (head, base):
        if listed(branches, name):
            return stop(f"{name} is a release branch of this project")
    why, error = promoted(repo, head)
    if error:
        return gate("release", "fail", error)
    if why:
        return stop(why)
    why, error = version_change(repo, base, own, files)
    if error:
        return gate(
            "release", "fail", f"cannot read what changes against {base}: {error}"
        )
    if why:
        return stop(why)
    answer = recorded_release(repo, pr.get("headRefOid") or "")
    if answer == "yes":
        return stop("the test record says this is a release")
    if answer == "":
        return gate(
            "release",
            "fail",
            "the test record does not say whether this is a release: record the "
            "round again with --release yes or no",
        )
    return gate("release", "pass", "not a release")


def review_gate(pr):
    decision = pr.get("reviewDecision") or ""
    if decision == "CHANGES_REQUESTED":
        return gate("review", "fail", "a reviewer requested changes", stop=True)
    if decision == "REVIEW_REQUIRED":
        return gate("review", "fail", "the base branch requires a review", stop=True)
    asked = [
        r.get("login") or r.get("name") or r.get("slug") or "a reviewer"
        for r in pr.get("reviewRequests") or []
    ]
    if asked:
        return gate(
            "review", "fail", f"review requested from {', '.join(asked)}", stop=True
        )
    _, failed, pending = sort_checks(pr.get("statusCheckRollup"))
    if pr.get("mergeStateStatus") == "BLOCKED" and not failed and not pending:
        return gate("review", "fail", "branch protection blocks the merge", stop=True)
    return gate("review", "pass", "approved" if decision else "no review required")


def current_gate(repo, pr):
    head = pr.get("headRefOid") or ""
    if head != repo.head:
        return gate(
            "current",
            "fail",
            f"local HEAD {short(repo.head)} is not the pull request's head "
            f"{short(head)}: push or pull first",
        )
    if repo.dirty():
        return gate("current", "fail", "tracked files have uncommitted changes")
    return gate("current", "pass", f"head {short(head)}, tracked files clean")


def base_gate(repo, pr):
    base = pr.get("baseRefName") or ""
    ref = f"refs/remotes/{repo.remote}/{base}"
    rc, _, err = repo.try_git("fetch", "-q", repo.remote, f"+refs/heads/{base}:{ref}")
    if rc:
        why = (err.splitlines() or [f"exit {rc}"])[-1]
        return gate("up-to-date", "fail", f"could not fetch {base}: {why}")
    again = f"merge {repo.remote}/{base} into the branch, then test again"
    state = pr.get("mergeStateStatus") or ""
    if pr.get("mergeable") == "CONFLICTING" or state == "DIRTY":
        return gate("up-to-date", "fail", f"conflicts with {base}: {again}")
    if repo.try_git("merge-base", "--is-ancestor", ref, "HEAD")[0]:
        n = repo.try_git("rev-list", "--count", f"HEAD..{ref}")[1]
        behind = count(int(n), "commit") if n.isdigit() else "some commits"
        return gate("up-to-date", "fail", f"{behind} behind {base}: {again}")
    if state == "BEHIND":
        return gate("up-to-date", "fail", f"behind {base}, GitHub says: {again}")
    return gate("up-to-date", "pass", f"contains the tip of {base}")


def tested_gate(repo, head):
    try:
        rounds = load_record(repo.record_file)["rounds"]
    except RecordError as exc:
        return gate("tested", "fail", str(exc))
    where = repo.record_file.relative_to(repo.root).as_posix()
    if not rounds:
        return gate(
            "tested",
            "fail",
            f"no test record ({where}): run the acceptance test, then ship.py record",
        )
    last, n = rounds[-1], len(rounds)
    if last.get("result") != "pass":
        stuck = stop_reason(rounds)
        if stuck:
            why = f"round {n} failed, {stuck}: tell the user what is stuck"
            return gate("tested", "fail", why, stop=True)
        left = ", ".join(open_ids(last).values()) or "not named"
        return gate("tested", "fail", f"round {n} failed, still open: {left}")
    if last.get("commit") != head:
        return gate(
            "tested",
            "fail",
            f"round {n} passed on {short(last.get('commit'))}, the head is now "
            f"{short(head)}: test again",
        )
    tester = last.get("tester") or "agent"
    return gate("tested", "pass", f"round {n} passed on {short(head)} ({tester})")


def ci_gate(pr, expected=False):
    """CI as it stands now.

    `expected`: a workflow here runs on pull requests, so a pull request
    without a single check has not been picked up yet; that is not a pass.
    """
    passed, failed, pending = sort_checks(pr.get("statusCheckRollup"))
    if failed:
        return gate(
            "ci", "fail", f"failed: {check_names(failed)}", hints=log_hints(failed)
        )
    if pending:
        total = len(passed) + len(pending)
        return gate(
            "ci",
            "pending",
            f"{len(pending)} of {total} still running: {check_names(pending)}",
        )
    if not passed and expected:
        return gate(
            "ci",
            "pending",
            "no check has shown up yet, and workflows here run on pull requests",
        )
    if not passed:
        return gate("ci", "pass", "no CI checks on this pull request")
    return gate("ci", "pass", f"{count(len(passed), 'check')} finished, none failed")


def evaluate(repo, pr, no_checks_ok=False):
    """Every gate for the current branch's pull request; CI as it stands now."""
    first = pr_gate(repo, pr)
    if first["state"] != "pass":
        return [
            first,
            skipped("own"),
            policy_gate(repo),
            skipped("release"),
            skipped("review"),
            skipped("current"),
            skipped("up-to-date"),
            tested_gate(repo, repo.head),
            skipped("ci"),
        ]
    # First, because it fetches the base branch, which the policy gate reads.
    up_to_date = base_gate(repo, pr)
    return [
        first,
        own_gate(repo, pr),
        policy_gate(repo, pr),
        release_gate(repo, pr),
        review_gate(pr),
        current_gate(repo, pr),
        up_to_date,
        tested_gate(repo, pr.get("headRefOid") or ""),
        ci_gate(pr, repo.expects_checks() and not no_checks_ok),
    ]


def verdict(gates):
    """Exit code for a list of gates: 0 all hold, 3 the user's call, 1 otherwise."""
    bad = [g for g in gates if g["state"] != "pass"]
    if not bad:
        return 0
    return EXIT_STOP if any(g["stop"] for g in bad) else EXIT_FAIL


# ---------------------------------------------------------------- output


def render(repo, pr, gates):
    if pr:
        state = (pr.get("state") or "OPEN").lower()
        note = f" ({state})" if state != "open" else ""
        if not note and pr.get("isDraft"):
            note = " (draft)"
        title = (
            f"Pull request #{pr.get('number')}: {pr.get('headRefName')} -> "
            f"{pr.get('baseRefName')}{note}"
        )
    else:
        title = f"Branch {repo.branch}: no pull request"
    lines = [title]
    for g in gates:
        lines.append(f"  {WORD[g['state']]:<5} {g['gate']:<11} {g['detail']}")
        lines.extend(f"{'':19}{hint}" for hint in g["hints"])
    bad = [g for g in gates if g["state"] in ("fail", "pending")]
    if verdict(gates) == 0:
        lines.append("Result: ready to merge")
    elif any(g["stop"] for g in bad):
        mine = ", ".join(g["gate"] for g in bad if g["stop"])
        lines.append(f"Result: stop and ask the user ({mine})")
    else:
        lines.append(f"Result: not ready ({', '.join(g['gate'] for g in bad)})")
    return "\n".join(lines)


def report(repo, pr, gates):
    return {
        "schema": SCHEMA,
        "branch": repo.branch,
        "head": repo.head,
        "pr": pr
        and {
            "number": pr.get("number"),
            "url": pr.get("url"),
            "base": pr.get("baseRefName"),
            "draft": bool(pr.get("isDraft")),
        },
        "ready": verdict(gates) == 0,
        "stop": verdict(gates) == EXIT_STOP,
        "gates": [
            {k: g[k] for k in ("gate", "state", "detail", "hints")} for g in gates
        ],
    }


def cmd_status(args, repo):
    pr = repo.pr()
    gates = evaluate(repo, pr, args.allow_no_checks)
    if args.json:
        print(json.dumps(report(repo, pr, gates), indent=2))
    else:
        print(render(repo, pr, gates))
    return 0 if args.exit_zero else verdict(gates)


# ---------------------------------------------------------------- CI wait


def grace_seconds(args, repo):
    if args.grace is not None:
        return args.grace
    return FIRST_CHECK if repo.has_workflows() else 0


def ran_checks(pr):
    """The checks that ran on the pull request; a skipped one did not."""
    return [
        item
        for item in pr.get("statusCheckRollup") or []
        if (item.get("conclusion") or item.get("state") or "").upper() != "SKIPPED"
    ]


def settle_seconds(args, repo, pr):
    """How long a draft has to stay mergeable after it is marked ready.

    A workflow can skip a draft and start when it is marked ready. Where one
    says so, or where no check has really run on the head yet, the first check
    gets as long to show up as it gets in `wait`.
    """
    if args.settle is not None:
        return args.settle
    expected = repo.expects_checks() and not args.allow_no_checks
    if repo.starts_on_ready() or (expected and not ran_checks(pr)):
        return max(SETTLE, grace_seconds(args, repo))
    return SETTLE


def nap(step, waited, *limits):
    """Sleep `step` seconds, or less when one of the limits comes first."""
    left = [limit - waited for limit in limits if limit > waited]
    time.sleep(max(0.01, min([step, *left])))


def wait_for_ci(repo, timeout, grace, no_checks_ok=False):
    """Poll until every check on the local HEAD has finished.

    Returns (ci gate, pull request). `grace` is how long to wait for the first
    check to show up, and for GitHub to see a push, before judging. No check
    at all is a failure when a workflow here runs on pull requests, unless
    the caller says that none of them runs for this change.
    """
    expected = repo.expects_checks() and not no_checks_ok
    start = time.monotonic()
    shown = ""
    while True:
        pr = repo.pr()
        if pr is None or pr.get("state") != "OPEN":
            return gate("ci", "fail", f"no open pull request for {repo.branch}"), pr
        waited = time.monotonic() - start
        seen = pr.get("headRefOid") == repo.head
        passed, failed, pending = sort_checks(
            pr.get("statusCheckRollup") if seen else []
        )
        if failed or (seen and passed and not pending):
            return ci_gate(pr), pr
        if seen and not pending and waited >= grace:
            if expected:
                detail = (
                    f"no check has shown up after {int(waited)} s, and workflows "
                    "here run on pull requests: look at the Actions tab; when "
                    "none of them runs for this change, add --allow-no-checks"
                )
                return gate("ci", "fail", detail), pr
            return ci_gate(pr), pr
        if not seen and waited >= grace:
            detail = (
                f"the pull request's head is {short(pr.get('headRefOid'))}, "
                f"local HEAD is {short(repo.head)}: push first"
            )
            return gate("ci", "fail", detail), pr
        if waited >= timeout:
            names = check_names(pending) or "no check has shown up"
            detail = f"still running after {int(waited)} s: {names}"
            return gate("ci", "pending", detail), pr
        if pending:
            line = f"waiting for CI: {len(passed)} finished, {len(pending)} running"
        elif seen:
            line = "waiting for the first check to show up"
        else:
            line = "waiting for GitHub to show the pushed commit"
        if line != shown:
            print(line, file=sys.stderr, flush=True)
            shown = line
        nap(poll_seconds(), waited, timeout, *(() if pending else (grace,)))


def cmd_wait(args, repo):
    grace = grace_seconds(args, repo)
    ci, _ = wait_for_ci(repo, args.timeout, grace, args.allow_no_checks)
    print(f"CI {WORD[ci['state']]}: {ci['detail']}")
    for hint in ci["hints"]:
        print(f"  {hint}")
    return 0 if ci["state"] == "pass" else EXIT_FAIL


# ---------------------------------------------------------------- merge


def merge_plan(repo, pr, args):
    """Merge method and commit subject, following what the base branch does.

    Returns (method, subject, problem); `problem` says why there is no plan.
    """
    info = repo.info()
    allowed = [m for m, key in METHODS.items() if info.get(key)] or ["merge"]
    if args.method and args.method not in allowed:
        problem = (
            f"this repository does not allow {args.method} merges "
            f"(allowed: {', '.join(allowed)})"
        )
        return "", "", problem
    ref = f"refs/remotes/{repo.remote}/{pr.get('baseRefName')}"
    fmt = "--format=%h%x09%P%x09%s"  # the hash keeps the line from starting with a tab
    out = repo.try_git("log", "--first-parent", "-n", "30", fmt, ref)[1]
    rows = [line.split("\t", 2) for line in out.splitlines() if line.count("\t") >= 2]
    subjects = [subject for _, _, subject in rows]
    merges = [subject for _, parents, subject in rows if len(parents.split()) > 1]
    method = args.method
    if not method and "merge" in allowed and (merges or "squash" not in allowed):
        method = "merge"
    if not method:
        method = "squash" if "squash" in allowed else allowed[0]
    subject = args.subject
    sample = merges or subjects
    if not subject and method == "merge" and sample:
        conventional = sum(bool(CONVENTIONAL.match(s)) for s in sample)
        if conventional * 2 > len(sample):
            subject = f"chore: merge {pr.get('headRefName')}"
    return method, subject, ""


def watch(repo, number, timeout, settle=0, marked=False, expected=False):
    """Read the pull request again until GitHub's view of it has held still.

    Marking a draft ready can start checks, request a review from the code
    owners and bring branch protection in, and none of that shows at once. So
    after `marked` the pull request has to look mergeable for `settle` seconds
    and on two reads at least. With `expected`, a workflow here runs on pull
    requests, so by then a check must have run: one that was skipped on the
    draft does not count. Returns None when it can be merged, else the gate
    that does not hold.
    """
    looks = 2 if marked else 1
    start = time.monotonic()
    calm_from = None
    calm = unknown = 0
    shown = ""
    while True:
        pr = repo.pr()
        state = (pr or {}).get("state") or "CLOSED"
        if state == "MERGED":
            return gate("pr", "fail", f"#{number} is already merged, not by this run")
        if state != "OPEN":
            return gate("pr", "fail", f"#{number} was closed")
        head, base = pr.get("headRefOid") or "", pr.get("baseRefName")
        if head != repo.head:
            detail = (
                f"the head of #{number} is now {short(head)}, the tested commit "
                f"is {short(repo.head)}: pull and test again"
            )
            return gate("current", "fail", detail)
        review = review_gate(pr)
        if review["state"] != "pass":
            return review
        _, failed, pending = sort_checks(pr.get("statusCheckRollup"))
        if failed:
            detail = f"checks failed: {check_names(failed)}"
            return gate("ci", "fail", detail, hints=log_hints(failed))
        merge_state = pr.get("mergeStateStatus") or "UNKNOWN"
        if merge_state in ("BEHIND", "DIRTY") or pr.get("mergeable") == "CONFLICTING":
            word = "behind" if merge_state == "BEHIND" else "in conflict with"
            detail = (
                f"#{number} is {word} {base}: merge {repo.remote}/{base} into "
                "the branch and test again"
            )
            return gate("up-to-date", "fail", detail)
        draft = bool(pr.get("isDraft")) or merge_state == "DRAFT"
        if draft and not marked:
            return gate("draft", "fail", f"#{number} was turned into a draft")
        waited = time.monotonic() - start
        step, limit, line = min(poll_seconds(), 3), timeout, shown
        if pending:
            # A check showed up: from here on the usual time to settle is enough.
            calm, calm_from, settle = 0, None, min(settle, SETTLE)
            if waited >= timeout:
                names = check_names(pending)
                detail = f"checks still running after {int(waited)} s: {names}"
                return gate("ci", "pending", detail)
            step = poll_seconds()
            line = f"waiting for CI: {len(pending)} running"
        elif draft or merge_state == "UNKNOWN":
            calm, calm_from = 0, None
            unknown += 1  # counted over the whole watch, so this always ends
            if unknown >= UNKNOWN_LOOKS and draft:
                detail = (
                    f"GitHub still shows #{number} as a draft after it was "
                    "marked ready: run ship.py merge again"
                )
                return gate("draft", "pending", detail)
            if unknown >= UNKNOWN_LOOKS:
                detail = (
                    f"GitHub has not said whether #{number} can be merged: "
                    "run ship.py merge again"
                )
                return gate("mergeable", "pending", detail)
        else:
            calm += 1
            if calm_from is None:
                calm_from = waited
            limit = calm_from + settle
            if calm >= looks and waited >= limit:
                if marked and expected and not ran_checks(pr):
                    detail = (
                        f"no check ran on #{number} in the {int(waited)} s after "
                        "it was marked ready, and workflows here run on pull "
                        "requests: look at the Actions tab; when none of them "
                        "runs for this change, add --allow-no-checks"
                    )
                    return gate("ci", "fail", detail)
                return None
            if settle >= 1:
                line = f"watching #{number} for {settle:g} s before the merge"
        if line != shown:
            print(line, file=sys.stderr, flush=True)
            shown = line
        nap(step, waited, limit)


def update_base(repo, base):
    """Switch to the merged base; one sentence on where that left the checkout."""
    for step in (
        ("fetch", "-q", repo.remote),
        ("checkout", "-q", base),
        ("merge", "-q", "--ff-only", f"{repo.remote}/{base}"),
    ):
        rc, out, err = repo.try_git(*step)
        if rc:
            why = git_said(err or out, rc).rstrip(".")
            failed = f"git {' '.join(step)} failed: {why}"
            now = repo.try_git("branch", "--show-current")[1] or "no branch"
            if now == base:
                return (
                    f"Now on {base}, which could not be brought up to "
                    f"{repo.remote}/{base}: {failed}."
                )
            return f"Still on {now}: {failed}."
    return f"Now on {base} at {short(repo.try_git('rev-parse', 'HEAD')[1])}."


def refusal(gates):
    """The last line when a gate does not hold and nothing was changed."""
    bad = [g for g in gates if g["state"] in ("fail", "pending")] or gates
    first = next((g for g in bad if g["stop"]), bad[0])
    rest = ", ".join(g["gate"] for g in bad if g is not first)
    also = f" Also not holding: {rest}." if rest else ""
    line = f"{first['gate']}: {first['detail'].rstrip('.')}.{also}"
    return f"STOP: {line} Ask the user." if first["stop"] else f"Not merged: {line}"


def finish(args, repo, pr):
    """Every gate holds: mark ready, watch, merge. The outcome is the last line."""
    number, base = str(pr.get("number")), pr.get("baseRefName")
    draft = bool(pr.get("isDraft"))
    method, subject, problem = merge_plan(repo, pr, args)
    if problem:
        print(f"Not merged: {problem}.")
        return EXIT_TOOL
    cmd = ["pr", "merge", number, f"--{method}", "--match-head-commit", repo.head]
    if subject:
        cmd.append(f"--subject={subject}")
    settle = settle_seconds(args, repo, pr) if draft else args.settle or 0
    if args.dry_run:
        first = ""
        if draft:
            first = f"mark #{number} ready, watch it for {settle:g} s, then "
        print(f"Dry run. Would {first}run: gh {shlex.join(cmd)}")
        return 0
    undrafted = ""
    if draft:
        rc, out, err = repo.gh("pr", "ready", number)
        if rc:
            why = said(err or out, rc).rstrip(".")
            print(f"Not merged: gh pr ready failed: {why}.")
            return EXIT_TOOL
        undrafted = f" #{number} is no longer a draft."
    expected = repo.expects_checks() and not args.allow_no_checks
    problem = watch(repo, number, args.timeout, settle, draft, expected)
    if problem:
        for hint in problem["hints"]:
            print(f"  {hint}")
        if problem["gate"] in ("pr", "draft"):
            undrafted = ""
        if problem["stop"]:
            print(f"STOP: {problem['detail']}.{undrafted} Ask the user.")
            return EXIT_STOP
        print(f"Not merged: {problem['detail']}.{undrafted}")
        return EXIT_FAIL
    rc, out, err = repo.gh(*cmd, timeout=120)
    if rc:
        why = said(err or out, rc).rstrip(".")
        print(f"Not merged: gh pr merge failed: {why}.{undrafted}")
        return EXIT_FAIL
    done = f"Merged #{number} into {base} ({method}) at {short(repo.head)}."
    if not args.stay:
        done = f"{done} {update_base(repo, base)}"
    print(done)
    return 0


def cmd_merge(args, repo):
    pr = repo.pr()
    gates = evaluate(repo, pr, args.allow_no_checks)
    before_ci = gates[:-1]
    if verdict(before_ci) == 0 and not args.dry_run:
        grace = grace_seconds(args, repo)
        ci, seen = wait_for_ci(repo, args.timeout, grace, args.allow_no_checks)
        pr = seen or pr
        gates = [*before_ci, ci]
    print(render(repo, pr, gates))
    code = verdict(gates)
    if code:
        print(refusal(gates))
        return code
    return finish(args, repo, pr)


# ---------------------------------------------------------------- entry


def seconds(text):
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of seconds")
    if value < 0:
        raise argparse.ArgumentTypeError("seconds cannot be negative")
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ship.py",
        description="Test record, CI wait and gated merge for a pull request "
        "you opened.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    status = sub.add_parser("status", help="show every merge gate")
    status.add_argument("--json", action="store_true", help="machine-readable")
    status.add_argument("--exit-zero", action="store_true", help="always exit 0")
    record = sub.add_parser("record", help="store one round of the acceptance test")
    record.add_argument("--result", required=True, choices=("pass", "fail"))
    record.add_argument(
        "--tester",
        default="agent",
        choices=("agent", "session"),
        help="who tested: a separate agent, or the building session",
    )
    record.add_argument(
        "--open",
        nargs="*",
        default=[],
        metavar="ID",
        help="ids of the blocker and should-fix findings still open",
    )
    record.add_argument("--notes", default="", help="one line about the round")
    record.add_argument(
        "--release",
        default="",
        choices=("yes", "no"),
        help="with a pass: does this pull request raise the version, add the "
        "notes of one, publish, deploy or move a release branch on?",
    )
    wait = sub.add_parser("wait", help="return when CI on the head commit is done")
    merge = sub.add_parser("merge", help="check the gates, wait for CI, merge")
    for cmd in (wait, merge):
        cmd.add_argument(
            "--timeout", type=seconds, default=1800, metavar="S", help="default 1800"
        )
        cmd.add_argument(
            "--grace",
            type=seconds,
            default=None,
            metavar="S",
            help="how long to wait for the first check to show up "
            f"(default {FIRST_CHECK} with workflows in the repository, else 0)",
        )
    for cmd in (status, wait, merge):
        cmd.add_argument(
            "--allow-no-checks",
            action="store_true",
            help="accept a pull request on which no check shows up, when no "
            "workflow runs for this change",
        )
    merge.add_argument("--method", choices=tuple(METHODS), help="default: as the base")
    merge.add_argument("--subject", default="", help="commit subject of the merge")
    merge.add_argument("--dry-run", action="store_true", help="gates only, no merge")
    merge.add_argument(
        "--stay", action="store_true", help="do not switch to the base afterwards"
    )
    merge.add_argument(
        "--settle",
        type=seconds,
        default=None,
        metavar="S",
        help="how long a draft has to stay mergeable after it is marked ready "
        f"(default {SETTLE}; as --grace where a check is still to come)",
    )
    return parser


COMMANDS = {
    "status": cmd_status,
    "record": cmd_record,
    "wait": cmd_wait,
    "merge": cmd_merge,
}


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "record":
        args.open = finding_ids(args.open)
        if args.result == "pass" and args.open:
            parser.error("a passed round has no open findings; record it as fail")
        if args.result == "fail" and not args.open:
            parser.error("name the findings that are still open: --open F1 F2")
        if args.result == "pass" and not args.release:
            parser.error(
                "say whether this pull request is a release: --release yes or no"
            )
    quiet = getattr(args, "exit_zero", False)
    try:
        return COMMANDS[args.cmd](args, Repo())
    except ToolError as exc:
        if args.cmd == "merge":
            print(f"Not merged: {str(exc).rstrip('.')}.")
            return EXIT_TOOL
        print(f"ship: {exc}", file=sys.stdout if quiet else sys.stderr)
        return 0 if quiet else EXIT_TOOL


if __name__ == "__main__":
    sys.exit(main())
