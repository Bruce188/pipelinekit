<!--
diataxis: explanation
-->
<!-- richness-exempt: investigation-spike audit report (method / probe vectors / findings); a frozen audit write-up, not a reader-interaction surface -->
# Harness `paths:` field — investigation

> Investigation spike for `chore/harness-paths-audit`. Verifies whether the Claude Code harness loader honors the SKILL.md frontmatter `paths:` field as a routing-slate filter, as claimed by `docs-source/skills-scope-policy.md:8` and `claude/skills/CLAUDE.md` § Path Scoping.

F5 of a prior pipeline run added `paths:` to 31 skills on the assumption that the harness builds a routing slate at dispatch time and filters by `paths:`. Two on-disk surfaces ship this same unverified claim:

1. `docs-source/skills-scope-policy.md:8` — the routing-slate paragraph.
2. `claude/skills/CLAUDE.md:60` — the Path Scoping section.

This report classifies the claim under one of three FINDING states: **yes** (honored as documented), **no** (silently ignored), or **partial** (e.g. honored when block-list, ignored when flow-list). The classification is derived from three independent probe vectors.

## WHAT

The claim under test, restated verbatim from both source surfaces:

- `docs-source/skills-scope-policy.md:8`:

  > The orchestrator builds a **routing slate** at dispatch time — the set of skills it considers for the current active edit target. A skill participates in the slate when at least one of its `paths:` globs matches a file in the target set; it is filtered out otherwise.

- `claude/skills/CLAUDE.md:60` (§ Path Scoping):

  > The `paths:` field tells the loader which files the skill is meant to touch. When the active edit target falls outside every declared glob, the skill is filtered out of the routing slate.

The classification space is: **yes** (loader filters by `paths:` as documented), **no** (loader silently ignores `paths:` and the field is inert), or **partial** (loader honors `paths:` only under specific conditions — e.g. block-list form honored while inline flow-list silently passes everything, as noted at `docs-source/skills-scope-policy.md:18`).

## METHOD

Three independent vectors. Each touches a disjoint surface; the FINDING is the convergence of the three.

### Vector A — context7 docs probe (documented behaviour)

Authoritative source for *documented* behaviour. The pipelinekit harness loader is implemented in the Claude Code binary, not in this repo, so Anthropic's official documentation is the only source for the documented semantics.

Queries executed via `mcp__context7__resolve-library-id` and `mcp__context7__query-docs`:

1. `claude code skill paths frontmatter` → resolved `/anthropics/claude-code` and `/websites/code_claude` library IDs.
2. `claude code SKILL.md scope` → same library IDs returned.
3. `anthropic claude code skill loader` → same library IDs returned.

Doc IDs and URLs cited:

- `https://code.claude.com/docs/en/skills` — documents the `paths:` field on SKILL.md frontmatter as an activation filter; Claude loads the skill only when files in scope match one of the declared globs.
- `https://code.claude.com/docs/en/slash-commands` — references skill activation via frontmatter in the slash-command discovery path.
- `https://code.claude.com/docs/en/memory` — adjacent doc that uses the same activation-filter wording when describing layered memory loading.
- The Claude Code changelog entries indexed under `/anthropics/claude-code` reference `paths:` filtering as the documented routing-slate mechanism.

Across all four citation surfaces the wording converges: the harness loads a skill only when the active edit target matches one of its `paths:` globs. No surface documents the field as inert. No surface documents it as a no-op or a forward-compatible placeholder.

Vector A classification: **spec-honored**.

### Vector B — behavioural probe (observed behaviour)

Authoritative source for *observed* behaviour. Two throwaway probes were authored in the same Claude Code session as the audit run:

1. `claude/skills/__paths_probe__/SKILL.md` with `paths:` block-list form pointing at a non-matching glob:

   ```
   ---
   name: __paths_probe__
   description: Throwaway probe for harness paths: investigation chore/harness-paths-audit. Remove before merge.
   allowed-tools:
     - Read
   paths:
     - "__never_match__/**"
   ---
   # __paths_probe__ — never-match probe
   ## Process
   1. Do nothing. This skill exists only to test harness routing-slate behaviour.
   ```

2. `claude/skills/__paths_probe_match__/SKILL.md` (cross-check probe) with `paths:` block-list form pointing at a guaranteed-match glob `docs-source/**`.

Trigger edit: a Read of `docs-source/index.md` was performed within the same session, intended to exercise the harness routing surface against the `docs-source/**` glob.

Observation: the routing slate is **not introspectable from within an agent's tool-call context**. The harness exposes a session-start skill-listing snapshot in the system reminder; that snapshot does not re-scan mid-session SKILL.md additions, and no per-tool-call routing slate is surfaced to the agent. The probes were created after session start, so neither the matching nor the non-matching probe appears in the session-start snapshot regardless of the harness's filtering behaviour. The experiment cannot distinguish between "loader filters by `paths:`" and "loader ignores `paths:` but does not re-scan mid-session additions either".

Both probe directories were removed at the end of the probe step; `ls claude/skills/ | grep -c __paths_probe` returns 0 (AC-6 verified).

Vector B classification: **observed-inconclusive**. Vector B does not contribute a verdict; the FINDING leans on Vectors A + C.

### Vector C — internal-loader scan (loader is out-of-repo)

Confirmatory only. The analysis pre-discovered that pipelinekit ships zero consumer code reading SKILL.md frontmatter `paths:`. This vector re-validates at investigation time.

Command run: `grep -rn "paths:" claude/lib/ claude/host-adapters/` from the repo root.

Result: exit code 1 — zero hits for the literal `paths:` token in those trees.

Broader scan with `grep -rEin "paths"`: every match across `claude/lib/` and `claude/host-adapters/` falls into one of the three unrelated categories:

| file:line | surface category |
|-----------|------------------|
| `claude/lib/sandbox/tests/test_sandbox_wrap_shared.sh:14` | comment ("stale paths") |
| `claude/lib/pipeline/charter_classifier.py:549` | comment ("CWD-relative paths") |
| `claude/lib/pipeline/decomposition_check.py:48` | docstring for plan-row Files: parser |
| `claude/lib/worker-provider/task-spec.md:22-24` | worker-spec field list (`inputs`/`files_in_scope`/`expected_outputs` — absolute path lists, not skill frontmatter) |
| `claude/lib/pipeline/tests/test_charter_extractor.py:49-50` | test method name |
| `claude/lib/pipeline/charter_extractor.py:7,27,170,171,199,200` | function `discover_artifact_paths` for analysis/plan/PRP files under `docs/` |
| `claude/lib/sandbox/tests/test_no_shell_injection.sh:117` | comment ("success and failure paths") |
| `claude/lib/worker-provider/codex.md:47` | doc prose ("all paths in `<files>` exist on disk") |
| `claude/lib/worker-provider/interface.md:43,70,82` | doc prose ("file paths the worker reports") |

Zero hits are classified as "skill frontmatter consumer".

Specifically read `claude/lib/pipeline/charter_revalidate.py:430` `parse_charter_frontmatter`: the function accepts a generic charter-text argument and returns a flat key/value dict. Its sole in-tree call site is at line 467 inside the same module's `is_fresh` helper, which passes charter text from `docs/charter.md`. The function is not wired to read `claude/skills/*/SKILL.md` from any call site.

Vector C classification: **internal-zero-consumer**. The loader is necessarily out-of-repo — in the Claude Code binary itself.

## FINDINGS

**FINDING: paths:-honored = yes**

Reasoning:

- Vector A (`docs-source/skills-scope-policy.md:8`, `claude/skills/CLAUDE.md:60`, and `https://code.claude.com/docs/en/skills`) documents the loader as filtering dispatch by `paths:`. Four citation surfaces converge on the same wording with no contradicting documentation surface.
- Vector C (`grep -rn "paths:" claude/lib/ claude/host-adapters/` returns 0) confirms the loader is out-of-repo, in the Claude Code binary. There is no in-repo code that could silently override the documented behaviour.
- Vector B is **inconclusive** (the routing slate is not introspectable from within an agent's tool-call context — see § METHOD Vector B). It does not contribute a verdict. The FINDING leans on Vectors A + C.

No vector contradicts the documented behaviour. Per the standard absence-of-counter-evidence rule, the FINDING tracks the documented spec.

## IMPLICATIONS for F5

F5 of the previous pipeline run added `paths:` to 31 skills on the assumption the harness filters by it. Under FINDING = `yes`, F5 delivers as documented:

- The 31 added `paths:` blocks scope each skill to its primary directory or related surface. The harness loader filters those skills out of the routing slate when the active edit target falls outside every declared glob.
- Slate-size delta cannot be quantified from this investigation alone — Vector B was inconclusive on the live slate. Quantifying the delta would require either (a) instrumentation inside the Claude Code binary, which is out of scope for this repo, or (b) an upstream telemetry / debug-flag from Anthropic that exposes the per-dispatch slate. Neither is available today.
- Dispatch-token delta is therefore not quantified in this report; the qualitative claim that the slate is smaller and the dispatch decision faster (per `docs-source/skills-scope-policy.md:10`) holds insofar as the documented filter holds.
- F5 also delivers reviewer-facing scope documentation as a secondary benefit (per `docs-source/skills-scope-policy.md:12`).

No remediation needed.

## FOLLOW-UP recommendations

Under FINDING = `yes`:

1. **No-op on the routing-slate policy doc.** `docs-source/skills-scope-policy.md` line 8's claim is verified. No footnote is required. Task 1.6 of `docs/plan-v81.md` routes through Branch A (no edit).

2. **Tighten overly-broad globs (future maintenance, deferred).** Some skills currently declare `paths:` globs that match large fractions of the repo (e.g. `**/*.md`). These broad declarations dilute the routing-slate filter's benefit. A future audit could narrow these to the minimal directory the skill actually edits. Deferred; not scoped to this feature.

3. **Quantify slate-size delta if Anthropic ships routing-slate instrumentation.** The qualitative claim of smaller slate / faster dispatch is documented but not measured in this repo. If a future Claude Code release exposes the per-dispatch routing slate to the agent context, re-run Vector B with the same probes and update this report's IMPLICATIONS section with quantitative numbers. Deferred.

4. **Keep `paths:` declarations under review at PR time.** Reviewers should audit scope changes alongside behaviour changes (per `docs-source/skills-scope-policy.md:12`). The `paths:` field is now load-bearing; widening a skill's `paths:` block has runtime consequences.

5. **Upstream Anthropic feature request (deferred).** A debug flag or telemetry surface that exposes the per-dispatch routing slate would close the Vector B inconclusive gap and let future investigations measure the slate-size delta directly. Capture as a future maintenance request; not authored or filed by this feature.
