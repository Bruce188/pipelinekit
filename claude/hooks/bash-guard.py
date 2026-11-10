#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool. One process, one parse, four check groups.

Usage: bash-guard.py [git|docker|fetch|sql]   (no argument = all groups)

settings.json registers this script once per group, each with an `if` rule
(`Bash(git *)`, `Bash(docker *)`, ...), so it only spawns when that kind of
command is present. The group argument also keeps the handlers distinct.

Exit 0 = allow, exit 2 + stderr = block, exit 0 + JSON on stdout = ask.
Stdlib only. Never exits 1 on purpose, so `onFailure: "block"` is safe.

Groups:
  git    --no-verify / commit -n, -c core.hooksPath, override env vars,
         git config writes (--global/--system, any core.hooksPath),
         git remote add/set-url, push to a non-origin remote, push to
         main/master, staging never-stage paths (git add/stage, commit -a,
         commit <paths>) and bulk staging outside .claude/worktrees/.
  docker docker/podman run/create bind-mounts of sensitive host paths
         (block) and --privileged (ask).
  fetch  curl/wget output piped or substituted into a shell or interpreter.
  sql    DROP/TRUNCATE sent to psql/mysql/mariadb/sqlite3 (ask).

Destructive-but-legitimate git (reset --hard, clean -f, push --force,
branch -D, checkout/restore .) is handled by native `permissions.ask` rules,
which are documented to prompt even in bypassPermissions mode.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys

HOME = os.path.expanduser("~")
CLAUDE_HOME = os.environ.get("CLAUDE_HOME", os.path.join(HOME, ".claude"))
NEVER_STAGE = os.path.join(CLAUDE_HOME, "config", "never-stage.txt")

SEPARATORS = {";", "&", "&&", "|", "||", "|&", "\n", "(", ")", ";;"}
WRAPPERS = {
    "sudo",
    "command",
    "builtin",
    "nohup",
    "time",
    "nice",
    "exec",
    "noglob",
    "stdbuf",
    "timeout",
    "env",
    "xargs",
}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
INTERPRETERS = {"python", "python3", "perl", "ruby", "node"}
DB_CLIENTS = {"psql", "mysql", "mariadb", "sqlite3"}
PROTECTED_BRANCHES = {"main", "master"}
OVERRIDE_VARS = re.compile(r"(ALLOW_MAIN_PUSH|PIPELINEKIT_ALLOW_SECRET)=")
SUBST = re.compile(r"\$\(([^()]*(?:\([^()]*\)[^()]*)*)\)|`([^`]*)`")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2(?=\s|$)", re.S)


class Block(Exception):
    pass


class Ask(Exception):
    pass


# ---------------------------------------------------------------- parsing


def tokenize(cmd: str) -> list[str]:
    lex = shlex.shlex(cmd, posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    return list(lex)


def pipelines(cmd: str) -> list[list[list[str]]]:
    """Split a command line into pipelines of segments (argv lists).

    Command substitutions and `sh -c` strings are parsed recursively and
    returned as extra pipelines. Raises Block if the text can't be parsed.
    """
    cmd = HEREDOC.sub("<<EOF\n", cmd)
    try:
        toks = tokenize(cmd)
    except ValueError as exc:
        raise Block(
            f"could not parse the command ({exc}); simplify the quoting"
        ) from None
    out: list[list[list[str]]] = []
    pipe: list[list[str]] = []
    seg: list[str] = []
    skip_next = False
    for t in toks:
        if skip_next:
            skip_next = False
            continue
        if t in SEPARATORS or (set(t) <= set(";&|\n()") and t):
            if seg:
                pipe.append(seg)
                seg = []
            if t not in ("|", "|&") and pipe:
                out.append(pipe)
                pipe = []
            continue
        if set(t) <= set("<>&") and t:  # redirect operator: drop it and its target
            skip_next = True
            continue
        seg.append(t)
    if seg:
        pipe.append(seg)
    if pipe:
        out.append(pipe)
    extra: list[list[list[str]]] = []
    for p in out:
        for s in p:
            for tok in s:
                for m in SUBST.finditer(tok):
                    extra += pipelines(m.group(1) or m.group(2) or "")
            argv = strip_wrappers(s)
            if argv and os.path.basename(argv[0]) in SHELLS | {"eval"}:
                if os.path.basename(argv[0]) == "eval":
                    extra += pipelines(" ".join(argv[1:]))
                elif "-c" in argv[1:-1]:
                    extra += pipelines(argv[argv.index("-c") + 1])
    return out + extra


def strip_wrappers(seg: list[str]) -> list[str]:
    """Drop leading VAR=val assignments and wrapper commands (sudo, env, timeout...)."""
    i = 0
    while i < len(seg):
        t = seg[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
            continue
        name = os.path.basename(t)
        if name in WRAPPERS:
            i += 1
            # wrapper options (and the duration argument of timeout)
            while i < len(seg) and (
                seg[i].startswith("-")
                or (name == "timeout" and re.match(r"^\d", seg[i]))
            ):
                i += 1
            continue
        break
    return seg[i:]


def name_of(argv: list[str]) -> str:
    return os.path.basename(argv[0]) if argv else ""


# ---------------------------------------------------------------- never-stage


def load_patterns(path: str = NEVER_STAGE) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return [
                ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")
            ]
    except OSError:
        raise Block(f"never-stage list missing at {path}; default-deny") from None


def _match_one(path: str, pat: str) -> bool:
    """gitignore-style match of a repo-relative path against one pattern."""
    dir_only = pat.endswith("/")
    pat = pat.rstrip("/")
    parts = path.split("/")
    if pat.startswith("**/"):
        pat, anchored = pat[3:], False
    else:
        anchored = "/" in pat
        pat = pat.lstrip("/")
    width = pat.count("/") + 1
    starts = [0] if anchored else range(len(parts))
    for i in starts:
        # The pattern may match the path or any parent directory of it.
        for k in range(i + width, len(parts) + 1):
            if dir_only and k == len(parts):
                break  # dir pattern: something must live under the match
            if fnmatch.fnmatchcase("/".join(parts[i:k]), pat):
                return True
            if not anchored:
                break  # unanchored: windows of exactly `width` components
    return False


def never_stage(path: str, patterns: list[str]) -> str | None:
    """Return the pattern that makes `path` protected, or None. `!pat` re-allows."""
    path = path.replace("\\", "/")
    path = path[2:] if path.startswith("./") else path
    hit = None
    for pat in patterns:
        if pat.startswith("!"):
            if hit and _match_one(path, pat[1:]):
                hit = None
        elif _match_one(path, pat):
            hit = pat
    return hit


# ---------------------------------------------------------------- git

GIT_GLOBAL_WITH_ARG = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--config-env",
    "--exec-path",
    "--super-prefix",
    "--list-cmds",
}


def run_git(cwd: str, *args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=10
        )
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def split_git(argv: list[str], cwd: str) -> tuple[str, list[str], str]:
    """Return (subcommand, args, effective cwd) after git's global options."""
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        opt = argv[i]
        key, eq, val = opt.partition("=")
        if key in GIT_GLOBAL_WITH_ARG and not eq:
            val = argv[i + 1] if i + 1 < len(argv) else ""
            i += 1
        if key in ("-c", "--config-env") and re.match(r"(?i)\s*core\.hookspath\b", val):
            raise Block("git -c core.hooksPath=... bypasses the git hooks")
        if key == "-C" and val:
            cwd = os.path.join(cwd, os.path.expanduser(val))
        i += 1
    sub = argv[i] if i < len(argv) else ""
    return sub, argv[i + 1 :], cwd


def check_git(argv: list[str], cwd: str, ctx: dict) -> None:
    sub, args, gcwd = split_git(argv, cwd)
    if "--no-verify" in args:
        raise Block(f"git {sub} --no-verify skips the git hooks")
    if sub == "config":
        check_git_config(args)
    elif sub == "remote" and args and args[0] in ("add", "set-url"):
        raise Block(
            f"git remote {args[0]} is not allowed; ask the user to change remotes"
        )
    elif sub == "push":
        check_push(args, gcwd)
    elif sub in ("add", "stage"):
        check_add(args, gcwd, ctx)
    elif sub == "commit":
        check_commit(args, gcwd, ctx)


def check_git_config(args: list[str]) -> None:
    read_flags = {
        "--get",
        "--get-all",
        "--get-regexp",
        "--get-urlmatch",
        "--list",
        "-l",
        "--get-color",
        "--get-colorbool",
    }
    write_flags = {
        "--unset",
        "--unset-all",
        "--add",
        "--replace-all",
        "--edit",
        "-e",
        "--rename-section",
        "--remove-section",
    }
    scoped = any(a in ("--global", "--system") for a in args)
    if args and args[0] in ("get", "list"):
        return
    positional = [a for a in args if not a.startswith("-")]
    if args and args[0] in ("set", "unset", "edit", "rename-section", "remove-section"):
        is_write, positional = True, positional[1:]
    elif any(a in read_flags for a in args):
        is_write = False
    else:
        is_write = any(a in write_flags for a in args) or len(positional) >= 2
    if not is_write:
        return
    if any(p.lower() == "core.hookspath" for p in positional):
        raise Block("changing core.hooksPath bypasses the git hooks; ask the user")
    if scoped:
        raise Block("git config --global/--system writes are not allowed; ask the user")


def check_push(args: list[str], cwd: str) -> None:
    with_arg = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
    positional: list[str] = []
    remote = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--all", "--mirror", "--branches"):
            raise Block(f"git push {a} would push main/master too; push one branch")
        if a.startswith("--repo="):
            remote = a.split("=", 1)[1]
        elif a in with_arg:
            if a == "--repo" and i + 1 < len(args):
                remote = args[i + 1]
            i += 1
        elif a == "--":
            positional += args[i + 1 :]
            break
        elif not a.startswith("-"):
            positional.append(a)
        i += 1
    if remote is None and positional:
        remote = positional.pop(0)
    if remote is not None and remote != "origin":
        raise Block(f"push to remote '{remote}' is not allowed; only origin")
    refspecs = positional
    if not refspecs:
        rc, out = run_git(cwd, "symbolic-ref", "--short", "-q", "HEAD")
        refspecs = [out.strip()] if rc == 0 and out.strip() else []
    for spec in refspecs:
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        dst = dst.lstrip("+")
        if dst == "HEAD":
            rc, out = run_git(cwd, "symbolic-ref", "--short", "-q", "HEAD")
            dst = out.strip()
        if dst.startswith(("refs/heads/", "heads/")):
            dst = dst.split("heads/", 1)[1]
        if dst in PROTECTED_BRANCHES and not spec.startswith(":"):
            raise Block(
                f"direct push to {dst} is not allowed; push a branch and open a PR"
            )


def in_worktree(cwd: str) -> bool:
    rc, top = run_git(cwd, "rev-parse", "--show-toplevel")
    return (
        "/.claude/worktrees/"
        in (top.strip() if rc == 0 else os.path.abspath(cwd)) + "/"
    )


def repo_rel(cwd: str, path: str) -> str:
    rc, top = run_git(cwd, "rev-parse", "--show-toplevel")
    absp = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
    if rc == 0 and top.strip():
        rel = os.path.relpath(absp, top.strip())
        if not rel.startswith(".."):
            return rel
    return path


def check_paths(paths: list[str], ctx: dict, how: str) -> None:
    if "patterns" not in ctx:
        ctx["patterns"] = load_patterns()
    pats = ctx["patterns"]
    for p in paths:
        hit = never_stage(p, pats)
        if hit:
            raise Block(
                f"{how} '{p}' matches never-stage pattern '{hit}' "
                f"({NEVER_STAGE}); it must not be committed"
            )


BULK_PATHSPECS = {
    ".",
    "./",
    ":/",
    ":",
    "*",
    "-A",
    "--all",
    "-u",
    "--update",
    "--no-ignore-removal",
}


def check_add(args: list[str], cwd: str, ctx: dict) -> None:
    flags = [a for a in args if a.startswith("-") and a != "--"]
    after_dd = args[args.index("--") + 1 :] if "--" in args else []
    specs = after_dd + [
        a for a in args[: len(args) - len(after_dd)] if not a.startswith("-")
    ]
    for s in specs:
        if "$" in s or "`" in s:
            raise Block(
                f"git add path '{s}' uses shell expansion; name the files literally"
            )
    if any(f.startswith("--pathspec-from-file") for f in flags):
        raise Block("git add --pathspec-from-file can't be checked; name the files")
    bulk = [
        a
        for a in flags + specs
        if a in BULK_PATHSPECS
        or a.startswith(":(")
        or (a.startswith("-") and not a.startswith("--") and set(a[1:]) & {"A", "u"})
    ]
    if bulk and not in_worktree(cwd):
        raise Block(
            f"bulk staging ({bulk[0]}) may stage protected files; "
            "git add specific paths instead"
        )
    check_paths(
        [repo_rel(cwd, s) for s in specs if not s.startswith(":")], ctx, "staging"
    )
    # Ask git what the command would actually stage (covers dirs, globs, -A, -u).
    safe_flags = [
        f
        for f in flags
        if f
        in (
            "-A",
            "--all",
            "-u",
            "--update",
            "-f",
            "--force",
            "--no-ignore-removal",
            "--sparse",
        )
        or (f.startswith("-") and not f.startswith("--") and set(f[1:]) <= set("Auf"))
    ]
    rc, out = run_git(
        cwd,
        "-c",
        "core.quotepath=off",
        "add",
        "--dry-run",
        "--ignore-missing",
        *safe_flags,
        "--",
        *specs,
    )
    staged = [m.group(1) for m in re.finditer(r"^add '(.*)'$", out, re.M)]
    check_paths(staged, ctx, "staging")


COMMIT_WITH_ARG = set("mFcCt")
COMMIT_LONG_WITH_ARG = {
    "--message",
    "--file",
    "--reuse-message",
    "--reedit-message",
    "--template",
    "--author",
    "--date",
    "--fixup",
    "--squash",
    "--trailer",
    "--cleanup",
    "--pathspec-from-file",
}


def check_commit(args: list[str], cwd: str, ctx: dict) -> None:
    all_flag = False
    specs: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            specs += args[i + 1 :]
            break
        if a.startswith("--"):
            key = a.split("=", 1)[0]
            if key == "--all":
                all_flag = True
            if key == "--pathspec-from-file":
                raise Block(
                    "git commit --pathspec-from-file can't be checked; name the files"
                )
            if key in COMMIT_LONG_WITH_ARG and "=" not in a:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:]):
                if ch == "n":
                    raise Block("git commit -n (--no-verify) skips the git hooks")
                if ch == "a":
                    all_flag = True
                if ch in COMMIT_WITH_ARG:
                    if j == len(a) - 2:  # argument is the next token
                        i += 1
                    break
        else:
            specs.append(a)
        i += 1
    if all_flag:
        if not in_worktree(cwd):
            raise Block(
                "git commit -a may commit protected files; git add specific paths first"
            )
        rc, out = run_git(cwd, "-c", "core.quotepath=off", "diff", "--name-only")
        check_paths(out.split("\n") if out else [], ctx, "committing")
    if specs:
        if any(
            s in BULK_PATHSPECS or s.startswith(":") for s in specs
        ) and not in_worktree(cwd):
            raise Block("git commit with a bulk pathspec may commit protected files")
        check_paths(
            [repo_rel(cwd, s) for s in specs if not s.startswith(":")],
            ctx,
            "committing",
        )


# ---------------------------------------------------------------- docker

SENSITIVE_EXACT = {
    "/",
    "/home",
    "/etc",
    "/root",
    "/var",
    "/usr",
    "/boot",
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/var/run/docker.sock",
    "/run/docker.sock",
    HOME,
}
SENSITIVE_TREES = ["/etc", "/root", "/proc", "/sys", "/dev", "/boot"] + [
    os.path.join(HOME, d)
    for d in (
        ".ssh",
        ".aws",
        ".azure",
        ".gnupg",
        ".kube",
        ".config",
        ".docker",
        ".claude",
        ".git-credentials",
        ".npmrc",
    )
]
# Mount sources are compared after symlink resolution, so the lists also need
# the resolved spellings: on macOS /etc and /var are links into /private.
SENSITIVE_EXACT |= {os.path.realpath(p) for p in SENSITIVE_EXACT}
SENSITIVE_TREES += [os.path.realpath(p) for p in SENSITIVE_TREES]


def host_path(src: str, cwd: str) -> str | None:
    """Resolve a bind-mount source; None means it is a named volume."""
    if not src or not (src[0] in "/.~$" or src.startswith("${")):
        return None
    src = re.sub(r"^\$\{?HOME\}?", HOME, src)
    src = re.sub(r"^\$\{?PWD\}?|^\$\(pwd\)", cwd, src)
    if "$" in src or "`" in src:
        raise Block(
            f"docker mount source '{src}' has an unresolved variable; spell it out"
        )
    return os.path.realpath(os.path.join(cwd, os.path.expanduser(src)))


def check_docker(argv: list[str], cwd: str) -> None:
    args = argv[1:]
    if args[:1] == ["container"]:
        args = args[1:]
    if not args or args[0] not in ("run", "create"):
        return
    sources: list[str] = []
    privileged = False
    # ponytail: scans every token instead of modelling docker's option table, so a
    # `-v src:dst` after the image name is also checked (harmless over-match).
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--privileged" or a.startswith("--privileged="):
            privileged = a in ("--privileged", "--privileged=true")
        elif a in ("-v", "--volume", "--mount"):
            val = args[i + 1] if i + 1 < len(args) else ""
            i += 1
            sources.append(mount_source(a, val))
        elif a.startswith(("--volume=", "--mount=")):
            key, val = a.split("=", 1)
            sources.append(mount_source(key, val))
        elif a.startswith("-v") and len(a) > 2:
            sources.append(mount_source("-v", a[2:]))
        i += 1
    for src in sources:
        hp = host_path(src, cwd)
        if hp is None:
            continue
        if hp in SENSITIVE_EXACT or any(
            hp == t or hp.startswith(t + "/") for t in SENSITIVE_TREES
        ):
            raise Block(f"docker mount of sensitive host path '{hp}' is not allowed")
    if privileged:
        raise Ask("docker --privileged gives the container full host access")


def mount_source(flag: str, val: str) -> str:
    if flag == "--mount":
        for kv in val.split(","):
            k, _, v = kv.partition("=")
            if k in ("source", "src"):
                return v if v.startswith(("/", ".", "~", "$")) else ""
        return ""
    return val.split(":", 1)[0] if ":" in val else ""


# ---------------------------------------------------------------- fetch / sql


def reads_stdin_code(argv: list[str]) -> bool:
    name = name_of(argv)
    if name in SHELLS:
        for a in argv[1:]:
            if a == "-c":
                return False
            if a in ("-s", "--"):
                return True
            if not a.startswith("-"):
                return False
        return True
    if re.match(r"^(python3?(\.\d+)?|perl|ruby|node)$", name):
        for a in argv[1:]:
            if a in ("-c", "-e", "-m", "-E", "--eval", "-p"):
                return False
            if a == "-":
                return True
            if not a.startswith("-"):
                return False
        return True
    return name == "source" or name == "."


FETCH_SUBST = re.compile(r"(\$\(|`)\s*(\S*/)?(curl|wget)\b")
PROC_SUBST = re.compile(
    r"(^|[;&|(\s])(source|\.|eval|(ba|z|da|k)?sh|python3?|perl|ruby|node)"
    r"\s+(-\S+\s+)*<\(\s*(\S*/)?(curl|wget)\b"
)


def check_fetch(pipeline: list[list[str]], raw: str) -> None:
    seen_fetch = False
    for seg in pipeline:
        argv = strip_wrappers(seg)
        if name_of(argv) in ("curl", "wget"):
            seen_fetch = True
        elif seen_fetch and argv and reads_stdin_code(argv):
            raise Block(
                "piping a download into a shell or interpreter; download, inspect, run"
            )
        # bash -c "$(curl ...)", eval "$(curl ...)", python3 -c "$(curl ...)"
        if (
            argv
            and (name_of(argv) in SHELLS | INTERPRETERS | {"eval", "source", "."})
            and any(FETCH_SUBST.search(t) for t in argv[1:])
        ):
            raise Block(
                "running downloaded code via substitution; download, inspect, then run"
            )
    # bash <(curl ...), source <(wget ...): the tokenizer splits `<(`; match text.
    if PROC_SUBST.search(raw):
        raise Block(
            "running downloaded code via process substitution; download, inspect, run"
        )


SQL_DESTRUCTIVE = re.compile(
    r"(?i)\b(drop\s+(table|database|schema|index|view)|truncate(\s+table)?\s+\w)"
)


def check_sql(pipes: list[list[list[str]]], raw: str) -> None:
    if any(
        name_of(strip_wrappers(s)) in DB_CLIENTS for p in pipes for s in p
    ) and SQL_DESTRUCTIVE.search(raw):
        raise Ask("destructive SQL (DROP/TRUNCATE) sent to a database client")


# ---------------------------------------------------------------- main


def check_env(seg: list[str], argv: list[str]) -> None:
    """Assignments in front of a command (or exported) that disable the git hooks."""
    assigned = seg[: len(seg) - len(argv)]
    if name_of(argv) in ("export", "declare", "typeset"):
        assigned += argv[1:]
    for t in assigned:
        if OVERRIDE_VARS.match(t):
            raise Block(f"{t.split('=')[0]} is a human-only override")
        if re.match(r"(?i)GIT_CONFIG_\w*=.*hookspath", t):
            raise Block(
                "setting core.hooksPath through GIT_CONFIG_* bypasses the git hooks"
            )


def guard(cmd: str, cwd: str, groups: set[str]) -> None:
    pipes = pipelines(cmd)
    ctx: dict = {}
    run_cwd = cwd
    for pipe in pipes:
        if "fetch" in groups:
            check_fetch(pipe, cmd)
        for seg in pipe:
            argv = strip_wrappers(seg)
            name = name_of(argv)
            if "git" in groups:
                check_env(seg, argv)
            if name == "cd" and len(argv) > 1:
                run_cwd = os.path.join(run_cwd, os.path.expanduser(argv[1]))
            elif name == "git" and "git" in groups:
                check_git(argv, run_cwd, ctx)
            elif name in ("docker", "podman") and "docker" in groups:
                check_docker(argv, run_cwd)
    if "sql" in groups:
        check_sql(pipes, cmd)


ALL_GROUPS = {"git", "docker", "fetch", "sql"}


def main() -> int:
    groups = set(sys.argv[1:]) & ALL_GROUPS or ALL_GROUPS
    try:
        data = json.load(sys.stdin)
    except ValueError:
        print("BLOCKED: bash-guard got invalid hook input", file=sys.stderr)
        return 2
    cmd = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or os.getcwd()
    try:
        guard(cmd, cwd, groups)
    except Block as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    except Ask as exc:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "ask",
                        "permissionDecisionReason": str(exc),
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
