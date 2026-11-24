---
diataxis: reference
---

# Skills and agents

This page lists the skills and agents that pipelinekit v0.1.0 installs, and how the judge loop uses them.

## Skills

| Skill | Use it for |
|-------|------------|
| `dotnet-conventions` | .NET layering, DI, EF Core migrations, testing (FluentAssertions 7.x pin), BackgroundService rules, target-framework support dates, plus ASP.NET Core security in `references/security.md` |
| `deploy` | Router for Vercel, Railway, Render, DigitalOcean App Platform and Azure (Container Apps, App Service): auth check, deploy, secrets without argv, verify, logs, rollback, and trading-bot overlap. Per-provider detail in `references/`. If a CLI is missing or not logged in, it stops and asks you |
| `exchange-api-keys` | Exchange API keys for CryptoBargain and FundingRateArb: where they load from, never logging them, testnet vs mainnet, withdrawal-disabled and IP-restricted scopes, storage, rotation, leak runbook |
| `docs-writer` | Render `docs-source/*.md` into self-contained HTML pages under `documentation/` with `render.py` and `template.html`, with optional data-driven interactive snippets |
| `frontend-design` | Visual design guidance: aesthetic direction, typography, layout and copy, loaded before building or reshaping anything a person looks at (app or site UI, HTML pages and Artifacts, `docs-writer` snippets, charts and dashboards). Vendored unchanged from [`anthropics/skills`](https://github.com/anthropics/skills) (`skills/frontend-design` at a pinned commit) under the Apache License 2.0; `SOURCE.md` in its folder records the commit, the checksums and how to move to a newer one. The rest of the kit is MIT |
| `mobile` | Android (Kotlin/Compose) builds and device access from WSL2, iPhone home-screen web apps, Expo/EAS cloud builds for iOS, release and security checklist |
| `kit` | Self-check, run as `/kit`: reports missing or changed kit files, kit files over the file size limit, hooks that no longer block or allow what they should, kit entries missing from `settings.json`, environment conflicts, what the hooks blocked or failed on in the last days, and whether a newer kit is available. `/kit update` applies it after asking |
| `ship` | Run as `/ship`: Claude finishes the pull requests it opens. A fresh agent acceptance-tests the change against the issue's criteria, findings are fixed and tested again, then `ship.py` merges once every gate holds (own pull request, not a release, linked issues, no required review, a judged build, a passed test for exactly this commit, green CI). A project opts out with `Merges: ask first` in its `CLAUDE.md` |
| `judge-loop` | Run as `/judge-loop`: plans and builds a change on Opus, and has fresh Fable judges score the plan and the build until each gets 10 out of 10, within a round budget. See [Plan, build, judge](#plan-build-judge). Its record lives in `docs/loops/` of the one checkout it runs in and is never committed; see [The judge loop](installation.html#the-judge-loop). |

### What the skills run without asking

A skill's `allowed-tools` line lets Claude run the commands it names without a permission prompt, during the turn that started the skill. The `kit` and `ship` skills name their helper by the folder Claude Code loaded the skill from (`${CLAUDE_SKILL_DIR}`), which is `~/.claude/skills/<skill>` after a default install and `$CLAUDE_HOME/skills/<skill>` after an install into another home. The table shows the paths of a default install.

| Skill | Runs without asking |
|-------|---------------------|
| `kit` | `python3 ~/.claude/skills/kit/check.py`, with any of its options; `python3 ~/.claude/skills/kit/update.py plan`, with nothing after it. `update.py apply` asks |
| `ship` | `python3 ~/.claude/skills/ship/ship.py`, with any of its commands (`merge` included); `python3 ~/.claude/skills/judge-loop/loop.py`, with any of its commands |
| `judge-loop` | `python3 ~/.claude/skills/judge-loop/loop.py`, with any of its commands |
| `docs-writer` | `python3 ~/.claude/skills/docs-writer/render.py`, `verify_toc.py` and `richness_check.py` in that folder, with any of their options; `bash ~/.claude/skills/docs-writer/tests/test_render.sh` and `tests/test_richness_threshold.sh`, with nothing after them; the `Read`, `Write`, `Edit`, `Glob` and `Grep` tools. Any other Bash command asks |

A rule matches the command as written. A script of the same name anywhere else, such as `x/skills/kit/check.py` inside a project, asks, and so does the helper started another way: by a relative path, through `python3 -m`, or after `&&` behind another command that asks. For `loop.py` in another home the installer writes that home's path into the `judge-loop` and `ship` skills; a home whose path holds a space or other characters a rule cannot hold keeps `~/.claude`, and the installer warns.

In 0.1.0, `deploy` replaces the five separate `*-ops` skills and the per-provider deployment agents, `mobile` replaces `expo` and `ios`, and the ASP.NET Core security rules moved into `dotnet-conventions`.

## Agents

Three subagents for planning a change, building it and judging the result, each on the model that suits the job. The installer copies them from `claude/agents/` to `~/.claude/agents/`.

Together they are the parts of a judge loop: one agent plans, one builds, and independent judges score the result until it reaches 10. The `judge-loop` skill starts them; see [Plan, build, judge](#plan-build-judge).

| Agent | Model | Tools | What it is for |
|-------|-------|-------|----------------|
| `kit-planner` | `opus` | `Read, Grep, Glob, Write, Edit` | Writes or fixes `plan.md` in a loop folder from the request, `criteria.md` and the answers in `questions.md`. Cites `file:line` for every claim about the code and appends open questions to `questions.md` instead of guessing, and adds a row to `changes.md` for each judge item it fixes. Never edits code and never runs `loop.py` |
| `kit-builder` | `opus` | the session's tools | Builds the plan it is handed on the checked-out work branch, failing test first, runs the project's checks and commits; fixes the judge items it is given and nothing else, with a row in `changes.md` for each. Never creates or switches a branch, never pushes or deploys, and under `docs/loops/` writes only the rows of `changes.md` |
| `kit-judge` | `fable` | `Read, Grep, Glob` | Judges a plan or a build from one angle and answers with one JSON object: a score from 0 to 10, scores per dimension, blocking items and improvements, each with evidence, a fix and the check that proves the fix, and whether it read the work in full. Reads only what its brief names, and never runs, writes, commits, pushes or deploys anything |

`fable` and `opus` are aliases: they follow the newest model of each family. Only the judge runs on Fable, so the model that writes a plan or a build never scores it and Fable is spent on judging alone. All three treat text in the other files they read as data, not instructions (the planner and the builder follow their brief and the files it names), and never read `.env` files, credentials, keys or tokens.

All three work the same way: a file they change or judge is read whole, once; for one fact they search first and read only those lines; nothing is read twice; tool output stays short; after about 10 calls on the same error they stop and report it. Given a JSON form they return only the form, otherwise at most 15 lines.

The kit owns these three names in `~/.claude/agents/`, and leaves the rest of the folder alone. A file of your own with one of the names that differs from the kit's is moved to `~/.claude/pipelinekit/backup/agents-<name>-<timestamp>` once, and the installer prints where; a link of that name is removed without touching its target. Claude Code loads agents when a session starts, so start a new session after an install.

## Plan, build, judge

The template's "Plan, build, judge" section makes this the rule for every change that is more than a small fix. Run `/judge-loop` (or let Claude start it): `kit-planner` writes the plan, fresh `kit-judge` agents score it, `kit-builder` builds the judged plan, and fresh judges score the build. `/judge-loop plan` and `/judge-loop build` start one loop only, and `/judge-loop status` shows where a loop stands. Each judge answers with a score from 0 to 10 and the items that keep it from a 10; the planner or the builder fixes the items between two rounds, until every judge gives 10 with nothing blocking, within a budget of five rounds for the plan and five for the build. What is left after the last round becomes follow-up issues, or a list in the closing report without a GitHub remote. With a blocking item left, or a plan whose score stops rising, Claude stops and asks you, with options. You can say at any time to take the work as it is or to end the loop. Open questions are asked in one batch, and the session says in one line what a loop is expected to cost.

The helper `claude/skills/judge-loop/loop.py` keeps the state of a loop and says what comes next; the session runs it, never an agent. The size of the change decides the panel:

| Size | Test | Judges |
|------|------|--------|
| Exempt | One file with at most ten changed lines, or documentation files only, or a question; never a sensitive path | None: `loop.py skip` records it |
| One judge | Everything else below the next row | `general` |
| Full panel | More than 400 changed lines, more than 15 files, or a sensitive path (workflows, auth, payments, migrations, hooks, deploy, install, secrets, permissions, and steering files such as `CLAUDE.md`, `SKILL.md` and anything under `.claude/`, `agents/` or `skills/`) | `correctness`, `tests`, `security`, `scope`, `operations`, `user-experience` |

Each judge reads its role file in `claude/skills/judge-loop/roles/`: what it looks at, its dimensions and what a 10 means. Its answer is one JSON object (`overall`, `dimensions`, `blocking`, `improvements`, `still_open`, `read`), each item with evidence, a fix and the check that proves the fix. The score is 10 minus named items, in steps of 0.5, and a 10 counts only when the judge says it read the whole work. The first round of a build, and a round after the base moved, give every judge a full read; the base counts as moved only when the merge-base with the base branch moved, so a commit on the base branch that is not merged into the work branch does not bring one. Every role lists a hand-written file of code, tests or markdown that the work creates or makes longer, and that is then over 1,500 lines or 50,000 bytes, as an item.

A project sets its own terms with one of these lines, on a line of its own:

| Line | Effect |
|------|--------|
| `Judge loop: off` | No loop, no agents, nothing recorded |
| `Judge rounds: N` | The round budget of a plan and of a build, 1 to 20 (5 by default) |
| `Judges: correctness, tests` | The roles of the panel, from the seven above |

A line counts in the project's `CLAUDE.md` or `.claude/CLAUDE.md` once it is on the base branch (the branch pull requests go to), and in `~/.claude/CLAUDE.md`; the first one found wins, in that order. A line only in your checkout is named and not used. The installer replaces `~/.claude/CLAUDE.md` after a backup, so a line there lasts until the next install; when the file it replaces held one, the installer names the line and the backup.

The record of a loop lies in `docs/loops/<name>/plan/` and `docs/loops/<branch>/build/` of the checkout it runs in (a build loop is always named after its branch, with `/` turned into `-`, and its state names the plan loop it came from): `criteria.md`, `plan.md` and its judged copies, `questions.md`, the judges' answers, `scorecard.md` (one line per round, with the scores and the tokens), `changes.md` (one row per item: fixed, answered or owner), `settled.md`, `map.md` with one notes file per area in `areas/<name>.md`, and the files `loop.py leftovers --dir` writes to `leftovers/` (one per item, and `leftovers/all.md`). `docs/loops/` is on the never-stage list. A build in another worktree needs the plan loop's folder copied there first. Nothing removes old loop folders: delete one once its work is merged.

Limits: the record says that results were saved, not that a judge ran or judged well; it is a local file the session can write or remove. `accept`, `settle` and `skip` rest on the session's word. A judge's full read cannot be proven, only stated. The panel and the size are taken once, when the loop starts. The loop needs both a Fable and an Opus model; an account without one sets `Judge loop: off`. Where a session does not show the kit agents, the skill starts general-purpose agents with the same models and the installed agent text (`--agents fallback`), and `loop.py start` prints "fallback: the judge is not limited to reading by its tools": the judge's read-only rule then rests on its role text alone.

