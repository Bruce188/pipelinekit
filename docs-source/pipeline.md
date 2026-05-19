# /pipeline

The /pipeline autonomous orchestrator: charter discovery, analyze, plan, implement, review, merge. Per-phase reference.

<div data-snippet="pipeline-phase-diagram"></div>

<h2 id="invocation">Invocation</h2>
<div class="codehilite"><pre><span></span><code>/pipeline                  # uses docs/features.md in current project
/pipeline path/to/features.md
/pipeline --plan           # ingest most recent ~/.claude/plans/*.md
/pipeline --from &quot;free text seed for feature generation&quot;
/pipeline --renew          # rebuild from deferred + failed features
/pipeline --max-usd 5      # halt at phase boundary if cumulative cost &gt; $5
/pipeline --max-turns 100  # halt at phase boundary if cumulative sub-agent turns &gt; 100
/pipeline --no-parallel    # force sequential implementation
</code></pre></div>

<h2 id="feature-file-docs-features-md">Feature file (<code>docs/features.md</code>)</h2>
<div class="codehilite"><pre><span></span><code><span class="gh"># Features</span>

<span class="gu">## feat/user-auth</span>
<span class="gs">**Description:**</span> Add session-based auth with email + password.
<span class="gs">**Constraints:**</span> Use bcrypt, do not break existing /api/me endpoint.
<span class="gs">**Acceptance Criteria:**</span>
<span class="k">1.</span> POST /api/login returns 200 + session cookie on valid creds
<span class="k">2.</span> POST /api/login returns 401 on invalid creds
<span class="k">3.</span> Existing /api/me continues to work

<span class="gu">## docs/onboarding-guide</span>
<span class="gs">**Description:**</span> Write <span class="sb">`documentation/onboarding.md`</span> for new contributors.
<span class="gs">**Constraints:**</span> Keep under 400 words.

<span class="gu">## chore/dep-bump</span>
<span class="gs">**Description:**</span> Bump express 4.18 → 4.19.
</code></pre></div>

<h2 id="tdd-routing-dev-vs-non-dev">TDD routing (dev vs non-dev)</h2>
<p>The pipeline derives a routing class from the feature's H2 prefix:</p>
<table>
<thead>
<tr>
<th>Prefix</th>
<th>Class</th>
<th>Implementation phase</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>feat</code>, <code>fix</code>, <code>refactor</code>, <code>perf</code>, <code>test</code></td>
<td><strong>dev</strong></td>
<td>tdd-test-writer → tdd-implementer (paired, context-isolated)</td>
</tr>
<tr>
<td><code>docs</code>, <code>chore</code>, <code>style</code>, <code>build</code>, <code>ci</code>, <code>content</code>, <code>ops</code>, <code>research</code></td>
<td><strong>non-dev</strong></td>
<td>Standard <code>implement-plan</code> Agent dispatch</td>
</tr>
</tbody>
</table>
<p>Override the auto-derivation with a per-feature line:</p>
<div class="codehilite"><pre><span></span><code><span class="gu">## chore/critical-migration</span>
<span class="gs">**Type:**</span> dev
<span class="gs">**Description:**</span> Behavior-critical migration; want TDD even though the prefix is chore.
</code></pre></div>

<p>Valid override values: <code>dev</code>, <code>non-dev</code>.</p>
<h2 id="phases">Phases</h2>
<p>Per feature, the pipeline runs:</p>
<ol>
<li><strong>Analyze</strong> — context-gather, key-file identification, MCP doc lookups</li>
<li><strong>Plan</strong> — task breakdown with parallel-execution annotations</li>
<li><strong>Branch</strong> — <code>/new-branch &lt;feature-name&gt;</code></li>
<li><strong>Implement</strong> — <code>dev</code> → TDD pair; <code>non-dev</code> → standard implement</li>
<li><strong>Review</strong> — multi-agent: code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer</li>
<li><strong>Path A / B / C</strong> — A: merge clean; B: fix findings (≤5 cycles); C: replan</li>
</ol>
<p>State persists in <code>docs/pipeline-state.md</code> per run. Resume by re-invoking <code>/pipeline</code>.</p>
<h2 id="charter-mode">Charter Mode</h2>
<p>Charter Mode is the default-on front-loaded alignment phase added in Step 0 of <code>/pipeline</code>. Before the pipeline processes features, it asks the user a structured set of questions to produce <code>docs/charter.md</code>. Downstream phases (<code>/analyze</code>, <code>/create-plan</code>, <code>/implement-plan</code>, <code>/review</code>, <code>/ppr</code>) read this charter to scope their work.</p>
<h3 id="when-it-runs">When it runs</h3>
<p>Step 0 runs by default on every interactive <code>/pipeline</code> invocation, unless one of the following opt-out conditions is met (checked in order):</p>
<ol>
<li><code>--no-charter</code> flag is present → skip entirely (legacy autonomous flow restored).</li>
<li><code>--charter &lt;path&gt;</code> flag is present → adopt the existing charter at <code>&lt;path&gt;</code>, skip discovery.</li>
<li><code>--max-questions 0</code> → treated as <code>--no-charter</code> (alias).</li>
<li><code>docs/charter.md</code> exists AND <code>progress.md</code> <code>**Charter:**</code> pointer is valid → skip (already chartered for this run).</li>
</ol>
<h3 id="opt-out-flags">Opt-out flags</h3>
<table>
<thead>
<tr>
<th>Flag</th>
<th>Effect</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>--no-charter</code></td>
<td>Skip Step 0; restore legacy autonomous behavior</td>
</tr>
<tr>
<td><code>--charter &lt;path&gt;</code></td>
<td>Adopt an existing charter file; skip discovery loop</td>
</tr>
<tr>
<td><code>--max-questions &lt;N&gt;</code></td>
<td>Cap total <code>AskUserQuestion</code> calls at <code>N</code>; <code>0</code> = <code>--no-charter</code> alias</td>
</tr>
</tbody>
</table>
<p><code>--no-charter</code> and <code>--charter</code> are mutually exclusive. Using both together stops the pipeline with: <code>ERROR: --no-charter and --charter are mutually exclusive.</code></p>
<p>Providing <code>--charter &lt;path&gt;</code> with a missing file stops the pipeline with: <code>ERROR: --charter path not found: &lt;path&gt;</code></p>
<h3 id="subprocess-mode-constraint">Subprocess-mode constraint</h3>
<p><strong><code>AskUserQuestion</code> is interactive-session-only.</strong> Charter Discovery cannot run inside a subprocess driver (<code>claude -p</code> or equivalent). If you re-introduce a subprocess driver in a fork:</p>
<ul>
<li>The driver MUST check for an existing charter before launching any phase.</li>
<li>If <code>docs/charter.md</code> is absent AND neither <code>--no-charter</code> nor <code>--charter &lt;path&gt;</code> is set, the driver MUST exit non-zero with:</li>
</ul>
<p><code>ERROR: subprocess mode cannot run Charter Discovery (AskUserQuestion is interactive-only). Run /pipeline interactively first, or pass --no-charter.</code></p>
<h3 id="charter-file-shape">Charter file shape</h3>
<p><code>docs/charter.md</code> contains 9 required sections (in order):</p>
<ol>
<li><strong>Goal</strong> — what the feature/iteration achieves</li>
<li><strong>Users</strong> — who it serves</li>
<li><strong>Problem</strong> — the pain being solved</li>
<li><strong>Success</strong> — measurable outcomes</li>
<li><strong>Non-Goals</strong> — explicit exclusions</li>
<li><strong>Constraints</strong> — hard technical or process limits</li>
<li><strong>MVP Boundary</strong> — what is "In" vs "Out" for this iteration</li>
<li><strong>Prior Art</strong> — existing work this relates to or supersedes</li>
<li><strong>Open Questions</strong> — unresolved items for future decisions</li>
</ol>
<p>Plus frontmatter (<code>version</code>, <code>created</code>, <code>status</code>) and an optional <strong>Decision Log</strong> table.</p>
<p>Versioning follows the same convention as <code>plan.md</code> and <code>analysis.md</code> — see <code>claude/rules/workflow.md</code> § Versioning Convention.</p>
<h3 id="how-downstream-phases-consume-the-charter">How downstream phases consume the charter</h3>
<table>
<thead>
<tr>
<th>Phase</th>
<th>Charter usage</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>/analyze</code></td>
<td>Scopes investigation to MVP Boundary; flags Non-Goal areas without deep traversal</td>
</tr>
<tr>
<td><code>/create-plan</code></td>
<td>Gates tasks against Non-Goals and MVP Boundary; defers out-of-scope items</td>
</tr>
<tr>
<td><code>/implement-plan</code></td>
<td>Prepends charter Goal + Constraints to each task subagent's context</td>
</tr>
<tr>
<td><code>/review</code></td>
<td>Classifies findings as in-scope or out-of-scope per charter; defers out-of-scope findings</td>
</tr>
<tr>
<td><code>/ppr</code></td>
<td>Derives PR <code>## Summary</code> opening line from charter Goal</td>
</tr>
</tbody>
</table>
<h2 id="relationship-to-native-goal">Relationship to native /goal</h2>
<p><code>/pipeline</code> charter goals and the native <code>/goal</code> feature coexist independently — they serve different lifecycle scopes and have no integration today.</p>
<p>Charter goals (written to <code>docs/charter.md</code> during Step 0 and referenced in <code>docs/pipeline-state.md</code>) are <strong>feature-bound</strong>: they persist across session restarts, survive <code>/compact</code> and context resets, and are re-evaluated once per pipeline phase by the phase subagent. Native <code>/goal</code> conditions are <strong>session-bound</strong>: the model re-evaluates the goal predicate on every turn, and the goal is lost when the session ends.</p>
<table>
<thead>
<tr>
<th>Use /pipeline charter goals when…</th>
<th>Use /goal when…</th>
</tr>
</thead>
<tbody>
<tr>
<td>Work spans multiple phases or sessions (feature-bound, multi-phase lifecycle)</td>
<td>Completion can be checked in the current session without persistence (session-bound, ephemeral)</td>
</tr>
<tr>
<td>Goal state must survive resume — stored in <code>docs/charter.md</code> and <code>docs/pipeline-state.md</code></td>
<td>Goal lives in-memory only — no on-disk artifact</td>
</tr>
<tr>
<td>Evaluation is structured per-phase with explicit Acceptance Criteria</td>
<td>Evaluation is a per-turn model self-check with no structured AC format</td>
</tr>
</tbody>
</table>
<p>F15 historically considered native <code>/goal</code> integration as a pipeline-level stop condition. The current integration surface is none — <code>/pipeline</code> charter goals and <code>/goal</code> coexist independently.</p>
<h2 id="documentation-update-phase">Documentation Update Phase</h2>
<p>After a feature's squash-merge passes the <strong>Post-Merge Verification Gate</strong>
(<code>claude/skills/pipeline/SKILL.md</code> § Post-Merge Verification Gate), the pipeline
runs a best-effort documentation update phase. The phase dispatches the
<code>docs-writer</code> subagent to read the merged diff and update files in <code>documentation/</code>
(the committed application-docs directory, distinct from <code>docs/</code> which is
workflow-only). The doc update lands as a separate <code>docs: &lt;feature description&gt;</code>
commit on the base branch — the merge commit stays clean.</p>
<p><strong>Execution order (Path A success):</strong>
1. Squash-merge lands on <code>$BASE</code>.
2. Post-merge cleanup + <code>git pull origin "$BASE"</code> (Path A step 7).
3. <strong>Post-Merge Verification Gate</strong> runs — on failure, revert; on success, append <code>POSTMERGE_OK: &lt;cmd&gt;</code>.
4. <strong>Documentation Update Phase</strong> — dispatches <code>docs-writer</code> via Agent tool; emits beacon <code>docs-pre</code> before dispatch and <code>docs-done</code> on success.
5. <strong>Step 5.9</strong> emits <code>feature-done</code>.</p>
<p><strong>Opt-out:</strong> Set <code>PIPELINE_SKIP_DOCS=1</code> to skip the docs phase. Default is "phase runs"
(mirrors <code>SKIP_POSTMERGE_VERIFY=1</code> semantics — opt-out, not opt-in). When skipped, the
Run Log gets <code>Docs: SKIPPED (PIPELINE_SKIP_DOCS=1)</code> and neither <code>docs-pre</code> nor
<code>docs-done</code> is emitted.</p>
<p><strong>Failure semantics (best-effort):</strong> A docs-writer subagent failure does NOT downgrade
<code>feature-done</code> to <code>feature-failed</code>. The Run Log gets <code>Docs: SKIPPED (subagent error)</code>
and the feature still completes with terminal status <code>SUCCESS</code>. Docs are a tail step,
not load-bearing.</p>
<p><strong>Subprocess-mode constraint:</strong> The out-of-process <code>orchestrate.sh</code> is not shipped in
pipelinekit (see § What was removed in the portable build). If <code>orchestrate.sh</code> is
ever introduced, it would need its own docs-phase parallel — record as a deferred
dependency.</p>
<h2 id="worker-delegation">Worker Delegation</h2>
<p>The implement phase of <code>/pipeline</code> dispatches each plan task to a worker. The default
worker is <strong>ClaudeWorker</strong> — the in-session Agent-tool worktree fan-out documented
in <code>claude/skills/implement-plan/SKILL.md</code> § Step 1.5. ClaudeWorker is always
available and requires no external runtime.</p>
<p>Plan task prompts MAY include an optional <code>worker:</code> header to request a different
worker class (for example, an external worker class for long-running parallel work).
When the header is absent or set to <code>worker: claude</code>, pipelinekit dispatches via
ClaudeWorker. Routing logic for non-default worker classes is <strong>not wired in this
build</strong> — see Phase 3 of the worker-delegation initiative (deferred).</p>
<h3 id="worker-classes">Worker classes</h3>
<table>
<thead>
<tr>
<th>Class</th>
<th>Status</th>
<th>Dispatch mechanism</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>claude</code></td>
<td>default; always available</td>
<td>In-session Agent tool + worktree isolation</td>
</tr>
</tbody>
</table>
<p>Per-class implementation specs live in <code>claude/lib/worker-provider/&lt;class&gt;.md</code>.
The contract every worker class implements is documented in
<code>claude/lib/worker-provider/interface.md</code>. The per-task spec schema that every
worker reads from <code>.claude/tasks/&lt;task-id&gt;/spec.md</code> is documented in
<code>claude/lib/worker-provider/task-spec.md</code>.</p>
<h3 id="opt-in-format">Opt-in format</h3>
<p>Add a <code>worker:</code> line to a plan task prompt's header block:</p>
<div class="codehilite"><pre><span></span><code>### Task 1.1: Build the thing
&gt; Model: sonnet | Effort: medium | Agent: none | worker: claude
</code></pre></div>

<p>In this build, the header is acknowledged but ignored — every task dispatches via
ClaudeWorker regardless. The header reservation lets plan authors begin annotating
plans today; routing arrives in a future iteration.</p>
<h2 id="sandbox-provider">Sandbox Provider</h2>
<p><code>/pipeline</code> runs each phase's command stream inside a sandbox provider chosen by
<code>claude/lib/sandbox/SandboxProvider.sh</code>. The provider selection ladder is:</p>
<ol>
<li><code>SANDBOX_PROVIDER=podman</code> | <code>docker</code> | <code>worktree-only</code> — explicit override.</li>
<li><code>SANDBOX_PROVIDER=auto</code> (default) — <strong>engine-when-present</strong>: prefer <code>podman</code>,
   else <code>docker</code>, else fall back to <code>worktree-only</code>. The fallback keeps the
   pipeline runnable on hosts without a container engine; on engines-available
   hosts the container provider is selected automatically.</li>
<li><code>PIPELINE_NO_SANDBOX=1</code> — short-circuit to <code>worktree-only</code> regardless of
   detected engines.</li>
</ol>
<h3 id="shell-injection-hardening-exec-style-argv">Shell-injection hardening (exec-style argv)</h3>
<p>Sandbox providers (<code>podman.sh</code>, <code>docker.sh</code>) dispatch the inner command as
<strong>exec-style argv</strong>, never as a shell string. The env-scrub prefix is read via
<code>env-scrub.py --prefix-args</code> (one token per line: <code>env</code>, then alternating
<code>-u VAR</code> pairs), loaded into a bash array with <code>mapfile -t prefix</code>, and
passed alongside the user's argv:</p>
<div class="codehilite"><pre><span></span><code>mapfile<span class="w"> </span>-t<span class="w"> </span>prefix<span class="w"> </span>&lt;<span class="w"> </span>&lt;<span class="o">(</span>python3<span class="w"> </span><span class="s2">&quot;</span><span class="si">${</span><span class="nv">claude_home</span><span class="si">}</span><span class="s2">/hooks/env-scrub.py&quot;</span><span class="w"> </span>--prefix-args<span class="o">)</span>
podman<span class="w"> </span>run<span class="w"> </span>--rm<span class="w"> </span>...<span class="w"> </span><span class="s2">&quot;</span><span class="nv">$image</span><span class="s2">&quot;</span><span class="w"> </span><span class="s2">&quot;</span><span class="si">${</span><span class="nv">prefix</span><span class="p">[@]</span><span class="si">}</span><span class="s2">&quot;</span><span class="w"> </span><span class="s2">&quot;</span><span class="nv">$@</span><span class="s2">&quot;</span>
</code></pre></div>

<p>This eliminates the shell-injection surface that <code>sh -c "$scrubbed"</code> would
expose if a caller ever passed AI-generated text containing shell
metacharacters. Provider authors <strong>must not</strong> reintroduce <code>sh -c</code> for
command dispatch — <code>claude/lib/sandbox/tests/test_no_shell_injection.sh</code>
guards against regression.</p>
<p>The <code>sandbox_enter</code> API surface is unchanged: callers still invoke
<code>sandbox_enter "$wt" cmd arg1 arg2 ...</code> exactly as before.</p>
<h3 id="build-amp-pull">Build &amp; Pull</h3>
<p>The sandbox base image is built locally from <code>scripts/sandbox/Containerfile</code>
via the wrapper script:</p>
<div class="codehilite"><pre><span></span><code>bash<span class="w"> </span>scripts/sandbox/build.sh
<span class="nb">export</span><span class="w"> </span><span class="nv">PIPELINEKIT_SANDBOX_TAG</span><span class="o">=</span>pipelinekit/sandbox-base:&lt;git-short-sha&gt;
</code></pre></div>

<p>The build script auto-detects <code>podman</code> (preferred) or <code>docker</code>, applies the
<code>pipelinekit/sandbox-base:latest</code> alias locally (suppress with <code>--no-latest</code>),
and prints the exact <code>export</code> line for the resolved tag on success.</p>
<p>The image is <strong>local-only</strong>: there is no <code>push</code> step in <code>build.sh</code> and no
registry hostname appears in the recipe. Do not publish this image to a
public registry — the namespace is unclaimed and the recipe omits any
registry-pin or signature step that would make a public publish safe.</p>
<p>Size budget: the slim base + apt cache cleanup keeps the compressed image
under 1 GB. Enforcing that ceiling in CI (assert <code>&lt;engine&gt; image inspect</code>
size) is a follow-up; today it is a soft target verified by inspection.</p>
<p>WSL2 storage hygiene: layered worktrees and npm caches can balloon on
Windows-hosted Linux. Reclaim space with <code>podman system prune</code> or
<code>docker system prune</code> after pipeline runs accumulate unused layers.</p>
<h2 id="optional-subprocess-driver">Optional subprocess driver</h2>
<p><code>claude/skills/pipeline/orchestrate.sh</code> ships as an <strong>OPTIONAL</strong> out-of-process
driver stub. The in-process <code>/pipeline</code> Skill remains the canonical entry
point for interactive sessions. The stub exists for unattended runs (CI cron,
scheduled batch processing) where maximum context isolation between phases
matters more than the convenience of the in-process Skill.</p>
<p>The stub exposes a single library function:</p>
<div class="codehilite"><pre><span></span><code>.<span class="w"> </span>claude/skills/pipeline/orchestrate.sh
run_phase<span class="w"> </span>analyze<span class="w"> </span>prompt.txt<span class="w"> </span>/path/to/worktree
</code></pre></div>

<p><code>run_phase</code> reads the phase prompt from a file, then dispatches <code>claude -p</code>
<strong>inside</strong> the sandbox provider chosen by <code>claude/lib/sandbox/SandboxProvider.sh</code>
— i.e., the subprocess invocation participates in the same <code>sandbox_enter</code> /
<code>sandbox_exit</code> isolation boundary used by the in-process Skill.</p>
<p><strong>Charter Discovery constraint.</strong> A subprocess driver cannot run Step 0
Charter Discovery because <code>AskUserQuestion</code> is interactive-session-only. When
generating phase prompts for unattended runs, pass <code>--no-charter</code> to the
<code>/pipeline</code> invocation that produced the prompt files (or adopt a pre-built
charter with <code>--charter &lt;path&gt;</code>).</p>
<p><strong>Stub scope.</strong> <code>orchestrate.sh</code> demonstrates the per-phase wrapping contract.
A full driver must iterate over phases and features, persist
<code>docs/pipeline-state.md</code> between phases, and handle Path A/B/C transitions
per the contract in <code>~/.claude/skills/pipeline/reference.md</code>. Forks are
expected to extend the stub; the upstream stub deliberately does not
re-implement the full pipeline loop.</p>
<p><strong>Wrap surface (multi-callsite).</strong> <code>orchestrate.sh</code> exposes three wrap helpers: <code>run_phase</code> (wraps <code>claude -p</code>), <code>run_host_adapter</code> (wraps <code>host-adapters/&lt;host&gt;.sh</code>), and <code>run_mcp</code> (wraps an MCP-server launch — interface-first scaffolding, no consumer ships using it today). All three dispatch via the public <code>sandbox_wrap &lt;task-id&gt; &lt;worktree&gt; &lt;command...&gt;</code> helper, which emits <code>SANDBOX_ENTER: provider=&lt;X&gt;, task=&lt;task-id&gt;, image=&lt;image&gt;</code> to stderr at wrap time. Forks adding new external-subprocess entry points should reuse <code>sandbox_wrap</code>.</p>
<p><strong>Worktree-only delegation (in-process Skill).</strong> When <code>provider_detect</code> resolves to <code>worktree-only</code>, the in-process Skill should prefer the native <code>EnterWorktree</code> tool (Claude Code <code>&gt;= 2.1.143</code>) with <code>worktree.bgIsolation</code> and <code>worktree.baseRef</code> settings, instead of bash worktree plumbing. The subprocess driver itself remains bash-only (the legacy <code>(cd "$wt" &amp;&amp; exec "$@")</code> body in <code>providers/worktree-only.sh</code>) — this delegation note is for the in-process Skill path. See the <a href="https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md">Claude Code changelog</a> for the <code>worktree.bgIsolation</code> (2.1.143) and <code>worktree.baseRef</code> (2.1.133) entries. Actual delegation in the in-process Skill is deferred to a follow-up feature.</p>
<h2 id="what-was-removed-in-the-portable-build">What was removed in the portable build</h2>
<ul>
<li><code>claude -p</code> subprocess invocations as the <strong>primary</strong> phase-dispatch mechanism.
  Phase dispatch in the in-process Skill is always via the <code>Agent</code> tool with
  subagent isolation. The optional <code>orchestrate.sh</code> stub (see above) is the
  only place <code>claude -p</code> still appears in shipped code.</li>
</ul>
