# Source of this skill

`SKILL.md` and `LICENSE.txt` in this folder are Anthropic's `frontend-design` skill, copied from:

- Repository: https://github.com/anthropics/skills
- Path: `skills/frontend-design`
- Commit: `41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f`
- Commit date: 2026-09-03
- Licence: Apache License 2.0 (`LICENSE.txt`); upstream has no NOTICE file.

Both files are unchanged. This file is the kit's own.

| file | git blob | sha256 |
|------|----------|--------|
| `SKILL.md` | `a5333457c414d20d625f307df945842c0952ecc3` | `d91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3` |
| `LICENSE.txt` | `f433b1a53f5b830a205fd2df78e2b34974656c7b` | `0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594` |

`.gitattributes` marks both files `-text`, so no checkout changes their bytes.

## Moving to a newer commit

1. Fetch both files at the new commit, from the repository root:

   ```bash
   for f in SKILL.md LICENSE.txt; do
     gh api -H 'Accept: application/vnd.github.raw' \
       "repos/anthropics/skills/contents/skills/frontend-design/$f?ref=<commit>" \
       > "claude/skills/frontend-design/$f"
   done
   ```

2. Replace the commit, the commit date, the blob ids (`git hash-object <file>`) and the checksums (`sha256sum <file>`) in this file.
3. Run `python3 -m pytest -q claude/skills/kit/tests/test_frontend_design.py`.
4. Add a line to `CHANGELOG.md`.
