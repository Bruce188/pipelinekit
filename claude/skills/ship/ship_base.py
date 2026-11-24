"""Constants, the command runner, the repository and the test record of ship.py."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ship_ci import runs_for, starts_when_ready

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


def gate(name, state, detail, stop=False, hints=()):
    return {
        "gate": name,
        "state": state,
        "detail": detail,
        "stop": bool(stop and state == "fail"),
        "hints": list(hints),
    }


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


def progress(line):
    """A line about what the helper is waiting for, on stderr.

    What was printed to stdout before goes out first, so through a pipe the
    gate table does not come after the lines that follow it.
    """
    sys.stdout.flush()
    print(line, file=sys.stderr, flush=True)


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

    def expects_checks(self):
        """A workflow here runs on the branch's pull request or on its pushes.

        Either way a check shows up on the pull request's head. Its `on:`
        block decides; a word in a comment or a step does not count.
        """
        return any(runs_for(text, self.branch) for text in self.workflows())

    def starts_on_ready(self):
        return any(starts_when_ready(text) for text in self.workflows())


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
    """Test records and reports are local working notes: keep them out of git.

    Returns why the exclude line could not be added, or an empty string.
    """
    if repo.try_git("check-ignore", "-q", "docs/uat/")[0] == 0:
        return ""
    rc, out, err = repo.try_git("rev-parse", "--git-path", "info/exclude")
    if rc:
        why = git_said(err or out, rc).rstrip(".")
        return f"could not find the exclude file of this repository: {why}"
    exclude = repo.root / out
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        old = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        gap = "" if not old or old.endswith("\n") else "\n"
        exclude.write_text(f"{old}{gap}docs/uat/\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        why = getattr(exc, "strerror", None) or str(exc)
        return f"could not add docs/uat/ to {out}: {why}"
    return ""


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


def cmd_record(args, repo, behind=None):
    """Store one round. `behind`: returns why a pass cannot be recorded (the
    branch is not up to date with its base, or that could not be checked), or
    ''; a pass is not recorded while it says something."""
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
    reason = behind() if behind and args.result == "pass" else ""
    if reason:
        print(f"ship: not recorded: {reason}", file=sys.stderr)
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
