"""The shared helpers of the check.py tests: the loaded module and ways to run and
change an installed kit."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
CHECK = KIT / "check.py"
REPO = KIT.parents[2]



_spec = importlib.util.spec_from_file_location("kit_check", CHECK)
check_py = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_py)


def check(kit, *args, cwd=None, env=None):
    p = subprocess.run(
        [sys.executable, str(CHECK), *args],
        capture_output=True,
        text=True,
        env=dict(kit["env"], **(env or {})),
        cwd=cwd or kit["root"],
    )
    return p.returncode, p.stdout + p.stderr


def replace_script(kit, rel, body):
    path = kit["home"] / rel
    path.write_text(body)
    path.chmod(0o755)


def edit_json(kit, rel, change):
    path = kit["home"] / rel
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, indent=2))


def snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
