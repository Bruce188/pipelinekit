---
diataxis: reference
---

# File size limit

A hand-written text file (code, tests, markdown) has at most 1,500 lines and 50,000 bytes. Claude Code's Read tool returns a text file whole only up to 25,000 tokens and past that a first page, so a longer file is read in pieces or only in part. The global `pre-commit` hook runs `~/.claude/hooks/filesize.py` on the staged files. `git merge` does not run `pre-commit` for a merge it makes without conflicts, so the global `pre-merge-commit` hook runs the same check on the merged files before the merge is recorded (see [Git hooks](components.html#git-hooks)).

## What is refused

- A commit or merge that adds a file over the limit, or takes a file from under the limit to over it, is refused with `[pre-commit.file-size]`. The refusal names each file, its lines and bytes, and what it was before; a control character in a path is shown as `?`, and a byte that is not UTF-8 as an escape. The event log gets the first path and its size, never the content.
- A refused merge is left unfinished: split the file, then `git commit` concludes the merge, and `pre-commit` checks it again.
- A file that was already over the limit before the commit gets a warning with `[pre-commit.file-size-over]`, and the commit or merge goes on. A renamed file keeps the size it had under its old name; when a commit concludes a merge, or `git merge` records one, a file over the limit in either parent counts as already over.
- A check that fails to run warns with `[pre-commit.file-size-failed]`, records an error and lets the commit or merge through.

### A sample refusal

```text
pre-commit: commit refused, over the file size limit of 1,500 lines and 50,000 bytes:
  src/parser.py: 1,900 lines, 15,993 bytes (new file)
Split the file: new code that would take a file past the limit goes in a new file.
A generated, vendored or data file can be listed in .file-size-exempt at the top of
the repository, one pattern per line. [pre-commit.file-size]
```

The last line is one line in the terminal; it is wrapped here.

## What is not checked

Git runs neither hook for `git rebase`, `git cherry-pick`, `git revert`, `git am` or `git stash`, so what those commands record is not checked. `git commit --no-verify` skips both hooks too; `bash-guard.py` refuses it for Claude.

## What is not counted

- Binary files (a NUL byte in the first 8,000 bytes, or `binary` or `-diff` in a staged `.gitattributes`), deleted files, symlinks and submodules. A blob over 50,000 bytes is read in pieces and dropped once its first 8,000 bytes show it is binary.
- A path marked `linguist-generated` or `linguist-vendored` in a staged `.gitattributes`.
- By default, generated, vendored, lock and data files, and the project and designer files an IDE writes:

| Kind | Patterns |
|------|----------|
| Lock files | `*.lock`, `*.lockb`, `*.lockfile`, `*-lock.json`, `*-lock.yaml`, `npm-shrinkwrap.json`, `packages.lock.json`, `Package.resolved`, `go.sum` |
| Vendored folders | `vendor/`, `vendored/`, `third_party/`, `third-party/`, `node_modules/` |
| Generated files and folders | `generated/`, `__generated__/`, `dist/`, `*.min.js`, `*.min.css`, `*.map`, `*.generated.*`, `*.g.cs`, `*.g.dart`, `*.freezed.dart`, `*.designer.cs`, `*.Designer.cs`, `*ModelSnapshot.cs`, `*.pb.go`, `*_pb2.py`, `*_pb2.pyi`, `*.snap` |
| Project and designer files an IDE writes | `*.pbxproj`, `*.xcstrings`, `*.storyboard`, `*.xib`, `*.resx` |
| Data files | `*.json`, `*.jsonl`, `*.ndjson`, `*.geojson`, `*.csv`, `*.tsv`, `*.ipynb`, `*.svg` |

Only what the commit carries exempts a file. `$GIT_DIR/info/attributes`, `core.attributesFile` and the system attributes file are not read, and an unstaged edit to `.gitattributes` or to `.file-size-exempt` exempts nothing.

## Exempting more paths

A project lists more paths in `.file-size-exempt` at the top of the repository, one pattern per line, gitignore style, and commits it. Only the staged copy counts: when the unstaged changes of a tracked list name a refused file, the refusal says to stage the list (`git add .file-size-exempt`). This repository lists `documentation/`, the rendered pages.

### A sample list

```text
# The rendered docs site
documentation/
# One generated client, at the top of the repository only
/src/api/client.ts
*.generated.sql
fixtures/**/*.txt
```

### Pattern syntax

| Pattern | Matches |
|---------|---------|
| `name` | A file or folder of that name at any depth |
| `name/` | Only a folder of that name, and everything in it |
| `/name`, `src/name` | A `/` in front or in the middle anchors the pattern to the top of the repository |
| `*` | Any characters inside one folder or file name |
| `?` | One character other than `/` |
| `[ch]`, `[a-z]` | One character of the set or range |
| `[!ch]`, `[^ch]` | One character not in the set |
| `**` | Any number of folders: `**/name`, `src/**`, `a/**/b` |
| `# text` | A comment |
| `!name` | Not supported: the line is skipped with a warning |

A line that is not a valid pattern, such as one with the reversed range `[z-a]`, is skipped with a warning that names its line. A list over 1,000 lines or 64,000 bytes is used up to that point, with a warning. A list staged as a link, a submodule or a folder, or that is not UTF-8 text, is not used, and the hook warns that it is not.

## Silencing the over-limit warning

`[pre-commit.file-size-over]` comes back each time a file that is already over the limit changes; it is not logged. To stop it, split the file under the limit. A generated, vendored or data file can instead be listed in `.file-size-exempt`, staged with the commit.

## Merges and the repository's own hook

After the size check, `pre-merge-commit` runs the repository's own `.git/hooks/pre-merge-commit`, and `.githooks/pre-merge-commit` only when it is the executable file the current commit has. The merge has already written the incoming branch's files to the working tree, so a merge never runs a hook it brings in; a hook skipped this way gets a one-line warning.