#!/usr/bin/env python3
"""Test env-scrub.py --prefix-args mode.

Verifies the prefix-args mode emits one token per line so callers can use
`mapfile -t` (bash) to read into an argv array — supporting exec-style argv
dispatch instead of shell-string concatenation.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "env-scrub.py"


def run_prefix_args() -> list[str]:
    result = subprocess.run(
        ["python3", str(SCRIPT), "--prefix-args"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def test_first_token_is_env():
    tokens = run_prefix_args()
    assert tokens, "prefix-args produced no output"
    assert tokens[0] == "env", f"first token should be 'env', got {tokens[0]!r}"


def test_alternating_dash_u_and_varname():
    tokens = run_prefix_args()
    body = tokens[1:]
    assert len(body) % 2 == 0, f"body must have even length, got {len(body)}"
    for i in range(0, len(body), 2):
        assert body[i] == "-u", f"token {i+1} should be '-u', got {body[i]!r}"
        assert body[i + 1].isidentifier(), (
            f"token {i+2} should be an env var name, got {body[i+1]!r}"
        )


def test_no_whitespace_in_any_token():
    tokens = run_prefix_args()
    for t in tokens:
        assert " " not in t and "\t" not in t, (
            f"token {t!r} contains whitespace; would break mapfile -t"
        )


def test_includes_known_scrub_var():
    tokens = run_prefix_args()
    assert "ANTHROPIC_API_KEY" in tokens, (
        "ANTHROPIC_API_KEY missing from prefix-args output"
    )


def test_preserved_vars_excluded():
    tokens = run_prefix_args()
    assert "GITHUB_TOKEN" not in tokens, "GITHUB_TOKEN should be preserved, not scrubbed"
    assert "GH_TOKEN" not in tokens, "GH_TOKEN should be preserved, not scrubbed"


def main() -> int:
    failures: list[str] = []
    for name in (
        "test_first_token_is_env",
        "test_alternating_dash_u_and_varname",
        "test_no_whitespace_in_any_token",
        "test_includes_known_scrub_var",
        "test_preserved_vars_excluded",
    ):
        try:
            globals()[name]()
            print(f"PASS {name}")
        except AssertionError as e:
            failures.append(f"{name}: {e}")
            print(f"FAIL {name}: {e}")
    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nall pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
