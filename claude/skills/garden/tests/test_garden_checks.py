"""garden.py scan: the Checks section for each stack (criterion 3)."""

import json

import pytest
from garden_testkit import Sandbox, section


@pytest.fixture
def sb(tmp_path):
    return Sandbox(tmp_path)


def rows(sb):
    return {(r["kind"], r["stack"]): r for r in sb.scan_json()["checks"]["rows"]}


FULL = {
    "node": (
        {
            "package.json": json.dumps({"name": "x", "scripts": {"build": "tsc"}}),
            "eslint.config.js": "export default [];\n",
            ".prettierrc.json": "{}\n",
            "tsconfig.json": "{}\n",
            "vitest.config.ts": "export default {};\n",
        },
        {
            "lint": ("yes", "eslint.config.js"),
            "format": ("yes", ".prettierrc.json"),
            "types": ("yes", "tsconfig.json"),
            "tests": ("yes", "vitest.config.ts"),
        },
    ),
    "python": (
        {
            "pyproject.toml": "[project]\nname = 'x'\n\n"
            "[tool.ruff]\nline-length = 100\n"
            "\n[tool.ruff.format]\n\n[tool.mypy]\nstrict = true\n\n"
            "[tool.pytest.ini_options]\n",
        },
        {
            "lint": ("yes", "pyproject.toml"),
            "format": ("yes", "pyproject.toml"),
            "types": ("yes", "pyproject.toml"),
            "tests": ("yes", "pyproject.toml"),
        },
    ),
    "dotnet": (
        {
            "App/App.csproj": "<Project><PropertyGroup>"
            "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>"
            "</PropertyGroup></Project>\n",
            ".editorconfig": "root = true\n",
            "App.Tests/App.Tests.csproj": "<Project><ItemGroup>"
            '<PackageReference Include="xunit" />'
            "</ItemGroup></Project>\n",
        },
        {
            "lint": ("yes", "App/App.csproj"),
            "format": ("yes", ".editorconfig"),
            "types": ("built in", None),
            "tests": ("yes", "App.Tests/App.Tests.csproj"),
        },
    ),
    "go": (
        {
            "go.mod": "module example.com/x\n\ngo 1.22\n",
            ".golangci.yml": "linters: {}\n",
            "pkg/x_test.go": "package pkg\n",
        },
        {
            "lint": ("yes", ".golangci.yml"),
            "format": ("built in", "go.mod"),
            "types": ("built in", "go.mod"),
            "tests": ("yes", "pkg/x_test.go"),
        },
    ),
    "rust": (
        {
            "Cargo.toml": "[package]\nname = 'x'\n\n[lints.clippy]\nall = 'warn'\n",
            "rustfmt.toml": "edition = '2021'\n",
            "tests/it.rs": "#[test]\nfn works() {}\n",
        },
        {
            "lint": ("yes", "Cargo.toml"),
            "format": ("yes", "rustfmt.toml"),
            "types": ("built in", "Cargo.toml"),
            "tests": ("yes", "tests/it.rs"),
        },
    ),
}

BARE = {
    "node": ({"package.json": '{"name": "x"}\n'}, ("lint", "format", "types", "tests")),
    "python": (
        {"requirements.txt": "requests\n"},
        ("lint", "format", "types", "tests"),
    ),
    "dotnet": ({"src/App/App.csproj": "<Project />\n"}, ("lint", "format", "tests")),
    "go": ({"go.mod": "module example.com/x\n"}, ("lint", "tests")),
    "rust": ({"Cargo.toml": "[package]\nname = 'x'\n"}, ("lint", "tests")),
}


@pytest.mark.parametrize("stack", sorted(FULL))
def test_each_kind_is_found_with_the_file_that_shows_it(sb, stack):
    files, expected = FULL[stack]
    for rel, text in files.items():
        sb.write(rel, text)
    found = rows(sb)
    for kind, (state, name) in expected.items():
        r = found[(kind, stack)]
        assert r["state"] == state, (kind, r)
        if name:
            assert r["file"] == name, (kind, r)
    keys = {f["key"] for f in sb.scan_json()["findings"]}
    assert not any(k.startswith("checks.") and k.endswith("." + stack) for k in keys)


@pytest.mark.parametrize("stack", sorted(BARE))
def test_a_bare_project_gets_a_finding_for_each_missing_kind(sb, stack):
    files, missing = BARE[stack]
    for rel, text in files.items():
        sb.write(rel, text)
    data = sb.scan_json()
    assert [s["stack"] for s in data["stacks"]] == [stack]
    found = {(r["kind"], r["stack"]): r for r in data["checks"]["rows"]}
    for kind in missing:
        assert found[(kind, stack)]["state"] == "no", kind
        assert found[(kind, stack)]["file"] is None
    keys = {f["key"] for f in data["findings"]}
    for kind in missing:
        assert f"checks.{kind}.{stack}" in keys
    text = sb.scan()
    assert "- lint (" in section(text, "## Checks")
    assert "none found" in section(text, "## Checks")


def test_ci_hooks_and_secret_scan_are_named_by_their_file(sb):
    sb.write("pyproject.toml", "[project]\nname = 'x'\n")
    sb.write(".github/workflows/ci.yml", "on: push\n")
    sb.write(
        ".pre-commit-config.yaml",
        "repos:\n  - repo: https://github.com/gitleaks/gitleaks\n",
    )
    found = rows(sb)
    assert (found[("ci", None)]["state"], found[("ci", None)]["file"]) == (
        "yes",
        ".github/workflows/ci.yml",
    )
    assert found[("hooks", None)]["file"] == ".pre-commit-config.yaml"
    assert found[("secrets", None)]["file"] == ".pre-commit-config.yaml"
    checks = section(sb.scan(), "## Checks")
    assert "- CI: yes, .github/workflows/ci.yml" in checks
    assert "- commit hooks: yes, .pre-commit-config.yaml" in checks
    assert "- secret scan: yes, .pre-commit-config.yaml" in checks


def test_a_hook_in_the_checkouts_own_hooks_folder_counts(sb):
    sb.write("go.mod", "module x\n")
    sb.write(".git/hooks/pre-commit", "#!/bin/sh\n")
    assert rows(sb)[("hooks", None)]["file"] == ".git/hooks/pre-commit"


def test_sample_hooks_from_git_init_do_not_count(sb):
    sb.write("go.mod", "module x\n")
    assert rows(sb)[("hooks", None)]["state"] == "no"


def test_an_unknown_project_gets_ci_and_hook_rows_and_a_line(sb):
    sb.write("README.md", "# docs only\n")
    sb.write(".github/workflows/pages.yml", "on: push\n")
    data = sb.scan_json()
    assert data["checks"]["recognised"] is False
    assert [r["kind"] for r in data["checks"]["rows"]] == ["ci", "hooks"]
    checks = section(sb.scan(), "## Checks")
    assert "- CI: yes, .github/workflows/pages.yml" in checks
    assert "- commit hooks: none found" in checks
    assert "the project's stack was not recognised" in checks


def test_two_stacks_get_rows_of_their_own(sb):
    sb.write("package.json", '{"name": "web", "devDependencies": {"eslint": "9"}}\n')
    sb.write("pyproject.toml", "[project]\nname = 'api'\n")
    found = rows(sb)
    assert found[("lint", "node")] == {
        "kind": "lint",
        "stack": "node",
        "state": "yes",
        "file": "package.json",
        "hidden": False,
    }
    assert found[("lint", "python")]["state"] == "no"


def test_node_tests_from_the_test_script(sb):
    sb.write("package.json", '{"scripts": {"test": "node --test"}}\n')
    assert rows(sb)[("tests", "node")]["file"] == "package.json"
    sb.write(
        "package.json", '{"scripts": {"test": "echo \\"Error: no test specified\\""}}\n'
    )
    assert rows(sb)[("tests", "node")]["state"] == "no"


def test_a_broken_package_json_still_scans(sb):
    sb.write("package.json", "{ not json")
    assert sb.garden("scan").returncode == 0
    assert rows(sb)[("lint", "node")]["state"] == "no"
