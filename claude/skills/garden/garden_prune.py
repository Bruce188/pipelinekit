"""Pruning: tests that assert nothing, skipped tests, and the dead-code tools.

Python test files are parsed with `ast`, never imported. Skip markers are
found with a pattern per stack. Dead-code tools are looked up on PATH and in
the project's dependency files; none of them is run. Nothing is deleted.
"""

from __future__ import annotations

import ast
import re
import shutil

from garden_checks import matching, names_in_package, package_json
from garden_common import MAX_READ, SAFE_IDENT, shown

MAX_TEST_FILES = 3000
MAX_LISTED = 20
PY_TESTS = ("**/test_*.py", "**/*_test.py")
# Calls that check something: assertEqual, assert_called_once, expect(...),
# pytest.raises, pytest.fail, and helpers named like them.
CHECK_CALL = re.compile(
    r"(?:assert|expect|verify|check|should|raises|warns|fail\b|deprecated_call)", re.I
)

SKIP_MARKERS = {
    "python": (
        ("**/test_*.py", "**/*_test.py", "**/conftest.py"),
        re.compile(
            r"@(?:pytest\.mark\.skip(?:if)?|unittest\.skip(?:If|Unless)?|skip(?:If|Unless)?)\b"
            r"|\bpytest\.skip\s*\(|\.skipTest\s*\("
        ),
    ),
    "node": (
        tuple(
            f"**/*{part}.{ext}"
            for part in (".test", ".spec")
            for ext in ("js", "jsx", "ts", "tsx", "mjs", "cjs", "mts", "cts")
        )
        + ("**/__tests__/*.js", "**/__tests__/*.ts", "**/__tests__/*.tsx"),
        re.compile(
            r"\b(?:it|test|describe|context|suite)\.(?:skip|todo)\s*\("
            r"|\b(?:xit|xtest|xdescribe|xcontext)\s*\("
        ),
    ),
    "dotnet": (
        ("**/*.cs", "**/*.fs", "**/*.vb"),
        re.compile(
            r"\[\s*(?:Fact|Theory|Test|TestMethod)\s*\([^\]\n]*\bSkip\s*="
            r"|\[\s*(?:Ignore|Skip)\b|\bAssert\.Ignore\s*\("
        ),
    ),
    "go": (("**/*_test.go",), re.compile(r"\b[tb]\.Skip(?:f|Now)?\s*\(")),
    "rust": (("**/*.rs",), re.compile(r"#\[\s*ignore\b")),
}

DEAD_CODE_TOOLS = {
    "python": ("vulture", "deadcode"),
    "node": ("knip", "ts-prune", "ts-unused-exports", "unimported"),
    "dotnet": ("jb",),
    "go": ("deadcode", "staticcheck", "golangci-lint"),
    "rust": ("cargo-udeps", "cargo-machete"),
}
DEAD_CODE_CHANGE = {
    "python": "Add vulture as a dev dependency with a whitelist, run it in CI",
    "node": "Add knip as a dev dependency and run it in CI",
    "dotnet": "Raise IDE0051 and IDE0052 (unused members) to warnings in .editorconfig",
    "go": "Run staticcheck (it reports unused code) or deadcode in CI",
}


def call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def asserts_something(fn, helpers=frozenset()):
    """An assert or raise, a call named like a check, or a call to a checking helper."""
    for node in ast.walk(fn):
        if isinstance(node, (ast.Assert, ast.Raise)):
            return True
        if isinstance(node, ast.Call):
            name = call_name(node)
            if name and (CHECK_CALL.match(name) or name in helpers):
                return True
    return False


def checking_helpers(tree):
    """Module-level functions that check something, directly or through each other."""
    funcs = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not n.name.startswith("test")
    ]
    helpers = set()
    while True:
        more = {
            f.name
            for f in funcs
            if f.name not in helpers and asserts_something(f, helpers)
        }
        if not more:
            return frozenset(helpers)
        helpers |= more


def test_functions(tree):
    """Test functions at module level and in Test classes."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                yield node
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(
                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and item.name.startswith("test"):
                    yield item


def python_test_files(project):
    files = project.files()
    seen = []
    for pattern in PY_TESTS:
        seen.extend(f for f in matching(files, pattern) if f not in seen)
    return sorted(seen)[:MAX_TEST_FILES]


def no_assert_tests(project):
    """([(file, line, name)], files not parsed) for Python tests that check nothing."""
    found, unparsed = [], 0
    for name in python_test_files(project):
        text = project.read(name, MAX_READ)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            unparsed += 1
            continue
        helpers = checking_helpers(tree)
        for fn in test_functions(tree):
            if not asserts_something(fn, helpers):
                found.append((name, fn.lineno, fn.name))
    return found, unparsed


def skipped_tests(project, stack_names):
    """[(file, line, stack)] for each skip marker in the test files of the stacks."""
    files = project.files()
    out = []
    for stack in stack_names:
        patterns, rx = SKIP_MARKERS[stack]
        names = []
        for pattern in patterns:
            names.extend(f for f in matching(files, pattern) if f not in names)
        for name in sorted(names)[:MAX_TEST_FILES]:
            text = project.read(name, MAX_READ)
            if text is None:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    out.append((name, number, stack))
    return out


def dead_code_tools(project, stack_names):
    """{stack: [(tool, where)]}: the dead-code tools found, without running any."""
    pkg_names = (
        names_in_package(package_json(project)) if "node" in stack_names else set()
    )
    py_deps = ""
    if "python" in stack_names:
        for name in (
            "pyproject.toml",
            "requirements-dev.txt",
            "requirements.txt",
            "setup.cfg",
            ".pre-commit-config.yaml",
        ):
            py_deps += (project.read(name) or "") + "\n"
    out = {}
    for stack in stack_names:
        found = []
        if stack == "rust":
            found.append(("rustc dead_code warnings", "built in"))
        for tool in DEAD_CODE_TOOLS[stack]:
            if stack == "node" and tool in pkg_names:
                found.append((tool, "package.json"))
            elif stack == "node" and project.has(f"node_modules/.bin/{tool}"):
                found.append((tool, "node_modules"))
            elif stack == "python" and re.search(
                rf"(?<![\w-]){re.escape(tool)}(?![\w-])", py_deps
            ):
                found.append((tool, "project dependencies"))
            elif shutil.which(tool):
                found.append((tool, "PATH"))
        knip = project.has("knip.json") or project.has(".knip.json")
        if stack == "node" and knip and not any(t == "knip" for t, _ in found):
            found.append(("knip", "knip.json"))
        if stack == "dotnet":
            text = project.read(".editorconfig") or ""
            if re.search(r"IDE005[12]", text):
                found.append(("IDE0051/IDE0052 analyzers", ".editorconfig"))
        out[stack] = found
    return out


def listed(items):
    """The items the report may show, and how many it leaves out."""
    shown_items = [(f, n, *rest) for f, n, *rest in items if shown(f)]
    return shown_items[:MAX_LISTED], len(items) - len(shown_items[:MAX_LISTED])


def scan_pruning(project, stack_names):
    tests, unparsed = no_assert_tests(project) if "python" in stack_names else ([], 0)
    skipped = skipped_tests(project, stack_names)
    tools = dead_code_tools(project, stack_names)
    no_assert_rows, no_assert_more = listed(tests)
    skipped_rows, skipped_more = listed(skipped)
    by_stack = {}
    for _f, _n, stack in skipped:
        by_stack[stack] = by_stack.get(stack, 0) + 1
    return {
        "no_assert": [
            {"file": f, "line": n, "name": name if SAFE_IDENT.fullmatch(name) else None}
            for f, n, name in no_assert_rows
        ],
        "no_assert_total": len(tests),
        "no_assert_more": no_assert_more,
        "unparsed": unparsed,
        "python": "python" in stack_names,
        "skipped": [{"file": f, "line": n, "stack": s} for f, n, s in skipped_rows],
        "skipped_total": len(skipped),
        "skipped_more": skipped_more,
        "skipped_by_stack": by_stack,
        "dead_code_tools": {
            s: [{"tool": t, "where": w} for t, w in found] for s, found in tools.items()
        },
    }


def where(items, total):
    """The first listed place and how many more there are in all."""
    first = items[0]
    rest = total - 1
    return f"{first['file']}:{first['line']}" + (f" and {rest} more" if rest else "")


def prune_findings(pruning):
    out = []
    total = pruning["no_assert_total"]
    if total:
        place = (
            where(pruning["no_assert"], total)
            if pruning["no_assert"]
            else "names not shown"
        )
        out.append(
            {
                "key": "pruning.no-assert",
                "area": "Pruning",
                "title": "Tests that assert nothing",
                "evidence": f"{total} Python test function{'s' if total != 1 else ''} "
                f"without an assertion: {place}",
                "change": "Give each the assertion it was meant to make, or delete it "
                "once a search shows nothing relies on it",
                "size": "S" if total <= 5 else "M",
                "weight": 60,
            }
        )
    total = pruning["skipped_total"]
    if total:
        place = (
            where(pruning["skipped"], total)
            if pruning["skipped"]
            else "names not shown"
        )
        out.append(
            {
                "key": "pruning.skipped",
                "area": "Pruning",
                "title": "Skipped tests",
                "evidence": f"{total} skip marker{'s' if total != 1 else ''}: {place}",
                "change": "Fix and re-enable each skipped test, "
                "or delete it with the reason in the pull request",
                "size": "S" if total <= 3 else "M",
                "weight": 45,
            }
        )
    for stack, found in sorted(pruning["dead_code_tools"].items()):
        if found or stack not in DEAD_CODE_CHANGE:
            continue
        from garden_checks import STACK_NAMES

        out.append(
            {
                "key": f"pruning.dead-code-tool.{stack}",
                "area": "Pruning",
                "title": f"No dead-code tool for {STACK_NAMES[stack]}",
                "evidence": f"0 of {len(DEAD_CODE_TOOLS[stack])} known tools found "
                f"({', '.join(DEAD_CODE_TOOLS[stack])})",
                "change": DEAD_CODE_CHANGE[stack],
                "size": "S",
                "weight": 20,
            }
        )
    return out
