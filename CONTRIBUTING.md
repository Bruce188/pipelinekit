# Contributing to pipelinekit

Thanks for your interest in pipelinekit.

## Workflow

Branch from `main`, keep changes small, open a PR. Run `bash tests/test_install.sh`, the hook tests in `claude/hooks/tests/` and, for docs-writer changes, `claude/skills/docs-writer/tests/` before pushing.

## Commit messages

Commit messages follow the conventional-commit format. The accepted type set is:

`feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `style`, `build`, `ci`, `revert`

The regex is enforced by the [`claude/git-hooks/commit-msg`](claude/git-hooks/commit-msg) git hook — do not duplicate or re-state it here; if you need to know the exact pattern, read the hook.

Subject lines start with a lowercase letter, stay under ~70 characters, and contain no emoji.

## Before you commit

Some paths must never be staged — secrets, workflow metadata, local indices. The canonical list lives at [`claude/config/never-stage.txt`](claude/config/never-stage.txt) and the [`claude/hooks/bash-guard.py`](claude/hooks/bash-guard.py) hook refuses any matching path.

Local-only ignores (editor cruft, scratch files, anything Claude-specific to your machine) belong in `.git/info/exclude`, NOT in `.gitignore`. `.gitignore` is shared with every contributor; `.git/info/exclude` is yours alone.

## No AI attribution

Pull requests, commits, and source files MUST NOT carry AI-tool attribution metadata — the model name, the SDK vendor, the acronym for large language models, the `Co_Authored_By` trailer (written here with underscores so this very sentence does not trip the policy grep), the phrase produced-with-AI, or robot emoji. `scripts/install.sh` turns attribution off in `settings.json`.

## License

pipelinekit is MIT-licensed — see [`LICENSE`](LICENSE) at the repository root.
