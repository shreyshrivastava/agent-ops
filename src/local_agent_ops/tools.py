"""Workspace-confined tools the agent may call. Writes and commands are approval-gated."""

from __future__ import annotations

import difflib
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

ALLOWED_COMMANDS = {"python", "python3", "pytest", "ls", "cat", "grep", "git"}
BLOCKED_GIT = {"push", "reset", "clean", "rebase", "commit"}
MAX_OUTPUT = 4000

Approver = Callable[[str], bool]


class Workspace:
    def __init__(self, root: Path, approve: Approver, dry_run: bool = False) -> None:
        self.root = root.resolve()
        self.approve = approve
        self.dry_run = dry_run
        self.originals: dict[Path, str] = {}

    def net_lines(self) -> tuple[int, int]:
        """Lines added and removed by the final state of every file the agent wrote, versus where it started."""
        added = removed = 0
        for path, old in self.originals.items():
            new = path.read_text(encoding="utf-8") if path.exists() else ""
            for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm=""):
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1
        return added, removed

    def _path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise PermissionError(f"{relative} is outside the workspace")
        return path

    def list_files(self, path: str = ".") -> str:
        base = self._path(path)
        files = [
            str(p.relative_to(self.root))
            for p in sorted(base.rglob("*"))
            if p.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in p.relative_to(self.root).parts)
        ]
        return "\n".join(files[:200]) or "(empty)"

    def read_file(self, path: str) -> str:
        return self._path(path).read_text(encoding="utf-8")[:MAX_OUTPUT * 4]

    def write_file(self, path: str, content: str) -> str:
        target = self._path(path)
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        diff = list(difflib.unified_diff(old.splitlines(), content.splitlines(), f"a/{path}", f"b/{path}", lineterm=""))
        if not diff:
            return "No change."
        added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
        if self.dry_run:
            return f"DRY RUN: would change {path} (+{added} -{removed})."
        if not self.approve("\n".join(diff) + f"\n\nWrite {path}?"):
            return "User rejected this change. Try a smaller change or explain why it is needed."
        self.originals.setdefault(target, old)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        return f"Wrote {path} (+{added} -{removed})."

    def run_command(self, command: str) -> str:
        argv = shlex.split(command)
        if not argv or argv[0] not in ALLOWED_COMMANDS:
            return (f"Blocked: only {sorted(ALLOWED_COMMANDS)} are allowed, with no shell operators. "
                    "Commands already run in the workspace root, so never use cd.")
        if argv[0] == "git" and len(argv) > 1 and argv[1] in BLOCKED_GIT:
            return f"Blocked: git {argv[1]} is not allowed."
        if self.dry_run:
            return f"DRY RUN: would run `{command}`."
        if not self.approve(f"Run `{command}`?"):
            return "User rejected this command."
        result = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, timeout=120)
        return f"exit={result.returncode}\n{(result.stdout + result.stderr)[-MAX_OUTPUT:]}"


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "list_files", "description": "List files in the workspace.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a UTF-8 file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Replace a file's full content. The user sees a diff and must approve.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Run an allowlisted command (python, pytest, ls, cat, grep, read-only git) in the workspace.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
]
