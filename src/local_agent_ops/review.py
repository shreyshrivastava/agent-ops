"""`agent-ops review`: a read-only review of `git diff <base>`. Nothing is written or run."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from .agent import Chat, run_agent
from .tools import READ_ONLY_TOOLS, Workspace

MAX_DIFF_CHARS = 12000  # shortcut: a longer diff is cut; review a smaller range if it is
REVIEW_PROMPT = """You review a code change for a developer before they push it. You can only read files.
1. Read the diff, and any file you need to understand what the changed lines do.
2. Reply with numbered findings, most serious first. Each one gives `file:line`, what is wrong, and why it matters:
   bugs, missed edge cases, security risks, and changes that break callers or tests.
3. Only report what you have read. Say when you are unsure. If you find nothing wrong, say "No problems found."."""


def review_diff(root: Path, base: str, chat: Chat, max_steps: int = 10, log: Callable[[str], None] = print) -> str:
    diff = subprocess.run(["git", "diff", base], cwd=root, capture_output=True, text=True, check=True).stdout
    if not diff.strip():
        return f"No changes against {base}."
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n[diff cut here; review a smaller range to see the rest]"
    workspace = Workspace(root, lambda _: False, dry_run=True)  # reviewing never writes or runs anything
    return run_agent(f"Review this change (`git diff {base}`):\n```diff\n{diff}```", workspace, chat, max_steps,
                     log=log, system=REVIEW_PROMPT, tools=READ_ONLY_TOOLS)
