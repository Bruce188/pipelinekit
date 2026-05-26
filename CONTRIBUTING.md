# Contributing to pipelinekit

Thanks for your interest in pipelinekit. For the full workflow doctrine, please read the rendered governance doc: [`documentation/governance.html`](documentation/governance.html).

## Workflow

pipelinekit ships an autonomous workflow orchestrator behind `Skill: pipeline`. The full pipeline — Charter Discovery, analyze, plan, implement, review, push-and-PR, post-merge — is documented end-to-end in [`documentation/governance.html`](documentation/governance.html). In short: features land one at a time on dedicated branches via the orchestrator, with each phase dispatched as a fresh-context subagent.

## Commit messages

Commit messages follow the conventional-commit format. The accepted type set is:

`feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `style`, `build`, `ci`

The regex is enforced by [`claude/hooks/validate-commit-msg.sh`](claude/hooks/validate-commit-msg.sh) — do not duplicate or re-state it here; if you need to know the exact pattern, read the hook.

Subject lines start with a lowercase letter, stay under ~70 characters, and contain no emoji.

## Before you commit

Some paths must never be staged — secrets, workflow metadata, local indices. The canonical list lives at [`claude/config/never-stage.txt`](claude/config/never-stage.txt) and the [`claude/hooks/block-stage-sensitive.sh`](claude/hooks/block-stage-sensitive.sh) hook refuses any matching path.

Local-only ignores (editor cruft, scratch files, anything Claude-specific to your machine) belong in `.git/info/exclude`, NOT in `.gitignore`. `.gitignore` is shared with every contributor; `.git/info/exclude` is yours alone.

## No AI attribution

Pull requests, commits, and source files MUST NOT carry AI-tool attribution metadata — the model name, the SDK vendor, the acronym for large language models, the `Co_Authored_By` trailer (written here with underscores so this very sentence does not trip the policy grep), the phrase produced-with-AI, or robot emoji. The commit-message hook rejects these strings outright. The canonical block-list lives in `claude/hooks/strip-ai-attribution.sh`.

## License

pipelinekit is MIT-licensed — see [`LICENSE`](LICENSE) at the repository root.
