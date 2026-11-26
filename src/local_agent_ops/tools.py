"""Workspace-confined tools the agent may call. Writes and commands are approval-gated."""

from __future__ import annotations

import difflib
import fnmatch
import os
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

ALLOWED_COMMANDS = {"python", "python3", "pytest", "ls", "cat", "grep", "git"}
BLOCKED_GIT = {"push", "reset", "clean", "rebase", "commit"}
BLOCKED_GIT_FLAGS = {"-C", "--git-dir", "--work-tree"}  # would point git at another repository
MAX_OUTPUT = 4000
MAX_READ = 100_000
MAX_DIFF = 40  # changed lines allowed per edit to an existing file: keep fixes minimal
# Python's .pyc cache trusts file size + mtime (1s). An edit of the same size in the same second
# would otherwise run the stale cached code, so commands the agent runs never write bytecode.
NO_BYTECODE = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

Approver = Callable[[str], bool]


class Workspace:
    def __init__(self, root: Path, approve: Approver, dry_run: bool = False, read_only: tuple[str, ...] = (),
                 max_diff: int = MAX_DIFF) -> None:
        self.root = root.resolve()
        self.approve = approve
        self.dry_run = dry_run
        self.max_diff = max_diff  # 0 disables the limit
        self.read_only = read_only  # glob patterns, e.g. test files during `agent-ops fix`
        self.originals: dict[Path, str] = {}
        self.partial: set[Path] = set()
        self.plan: list[dict] = []     # the agent's checklist, kept current through update_plan
        self.changes: list[dict] = []  # every approved write: path, line counts and the agent's reason
        self.decisions: list[dict] = []  # decisions the agent recorded, flushed to DECISIONS.md by the loop
        self.attempt: dict[Path, str] = {}  # file contents before the current approach, for undoing it
        self.stale: set[Path] = set()  # files whose contents were trimmed from the model's context

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
        target = self._path(path)
        text = target.read_text(encoding="utf-8")
        self.stale.discard(target)
        if len(text) <= MAX_READ:
            return text
        # Writes replace whole files, so a file the model has only partly seen must never be written back.
        self.partial.add(target)
        return text[:MAX_READ] + f"\n\n[TRUNCATED: showing {MAX_READ} of {len(text)} characters. This file is read-only for you.]"

    def update_plan(self, steps: list) -> str:
        """Replace the plan. Each step is {"step": str, "status": "pending"|"in_progress"|"done"} or a plain string."""
        plan = []
        for item in steps or []:
            item = {"step": item, "status": "pending"} if isinstance(item, str) else dict(item)
            if not str(item.get("step", "")).strip():
                return "Error: every plan item needs a non-empty step."
            if item.get("status", "pending") not in ("pending", "in_progress", "done"):
                return f"Error: status must be pending, in_progress or done, not {item.get('status')!r}."
            plan.append({"step": str(item["step"]).strip(), "status": item.get("status", "pending")})
        self.plan = plan
        done = sum(item["status"] == "done" for item in plan)
        return f"Plan updated ({done}/{len(plan)} done)."

    def record_decision(self, decision: str, why: str) -> str:
        if not decision.strip() or not why.strip():
            return "Error: give both the decision and why."
        self.decisions.append({"decision": decision.strip(), "why": why.strip()})
        return "Decision recorded."

    def edit_file(self, path: str, old: str, new: str, reason: str = "") -> str:
        """Replace one exact, unique snippet. Far fewer tokens than rewriting the whole file."""
        target = self._path(path)
        if not target.exists():
            return f"Error: {path} does not exist. Use write_file to create it."
        text = target.read_text(encoding="utf-8")
        count = text.count(old) if old else 0
        if count != 1:
            return (f"Error: `old` must match exactly once in {path}, but it matched {count} times. "
                    "Copy it exactly from read_file and include enough surrounding lines to be unique.")
        return self._write(target, path, text.replace(old, new, 1), reason)

    def write_file(self, path: str, content: str, reason: str = "") -> str:
        target = self._path(path)
        if target in self.partial:
            return f"Refused: {path} is too large to have been read in full, so rewriting it would delete content."
        if target in self.stale:
            return f"Refused: your copy of {path} was trimmed from memory. Use edit_file, or read_file it again first."
        return self._write(target, path, content, reason)

    def undo_attempt(self) -> list[str]:
        """Put back every file the current approach changed (each restore is shown and approved). Returns the paths restored."""
        restored = []
        for target, before in list(self.attempt.items()):
            relative = target.relative_to(self.root).as_posix()
            if self._write(target, relative, before, "undo a failed approach before trying another", limit=False).startswith("Wrote"):
                restored.append(relative)
        self.attempt = {}
        return restored

    def _write(self, target: Path, path: str, content: str, reason: str, limit: bool = True) -> str:
        relative = target.relative_to(self.root).as_posix()
        if relative.split("/")[0] == ".agent-ops":
            return "Refused: .agent-ops holds this agent's own run traces and cannot be edited."
        if any(fnmatch.fnmatch(relative, p) or fnmatch.fnmatch(target.name, p) for p in self.read_only):
            return f"Refused: {path} is read-only in this mode. Fix the code under test, not the test."
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        diff = list(difflib.unified_diff(old.splitlines(), content.splitlines(), f"a/{path}", f"b/{path}", lineterm=""))
        if not diff:
            return "No change."
        added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
        if limit and self.max_diff and old and added + removed > self.max_diff:
            return (f"Refused: this edit changes {added + removed} lines of {path}; the limit is {self.max_diff}. "
                    "Make the smallest change that fixes the problem: touch only the lines that are wrong, "
                    "and do not reformat, rename or refactor anything else.")
        if self.dry_run:
            return f"DRY RUN: would change {path} (+{added} -{removed})."
        why = f"\nWhy: {reason.strip()}" if reason.strip() else ""
        if not self.approve("\n".join(diff) + f"\n{why}\nWrite {path}?"):
            return "User rejected this change. Try a smaller change or explain why it is needed."
        self.originals.setdefault(target, old)
        self.attempt.setdefault(target, old)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        self.changes.append({"path": relative, "added": added, "removed": removed, "reason": reason.strip()})
        return f"Wrote {path} (+{added} -{removed})."

    def run_command(self, command: str) -> str:
        argv = shlex.split(command)
        if not argv or argv[0] not in ALLOWED_COMMANDS:
            return (f"Blocked: only {sorted(ALLOWED_COMMANDS)} are allowed, with no shell operators. "
                    "Commands already run in the workspace root, so never use cd.")
        if argv[0] == "git" and (blocked := [a for a in argv[1:] if a in BLOCKED_GIT or a.split("=")[0] in BLOCKED_GIT_FLAGS]):
            return f"Blocked: git {blocked[0]} is not allowed."
        if outside := self._outside_paths(argv[1:]):
            return f"Blocked: {outside[0]} is outside the workspace."
        if self.dry_run:
            return f"DRY RUN: would run `{command}`."
        if not self.approve(f"Run `{command}`?"):
            return "User rejected this command."
        result = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, timeout=120, env=NO_BYTECODE)
        return f"exit={result.returncode}\n{(result.stdout + result.stderr)[-MAX_OUTPUT:]}"

    def _outside_paths(self, args: list[str]) -> list[str]:
        """Arguments (or --flag=value values) that look like paths and resolve outside the workspace."""
        outside = []
        for arg in args:
            value = arg.split("=", 1)[1] if arg.startswith("-") and "=" in arg else arg
            if value.startswith(("/", "~")) or ".." in value:
                path = (self.root / Path(value).expanduser()).resolve()
                if not path.is_relative_to(self.root):
                    outside.append(arg)
        return outside


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "list_files", "description": "List files in the workspace.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a UTF-8 file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Create a new file, or replace a whole file (prefer edit_file for existing files). The user sees a diff and your reason, and must approve.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"},
            "reason": {"type": "string", "description": "One or two sentences: what this change does and why it is needed."}},
            "required": ["path", "content", "reason"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Preferred way to change an existing file: replace one exact snippet `old` (copied from read_file, unique in the file) with `new`.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"},
            "reason": {"type": "string", "description": "What this change does and why it is needed."}},
            "required": ["path", "old", "new", "reason"]}}},
    {"type": "function", "function": {"name": "record_decision", "description": "Log an important decision (an approach chosen, an option rejected) and why, in the project's decision log.",
        "parameters": {"type": "object", "properties": {"decision": {"type": "string"}, "why": {"type": "string"}}, "required": ["decision", "why"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Run an allowlisted command (python, pytest, ls, cat, grep, read-only git) in the workspace.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "update_plan", "description": "Write your step-by-step plan for the task and mark progress. Call it first, and again whenever a step is finished.",
        "parameters": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object", "properties": {
            "step": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}},
            "required": ["step", "status"]}}}, "required": ["steps"]}}},
]

READ_ONLY_TOOLS = {"list_files", "read_file"}
