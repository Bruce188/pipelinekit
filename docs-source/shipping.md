---
diataxis: reference
---

# Shipping a pull request

With the kit installed, Claude finishes the pull requests it opens instead of handing each one to you to merge. The `ship` skill (`/ship`) describes the loop, and `claude/skills/ship/ship.py` holds the conditions for the merge.

1. The issue lists acceptance criteria as a checklist.
2. Claude builds the change, brings in its base, runs the project's tests and opens a draft pull request.
3. The build is judged with the judge loop until it reaches 10 (see [Plan, build, judge](skills.html#plan-build-judge)); a small fix is recorded with `loop.py skip --reason` instead.
4. `ship.py prepare` keeps the test reports out of git, and a fresh agent tests the change. It gets the criteria and the running build, not the code or the builder's notes. A web page is driven with Playwright, a command-line tool or installer runs in a throwaway directory, an API is started and called. A change with nothing user-visible gets a smoke run instead.
5. Findings are fixed, each bug with a regression test, and the test runs again until it passes.
6. `ship.py record` notes the result for the tested commit, and with a pass whether the pull request is a release (`--release yes` or `--release no`). `ship.py merge` waits for CI and merges.

`ship.py merge` refuses unless every gate holds:

| Gate | Holds when |
|------|------------|
| `pr` | The branch has an open pull request |
| `own` | Your GitHub account opened it, and it is not from a fork |
| `policy` | The project has not opted out. A project or user-level `CLAUDE.md` that is there but cannot be read, such as a named pipe, a folder, a file without read permission or a link to nothing, is named and stops the merge, since it may hold the opt-out line; it is opened without waiting, so it cannot hang the helper |
| `release` | It is not a release. A release is: a release, stage or version branch (`release/1.0`, `develop`, `staging`, `v2`, `chore/release-0.2.0`) into the default branch or into another long-lived branch; the default branch into another branch; anything into a deploy branch such as `production`, `prod-eu` or `gh-pages`; anything into `main` where another branch is the default; anything into a branch that is neither the default nor a known working branch; a branch that pull requests were merged into; a title that names a release or a version; a diff that sets a version or changes a release file of the project; a test record that says it is one (all below) |
| `linked` | GitHub closes every issue named on this merge, or another branch is the base: [Issue links](installation.html#issue-links) |
| `review` | No review is required, requested or asking for changes |
| `current` | The local commit is the pull request's head and nothing tracked is uncommitted |
| `up-to-date` | The branch holds its [base](installation.html#up-to-date-with-the-base), with no conflict |
| `judged` | The branch's build loop ended in 10, a used budget or your accept on this commit or an earlier one, or `loop.py skip` recorded this commit; a loop waiting for you stops and asks; `Judge loop: off` on the base branch or in your user-level `CLAUDE.md` passes and is named in the reason; the user-level file is read as the `policy` gate reads it, through a link, and one it cannot read stops the merge. Limits: [The judge loop](installation.html#the-judge-loop) |
| `tested` | The last test record is a pass for exactly this commit, and the loop is not stuck |
| `ci` | Every check has finished and passed. A pull request with no check at all passes only where no workflow runs on pull requests or on pushes to the branch, or with `--allow-no-checks`. The `on:` block of each workflow decides, with its branch filters (`branches`, `branches-ignore`, a push trigger with only `tags`); a word in a comment does not count. Where no workflow runs for the branch, and with `--allow-no-checks` unless `--grace` is given, `wait` and `merge` do not wait for a first check; one that shows up is still waited for. A draft whose checks were all skipped is pending where a workflow runs on pull requests: a check is still to come, and `merge` marks the draft ready and waits for it. A head commit whose message holds `[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]` or `[actions skip]`, or ends in a `skip-checks: true` trailer, gets no workflow run from GitHub, also not when the pull request is reopened: where a workflow runs for the branch and no check is on that commit, the gate fails and names the tag, `wait` and `merge` say so at once instead of waiting for a first check, and the way on is to push a commit without the tag |

The merge command names the tested commit (`--match-head-commit`), so a commit pushed in between is not merged. The helper has no `--admin` option, and `gh pr merge --admin` is on the `permissions.ask` list. The merge method follows the base branch: a merge commit where the branch already has them, squash otherwise.

A draft has to be marked ready before GitHub merges it, and that can start checks, add reviewers or turn on branch protection. The helper therefore watches the pull request after marking it ready and merges only when it stayed mergeable for the whole settle time: 30 seconds or, where a check is still to come because none has run yet or a workflow starts on `ready_for_review`, the `--grace` time when that is longer (90 seconds by default; `--grace 5` leaves it at 30). `--settle S` sets the time. While it watches it reads the head, the checks, the reviews and whether GitHub can merge; the author, the title and the base were checked before the draft was marked ready and are not checked again. Where a workflow runs on pull requests, a check must really have run by then: one that was skipped on the draft does not count, and only `--allow-no-checks` lifts that. If something showed up, the pull request stays ready and unmerged. The last line of output is the outcome: `Merged #12 into main ...`, `Not merged: ...` or `STOP: ...`. Two runs end otherwise: `merge --dry-run` with every gate holding ends with `Dry run. Would ...`, and a usage error, such as an unknown option, ends with the `ship.py merge: error: ...` line of argparse and exit code 2. The gate table goes to stdout and the waiting lines to stderr, in the order they happen, also through a pipe.

The release gate leans towards asking. A feature branch into a release branch such as `release/v1.0` is an ordinary change and merges; the release branch into `main` does not. A title counts when it is made of release words (`chore: prepare 0.3.0`, `Bump version: 1.2.3 to 1.2.4`, `chore: release kit 1.2.0`, `chore: bump version in package.json`, `chore: weekly release`, `chore: patch`, `Deploy`), not when it is about a release (`fix: release 1.2.0 broke the installer`, `chore: release script`), about a dependency (`chore(deps): bump lodash to 4.17.21`) or about a tool (`ci: bump python version to 3.12`); `docs`, `test`, `style`, `refactor` and `perf` titles never count.

The gate also reads the diff against the base branch. It does not work from a list of known manifests: a version is ordinary in the places known to hold the versions of other things, and held anywhere else, whatever the file format.

Held are:

- any change to a version file (`VERSION`, `version.txt`, `.bumpversion.cfg`, `.release-please-manifest.json`) and any numbered file in a release-notes directory (`docs/releases/1.2.4.md`, `docs/whatsnew/1.2.4.rst`, and the same under `changes/`, `news/` or `history/`);
- a new or changed value under a key with `version` in its name, in any manifest or data file: `package.json`, `pyproject.toml`, `Cargo.toml`, `pom.xml`, a `.csproj` or `.nuspec`, `Chart.yaml`, `Info.plist`, `CMakeLists.txt`, `build.gradle`, `setup.py`, `AssemblyInfo.cs`, `version.h`, an Ant `<property name="version" value="1.2.4"/>`, a `.nix` file, and files the helper has never heard of. In a file without a known format, a line that only swaps one three-part number for another counts too;
- a line of source code that sets a quoted version: an assignment (`__version__ = "1.2.4"`, `public static readonly string Version = "1.2.4";`), a key of an object, a struct or a dictionary (`version: "1.2.4",`), a `#define APP_VERSION "1.2.4"`, a tuple (`VERSION = (1, 2, 4)`, `__version_info__ = (1, 2, 4)`), Sphinx's `release = "1.2.4"`; and the header comment of a WordPress plugin or theme or of a userscript (` * Version: 1.2.4`, `// @version 1.2.4`). `app.config.*` and `vite.config.*` are read as manifests, so a Vite `define` with `JSON.stringify("1.2.4")` counts;
- a new version heading in release notes (`CHANGELOG`, `CHANGES`, `HISTORY`, `NEWS`, `RELEASES`, `RELEASE_NOTES`, with any extension): `## 1.2.4`, `## [1.2.4] - 2026-11-10`, `1.2.4` over an underline, `**1.2.4**`, `## kit 1.2.4`, a link definition `[1.2.4]: ...`, the first line of a `debian/changelog` entry (`demo (1.2.4-1) unstable; urgency=medium`).

Ordinary are: lock files; files that pin tools (`.nvmrc`, `.python-version`, `Dockerfile`, `docker-compose.yml`, `requirements*.txt`, `.pre-commit-config.yaml`, `packages.config`, `deps.edn`); everything under `.github/`, `.circleci/` and `.devcontainer/`; files in test, fixture, example and vendor directories; documentation (`README`, `.md`, `.rst`, `.txt`, `.html`); dependency tables and elements (`dependencies`, `[dependencies.clap]`, `<parent>`, `<dependency>`, `engines`); keys that name a tool or a format from a fixed list (`python-version`, `apiVersion`, `schemaVersion`, `minSdkVersion`); a whole number under a plain `version` key (`version: 2` is a format version); a changelog entry under an existing heading.

No reading of a diff is complete, so three more things decide:

- `ship.py record --result pass` takes `--release yes` or `--release no`. Whoever ran the test knows what the change is and says so; `yes` holds the pull request until a new commit, also when a later round on the same commit says `no`, and a pass without the answer is not accepted.
- A project names its own release files and branches in its `CLAUDE.md`, each on a line of its own: `Release files: app/build.txt, deploy/` and `Release branches: team-*, customer-*`. A change to one of the files, and a pull request from or into one of the branches, is held. A file value reads the way `.gitignore` reads a pattern: `deploy/`, and a plain name such as `deploy`, cover everything below a directory of that name at any depth, while `/deploy/` and `infra/deploy` cover only the one at that path; a glob such as `*.ver` matches the path or the file name. A value may end a sentence: `deploy/.` is `deploy/`. The `release` gate names a value that matches no tracked file under its line in `status`. A branch value ending in `/` covers every branch that starts with it; anything else is a glob on the whole name. As with the opt-out line, the `CLAUDE.md` on the base branch counts as well.
- A branch that other pull requests were merged into is a stage, whatever it is called, and merging it on is a promotion. The helper asks GitHub about every head branch that is not a topic branch (`feat/...`, `fix/...`); without an answer nothing merges.

The gate guards your own project against a slip. It is not a defence against a pull request written to get past it. It does not see: a version in a place the lists call ordinary (a label in a `Dockerfile`, a file under `tests/` or `examples/`, a `.md` file that is not release notes); a whole-number version under a plain `version` key; a version that source code builds at run time (`VERSION = ".".join(parts)`); a version in a `.tf`, `.tfvars` or `.hcl` file, where Terraform pins its providers and modules; a version Maven takes from `<properties>` or `${revision}`; files over 1 MB and binary files; a release whose title uses no release word (`chore: go live`) and whose diff sets no version. It holds some pull requests that are not releases: a nested package getting its first version, a version-like setting in a config file, an Ant property that pins a dependency (`junit.version`), a key that names a tool outside the fixed list (`KUBECTL_VERSION` or `POSTGRES_VERSION` in a `Makefile`, `postgres_version:` in Ansible vars), and the branch names and titles below. The tool list stays fixed on purpose: a project can carry the name of a tool, and a wider rule would let its own version through. When that happens, say that it may be merged, and merge it yourself.

How the gate reads some common branch names and titles:

| Branch the pull request comes from | Outcome |
|---|---|
| `qa-fixes`, `staging-eu`, `nightly-build`, `canary` | held: `qa`, `staging`, `nightly` or `canary`, alone or with one more part |
| `qa-fixes-login`, `staging-eu-2`, `dev-tools`, `test-utils`, `beta-feature` | ordinary: more than one part after the stage word, or a word that only names a stage when it stands alone |
| `feat/qa-fixes`, `hotfix/login`, `feat/21-v2`, `update-deps` | ordinary: a topic branch, or no stage or version word |
| `hotfix/1.2.1`, `prepare-1.2.0`, `bump-version`, `chore/bump-version`, `v2`, `1.x` | held: a version in the name, or a version bump |
| `release-notes-script`, `docs/release-notes` | ordinary: about release notes, not a release |

| Title | Outcome |
|---|---|
| `chore: lodash 4.17.21`, `chore: kit 1.2.0`, `chore: 1.2.0`, `chore: v2` | held: a name and a number, or a number alone |
| `chore: bump lodash to 4.17.21`, `chore(deps): bump lodash to 4.17.21`, `chore: upgrade react to 18.2.0` | ordinary: a dependency moves to a version |
| `chore: node 20`, `chore: python 3.12`, `fix: crash in 1.2.3` | ordinary: a tool, or a sentence about another version |
| `chore: release`, `chore: weekly release`, `chore: patch`, `chore: update version`, `Deploy` | held: a release word on its own |
| `chore: release script`, `docs: release 1.2.0`, `deploy docs`, `fix: patch`, `feat: v2 api` | ordinary: about how releases are made, a quiet or plain type, or more than the release word |
| `chore: go live` | ordinary, although it may be one: no release word and, unless the diff sets one, no version; say `--release yes` |

Known working branches are: the default branch; the shared branches `develop`, `development`, `dev`, `integration`, `staging`, `stage`, `next`, `beta`, `alpha`, `canary`, `preview`, `nightly`, `edge`, `uat`, `qa`, `preprod`, `test`, `testing` and `trunk`; branches under `integration/`, `staging/`, `stage/`, `uat/`, `qa/` and `preprod/`; release lines, which is anything that starts with `release/`, `release-`, `releases/`, `rel/`, `rc/`, `hotfix/`, `support/` or `maint/`, and bare version names such as `1.x` or `v2`; topic branches such as `feat/12-base` (a stacked pull request). A pull request into any other branch (`customer-a`, `release`) is held, because the helper cannot know what that branch stands for. Name such a branch on a `Release branches:` line when it is a release branch. As the branch a pull request comes from, `hotfix/login-crash` is a fix like any other; only a hotfix branch with a version in its name (`hotfix/1.2.1`), or one that other pull requests were merged into, is held.

These stay yours: release pull requests, tags, publishing and production deploys; pull requests someone else opened; anything behind a required review or branch protection. Claude also stops and asks when the same finding is still open on three tested commits in a row (the first try and two fix attempts; more rounds on one commit count once, so recording the same failure again does not stop), after five failed rounds in a row, when the judge loop is waiting for you, and when a test needs a decision the criteria do not settle. A stuck loop shows in `ship.py status` and blocks `ship.py merge` until you decide.

To turn self-merging off for a project, put this line in its `CLAUDE.md`:

```text
Merges: ask first
```

The same line in `~/.claude/CLAUDE.md` turns it off everywhere, and so does `PIPELINEKIT_MERGE` in the environment with any non-empty value but `auto`. Claude then asks before it merges. The line counts on its own line, also as a list or task item, a heading, a table cell or two cells of a row (`| Merges | ask first |`), in bold, as a block quote, in quotation marks (`"Merges: ask first"`), in backticks or inside an HTML comment. `Merging: ask first`, `Merges - ask first`, `Merges: always ask first`, `Merges: never`, `Merges: off` and `Merges: manual` count as the same line. A sentence that starts with the line counts too (`Merges: ask first is what we want.`): when in doubt, the helper asks. A sentence that only mentions it further on does not. The `CLAUDE.md` on the base branch counts as well, so a branch cannot drop the line for its own pull request.

Test reports and screenshots go to `docs/uat/` in the project. That directory is local: `ship.py prepare` adds it to `.git/info/exclude` before the test starts, so `git status` does not list the reports (`ship.py record` adds it too), and it is on the never-stage list. `ship.py status` and `ship.py merge --dry-run` change nothing in the repository. The kit does not install Playwright; `/kit` reports whether `gh` and Playwright are available.

```bash
python3 ~/.claude/skills/ship/ship.py status           # every gate, with the reason
python3 ~/.claude/skills/ship/ship.py prepare          # keep docs/uat/ out of git, print the report paths
python3 ~/.claude/skills/ship/ship.py merge --dry-run  # what would be merged, and how
```

Exit code 0 means done, 1 means a gate or a check failed, 2 means the helper could not run, 3 means stop and ask.

