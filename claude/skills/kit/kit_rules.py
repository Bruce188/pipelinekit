"""The kit's permission rules as they read in one CLAUDE_HOME.

Stdlib only; check.py and scripts/install.sh render the rules through it.
"""

from __future__ import annotations

import os
import re

KIT_HOME = "~/.claude/"
PATH_TOOLS = ("Read", "Edit", "Write")
GLOB_CHAR = re.compile(r"[\\*?\[]")


def home_rule(rule: str, home: str) -> str:
    """A kit permission rule with its ~/.claude/ turned into this CLAUDE_HOME.

    A home below the user's home is named from ~/, any other from the root:
    // in a path rule, where a single / is the project's folder. A character
    a path rule reads as a glob is escaped. The default home stays ~/.claude/.
    """
    tool, paren, rest = rule.partition("(")
    if not paren or tool not in PATH_TOOLS or not rest.startswith(KIT_HOME):
        return rule
    home = os.path.abspath(os.path.expanduser(home))
    user = os.path.abspath(os.path.expanduser("~"))
    if user != "/" and os.path.commonpath([home, user]) == user:
        rel = os.path.relpath(home, user)
        at = "~" if rel == "." else "~/" + GLOB_CHAR.sub(r"\\\g<0>", rel)
    else:
        at = "/" + GLOB_CHAR.sub(r"\\\g<0>", home)
    return f"{tool}({at}/{rest[len(KIT_HOME) :]}"
