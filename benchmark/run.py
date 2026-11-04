"""Benchmark the agent with its minimal-code rules versus a plain baseline prompt.

Each task is copied to a temp dir, the agent runs with every action auto-approved,
then the ORIGINAL test files are restored and run, so edited tests cannot pass.

    PYTHONPATH=src python3 benchmark/run.py [--runs 1] [--model NAME]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from local_agent_ops.agent import DEFAULT_MODEL, SYSTEM_PROMPT, ollama_chat, run_agent
from local_agent_ops.tools import Workspace

HERE = Path(__file__).parent
BASELINE_PROMPT = """You are a coding agent working inside one repository. Complete the user's task.
Commands already run in the repository root: use `python3 -m unittest`, never `cd`, pipes, or other shell syntax.
When done, reply with a short summary and stop calling tools."""
MODES = {"minimal-rules": SYSTEM_PROMPT, "baseline": BASELINE_PROMPT}


def run_task(task_dir: Path, system: str, model: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / task_dir.name
        shutil.copytree(task_dir, work, ignore=shutil.ignore_patterns("task.txt", "__pycache__"))
        workspace = Workspace(work, approve=lambda _: True)
        calls: list[str] = []
        start = time.monotonic()
        try:
            run_agent((task_dir / "task.txt").read_text(), workspace, ollama_chat(model), log=calls.append, system=system)
        except Exception as error:  # a crashed run counts as a failure, not a crashed benchmark
            calls.append(f"crash: {error}")
        seconds = time.monotonic() - start
        added, removed = workspace.net_lines()
        for test in task_dir.glob("test_*.py"):
            shutil.copy(test, work / test.name)
        graded = subprocess.run([sys.executable, "-m", "unittest"], cwd=work, capture_output=True, timeout=60)
        return {"passed": graded.returncode == 0, "added": added, "removed": removed,
                "tool_calls": len(calls), "seconds": round(seconds, 1)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--only", default="", help="Run only tasks whose name contains this text, e.g. 'feature'.")
    parser.add_argument("--out", default="results.json")
    args = parser.parse_args()

    results = []
    for task_dir in sorted(p for p in (HERE / "tasks").iterdir() if p.is_dir() and args.only in p.name):
        for mode, system in MODES.items():
            for run in range(args.runs):
                result = {"task": task_dir.name, "mode": mode, "run": run, **run_task(task_dir, system, args.model)}
                print(json.dumps(result), flush=True)
                results.append(result)

    (HERE / args.out).write_text(json.dumps({"model": args.model, "results": results}, indent=2) + "\n")
    print("\n" + summarize(results))


def summarize(results: list[dict]) -> str:
    lines = ["| Mode | Pass rate | Avg net lines changed | Avg tool calls | Avg seconds |", "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        rows = [r for r in results if r["mode"] == mode]
        n = len(rows)
        lines.append(f"| {mode} | {sum(r['passed'] for r in rows)}/{n} "
                     f"| {sum(r['added'] + r['removed'] for r in rows) / n:.1f} "
                     f"| {sum(r['tool_calls'] for r in rows) / n:.1f} | {sum(r['seconds'] for r in rows) / n:.0f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
