"""Checks: which fast checks a project has, and the file that shows each one.

Stacks are recognised by their marker files. For each recognised stack the
scan looks for lint, format, types and tests; CI, commit hooks and a secret
scan are looked for once per project. A project of no recognised stack gets
the CI and commit-hook rows only. Nothing is run: files are listed and read.
"""

from __future__ import annotations

import json
import re

from garden_common import shown

STACKS = ("node", "python", "dotnet", "go", "rust")
STACK_NAMES = {
    "node": "Node",
    "python": "Python",
    "dotnet": ".NET",
    "go": "Go",
    "rust": "Rust",
}
MARKERS = {
    "node": ("package.json",),
    "python": (
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "Pipfile",
    ),
    "dotnet": ("*.sln", "*.slnx", "*.csproj", "*.fsproj", "*.vbproj"),
    "go": ("go.mod",),
    "rust": ("Cargo.toml",),
}
STACK_KINDS = ("lint", "format", "types", "tests")
COMMON_KINDS = ("ci", "hooks", "secrets")
KIND_NAMES = {
    "lint": "lint",
    "format": "format",
    "types": "types",
    "tests": "tests",
    "ci": "CI",
    "hooks": "commit hooks",
    "secrets": "secret scan",
}
PRE_COMMIT = ".pre-commit-config.yaml"
JS_EXT = "{js,jsx,ts,tsx,mjs,cjs,mts,cts}"

# A probe is (how, where, what):
#   ("file", glob, None)          a file of the project matches the glob
#   ("text", glob, regex)         a file matching the glob holds the regex
#   ("dep", name, None)           package.json names it (key or dependency)
#   ("builtin", glob, None)       the language has it; the glob names the marker
PROBES = {
    ("node", "lint"): [
        ("file", "eslint.config.*", None),
        ("file", ".eslintrc*", None),
        ("file", "biome.json*", None),
        ("file", ".oxlintrc.json", None),
        ("dep", "eslintConfig", None),
        ("dep", "eslint", None),
        ("dep", "@biomejs/biome", None),
        ("dep", "oxlint", None),
        ("dep", "standard", None),
        ("dep", "xo", None),
    ],
    ("node", "format"): [
        ("file", ".prettierrc*", None),
        ("file", "prettier.config.*", None),
        ("file", "biome.json*", None),
        ("file", "dprint.json", None),
        ("file", ".dprint.json", None),
        ("dep", "prettier", None),
        ("dep", "dprint", None),
    ],
    ("node", "types"): [
        ("file", "tsconfig*.json", None),
        ("dep", "typescript", None),
    ],
    ("node", "tests"): [
        ("file", "jest.config.*", None),
        ("file", "vitest.config.*", None),
        ("file", "vitest.workspace.*", None),
        ("file", "playwright.config.*", None),
        ("file", "cypress.config.*", None),
        ("file", ".mocharc*", None),
        ("file", "karma.conf.*", None),
        ("dep", "jest", None),
        ("dep", "vitest", None),
        ("dep", "mocha", None),
        ("dep", "ava", None),
        ("dep", "@playwright/test", None),
        ("file", f"**/*.test.{JS_EXT}", None),
        ("file", f"**/*.spec.{JS_EXT}", None),
    ],
    ("python", "lint"): [
        ("file", "ruff.toml", None),
        ("file", ".ruff.toml", None),
        ("file", ".flake8", None),
        ("file", ".pylintrc", None),
        ("file", "pylintrc", None),
        ("text", "pyproject.toml", r"^\s*\[\s*tool\.(?:ruff|pylint|flake8)\b"),
        ("text", "setup.cfg", r"^\s*\[\s*flake8\s*\]"),
        ("text", "tox.ini", r"^\s*\[\s*flake8\s*\]"),
        ("text", PRE_COMMIT, r"\b(?:ruff|flake8|pylint)\b"),
    ],
    ("python", "format"): [
        ("text", "pyproject.toml", r"^\s*\[\s*tool\.(?:black|ruff\.format|yapf)\b"),
        ("text", "ruff.toml", r"^\s*\[\s*format\s*\]"),
        ("text", ".ruff.toml", r"^\s*\[\s*format\s*\]"),
        ("file", ".style.yapf", None),
        ("text", PRE_COMMIT, r"\b(?:black|ruff-format|yapf|autopep8)\b"),
    ],
    ("python", "types"): [
        ("file", "mypy.ini", None),
        ("file", ".mypy.ini", None),
        ("file", "pyrightconfig.json", None),
        ("text", "pyproject.toml", r"^\s*\[\s*tool\.(?:mypy|pyright)\b"),
        ("text", "setup.cfg", r"^\s*\[\s*mypy\b"),
        ("text", PRE_COMMIT, r"\b(?:mypy|pyright)\b"),
    ],
    ("python", "tests"): [
        ("file", "pytest.ini", None),
        ("text", "pyproject.toml", r"^\s*\[\s*tool\.pytest\b"),
        ("text", "setup.cfg", r"^\s*\[\s*tool:pytest\s*\]"),
        ("text", "tox.ini", r"^\s*\[\s*(?:pytest|tox|testenv)\b"),
        ("file", "conftest.py", None),
        ("file", "noxfile.py", None),
        ("file", "**/test_*.py", None),
        ("file", "**/*_test.py", None),
    ],
    ("dotnet", "lint"): [
        ("text", ".editorconfig", r"dotnet_(?:analyzer_)?diagnostic"),
        (
            "text",
            "Directory.Build.props",
            r"<(?:AnalysisLevel|AnalysisMode|EnableNETAnalyzers|TreatWarningsAsErrors)>"
            r"|StyleCop|Roslynator|SonarAnalyzer",
        ),
        (
            "text",
            "**/*.csproj",
            r"<(?:AnalysisLevel|AnalysisMode|EnableNETAnalyzers|TreatWarningsAsErrors)>"
            r"|StyleCop|Roslynator|SonarAnalyzer",
        ),
        ("file", "**/*.ruleset", None),
        ("file", "stylecop.json", None),
    ],
    ("dotnet", "format"): [
        ("file", ".editorconfig", None),
        ("file", ".csharpierrc*", None),
        ("text", ".config/dotnet-tools.json", r"csharpier"),
    ],
    ("dotnet", "types"): [
        ("builtin", "*.*proj", None),
        ("builtin", "**/*.*proj", None),
    ],
    ("dotnet", "tests"): [
        ("text", "**/*.csproj", r"Microsoft\.NET\.Test\.Sdk|xunit|NUnit|MSTest|TUnit"),
        (
            "text",
            "**/*.fsproj",
            r"Microsoft\.NET\.Test\.Sdk|xunit|NUnit|MSTest|Expecto",
        ),
    ],
    ("go", "lint"): [
        ("file", ".golangci.*", None),
        ("file", "staticcheck.conf", None),
        ("file", "revive.toml", None),
        ("text", ".github/workflows/*", r"golangci-lint|staticcheck|go vet"),
    ],
    ("go", "format"): [("builtin", "go.mod", None)],
    ("go", "types"): [("builtin", "go.mod", None)],
    ("go", "tests"): [("file", "**/*_test.go", None)],
    ("rust", "lint"): [
        ("file", "clippy.toml", None),
        ("file", ".clippy.toml", None),
        ("text", "Cargo.toml", r"^\s*\[\s*(?:workspace\.)?lints\b"),
        ("text", ".github/workflows/*", r"cargo\s+clippy"),
    ],
    ("rust", "format"): [
        ("file", "rustfmt.toml", None),
        ("file", ".rustfmt.toml", None),
        ("builtin", "Cargo.toml", None),
    ],
    ("rust", "types"): [("builtin", "Cargo.toml", None)],
    ("rust", "tests"): [
        ("file", "tests/*.rs", None),
        ("text", "**/*.rs", r"#\[\s*(?:cfg\(\s*)?test\b"),
    ],
    ("ci", None): [
        ("file", ".github/workflows/*.yml", None),
        ("file", ".github/workflows/*.yaml", None),
        ("file", ".gitlab-ci.yml", None),
        ("file", ".circleci/config.yml", None),
        ("file", "azure-pipelines.yml", None),
        ("file", "Jenkinsfile", None),
        ("file", ".travis.yml", None),
        ("file", "bitbucket-pipelines.yml", None),
        ("file", ".buildkite/*", None),
        ("file", ".woodpecker.yml", None),
        ("file", ".drone.yml", None),
    ],
    ("hooks", None): [
        ("file", PRE_COMMIT, None),
        ("file", ".husky/*", None),
        ("file", "lefthook.*", None),
        ("file", ".lefthook.*", None),
        ("file", ".githooks/*", None),
        ("dep", "simple-git-hooks", None),
        ("dep", "husky", None),
        ("dep", "lint-staged", None),
    ],
    ("secrets", None): [
        ("file", ".gitleaks.toml", None),
        ("file", "gitleaks.toml", None),
        ("file", ".gitleaksignore", None),
        ("file", ".secrets.baseline", None),
        ("file", ".talismanrc", None),
        ("file", ".secretlintrc*", None),
        ("file", ".trufflehogignore", None),
        ("text", PRE_COMMIT, r"gitleaks|detect-secrets|trufflehog|ggshield|talisman"),
        ("text", ".github/workflows/*", r"gitleaks|trufflehog|detect-secrets|ggshield"),
    ],
}

PROPOSALS = {
    ("lint", "node"): "Add ESLint (eslint.config.js) or Biome and run it in CI",
    ("lint", "python"): "Add ruff with a [tool.ruff] section and run it in CI",
    (
        "lint",
        "dotnet",
    ): "Turn on the .NET analyzers (AnalysisLevel in Directory.Build.props)",
    ("lint", "go"): "Add golangci-lint (.golangci.yml) and run it in CI",
    ("lint", "rust"): "Run cargo clippy in CI, with a [lints] table in Cargo.toml",
    ("format", "node"): "Add Prettier or Biome and check the format in CI",
    ("format", "python"): "Add ruff format (or black) and check the format in CI",
    (
        "format",
        "dotnet",
    ): "Add an .editorconfig and run dotnet format --verify-no-changes in CI",
    (
        "types",
        "node",
    ): "Add TypeScript, or a tsconfig.json with checkJs, and check types in CI",
    ("types", "python"): "Add mypy or pyright with a config and check types in CI",
    (
        "tests",
        "node",
    ): "Add a test runner (Vitest or Jest) with a first test, run in CI",
    ("tests", "python"): "Add pytest with a first test, run in CI",
    ("tests", "dotnet"): "Add a test project (xUnit) with a first test, run in CI",
    ("tests", "go"): "Add a first _test.go file and run go test in CI",
    ("tests", "rust"): "Add a first #[test] and run cargo test in CI",
    (
        "ci",
        None,
    ): "Add a CI workflow that runs lint, type check and tests on each pull request",
    (
        "hooks",
        None,
    ): "Add a pre-commit configuration that runs the fast checks before each commit",
    ("secrets", None): "Add gitleaks to the commit hooks and to CI",
}
SIZES = {
    "lint": "S",
    "format": "S",
    "types": "M",
    "tests": "M",
    "ci": "M",
    "hooks": "S",
    "secrets": "S",
}
WEIGHTS = {
    "tests": 100,
    "ci": 90,
    "lint": 80,
    "secrets": 65,
    "types": 55,
    "format": 50,
    "hooks": 40,
}
DEPENDENCY_KEYS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)


def glob_regex(pattern):
    """A glob with `**/` (any folders, or none), `*` (within one name) and `{a,b}`."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += r"(?:[^/]+/)*"
            i += 3
            continue
        ch = pattern[i]
        if ch == "*":
            out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        elif ch == "{":
            end = pattern.index("}", i)
            out += (
                "(?:"
                + "|".join(re.escape(p) for p in pattern[i + 1 : end].split(","))
                + ")"
            )
            i = end
        else:
            out += re.escape(ch)
        i += 1
    return re.compile(out + r"\Z")


_GLOBS = {}


def matching(files, pattern):
    if pattern not in _GLOBS:
        _GLOBS[pattern] = glob_regex(pattern)
    rx = _GLOBS[pattern]
    return [f for f in files if rx.match(f)]


def package_json(project):
    text = project.read("package.json")
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def names_in_package(pkg):
    names = set(k for k in pkg if isinstance(k, str))
    for key in DEPENDENCY_KEYS:
        deps = pkg.get(key)
        if isinstance(deps, dict):
            names.update(k for k in deps if isinstance(k, str))
    return names


def stacks(project):
    """[(stack, marker file)] for each stack whose marker the project holds."""
    files = project.files()
    found = []
    for stack in STACKS:
        for pattern in MARKERS[stack]:
            top = matching(files, pattern)
            deep = [] if top or stack != "dotnet" else matching(files, "**/" + pattern)
            hits = top or [f for f in deep if f.count("/") <= 3]
            if hits:
                found.append((stack, hits[0]))
                break
    return found


def probe(project, probes, pkg_names):
    """(state, file) for the first probe that holds: state is yes or built in."""
    files = project.files()
    for how, where, what in probes:
        if how == "dep":
            if where in pkg_names:
                return "yes", "package.json"
            continue
        hits = matching(files, where)
        if how in ("file", "builtin") and hits:
            return ("built in" if how == "builtin" else "yes"), hits[0]
        if how == "text":
            rx = re.compile(what, re.M | re.I)
            for name in hits[:400]:
                text = project.read(name)
                if text is not None and rx.search(text):
                    return "yes", name
    return "no", None


def local_hooks(project):
    """A hook in the checkout's own hooks folder, or a hooksPath set for this repo."""
    from garden_common import git

    if not project.in_git:
        return None
    rc, out = git(project.root, "config", "--local", "--get", "core.hooksPath")
    if rc == 0 and out.strip():
        return ".git/config"
    rc, out = git(project.root, "rev-parse", "--git-path", "hooks")
    if rc:
        return None
    folder = project.root / out.strip()
    try:
        names = sorted(p.name for p in folder.iterdir() if p.is_file())
    except OSError:
        return None
    for name in names:
        if name in ("pre-commit", "commit-msg", "pre-push"):
            return f".git/hooks/{name}"
    return None


def scan_checks(project):
    """The Checks section: stacks, one row per kind, and whether the stack was known."""
    found = stacks(project)
    if project.files_unavailable:
        return {
            "stacks": [],
            "recognised": False,
            "unavailable": True,
            "rows": [row(kind, None, "not checked", None) for kind in COMMON_KINDS],
        }
    pkg = package_json(project) if any(s == "node" for s, _ in found) else {}
    if not pkg and "package.json" in project.files():
        pkg = package_json(project)
    pkg_names = names_in_package(pkg)
    rows = []
    for stack, _marker in found:
        for kind in STACK_KINDS:
            probes = PROBES.get((stack, kind))
            if probes is None:
                continue
            state, name = probe(project, probes, pkg_names)
            if (stack, kind) == ("node", "tests") and state == "no":
                state, name = node_test_script(pkg)
            rows.append(row(kind, stack, state, name))
    kinds = COMMON_KINDS if found else ("ci", "hooks")
    for kind in kinds:
        state, name = probe(project, PROBES[(kind, None)], pkg_names)
        if kind == "hooks" and state == "no":
            local = local_hooks(project)
            if local:
                state, name = "yes", local
        rows.append(row(kind, None, state, name))
    return {
        "stacks": [{"stack": s, "marker": shown(m)} for s, m in found],
        "recognised": bool(found),
        "unavailable": False,
        "rows": rows,
    }


def node_test_script(pkg):
    scripts = pkg.get("scripts")
    test = scripts.get("test") if isinstance(scripts, dict) else None
    if isinstance(test, str) and test.strip() and "no test specified" not in test:
        return "yes", "package.json"
    return "no", None


def row(kind, stack, state, name):
    return {
        "kind": kind,
        "stack": stack,
        "state": state,
        "file": shown(name),
        "hidden": bool(name) and not shown(name),
    }


def check_findings(checks):
    out = []
    for r in checks["rows"]:
        if r["state"] != "no":
            continue
        kind, stack = r["kind"], r["stack"]
        where = f" for {STACK_NAMES[stack]}" if stack else ""
        key = f"checks.{kind}" + (f".{stack}" if stack else "")
        out.append(
            {
                "key": key,
                "area": "Checks",
                "title": f"No {KIND_NAMES[kind]} check{where}",
                "evidence": f"0 {KIND_NAMES[kind]} configurations found{where} "
                f"({len(PROBES.get((stack, kind)) or PROBES[(kind, None)])} "
                "places looked at)",
                "change": PROPOSALS.get((kind, stack))
                or PROPOSALS.get((kind, None), ""),
                "size": SIZES[kind],
                "weight": WEIGHTS[kind],
            }
        )
    return out
