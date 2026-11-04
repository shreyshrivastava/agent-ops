"""Run traces: one JSONL file per agent run, kept in <workspace>/.agent-ops/runs/ and never committed."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .audit import SECRET_VALUE_PATTERNS

TRACE_DIR = ".agent-ops"
VERSION = 1
# The auditor's patterns match whole values; unanchored copies find secrets inside file contents and output.
_SECRETS = [re.compile(p.pattern.strip("^$"), p.flags) for p in SECRET_VALUE_PATTERNS]


def mask(value: Any) -> Any:
    if isinstance(value, str):
        for pattern in _SECRETS:
            value = pattern.sub("[MASKED]", value)
        return value
    if isinstance(value, dict):
        return {k: mask(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    return value


class Trace:
    def __init__(self, root: Path, task: str, model: str = "") -> None:
        base = root / TRACE_DIR
        (base / "runs").mkdir(parents=True, exist_ok=True)
        (base / ".gitignore").write_text("*\n", encoding="utf-8")  # ignore traces in any repo without touching its .gitignore
        self.path = base / "runs" / f"{datetime.now():%Y%m%d-%H%M%S-%f}.jsonl"
        self.start = time.monotonic()
        self.event("start", task=task, model=model)

    def event(self, kind: str, **data: Any) -> None:
        line = {"v": VERSION, "t": round(time.monotonic() - self.start, 2), "kind": kind, **mask(data)}
        with self.path.open("a", encoding="utf-8") as file:  # append and close per event so a crash leaves a readable trace
            file.write(json.dumps(line, ensure_ascii=False) + "\n")


def list_runs(root: Path) -> list[dict]:
    runs = []
    for path in sorted((root / TRACE_DIR / "runs").glob("*.jsonl"), reverse=True):
        events = load(path)
        end = next((e for e in reversed(events) if e["kind"] == "end"), None)
        runs.append({"run": path.stem, "task": events[0].get("task", "") if events else "",
                     "steps": sum(e["kind"] == "tool" for e in events),
                     "outcome": end["reason"] if end else "incomplete", "seconds": events[-1]["t"] if events else 0})
    return runs


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_run(root: Path, run: str) -> Path:
    path = Path(run) if run.endswith(".jsonl") else root / TRACE_DIR / "runs" / f"{run}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No trace named {run}. Run `agent-ops runs` to list them.")
    return path


def render(events: list[dict]) -> str:
    lines = []
    for e in events:
        stamp = f"[{e['t']:>6.1f}s]"
        if e["kind"] == "start":
            lines.append(f"{stamp} task: {e['task']}  (model: {e.get('model') or 'unknown'})")
        elif e["kind"] == "model" and e.get("content"):
            lines.append(f"{stamp} model: {e['content'][:300]}")
        elif e["kind"] == "tool":
            args = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in e["args"].items() if k != "content")
            lines.append(f"{stamp} → {e['name']}({args})\n          {e['result'][:300].replace(chr(10), chr(10) + ' ' * 10)}")
        elif e["kind"] == "end":
            lines.append(f"{stamp} end ({e['reason']}): {e['summary'][:300]}")
    return "\n".join(lines)
