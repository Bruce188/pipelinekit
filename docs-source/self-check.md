---
diataxis: reference
---

# Self-check

`/kit` answers one question: is anything in this install not working? Run it after installing or updating the kit, and when a hook blocks something you did not expect or fails to start. Claude can also run it on its own when a kit hook misbehaves.

## What is checked

| Section | What is checked |
|---------|-----------------|
| Install | Every hook, the event-log helper, the file size check, git hook, skill and agent is present; `kit-judge.md` has the one tools line `Read, Grep, Glob`, else `kit-judge.md allows more than reading`; hooks are executable and have LF line endings; a skill helper that lost its executable bit (`ship.py`, `check.py`, `loop.py`) is a `[warn]` with the `chmod +x` that fixes it, since the skills run them through `python3`; `settings.json` is valid, its hook commands point to files that exist, attribution is off and the secret deny rules are there; the global `core.hooksPath`. A kit file over the file size limit (1,500 lines or 50,000 bytes) is a `[warn]`; the vendored `frontend-design` skill and the files the limit exempts by default are left out, and `--quick` skips this |
| Changes since install | Each installed file, the agent files included, against the hash recorded at install time; the kit's hook entries and deny/ask rules in `settings.json` |
| Live probe | Each hook gets input it must block and input it must allow: `git commit --no-verify`, a `docker` mount of `/etc`, `curl` piped into `sh`, `DROP TABLE` through `psql`, a `HEAD` file next to `refs/`, a non-conventional commit message, a commit that adds a file over the file size limit (to `pre-commit` and to `pre-merge-commit`), a push to `main`. The session-start check must report an install with nothing in it and say nothing about this one. Each refusal must also arrive in an event log, which the probe keeps in a temporary directory |
| Environment | python3, Claude Code and gitleaks versions; whether `gh` and Playwright are available; a `gh`, `claude` or `gitleaks` that fails on `--version` is a `[warn]`, and its output is not shown as a version; WSL; a repository that sets its own `core.hooksPath`; a Bash sandbox that keeps `gh` from reading its own login file; a `frontend-design` plugin enabled next to the kit's copy, as an `[info]` line that says how to keep one. Only the user-level `settings.json` is read, so a plugin enabled in one project's settings is not reported |
| Updates | Whether the remote of the checkout the install was made from has commits this install lacks: `up to date`, `update available` or `not checked`. Information only, never a problem. Not part of `--quick` |
| Activity | What the kit's hooks did in the last 7 days, read from the event log: each rule that blocked, asked, was overridden or failed, with a count and the last time. The 20 newest rules are listed, and a hook that failed is listed however old it is. See [Rule ids and the event log](hooks.html#rule-ids-and-the-event-log). Not part of `--quick` |

A line is `[fail]` when a guard is missing or does the wrong thing, `[warn]` when something changed but still works (for example a skill file you edited) or a hook failed while it ran, and `[info]` for context. The report ends with `Result: healthy`, or with the number of problems and the command that repairs the install. The check itself changes nothing in `~/.claude`.

The report repeats a name from `settings.json` or the install manifest only when it reads as a plain name: a hook's file name, an event, a rule, a version, a branch. Anything else is counted and not quoted, so a line that sits in one of those files cannot show up as a line of the report. Characters that draw as nothing or change how a line reads are removed. A plain name can still spell a word, so read the report as a list of names, not as advice.

## When a session starts

The same check runs when a session starts. `session-check.py` is a SessionStart hook that runs `check.py --quick` on `startup` (not on resume or after `/clear`); it takes about 0.2 seconds. A healthy install, warnings included, gives no output. With a `[fail]` you get one line with the number of problems and no text from the report, and Claude is told the same:

```text
pipelinekit: 2 problems in this install. Run /kit for the report.
```

The hook never blocks a session. A check that takes longer than 4 seconds is dropped, together with anything it started, and shows up under Activity as `session-check.timeout`. `PIPELINEKIT_SESSION_CHECK=0` in the environment switches it off, and `/kit` then says so.

## Running it from a shell

The checker is `claude/skills/kit/check.py`, stdlib only. It also runs outside a session:

```bash
python3 ~/.claude/skills/kit/check.py            # full report, about a second
python3 ~/.claude/skills/kit/check.py --quick    # no live probes
python3 ~/.claude/skills/kit/check.py --verbose  # also list the checks that passed
python3 ~/.claude/skills/kit/check.py --json     # for scripts
python3 ~/.claude/skills/kit/check.py --days 30  # activity of the last 30 days (1 to 365)
python3 ~/.claude/skills/kit/check.py --session ID  # activity of one session
python3 ~/.claude/skills/kit/check.py --no-remote   # do not ask the remote for updates
```

Exit code 0 means healthy, 1 means problems were found, 2 means the checker itself failed. `scripts/verify.sh` runs the same file. The JSON output has an `activity` list with every rule, where the text report shows the 20 most recent, and an `update` object with the state of the update check.

The repository checks itself the same way. In CI the `install-smoke` job installs the kit into an empty home directory and expects a healthy report, then removes one hook and expects the report to name it. The whole workflow also runs every Monday at 05:17 UTC and can be started by hand (`gh workflow run CI`). A failed scheduled run opens the issue `Weekly self-check failed`, or adds a comment to it while it is open (`scripts/ci-report.sh`); close the issue once a run is green again. GitHub starts scheduled runs from the default branch only, and pauses them after 60 days without activity in the repository.

The comparison data is `~/.claude/pipelinekit/manifest.json`, which the installer writes: kit version and commit, the checkout path and branch, whether serena was registered, a SHA-256 of every installed file, and the `settings.json` entries the kit owns. An install made before this file existed reports `install manifest not found`; run the installer once.

## Updates

The Updates section compares the commit the install was made from with the same branch on `origin` of that checkout. It asks the remote at most once in 24 hours (`git ls-remote`, nothing is fetched), gives it 5 seconds and keeps the answer in `update.json` next to the event log. Offline, without the checkout, or when the install was made from a checkout on no branch, it says `not checked`. An available update is an `[info]` line and never changes the result. `PIPELINEKIT_UPDATE_CHECK=0` switches the check off; `--no-remote` uses only an answer it already has.

`/kit update` applies an update from inside a session:

1. `update.py plan` fetches the branch and lists the new commits, at most 30, each as one cleaned line. Nothing else changes.
2. Claude shows them and asks whether to update.
3. After a yes, `update.py apply --to <commit>` fast-forwards the checkout to exactly the commit the plan listed, runs the installer and then the self-check. Its last line is `Updated <old> -> <new>. Self-check: healthy.`, or the same line with the number of problems or warnings when the new version is installed and its check has something to say. When the installer fails, the last line starts with `Not updated:` or, when the files were already replaced, with `Partly updated`, and a line `By hand: <command>` above it holds the installer command to run again.

The installer runs with what was chosen at install time: the global git hooks stay on or off, and serena is not registered where it was skipped. The update is refused, and nothing changes, when the checkout has uncommitted changes, is on another branch or has commits the remote lacks, and when the remote moved after the plan. The same two commands work from a shell:

```bash
python3 ~/.claude/skills/kit/update.py plan              # what would change
python3 ~/.claude/skills/kit/update.py apply --to COMMIT # the full commit id the plan printed
```

## Sandbox and limits

The Environment section warns about one conflict that is easy to miss. When the Bash sandbox is on, a `Read` deny rule for the `gh` login file (`hosts.yml`) also applies to `gh` itself, so `gh` fails in sandboxed commands, and so does `git` over https when it asks `gh` for the token. The line names the fix: add `gh *` to `sandbox.excludedCommands` in `settings.json`, or run `gh` outside the sandbox.

Two things are outside its reach. A `permissions.deny` match, or a prompt you declined, leaves no trace to report: Activity lists only what the kit's own hooks did. And the report describes the environment it runs in: another WSL distro, an SSH host or a sandboxed session can differ, so run the check there.

