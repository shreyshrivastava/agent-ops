"""Loop memory: the agent's plan and every change it made (with why), kept in .agent-ops/progress.json.

Each round of `fix`, and each re-run of `code` with the same task, starts by reading this file, so the
agent knows what is already done instead of starting from scratch.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .trace import TRACE_DIR, mask

STATUSES = ("pending", "in_progress", "done")


class Progress:
    def __init__(self, root: Path) -> None:
        self.path = root / TRACE_DIR / "progress.json"
        self.log_path = root / TRACE_DIR / "DECISIONS.md"  # append-only, kept across tasks
        self.task, self.plan, self.changes, self.notes, self.failed = "", [], [], [], []
        self.done_when, self.check_command = [], ""
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.task, self.plan = data.get("task", ""), data.get("plan", [])
                self.changes, self.notes = data.get("changes", []), data.get("notes", [])
                self.failed = data.get("failed_approaches", [])
                self.done_when, self.check_command = data.get("done_when", []), data.get("check_command", "")
            except (json.JSONDecodeError, AttributeError):
                pass  # a corrupt file is treated as no memory

    def begin(self, task: str, fresh: bool = False) -> bool:
        """Start or continue `task`. Returns True when earlier progress on the same task is being resumed."""
        if fresh or task != self.task:
            self.task, self.plan, self.changes, self.notes, self.failed = task, [], [], [], []
            self.done_when, self.check_command = [], ""
            self.decide(f"Started task: {task}", "fresh start" if fresh else "new task")
            return False
        return bool(self.plan or self.changes or self.notes or self.failed)

    def note(self, text: str) -> None:
        self.notes.append(text)

    def fail_approach(self, approach: str, evidence: str) -> None:
        self.failed.append({"approach": approach, "evidence": evidence[-300:]})
        self.decide(f"Abandoned approach #{len(self.failed)}: {approach}", f"it did not fix the problem: {evidence[-300:]}")

    def decide(self, decision: str, why: str) -> None:
        """Append one entry to DECISIONS.md, the human-readable log of what the agent decided and why."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        (self.log_path.parent / ".gitignore").write_text("*\n", encoding="utf-8")
        new = not self.log_path.exists()
        with self.log_path.open("a", encoding="utf-8") as file:
            if new:
                file.write("# Decision log\n\nWhat the agent decided, and why. Newest at the bottom.\n")
            file.write(mask(f"\n- **{datetime.now():%Y-%m-%d %H:%M}** {decision}\n  - why: {why}\n"))

    def briefing(self) -> str:
        """What the agent is told at the start of a run about work already done."""
        if not (self.plan or self.changes or self.notes or self.failed):
            return ""
        lines = ["Progress from earlier runs on this task (already applied to the files):"]
        if self.done_when:
            lines += ["Done when:"] + [f"  - {c}" for c in self.done_when]
            if self.check_command:
                lines.append(f"  - `{self.check_command}` passes")
        if self.plan:
            lines += ["Plan:"] + [f"  [{item['status']}] {item['step']}" for item in self.plan]
        if self.changes:  # only the latest, to keep the prompt small
            lines += ["Changes made:"] + [f"  {c['path']} (+{c['added']} -{c['removed']}): {c['reason'] or 'no reason given'}"
                                          for c in self.changes[-10:]]
        if self.failed:
            lines += ["Approaches that FAILED (their edits were undone). Do not repeat them; try something different:"]
            lines += [f"  {n}. {f['approach']} -> {f['evidence'][-150:]}" for n, f in enumerate(self.failed, 1)]
        if self.notes:
            lines += ["Notes:"] + [f"  {n}" for n in self.notes[-5:]]
        lines.append("Continue from here. Do not redo finished steps; re-read files before editing them.")
        return "\n".join(lines)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        (self.path.parent / ".gitignore").write_text("*\n", encoding="utf-8")
        data = {"task": self.task, "plan": self.plan, "changes": self.changes, "notes": self.notes,
                "failed_approaches": self.failed, "done_when": self.done_when, "check_command": self.check_command}
        self.path.write_text(json.dumps(mask(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_plan(plan: list[dict]) -> str:
    marks = {"pending": " ", "in_progress": "~", "done": "x"}
    return "\n".join(f"[{marks.get(item['status'], ' ')}] {item['step']}" for item in plan) or "(empty plan)"


def render_changes(changes: list[dict]) -> str:
    """A numbered, step-by-step account of what was changed and why."""
    return "\n".join(f"{n}. {c['path']} (+{c['added']} -{c['removed']})\n   why: {c['reason'] or 'no reason given'}"
                     for n, c in enumerate(changes, 1)) or "No files were changed."
