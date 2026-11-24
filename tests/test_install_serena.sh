#!/usr/bin/env bash
# The installer's serena step, against a fake uv and a fake serena in throwaway
# homes. PATH holds only the fakes and the system folders, so no serena or uv
# of the caller's is found or run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
REF="$(sed -n 's/^SERENA_REF="\${SERENA_REF:-\([0-9a-f]*\)}"$/\1/p' "$REPO_ROOT/scripts/install.sh")"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo "test_install_serena: no pinned SERENA_REF in install.sh" >&2; exit 1; }
NEW="start-mcp-server --context claude-code --project-from-cwd --agent-interface tools"
OLD="start-mcp-server --context claude-code --project-from-cwd"

# The project .mcp.json files pin the same commit as the installer.
for f in .mcp.json .mcp.json.template; do
  python3 - "$REPO_ROOT/$f" "$REF" <<'PY'
import json, sys
path, ref = sys.argv[1:]
args = json.load(open(path, encoding="utf-8"))["mcpServers"]["serena"]["args"]
assert f"git+https://github.com/oraios/serena@{ref}" in args, (path, args)
assert args[-2:] == ["--agent-interface", "tools"], (path, args)
PY
done
if grep -rhoE 'oraios/serena @ ?[0-9a-f]{40}|serena@[0-9a-f]{40}|\([0-9a-f]{40}\)' "$REPO_ROOT/.mcp.json" "$REPO_ROOT/.mcp.json.template" |
  grep -v "$REF" | grep -q .; then
  echo "test_install_serena: a .mcp.json comment names another serena commit" >&2; exit 1
fi

# fake_serena <bin> <version>: a serena that answers --version.
fake_serena() {
  printf '#!/bin/sh\n[ "$1" = --version ] && echo "Serena %s" && exit 0\nexit 3\n' "$2" >"$1/serena"
  chmod +x "$1/serena"
}
# home <case> [serena version] [uv: ok|fail|none]: a fresh home in $H with its bin.
home() {
  H="$T/$1"
  mkdir -p "$H/bin"
  [ -z "${2:-}" ] || fake_serena "$H/bin" "$2"
  case "${3:-ok}" in
    none) ;;
    *)
      cat >"$H/bin/uv" <<SH
#!/bin/sh
echo "\$*" >>"$H/uv.log"
[ "${3:-ok}" = fail ] && exit 1
printf '#!/bin/sh\n[ "\$1" = --version ] && echo "Serena 2.1.0" && exit 0\nexit 3\n' >"$H/bin/serena"
chmod +x "$H/bin/serena"
SH
      chmod +x "$H/bin/uv" ;;
  esac
}
install() { # output in $H/out, stderr also in $H/err
  local rc=0
  env -u CLAUDE_INSTALL_SKIP_SERENA -u SERENA_REF -u SERENA_ALLOW_ROLLING \
    PATH="$H/bin:/usr/bin:/bin" HOME="$H" CLAUDE_HOME="$H/.claude" USER_NAME="Test User" USER_EMAIL="t@example.com" \
    GIT_CONFIG_GLOBAL="$H/.gitconfig" XDG_CONFIG_HOME="$H/.config" GIT_CONFIG_NOSYSTEM=1 \
    PIPELINEKIT_STATE_DIR="$H/state" PIPELINEKIT_GIT_HOOKS=0 \
    bash "$REPO_ROOT/scripts/install.sh" >"$H/out" 2>"$H/err" || rc=$?
  cat "$H/err" >>"$H/out"
  [ "$rc" -eq 0 ] || { echo "test_install_serena: the install ($H) exited $rc" >&2; cat "$H/out" >&2; exit 1; }
}
registered() {
  python3 -c 'import json, sys; print(" ".join(json.load(open(sys.argv[1]))["mcpServers"]["serena"]["args"]))' "$H/.claude.json"
}
expect() { # expect <what> <want> <have>
  [ "$2" = "$3" ] || { echo "test_install_serena: $1: want '$2', have '$3'" >&2; cat "$H/out" >&2; exit 1; }
}

# (a) No serena: installed at the pin and registered with the tools interface.
home a "" ok
install
expect "uv call (a)" "tool install --quiet git+https://github.com/oraios/serena@$REF" "$(cat "$H/uv.log")"
expect "registration (a)" "$NEW" "$(registered)"

# (b) A serena 1.x on PATH: upgraded to the pin, with a note that the project
# files move one way, and registered with the tools interface.
home b "1.5.4.dev0-9b292a6c" ok
echo '{"keep": 1}' >"$H/.claude.json"
install
expect "uv call (b)" "tool install --force --quiet git+https://github.com/oraios/serena@$REF" "$(cat "$H/uv.log")"
grep -qF "[install] serena 1.5.4.dev0-9b292a6c cannot read the .serena/project.yml files that serena 2 writes; upgrading to $REF" "$H/out" ||
  { echo "test_install_serena: no line about the upgrade" >&2; cat "$H/out" >&2; exit 1; }
grep -qF 'serena 1.x cannot read them afterwards' "$H/out" ||
  { echo "test_install_serena: no note that the project files move one way" >&2; cat "$H/out" >&2; exit 1; }
expect "registration (b)" "$NEW" "$(registered)"
python3 -c 'import json, sys; assert json.load(open(sys.argv[1]))["keep"] == 1' "$H/.claude.json"

# (c) A serena 2.x on PATH: left as it is.
home c "2.0.0" ok
install
test ! -e "$H/uv.log" || { echo "test_install_serena: uv ran for a serena 2" >&2; exit 1; }
expect "registration (c)" "$NEW" "$(registered)"

# (d) A serena 1.x and no uv: a warning with the command, and the 1.x form,
# which that serena can start.
home d "1.5.4.dev0" none
install
grep -qF "[install][warn] serena 1.5.4.dev0 cannot read the .serena/project.yml files that serena 2 writes; upgrade it: uv tool install --force git+https://github.com/oraios/serena@$REF" "$H/err" ||
  { echo "test_install_serena: no warning naming the upgrade command" >&2; cat "$H/out" >&2; exit 1; }
expect "registration (d)" "$OLD" "$(registered)"

# (e) The upgrade fails: a warning, and the 1.x form.
home e "1.5.4.dev0" fail
install
grep -qF '[install][warn] serena upgrade failed' "$H/err" ||
  { echo "test_install_serena: no warning for the failed upgrade" >&2; cat "$H/out" >&2; exit 1; }
expect "registration (e)" "$OLD" "$(registered)"

# (f) A serena that names no version: registered in the 1.x form, with a warning.
home f "" none
printf '#!/bin/sh\nexit 2\n' >"$H/bin/serena"
chmod +x "$H/bin/serena"
install
grep -qF '[install][warn] could not read the version of' "$H/err" ||
  { echo "test_install_serena: no warning for an unknown version" >&2; cat "$H/out" >&2; exit 1; }
expect "registration (f)" "$OLD" "$(registered)"

echo "test_install_serena: PASS"