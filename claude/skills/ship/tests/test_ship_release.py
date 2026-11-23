"""Tests of ship.py: how a release is told from other work, answers and limits."""

import json
import sys
import time
from types import SimpleNamespace

import pytest
from ship_fixtures import (
    BRANCH,
    check,
    gates,
    held,
    last_line,
    refused,
    ship,
)

# ---------------------------------------------------------------- release wording

RELEASE_TITLES = [
    "chore: version bump",
    "chore: bump version",
    "chore: bump package version",
    "chore: increment version",
    "Bump version: 1.2.3 to 1.2.4",
    "Bump version: 1.2.3 \u2192 1.2.4",
    "chore: bump version (1.2.4)",
    "chore: bump version to v2",
    "chore: set version to 0.2.0",
    "chore: update version to 0.2.0",
    "Version 1.2.3",
    "chore: version 1.2.3",
    "build: version 0.2.0",
    "Prepare for 2.0 release",
    "chore: release",
    "Release",
    "ci: release",
    "chore: new release",
    "chore: cut release",
    "chore: prepare release",
    "Prepare release",
    "chore: release prep",
    "chore: release candidate",
    "chore: prepare 0.3.0",
    "chore: prepare v0.2.0",
    "Prepare 1.2.0",
    "chore: prepare 0.2.0 release",
    "chore: 1.2.4 release",
    "[release] 1.2.0",
    "[Release] v1.2.0",
    "Release-1.2.0",
    "chore: pre-release 1.0.0-beta.1",
    "chore: prerelease 1.0.0-beta.1",
    "chore: finalize v1.0",
    "chore: publish to npm",
    "chore: publish v2",
    "chore: publish packages",
    "chore: publish 1.2.0",
    "chore: release notes and version bump for 0.2.0",
    "chore: update changelog for 0.2.0",
    "chore: ship 0.2.0",
    "chore: deploy to production",
    "Merge develop into main",
    "feat: add thing (release 0.2.0)",
    "Bump to 1.2.4",
    "chore(release): prepare",
    "chore: release pipelinekit 0.2.0",
    "Cut 1.2.0",
    "chore: version packages",
    "chore: tag 1.0.0",
    "chore: 0.2.0",
    "chore: bump patch version",
    "bump minor version",
    "chore: bump app version to 1.2.4",
    "chore: bump version to 1.2.4 [skip ci]",
    "chore: release 1.2.3 [ci skip]",
    "Bumped version to 1.2.4",
    "Bumping version",
    "increase version",
    "update version number",
    "Hotfix 1.0.1",
    "chore: create release 1.2.0",
    "Initial release",
    "first release",
    "final release",
    "major release",
    "patch release",
    "stable release",
    "preparing release",
    "do the release",
    "finish 1.2.0",
    "Beta 2",
    "chore: rc1",
    "Promote to production",
    "chore: merge develop into main",
    "[maven-release-plugin] prepare release v1.2.3",
    "[Gradle Release Plugin] - new version commit: 1.2.4",
    "chore : release 1.2.3",
    "feat: 1.2.0",
    "feat!: 2.0.0",
    "chore: pipelinekit 0.2.0",
    "chore: bump version in package.json",
    "chore: release main",
    "chore: weekly release",
    "chore: next version",
    "chore: bump versions",
    "chore: v2.0.0 :tada:",
    "chore: re-release 1.2.3",
    "chore: upgrade version to 1.2.4",
    "chore: LTS release 1.2.4",
    "GA release",
    "REL 1.2.4",
    "chore: patch",
    "Deploy",
    "chore: rel 1.2.4",
]
ORDINARY_TITLES = [
    "fix: release 1.2.0 broke the installer",
    "fix: publish 1.2.0 fails on Windows",
    "fix: tag 1.0.0 not found by the resolver",
    "docs: release 1.2.0 notes",
    "chore(release): fix changelog script",
    "ci(release): pin action versions",
    "feat: cut 0.2 s from startup",
    "feat: add release notes page",
    "fix: version check in the installer",
    "docs: explain the release process",
    "chore: bump pipelinekit to 0.2.0",
    "chore(deps): bump lodash from 4.17.20 to 4.17.21 [skip ci]",
    "chore: update next to 15.0.1",
    "chore: update node to 20.1",
    "chore(deps): update dependency typescript to v5",
    "fix: hotfix script exits early",
    "hotfix: login crash",
    "fix: beta 2 flag is ignored",
    "chore: merge main into develop",
    "ci: bump python version to 3.12",
    "chore: update .NET version to 9.0",
    "chore: release script",
    "chore: minor update",
]
RELEASE_HEADS = [
    "chore/212-release-v0.2.0",
    "chore/212-release-0.2.0",
    "chore/212-release",
    "chore/213-version-bump",
    "build/214-release-0.2.0",
    "chore/release",
    "chore/prepare-release",
    "chore/bump-version-1.2.3",
    "chore/v0.2.0",
    "build/99-version-0.2.0",
    "version/2.0",
    "bump/1.2.3",
    "1.x",
    "1.2.x",
    "v2",
    "v1.2",
    "beta",
    "uat",
    "qa",
    "preprod",
    "release-candidate",
    "staging/eu",
    "staging",
    "test",
    "testing",
    "canary",
    "preview",
    "trunk",
    "master",
    "release/212-v0.2.0",
    "chore/release-0.2",
    "development",
    "develop",
    "dev",
    "next",
    "chore/12-bump-patch-version",
    "chore/12-patch-version",
    "chore/12-major-version-bump",
    "chore/12-hotfix-1.0.1",
    "chore/12-rc1",
    "staging-eu",
    "snapshot",
]
ORDINARY_HEADS = [
    "fix/release-1.2-regression",
    "feat/release-2.0-banner",
    "docs/release-1.2-notes",
    "feat/12-release-notes",
    "feat/21-v2",
    "feat/3-v2",
    "feat/61-v2",
    "release-notes-page",
]
# (head, base, default branch)
RELEASE_BRANCHES = [
    (BRANCH, "gh-pages", "main"),
    (BRANCH, "deploy/prod", "main"),
    (BRANCH, "env/production", "main"),
    (BRANCH, "prod", "main"),
    (BRANCH, "live", "main"),
    (BRANCH, "deploy", "main"),
    (BRANCH, "stable", "main"),
    ("main", "staging", "main"),
    ("main", "develop", "main"),
    ("main", "release/v1.0", "main"),
    (BRANCH, "main", "develop"),
    (BRANCH, "master", "develop"),
    ("release/1.0", "master", "develop"),
    ("release/1.0", "main", "develop"),
    ("develop", "main", "develop"),
    (BRANCH, "master", "main"),
    (BRANCH, "release", "main"),
    (BRANCH, "customer-a", "main"),
    (BRANCH, "prd", "main"),
    (BRANCH, "production-eu", "main"),
    (BRANCH, "production_eu", "main"),
    (BRANCH, "production-v2", "main"),
    (BRANCH, "prod-us", "main"),
    (BRANCH, "eu-production", "main"),
    (BRANCH, "aws-prod", "main"),
    (BRANCH, "azure-production", "main"),
    (BRANCH, "live-eu", "main"),
    (BRANCH, "deploy-prod", "main"),
    (BRANCH, "cloudflare-pages", "main"),
    (BRANCH, "heroku", "main"),
    (BRANCH, "netlify", "main"),
    (BRANCH, "vercel", "main"),
    (BRANCH, "publish", "main"),
    (BRANCH, "released", "main"),
    (BRANCH, "latest", "main"),
    ("staging", "production-eu", "main"),
    ("develop", "staging", "main"),
    ("develop", "release/1.0", "main"),
    ("changeset-release/next", "next", "main"),
    ("release/1.0", "develop", "main"),
]
ORDINARY_BRANCHES = [
    (BRANCH, "develop", "develop"),
    (BRANCH, "release/v0.1.0", "main"),
    ("fix/9-typo", "staging", "main"),
    (BRANCH, "feat/2-base", "main"),
    (BRANCH, "1.x", "main"),
    (BRANCH, "v2", "main"),
    (BRANCH, "staging/eu", "main"),
    (BRANCH, "next", "main"),
    (BRANCH, "release-1.2", "main"),
    (BRANCH, "hotfix/1.0.1", "main"),
    (BRANCH, "trunk", "trunk"),
]


@pytest.mark.parametrize("title", RELEASE_TITLES)
def test_a_title_that_names_a_release_is_held(title):
    assert held({"title": title}) == ("fail", True)


@pytest.mark.parametrize("title", ORDINARY_TITLES)
def test_a_title_about_a_release_is_not_held(title):
    assert held({"title": title}) == ("pass", False)


def test_the_name_of_the_repository_counts_as_a_release_word():
    for title in ("chore: pipelinekit 0.2.0", "chore: bump pipelinekit to 0.2.0"):
        assert held({"title": title}, name="o/pipelinekit") == ("fail", True), title


@pytest.mark.parametrize("head", RELEASE_HEADS)
def test_a_branch_that_names_a_release_is_held(head):
    assert held({"headRefName": head}) == ("fail", True)


@pytest.mark.parametrize("head", ORDINARY_HEADS)
def test_a_branch_about_a_release_is_not_held(head):
    assert held({"headRefName": head}) == ("pass", False)


@pytest.mark.parametrize(("head", "base", "default"), RELEASE_BRANCHES)
def test_a_deploy_or_a_promotion_is_held(head, base, default):
    over = {"headRefName": head, "baseRefName": base}
    assert held(over, default) == ("fail", True)


@pytest.mark.parametrize(("head", "base", "default"), ORDINARY_BRANCHES)
def test_a_change_into_a_working_branch_is_not_held(head, base, default):
    over = {"headRefName": head, "baseRefName": base}
    assert held(over, default) == ("pass", False)


def test_merge_refuses_what_goes_into_main_when_it_is_not_the_default(sb):
    sb.passed()
    sb.state(repo=sb.repo(defaultBranchRef={"name": "develop"}))
    done = refused(sb, "release", 3)
    assert "main is not the default branch (develop)" in last_line(done)


PACKAGE = (
    '{\n  "name": "x",\n  "version": "%s",\n  "dependencies": {"lodash": "%s"}\n}\n'
)
PYPROJECT = '[project]\nname = "x"\nversion = "%s"\ndependencies = ["requests>=%s"]\n'
CSPROJ = (
    "<Project>\n  <PropertyGroup>\n    <Version>%s</Version>\n"
    "  </PropertyGroup>\n</Project>\n"
)
LOG = "# Changelog\n\n%s## 1.0.0\n\n- first\n"
# (file, on the base, on the branch, what the gate says)
VERSION_CHANGES = [
    ("VERSION", "1.0.0\n", "1.1.0\n", "the diff changes VERSION"),
    ("pkg/VERSION", "1.0.0\n", "1.1.0\n", "the diff changes pkg/VERSION"),
    (
        "package.json",
        PACKAGE % ("1.0.0", "4.17.20"),
        PACKAGE % ("1.1.0", "4.17.20"),
        "the diff sets a version in package.json",
    ),
    (
        "pyproject.toml",
        PYPROJECT % ("1.0.0", "2.0"),
        PYPROJECT % ("1.1.0", "2.0"),
        "the diff sets a version in pyproject.toml",
    ),
    (
        "src/App/App.csproj",
        CSPROJ % "1.0.0",
        CSPROJ % "1.1.0",
        "the diff sets a version in src/App/App.csproj",
    ),
    (
        "src/x/__init__.py",
        '__version__ = "1.0.0"\n',
        '__version__ = "1.1.0"\n',
        "the diff sets a version in src/x/__init__.py",
    ),
    (
        "CHANGELOG.md",
        LOG % "",
        LOG % "## [1.1.0] - 2026-11-10\n\n- second\n\n",
        "the diff adds a version heading to CHANGELOG.md",
    ),
]
ORDINARY_CHANGES = [
    ("package.json", PACKAGE % ("1.0.0", "4.17.20"), PACKAGE % ("1.0.0", "4.17.21")),
    ("pyproject.toml", PYPROJECT % ("1.0.0", "2.0"), PYPROJECT % ("1.0.0", "2.1")),
    ("CHANGELOG.md", LOG % "", LOG % "## Unreleased\n\n### Added\n\n- second\n\n"),
    ("docs/guide.md", "# Guide\n", "# Guide\n\n## 2.0.0\n\nversion = 2\n"),
    ("src/x/__init__.py", "import os\n", "import os\nimport sys\n"),
]


@pytest.mark.parametrize(("path", "before", "after", "words"), VERSION_CHANGES)
def test_merge_refuses_a_change_of_the_version(sb, path, before, after, words):
    sb.change(path, before, after)
    sb.passed()
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        f"STOP: release: {words}: a new version is a release. Ask the user."
    )


@pytest.mark.parametrize(("path", "before", "after"), ORDINARY_CHANGES)
def test_a_change_next_to_the_version_is_not_a_release(sb, path, before, after):
    sb.change(path, before, after)
    assert gates(sb.ship("status", "--json"))["release"]["state"] == "pass"


def test_a_diff_that_cannot_be_read_is_not_taken_for_ordinary(sb):
    sb.state(pr=sb.pr(baseRefName="develop"))
    release = gates(sb.ship("status", "--json"))["release"]
    assert release["state"] == "fail"
    assert release["detail"].startswith("cannot read what changes against develop: ")


def test_many_files_that_can_hold_a_version_are_held():
    count = ship.MAX_VERSION_FILES + 1
    meta = ":100644 100644 " + "1" * 40 + " " + "2" * 40 + " M"
    raw = "".join(f"{meta}\0pkg{n}/package.json\0" for n in range(count))
    repo = SimpleNamespace(remote="origin", try_git=lambda *args: (0, raw, ""))
    assert ship.version_change(repo, "main") == (
        f"the diff changes {count} files that can hold a version: "
        "a new version is a release",
        "",
    )


def test_merge_says_where_a_base_that_cannot_be_moved_left_the_checkout(sb):
    sb.git("checkout", "-q", "main")
    sb.commit("chore: local only")
    sb.git("checkout", "-q", BRANCH)
    sb.passed()
    head = sb.head()
    origin = str(sb.tmp / "origin.git")
    sb.state(
        on_merge=["git", "--git-dir", origin, "update-ref", "refs/heads/main", head]
    )
    done = sb.ship("merge")
    assert done.returncode == 0, done.stdout + done.stderr
    last = last_line(done)
    assert last.startswith(
        f"Merged #7 into main (squash) at {head[:7]}. Now on main, which could "
        "not be brought up to origin/main: git merge -q --ff-only origin/main "
        "failed: fatal: "
    ), last
    assert "hint:" not in last and "Still on" not in last
    assert sb.git("branch", "--show-current") == "main"


def test_a_failed_git_command_is_told_without_its_hints():
    text = "hint: Diverging branches\nhint:\nfatal: Not possible to fast-forward.\n"
    assert ship.git_said(text, 128) == "fatal: Not possible to fast-forward."
    assert ship.git_said("hint: only\nplain words\n", 1) == "plain words"
    assert ship.git_said("", 7) == "exit 7"


# ---------------------------------------------------------------- what the diff holds

OLD, NEW = "1" * 40, "2" * 40


def verdict(path, before, after, own=()):
    """What the diff rules say about one changed file, without a repository."""
    old = OLD if before else "0" * 40
    raw = f":100644 100644 {old} {NEW} M\0{path}\0"
    was = before.splitlines()
    added = "".join(f"+{line}\n" for line in after.splitlines() if line not in was)
    patch = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n"

    def try_git(*args):
        if "--raw" in args:
            return 0, raw, ""
        if args[0] == "cat-file":
            return 0, {OLD: before, NEW: after}[args[2]], ""
        return 0, patch + added, ""

    repo = SimpleNamespace(remote="origin", try_git=try_git)
    why, error = ship.version_change(repo, "main", own)
    assert not error
    return why


def bump(path, text, old="1.2.3", new="1.2.4"):
    return path, text % old, text % new


POM = (
    "<project>\n  <modelVersion>4.0.0</modelVersion>\n"
    "  <parent>\n    <artifactId>base</artifactId>\n"
    "    <version>%s</version>\n  </parent>\n"
    "  <artifactId>demo</artifactId>\n  <version>%s</version>\n"
    "  <dependencies>\n    <dependency>\n      <artifactId>junit</artifactId>\n"
    "      <version>%s</version>\n    </dependency>\n  </dependencies>\n"
    "</project>\n"
)
PLIST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0">\n<dict>\n'
    "  <key>CFBundleName</key>\n  <string>Demo</string>\n"
    "  <key>CFBundleShortVersionString</key>\n  <string>%s</string>\n"
    "</dict>\n</plist>\n"
)
CHART = (
    'apiVersion: v2\nname: demo\nversion: %s\nappVersion: "%s"\n'
    "dependencies:\n  - name: redis\n    version: %s\n"
)
CARGO = (
    '[package]\nname = "demo"\nversion = "%s"\n\n'
    '[dependencies.clap]\nversion = "%s"\nfeatures = ["derive"]\n'
)
ENGINES = '{\n  "name": "x",\n  "version": "1.0.0",\n  "engines": {"node": ">=%s"}\n}\n'
WORKFLOW = (
    'steps:\n  - uses: actions/setup-python@%s\n    with:\n      python-version: "%s"\n'
)
HELD_FILES = [
    ("pom.xml", POM % ("3.0.0", "1.2.3", "4.13.1"), POM % ("3.0.0", "1.2.4", "4.13.1")),
    bump(
        "demo.nuspec",
        "<package>\n  <metadata>\n    <id>demo</id>\n"
        "    <version>%s</version>\n  </metadata>\n</package>\n",
    ),
    bump("src/App/Properties/AssemblyInfo.cs", '[assembly: AssemblyVersion("%s.0")]\n'),
    bump("ios/Demo/Info.plist", PLIST),
    bump(
        "CMakeLists.txt",
        "cmake_minimum_required(VERSION 3.20)\nproject(demo VERSION %s)\n",
    ),
    bump("DESCRIPTION", "Package: demo\nVersion: %s\n"),
    bump(".bumpversion.cfg", "[bumpversion]\ncurrent_version = %s\n"),
    bump(".release-please-manifest.json", '{\n  ".": "%s"\n}\n'),
    bump("VERSION.md", "%s\n"),
    bump("build/version.properties", "version=%s\n"),
    bump("package.json", '{"name":"demo-app","version":"%s","private":true}\n'),
    bump("Cargo.toml", '[package]\nname = "demo"\nversion = "%s"\n'),
    (
        "Chart.yaml",
        CHART % ("1.2.3", "1.2.3", "17.0.0"),
        CHART % ("1.2.4", "1.2.3", "17.0.0"),
    ),
    (
        "charts/demo/Chart.yaml",
        CHART % ("1.2.3", "1.2.3", "17.0.0"),
        CHART % ("1.2.3", "1.2.4", "17.0.0"),
    ),
    bump(
        "openapi.yaml",
        "openapi: 3.0.3\ninfo:\n  title: Demo\n  version: %s\npaths: {}\n",
    ),
    bump("demo.cabal", "name: demo\nversion: %s\n"),
    bump("meson.build", "project('demo', 'c', version : '%s')\n"),
    bump("snapcraft.yaml", "name: demo\nversion: '%s'\n"),
    bump("galaxy.yml", "namespace: acme\nname: demo\nversion: %s\n"),
    bump(
        "deno.jsonc",
        '{\n  // the package\n  "name": "@acme/demo",\n  "version": "%s"\n}\n',
    ),
    bump(
        "src-tauri/tauri.conf.json",
        '{\n  "productName": "demo",\n  "version": "%s"\n}\n',
    ),
    bump(
        "setup.py", 'from setuptools import setup\n\nsetup(name="demo", version="%s")\n'
    ),
    bump("include/version.h", '#define DEMO_VERSION "%s"\n'),
    bump(
        "app/build.gradle",
        'android {\n  defaultConfig {\n    versionName "%s"\n  }\n}\n',
    ),
    bump("MODULE.bazel", 'module(name = "app", version = "%s")\n'),
]
ORDINARY_FILES = [
    ("pom.xml", POM % ("3.0.0", "1.2.3", "4.13.1"), POM % ("3.0.1", "1.2.3", "4.13.1")),
    ("pom.xml", POM % ("3.0.0", "1.2.3", "4.13.1"), POM % ("3.0.0", "1.2.3", "4.13.2")),
    ("Cargo.toml", CARGO % ("1.0.0", "4.4"), CARGO % ("1.0.0", "4.5")),
    (
        "Chart.yaml",
        CHART % ("1.2.3", "1.2.3", "17.0.0"),
        CHART % ("1.2.3", "1.2.3", "17.0.1"),
    ),
    ("package.json", ENGINES % "18.0.0", ENGINES % "20.0.0"),
    bump("package-lock.json", '{\n  "name": "demo",\n  "version": "%s"\n}\n'),
    bump("tests/fixtures/package.json", '{"name": "x", "version": "%s"}\n'),
    bump("vendor/lib/VERSION", "%s\n"),
    (".github/workflows/ci.yml", WORKFLOW % ("v5", "3.12"), WORKFLOW % ("v6", "3.13")),
    bump("docker-compose.yml", 'version: "%s"\nservices: {}\n', "3.8", "3.9"),
    bump(".nvmrc", "%s\n", "20.1.0", "22.0.0"),
    bump("README.md", "# Demo\n\nInstall version %s.\n"),
    ("docs/guide.md", "# Guide\n", "# Guide\n\n## 2.0.0\n\nversion = 2.0.0\n"),
    (".readthedocs.yaml", "", "version: 2\nbuild:\n  os: ubuntu-22.04\n"),
    bump("config/app.yaml", "host: %s\nport: 8080\n", "10.0.0.1", "10.0.0.2"),
    bump("config/app.ini", "[server]\nhost = %s\n", "10.0.0.1", "10.0.0.2"),
    bump(
        "packages.config",
        '<packages>\n  <package id="Json" version="%s" targetFramework="net48" />\n'
        "</packages>\n",
    ),
    bump(
        "MODULE.bazel",
        'module(name = "app", version = "1.0.0")\n'
        'bazel_dep(name = "rules_go", version = "%s")\n',
    ),
    bump("deps.edn", '{:deps {org.clojure/clojure {:mvn/version "%s"}}}\n'),
    bump(
        "Package.swift",
        "let package = Package(\n  dependencies: [\n"
        '    .package(url: "https://example.invalid/x.git", from: "%s"),\n  ]\n)\n',
    ),
    bump("paket.dependencies", "source https://example.invalid\nnuget Json %s\n"),
]


@pytest.mark.parametrize(("path", "before", "after"), HELD_FILES)
def test_a_version_of_the_project_is_held_in_any_manifest(path, before, after):
    assert verdict(path, before, after).endswith(": a new version is a release")


@pytest.mark.parametrize(("path", "before", "after"), ORDINARY_FILES)
def test_a_version_of_something_else_is_ordinary(path, before, after):
    assert verdict(path, before, after) == ""


HELD_CODE = [
    bump(
        "app.config.js",
        "module.exports = {\n  expo: {\n    version: '%s',\n  },\n};\n",
    ),
    bump("app.config.ts", 'export default {\n  name: "demo",\n  version: "%s",\n};\n'),
    bump(
        "app.config.js",
        "export default {\n  android: { versionCode: %s },\n};\n",
        "7",
        "8",
    ),
    bump("src/meta.ts", 'export const meta = {\n  version: "%s",\n} as const;\n'),
    bump("meta.js", "module.exports = {\n  'version': '%s',\n};\n"),
    bump("src/AppInfo.cs", '    public static readonly string Version = "%s";\n'),
    bump("src/AppInfo.cs", '    public static string Version { get; } = "%s";\n'),
    bump("src/AppInfo.cs", '    public static string Version => "%s";\n'),
    bump("src/config.h", '#define APP_VERSION "%s"\n'),
    bump("src/app.cpp", 'static const std::string VERSION = "%s";\n'),
    bump("src/app.c", 'static const char *VERSION = "%s";\n'),
    bump("src/app.ts", 'export class App {\n  static readonly version = "%s";\n}\n'),
    bump("cmd/root.go", 'var rootCmd = &cobra.Command{\n\tVersion: "%s",\n}\n'),
    bump("lib/demo.ex", '  @version "%s"\n'),
    bump("lib/Demo.pm", "our $VERSION = '%s';\n"),
    bump("demo.lua", 'local VERSION = "%s"\n'),
    bump("demo.php", "define('APP_VERSION', '%s');\n"),
    bump("config/app.php", "return [\n    'version' => '%s',\n];\n"),
    bump("src/x/__init__.py", '__version__ = "%s"\n'),
]
ORDINARY_CODE = [
    bump("src/client.ts", 'const options = {\n  apiVersion: "%s",\n};\n'),
    bump("src/app.js", 'version === "%s" ? migrate() : start();\n'),
    bump("src/config.h", '#define PYTHON_VERSION "%s"\n'),
    bump("src/app.ts", 'const format = {\n  version: "%s",\n};\n', "1", "2"),
    bump("src/app.py", '    print("version: %s")\n'),
    bump("tests/meta.js", "module.exports = {\n  version: '%s',\n};\n"),
    bump("src/app.js", "  // version: '%s' was the last one with the old login\n"),
]


@pytest.mark.parametrize(("path", "before", "after"), HELD_CODE)
def test_a_version_set_in_source_code_is_held(path, before, after):
    assert verdict(path, before, after) == (
        f"the diff sets a version in {path}: a new version is a release"
    )


@pytest.mark.parametrize(("path", "before", "after"), ORDINARY_CODE)
def test_source_code_that_only_names_a_version_is_ordinary(path, before, after):
    assert verdict(path, before, after) == ""


@pytest.mark.parametrize("parser", ["tomllib", "by line"])
def test_toml_is_read_the_same_without_a_parser(monkeypatch, parser):
    if parser == "by line":
        monkeypatch.setattr(sys.modules["ship_gates"], "tomllib", None)
    held_one = bump("Cargo.toml", '[package]\nname = "demo"\nversion = "%s"\n')
    assert verdict(*held_one).startswith("the diff sets a version in Cargo.toml")
    assert (
        verdict("Cargo.toml", CARGO % ("1.0.0", "4.4"), CARGO % ("1.0.0", "4.5")) == ""
    )
    assert (
        verdict(
            "pyproject.toml", PYPROJECT % ("1.0.0", "2.0"), PYPROJECT % ("1.0.0", "2.1")
        )
        == ""
    )


NOTES = "Changelog\n=========\n\n%s1.2.3\n-----\n\n- first\n"
# (file, what the branch adds above the last version)
HELD_NOTES = [
    ("CHANGELOG.md", "1.2.4\n=====\n\n- second\n\n"),
    ("CHANGELOG.md", "1.2.4 (2026-11-10)\n------------------\n\n- second\n\n"),
    ("CHANGELOG.md", "## demo-app 1.2.4\n\n- second\n\n"),
    ("CHANGELOG.md", "## demo-app@1.2.4\n\n- second\n\n"),
    ("CHANGELOG.md", "#### [1.2.4]\n\n- second\n\n"),
    ("CHANGELOG.md", "## \U0001f389 1.2.4\n\n- second\n\n"),
    ("CHANGELOG.md", "**1.2.4**\n\n- second\n\n"),
    ("CHANGELOG.md", "demo-app 1.2.4 - November 10, 2026\n\n- second\n\n"),
    ("CHANGELOG.md", "Version 1.2.4\n\n- second\n\n"),
    ("CHANGELOG.md", "[1.2.4]: https://example.test/compare/v1.2.3...v1.2.4\n\n"),
    ("RELEASE_NOTES.md", "## 1.2.4\n\n- second\n\n"),
    ("CHANGELOG", "1.2.4\n-----\n\n- second\n\n"),
    ("docs/CHANGELOG.rst", "1.2.4\n-----\n\n- second\n\n"),
    ("HISTORY.rst", "1.2.4 (2026-11-10)\n++++++++++++++++++\n\n- second\n\n"),
    ("NEWS", "demo-app 1.2.4\n\n- second\n\n"),
]
ORDINARY_NOTES = [
    "Unreleased\n----------\n\n- bump lodash to 4.17.21\n\n",
    "Unreleased\n----------\n\n- needs Python 3.12 or newer\n\n",
    "Unreleased\n----------\n\n- fix a crash that 1.2.3 brought in\n\n",
    "Unreleased\n----------\n\n- second\n\n",
]


@pytest.mark.parametrize(("path", "added"), HELD_NOTES)
def test_a_new_version_in_the_release_notes_is_held(path, added):
    own = ship.own_words({"nameWithOwner": "o/demo-app"})
    why = verdict(path, NOTES % "", NOTES % added, own)
    assert (
        why == f"the diff adds a version heading to {path}: a new version is a release"
    )


@pytest.mark.parametrize("added", ORDINARY_NOTES)
def test_a_note_about_another_version_is_ordinary(added):
    own = ship.own_words({"nameWithOwner": "o/demo-app"})
    assert verdict("CHANGELOG.md", NOTES % "", NOTES % added, own) == ""


def test_a_new_file_of_release_notes_for_one_version_is_held():
    why = verdict("docs/releases/1.2.4.md", "", "# What is new\n\n- second\n")
    assert why == "the diff changes docs/releases/1.2.4.md: a new version is a release"


# ---------------------------------------------------------------- promotions


def test_a_branch_that_pull_requests_were_merged_into_is_a_stage():
    assert held({"headRefName": "team-blue"}) == ("pass", False)
    assert held({"headRefName": "team-blue"}, merged='[{"number": 3}]') == (
        "fail",
        True,
    )


def test_a_topic_branch_is_not_asked_about():
    def gh(*args, **more):
        raise AssertionError("asked GitHub about a topic branch")

    assert ship.promoted(SimpleNamespace(gh=gh), BRANCH) == ("", "")


@pytest.mark.parametrize(
    "answer", [(1, "", "HTTP 502"), (0, "<html>", ""), (0, "", ""), (0, "null", "")]
)
def test_no_answer_about_a_branch_is_not_taken_for_no(answer):
    repo = SimpleNamespace(gh=lambda *args, **more: answer)
    why, error = ship.promoted(repo, "team-blue")
    assert not why
    assert error.startswith("cannot ask GitHub what was merged into team-blue: ")


def test_merge_refuses_a_branch_that_pull_requests_were_merged_into(sb):
    sb.passed()
    sb.state(pr=sb.pr(headRefName="team-blue"), merged_into=[{"number": 3}])
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        "STOP: release: pull requests were merged into team-blue: merging it on "
        "is a promotion. Ask the user."
    )
    asked = sb.calls("pr list")[0]
    assert asked[asked.index("--base") + 1] == "team-blue"
    assert asked[asked.index("--state") + 1] == "merged"


def test_merge_waits_when_github_does_not_say_what_was_merged(sb):
    sb.passed()
    sb.state(pr=sb.pr(headRefName="team-blue"), list_error="HTTP 502")
    done = refused(sb, "release", 1)
    assert "cannot ask GitHub what was merged into team-blue: " in last_line(done)


# ---------------------------------------------------------------- the recorded answer


def test_a_passed_round_has_to_say_whether_it_is_a_release(sb):
    done = sb.ship("record", "--result", "pass")
    assert done.returncode == 2
    assert "--release yes or no" in done.stderr
    assert not (sb.work / "docs").exists()
    assert sb.ship("record", "--result", "fail", "--open", "F1").returncode == 0


def test_merge_refuses_what_the_record_calls_a_release(sb):
    sb.passed("yes")
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        "STOP: release: the test record says this is a release. Ask the user."
    )


def test_a_record_without_the_answer_does_not_pass(sb):
    sb.passed()
    file = sb.work / "docs" / "uat" / "feat-1-thing.json"
    data = json.loads(file.read_text())
    del data["rounds"][-1]["release"]
    file.write_text(json.dumps(data))
    assert "--release yes or no" in last_line(refused(sb, "release", 1))


# ---------------------------------------------------------------- project lines


def test_project_lines_name_release_files_and_branches():
    texts = [
        "# Rules\n\nRelease files: app/build.txt, deploy/\n"
        "- **Release branches:** `team-*`\n",
        "Release file: *.ver\nThe release files: are listed above.\n"
        "Release branch: Shipping\n",
    ]
    files, branches = ship.project_lines(texts)
    assert files == ["app/build.txt", "deploy/", "*.ver"]
    assert branches == ["team-*", "shipping"]


def test_merge_refuses_a_change_to_a_release_file_of_the_project(sb):
    sb.change("CLAUDE.md", "# Rules\n", "# Rules\n\nRelease files: app/build.txt\n")
    sb.change("app/build.txt", "7\n", "8\n")
    sb.passed()
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        "STOP: release: the diff changes app/build.txt, a release file of this "
        "project. Ask the user."
    )


def test_a_file_the_project_does_not_name_is_ordinary(sb):
    sb.change("app/build.txt", "7\n", "8\n")
    assert gates(sb.ship("status", "--json"))["release"]["state"] == "pass"


def test_merge_refuses_a_release_branch_of_the_project(sb):
    sb.change("CLAUDE.md", "# Rules\n", "# Rules\n\nRelease branches: feat/1-*\n")
    sb.passed()
    done = refused(sb, "release", 3)
    assert last_line(done) == (
        "STOP: release: feat/1-thing is a release branch of this project. Ask the user."
    )


# ---------------------------------------------------------------- answers, limits


def test_a_branch_cannot_drop_the_opt_out_of_its_base(sb):
    sb.git("checkout", "-q", "main")
    (sb.work / "CLAUDE.md").write_text("Merges: ask first\n")
    sb.git("add", "CLAUDE.md")
    sb.git("commit", "-q", "-m", "docs: ask before merging")
    sb.git("push", "-q", "origin", "main")
    sb.git("checkout", "-q", BRANCH)
    sb.git("merge", "-q", "-m", "chore: merge main", "main")
    sb.git("rm", "-q", "CLAUDE.md")
    sb.git("commit", "-q", "-m", "docs: drop the rules file")
    sb.git("push", "-q")
    sb.state()
    sb.passed()
    done = refused(sb, "policy", 3)
    assert "CLAUDE.md on main says `Merges: ask first`" in last_line(done)


@pytest.mark.parametrize(
    ("state", "words"),
    [("BEHIND", "behind main, GitHub says"), ("DIRTY", "conflicts with main")],
)
def test_merge_refuses_what_github_calls_behind_or_in_conflict(sb, state, words):
    sb.passed()
    sb.state(pr=sb.pr(isDraft=False, mergeStateStatus=state))
    assert words in last_line(refused(sb, "up-to-date", 1))


def test_finding_ids_split_on_commas_and_semicolons(sb):
    done = sb.ship("record", "--result", "fail", "--open", "F1,F2", "F3; F4")
    assert done.returncode == 0
    data = json.loads((sb.work / "docs/uat/feat-1-thing.json").read_text())
    assert data["rounds"][0]["open"] == ["F1", "F2", "F3", "F4"]


def test_record_refuses_the_default_branch(sb):
    sb.git("checkout", "-q", "main")
    done = sb.ship("record", "--result", "pass", "--release", "no")
    assert done.returncode == 2
    assert "main is not the branch of a pull request" in done.stderr
    assert not (sb.work / "docs").exists()


def test_seconds_may_be_decimals(sb):
    assert sb.ship("wait", "--timeout", "0.5", "--grace", "0.25").returncode == 0


@pytest.mark.parametrize("raw", ["<html>502 Bad Gateway</html>", "[]", "null", ""])
def test_an_unreadable_answer_from_gh_is_a_tool_error(sb, raw):
    sb.passed()
    sb.state(pr_raw=raw)
    done = sb.ship("status")
    assert done.returncode == 2
    assert "gh pr view: unreadable answer" in done.stderr
    done = sb.ship("merge")
    assert done.returncode == 2
    assert last_line(done) == "Not merged: gh pr view: unreadable answer."
    assert sb.calls("pr ready") == [] and sb.calls("pr merge") == []


def test_wait_does_not_sleep_past_its_timeout(sb):
    sb.state(pr=sb.pr(statusCheckRollup=[check("lint", "", "IN_PROGRESS")]))
    start = time.monotonic()
    done = sb.ship("wait", "--timeout", "1", SHIP_POLL_SECONDS="15")
    assert done.returncode == 1 and "still running after 1 s" in done.stdout
    assert time.monotonic() - start < 6
