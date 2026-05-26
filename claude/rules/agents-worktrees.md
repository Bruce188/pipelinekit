---
description: Detailed rules for agent management, worktree isolation, and merge protocol. Loads only when working inside Claude config tree or a project with one.
paths:
  - "**/.claude/**"
---

# Agent & Worktree Rules (Detailed)

## Subagent Defaults

子代理透過 `Agent` 工具派送為非瑣碎工作預設模式。每提示由 `claude/hooks/subagent-first-nudge.sh` (UserPromptSubmit) 強化，除非含退出短語。

常見派送形態：

- **Multi-feature batches**: "process features 7–11", "batch A", "5 at a time" → one subagent per feature, ALL dispatched in a single message so they run concurrently.
- **Autonomous runs**: "overnight", "while I sleep", "don't pause", "don't ask for confirmation", `--auto` → main orchestrates; never blocks on a single feature.
- **Independent investigations**: "audit X", "find all Y", "where is Z used" → dispatch `Explore` or `general-purpose`; do not grep inline if answer needs > 3 queries.
- **Long-running phases**: implement-plan / review with > 5 tasks or > 2k LOC → dispatch via `/pipeline` Phase Mode `subagent` (default per `~/.claude/rules/workflow.md § Phase Mode Precedence`).

Inline execution is the EXCEPTION, reserved for:
- **Trivial one-shots** under ~3 tool calls (read one file, edit one line, run one test).
- **Interactive Q&A** with the user present.
- **Per-prompt opt-out** via literal phrases: `no subagents`, `no agents`, `do it inline`, `inline mode`, `do it yourself`, `skip subagents`, `skip agents`, `no dispatch`, `don't dispatch`. Hook emits opt-out notice instead of default banner.

**Kill switch.** Export `PIPELINE_NO_SUBAGENT_NUDGE=1` to silence the nudge for a session — default-mode still applies; hook stops reminders.

**Self-correction rule.** 用戶若須說「用子代理」，先前決策有誤。即刻切換派送，勿以禮貌完成 inline 步驟——捨棄並派送。

**Parallelism reminder.** 單消息中多獨立子代理並行。跨五輪循序呼叫 `Agent` 五次會串行。打包至一條消息。

### Typed-subagent selection rule

Each dispatch MUST set `subagent_type` to the most specific matching agent. `general-purpose` is the legitimate fallback only when no specialist applies OR when a specialist explicitly fails (e.g. namespace collision); the fallback reason MUST be named in the dispatch prompt or surrounding narrative.

<!-- inventory parity: rows below must cover every entry in `ls claude/agents/*.md` (minus meta files CLAUDE.md / INDEX.md / NOTICE.md / README.md). When agents are added or removed, update both this table and the agents/ dir in the same commit. -->

| Task kind | `subagent_type` |
|-----------|-----------------|
| Code review against the diff | `code-reviewer` |
| Security audit / secret scan | `security-auditor` |
| Test-coverage analysis / new test authoring | `test-engineer` |
| Performance tuning / hot-path profiling | `performance-tuner` |
| Spec / requirements traceability | `spec-tracer` |
| Symbol / cross-file ref verification | `symbol-verifier` |
| Stack-trace triage / runtime debugging | `debugger` |
| Refactor / structural code reshape | `refactor-expert` |
| TDD red-phase test authoring | `tdd-test-writer` |
| TDD green-phase implementation | `tdd-implementer` |
| Docs authoring / changelog drafting | `docs-writer` |
| iOS / Expo mobile-app work | `mobile-dev` |
| Cloud deploy (Azure, Vercel, Railway, Render, DigitalOcean) | `deployment-engineer` (per-provider variants exist: `azure-deployment-engineer`, `vercel-deployment-engineer`, `railway-deployment-engineer`, `render-deployment-engineer`, `digitalocean-deployment-engineer`) |
| Live production smoke probe | `production-probe` |
| Incident response / outage triage | `incident-responder` |
| CLAUDE.md guardrail checks | `claude-md-guardian` |
| Read-only file/symbol exploration | `Explore` (built-in) |
| Plan-mode dry run | `Plan` (built-in) |
| Catch-all (no specialist matches) | `general-purpose` (built-in) — WITH justification |

### Anti-patterns — general-purpose default observations

Future contributors: pattern-match against these prior drift episodes.

- **F14 (subagent_type omission → silent general-purpose):** dispatched `Agent` calls without naming `subagent_type` defaulted to `general-purpose`; specialist context (e.g. `code-reviewer` rubric) never loaded. Symptom: review-phase panels produced generic findings without the panel-specific rubric.
- **F19 (review-teams bundle dispatched as one general-purpose call):** the 5-panel `--teams` review path collapsed onto a single `general-purpose` subagent rather than 5 named-specialist dispatches in one turn. Root cause: prose-only typed-dispatch contract; no enforcement at the dispatch boundary.
- **F20 (specialist-name collision → general-purpose substitution):** a typed-name resolution failure fell back to `general-purpose` silently. The fallback was correct, but the absence of a named justification in the dispatch prompt made the fallback invisible to reviewers, recurring as a regression two iterations later.

## Skill Isolation
Skills writing code should use `context: fork` in SKILL.md frontmatter. For parallel skill execution on different files, combine `context: fork` with `isolation: "worktree"`.

## Worktree Agent Prompt Requirement
每工作樹代理提示必須逐字含：
> Before reporting done: stage all your changes and commit with message `wip: [stream description]`. If a pre-commit hook fails, fix the issue and retry the commit. Do NOT report done without a successful commit — uncommitted worktree changes are lost on cleanup.

## Cross-Worker Scratchpad
每並行階段下的工作樹代理亦含暫存契約：
> Shared scratchpad: `<absolute path to .claude/scratchpad/<phase-id>/>`. If you discover something a sibling stream needs to know (shared utility, conflicting assumption, upstream dependency), drop a note there named `<your-stream>-to-<sibling-stream>.md` — small plain-text (<5KB). Before you report done, read any `*-to-<your-stream>.md` files left by siblings. Do not put file contents in the scratchpad — notes only.

暫存於 `.claude/scratchpad/<phase-id>/`，經 `.git/info/exclude` 排除。串流完成後主導於合併上下文中浮現所有 `*-to-*.md`，成功合併後刪除。失敗時保留供事後分析。

## Worktree Lifecycle

互動式工作樹用原生 `EnterWorktree` / `ExitWorktree`（Claude CLI `>= v2.1.72`）。`EnterWorktree` 於 `$HOME/.claude/worktrees/<branch>` 創建並切換 harness；`ExitWorktree` 返回 repo 不刪工作樹（主導按 § Lead Merge Protocol squash 合併）。CLI `< v2.1.72` 時回退手動 `git worktree add`——同 `$HOME/.claude/worktrees/<branch>` 規範以使 `verify-worktree-commit.sh` 觸發。子程序模式驅動器（未交付）亦用手動 `git worktree add`。

Lifecycle rules:
- Zero changes = auto-removed by Claude Code
- Uncommitted changes = persist (lead controls lifecycle)
- Agent finishes without committing = worktree dir exists until removed (recovery window)
- The commit instruction prevents needing recovery

## Env handoff via `.worktreeinclude`

工作者提示不再需內聯 env 複製樣板。工作樹創建讀 `.worktreeinclude`（從 `.worktreeinclude.template` 解析），將各匹配路徑從來源 repo 綁定掛載至新工作樹相同相對路徑。綁定掛載不可用時（無 WSL2 共享的 Windows 主機，或拒綁定的文件系統），回退至 `cp -p`。

**Opt-in flow:**
1. Copy `.worktreeinclude.template` (committed at repo root) to `.worktreeinclude`.
2. Edit `.worktreeinclude` to declare env/secret paths your worktree agents need.
3. Next worktree-creation step picks it up automatically.

**Hook composition.** 已解析 `.worktreeinclude` 列出機密路徑（通常 `.env`, `credentials*`）。現有 `block-stage-sensitive.sh` 鉤子（由 `claude/config/never-stage.txt` 驅動）已於工作樹內拒暫存，意外提交在同門控被阻。

**Why not in worker prompts.** 將 env 複製入提示意味每提示須枚舉機密——脆且易忘。`.worktreeinclude` 集中。

## Worktree Agent Task-Notification XML
Per NETMIND Part 1 §6.2, Claude Code uses a `<task-notification>` XML block to report worker results back to the coordinator. Every worktree agent's final response MUST end with a block in this format:

```xml
<task-notification>
  <task-id>[stream or task name]</task-id>
  <status>completed|failed|blocked</status>
  <summary>1-3 sentence summary of what was done (or why it failed).</summary>
  <files>
    <file>path/one.ext</file>
    <file>path/two.ext</file>
  </files>
  <usage>
    <total_tokens>[if available, else omit]</total_tokens>
    <tool_uses>[if available, else omit]</tool_uses>
  </usage>
</task-notification>
```

Rules:
- XML must be **last** content so lead parses unambiguously (regex finds `<task-notification>...</task-notification>` at tail).
- File list capped at 50 entries; excess summarized as `<files count="N"><file>...</file><more>N-50</more></files>`.
- Do not embed file contents — paths only.
- Agents failing to emit XML still accepted; lead logs: "worker X did not emit task-notification — falling back to free-form parsing."

## Lead Merge Protocol
工作樹代理完成後：
1. Parse `<task-notification>` block from each worker's final response. Log stream names, statuses, files. If missing, log "worker X did not emit task-notification — falling back to free-form parsing" and continue.
2. Check each worktree branch has commits: `git log worktree-branch --oneline -5`
3. No commits? Check worktree dir still exists: `ls .claude/worktrees/`. Copy/cherry-pick before cleanup.
4. **Squash-merge** into working branch: `git merge --squash worktree-branch` then commit with clean conventional message. Never use `--no-ff` — it preserves `wip:` commits on target branch.
5. Run `build && test` after all merges
6. Resolve conflicts (zero file overlap should prevent this)
7. Clean up only after successful merge + test: `git branch -d worktree-agent-*` + `rm -rf .claude/worktrees/agent-*`

## Commit Message Hygiene (No AI Traces)
特性分支與 main 提交絕不洩露 AI 工作流：
- **Never use:** `wip:`, `stream A/B/C/D/E`, `parallel streams`, `review-vN`, `apply review`, `N findings`, `merge: stream`, `across N streams`
- **Squash worktree commits** into one clean conventional commit per stream (e.g. `fix: harden execution engine close pipeline`)
- **Feature branch → main merges** use single descriptive message. No bullet lists of findings or stream names.
- **Review iteration commits** use generic language: `fix: address code review feedback` — no version numbers, no finding counts, no stream refs.
- Think: "Would a human developer write this?" If not, rewrite.

## Agent Team Failure Recovery
- Teammate fails or stuck: redirect via Shift+Down
- Two teammates claim same task: lead resolves via mid-flight steering
- One blocks on another: lead provides needed info directly

## Post-Parallel Evaluation
並行子代理運行後問：
- Did any agent fail and need rerunning?
- Were there merge conflicts?
- Did streams need info from each other?
- Was one stream blocked on another's output?
If yes, suggest agent teams next time.

## Plans with Parallel Work
Plans with parallel agent work (streams/teammates) MUST produce BOTH files:
- The plan file (docs/plan.md or docs/plan-vN.md)
- A prompts file (docs/prompts.md) with discrete teammate prompt blocks
Never embed teammate instructions as prose in the plan.
