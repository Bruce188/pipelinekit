#!/usr/bin/env python3
"""The judge loop helper: keeps the state of a plan or build loop and says what
comes next.

Commands: start, brief, save, round, status, diagnosed, resume, accept, abandon,
settle, leftovers and skip; `loop.py <command> --help` shows each. Every run
ends on one line, "<Word>: <what happened>. Next: <command, or who acts>.".
Exit codes: 0 done or go on; 1 fix, then another round; 2 refused or could not
run; 3 stop, do not fix: the line says who acts next.

Stdlib only, Python 3.10 or later, like check.py and ship.py.
"""

# ruff: noqa: E402, F403, F405
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loop_commands import *

if __name__ == "__main__":
    sys.exit(main())
