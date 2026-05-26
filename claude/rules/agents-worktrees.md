---
description: Detailed rules for agent management, worktree isolation, and merge protocol. Loads only when working inside Claude config tree or a project with one.
paths:
  - "**/.claude/**"
---

# Agent & Worktree Rules (Detailed)

## Subagent Defaults

子代理透過 `Agent` 工具派送為任何非瑣碎工作的預設執行模式，無需觸發關鍵字。每次提示由 `claude/hooks/subagent-first-nudge.sh` (UserPromptSubmit) 強化，除非提示含明確退出短語。

常見派送形態（皆預設子代理——列舉供參，非門控標準）：

- **Multi-feature batches**: "process features 7–11", "batch A", "parallel streams", "5 at a time" → one subagent per feature, ALL dispatched in a single message so they run concurrently.
- **Autonomous runs**: "overnight", "while I sleep", "don't pause", "don't ask for confirmation", "target 10 AM", `--auto` flag → main session orchestrates and never blocks on a single feature's implementation.
- **Independent investigations**: "audit X", "find all Y", "where is Z used" → dispatch `Explore` or `general-purpose` with the scoped question; do not grep inline if the answer needs > 3 queries.
- **Long-running phases**: any implement-plan / review phase with > 5 tasks or > 2k LOC diff → dispatch via `/pipeline` Phase Mode `subagent` (default for new features per `~/.claude/rules/workflow.md § Phase Mode Precedence`).

Inline execution is the EXCEPTION, reserved for:
- **Trivial one-shots** under ~3 tool calls where dispatch overhead exceeds the work itself (e.g. read one file, edit one line, run one test).
- **Interactive Q&A** with the user actively present and watching (turn-by-turn pairing).
- **Per-prompt opt-out** via these literal phrases: `no subagents`, `no agents`, `do it inline`, `inline mode`, `do it yourself`, `skip subagents`, `skip agents`, `no dispatch`, `don't dispatch`. The nudge hook detects these and emits an opt-out notice instead of the default-mode banner.

**Kill switch.** Export `PIPELINE_NO_SUBAGENT_NUDGE=1` to silence the nudge entirely for a session — the default-mode rule still applies, but the hook stops injecting reminders.

**Self-correction rule.** 用戶若須說「用子代理」或「確保繼續用子代理」，先前派送決策有誤。即刻切換派送模式處理剩餘工作，勿以「禮貌」完成當前 inline 步驟——捨棄（或留給子代理接手）並派送。

**Parallelism reminder.** 單條消息中多個獨立子代理並行運行。跨五輪循序呼叫 `Agent` 五次會使其串行，喪失並行性。打包至一條消息。

## Skill Isolation
Skills that write code should use `context: fork` in SKILL.md frontmatter. For parallel skill execution touching different files, combine `context: fork` with `isolation: "worktree"`.

## Worktree Agent Prompt Requirement
每個工作樹代理提示必須逐字包含以下指令：
> Before reporting done: stage all your changes and commit with message `wip: [stream description]`. If a pre-commit hook fails, fix the issue and retry the commit. Do NOT report done without a successful commit — uncommitted worktree changes are lost on cleanup.

## Cross-Worker Scratchpad
每個並行階段下的工作樹代理提示亦須包含暫存契約：
> Shared scratchpad: `<absolute path to .claude/scratchpad/<phase-id>/>`. If you discover something a sibling stream needs to know (shared utility, conflicting assumption, upstream dependency), drop a note there named `<your-stream>-to-<sibling-stream>.md` — small plain-text (<5KB). Before you report done, read any `*-to-<your-stream>.md` files left by siblings. Do not put file contents in the scratchpad — notes only.

暫存位於 `.claude/scratchpad/<phase-id>/`，透過 `.git/info/exclude` 排除於 git 外。所有串流完成後，主導在合併提交上下文中浮現所有 `*-to-*.md` 文件，然後在成功合併後刪除暫存。合併失敗時，暫存保留以供事後分析。

## Worktree Lifecycle

互動式工作樹創建使用原生 Claude Code `EnterWorktree` / `ExitWorktree` 工具（Claude CLI `>= v2.1.72`）。`EnterWorktree` 在 `$HOME/.claude/worktrees/<branch>` 下創建工作樹並將 harness 切換其中；`ExitWorktree` 返回來源 repo 而不刪除工作樹（主導可按 § Lead Merge Protocol squash 合併）。Claude CLI `< v2.1.72` 時，回退至手動 `git worktree add`——相同 `$HOME/.claude/worktrees/<branch>` 路徑規範適用以使 `verify-worktree-commit.sh` 繼續觸發。子程序模式驅動器（未隨此疊加層交付）亦使用手動 `git worktree add`，因其無 Claude harness 可派送工具呼叫。

Lifecycle rules (apply to both native-tool and manual paths):
- Zero changes = auto-removed by Claude Code
- Uncommitted changes = persist (lead controls lifecycle)
- Agent finishes without committing = worktree directory exists until removed (recovery window)
- The commit instruction prevents needing recovery

## Env handoff via `.worktreeinclude`

工作者提示不再需要內聯 env 複製樣板。工作樹創建讀取 `.worktreeinclude`（從 repo 根模板 `.worktreeinclude.template` 解析），並將各匹配路徑從來源 repo 綁定掛載至新工作樹相同相對路徑。綁定掛載不可用時（無 WSL2 掛載共享的 Windows 主機，或拒絕綁定的文件系統），機制回退至各匹配路徑的 `cp -p`。

**Opt-in flow:**
1. Copy `.worktreeinclude.template` (committed at repo root) to `.worktreeinclude`.
2. Edit `.worktreeinclude` to declare the env/secret paths your worktree agents need.
3. The next worktree-creation step picks it up automatically.

**Hook composition.** 已解析的 `.worktreeinclude` 列出機密路徑（通常為 `.env`, `credentials*`）。現有 `block-stage-sensitive.sh` 鉤子（由 `claude/config/never-stage.txt` 驅動）已在工作樹內拒絕暫存這些路徑，因此機密內容的意外提交在與主 repo 相同的門控處被阻止。

**Why not in worker prompts.** 將 env 複製命令放在工作者提示中意味著每個提示必須枚舉機密路徑——脆弱且易遺忘。`.worktreeinclude` 機制將列表集中於每個 repo 的一個文件中。

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
- The XML must be the **last** content in the response so the lead can parse unambiguously (regex finds `<task-notification>...</task-notification>` at the tail).
- File list capped at 50 entries; excess summarized as `<files count="N"><file>...</file><more>N-50</more></files>`.
- Do not embed file contents — paths only.
- Agents that fail to emit the XML are still accepted, but the lead logs: "worker X did not emit task-notification — falling back to free-form parsing."

## Lead Merge Protocol
所有工作樹代理完成後：
1. Parse the `<task-notification>` block from each worker's final response. Log stream names, statuses, and file lists. If a worker did not emit the block, log "worker X did not emit task-notification — falling back to free-form parsing" and continue.
2. Check each worktree branch has commits: `git log worktree-branch --oneline -5`
3. No commits? Check if worktree dir still exists: `ls .claude/worktrees/`. Copy/cherry-pick changes before cleanup.
4. **Squash-merge** into working branch: `git merge --squash worktree-branch` then commit with a clean conventional message. Never use `--no-ff` — it preserves `wip:` commits on the target branch.
5. Run `build && test` after all merges
6. Resolve conflicts (zero file overlap should prevent this)
7. Clean up only after successful merge + test: `git branch -d worktree-agent-*` + `rm -rf .claude/worktrees/agent-*`

## Commit Message Hygiene (No AI Traces)
特性分支與 main 上的提交消息絕不洩露 AI 工作流。具體而言：
- **Never use:** `wip:`, `stream A/B/C/D/E`, `parallel streams`, `review-vN`, `apply review`, `N findings`, `merge: stream`, `across N streams`
- **Squash worktree commits** into one clean conventional commit per stream (e.g. `fix: harden execution engine close pipeline`)
- **Feature branch → main merges** use a single descriptive message. No bullet-point lists of findings or stream names.
- **Review iteration commits** use generic language: `fix: address code review feedback` — no version numbers, no finding counts, no stream references.
- Think: "Would a human developer write this commit message?" If not, rewrite it.

## Agent Team Failure Recovery
- Teammate fails or stuck: redirect via Shift+Down
- Two teammates claim same task: lead resolves via mid-flight steering
- One blocks on another: lead provides needed info directly

## Post-Parallel Evaluation
並行子代理運行完成後，詢問：
- Did any agent fail and need rerunning?
- Were there merge conflicts?
- Did streams need info from each other?
- Was one stream blocked on another's output?
If yes to any, suggest agent teams for the next similar parallel task.

## Plans with Parallel Work
Plans with parallel agent work (streams/teammates) MUST produce BOTH files:
- The plan file (docs/plan.md or docs/plan-vN.md)
- A prompts file (docs/prompts.md) with discrete teammate prompt blocks
Never embed teammate instructions as prose in the plan.
