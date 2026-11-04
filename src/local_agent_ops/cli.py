"""Command-line interface: `code`, `fix`, `runs`, `replay` and `audit`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import DEFAULT_HOST, DEFAULT_MODEL, ollama_chat, run_agent
from .audit import audit_manifest
from .fix import TEST_FILES, fix_tests
from .tools import Workspace
from .trace import Trace, find_run, list_runs, load, render


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-ops", description="Local, approval-gated coding agent and manifest auditor.")
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit", help="Audit a sanitized JSON manifest before sharing it.")
    audit.add_argument("manifest", type=Path)
    audit.add_argument("--format", choices=("text", "markdown"), default="text")

    code = commands.add_parser("code", help="Run the local coding agent on a task.")
    code.add_argument("task")
    fix = commands.add_parser("fix", help="Run the tests and let the agent fix failures, up to --rounds times.")
    fix.add_argument("--test-cmd", default="python3 -m unittest")
    fix.add_argument("--rounds", type=int, default=3)
    for sub in (code, fix):
        sub.add_argument("--workspace", type=Path, default=Path("."))
        sub.add_argument("--model", default=DEFAULT_MODEL)
        sub.add_argument("--host", default=DEFAULT_HOST)
        sub.add_argument("--max-steps", type=int, default=15)
        sub.add_argument("--dry-run", action="store_true", help="Show intended writes and commands without doing them.")
        sub.add_argument("--yes", action="store_true", help="Approve every write and command (use only in a throwaway workspace).")
    code.add_argument("--no-trace", action="store_true", help="Do not save a run trace.")

    runs = commands.add_parser("runs", help="List saved run traces.")
    replay = commands.add_parser("replay", help="Show a saved run step by step.")
    replay.add_argument("run", help="Run name from `agent-ops runs`, or a path to a .jsonl trace.")
    for sub in (runs, replay):
        sub.add_argument("--workspace", type=Path, default=Path("."))

    args = parser.parse_args(argv)
    handlers = {"audit": lambda: _audit(args, parser), "code": lambda: _code(args), "fix": lambda: _fix(args),
                "runs": lambda: _runs(args), "replay": lambda: _replay(args)}
    return handlers[args.command]()


def _workspace(args: argparse.Namespace, read_only: tuple[str, ...] = ()) -> Workspace:
    def approve(prompt: str) -> bool:
        print(f"\n{prompt}")
        if args.yes:
            print("[auto-approved]")
            return True
        return input("Approve? [y/N] ").strip().lower() == "y"

    workspace = Workspace(args.workspace, approve, dry_run=args.dry_run, read_only=read_only)
    print(f"agent-ops · model={args.model} · workspace={workspace.root}")
    return workspace


def _code(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    trace = None if args.no_trace else Trace(workspace.root, args.task, args.model)
    try:
        summary = run_agent(args.task, workspace, ollama_chat(args.model, args.host), args.max_steps, trace=trace)
    except OSError as error:
        print(f"Cannot reach Ollama at {args.host}: {error}", file=sys.stderr)
        return 2
    added, removed = workspace.net_lines()
    print(f"\n{summary}\n\nnet: +{added} -{removed} lines")
    if trace:
        print(f"trace: agent-ops replay {trace.path.stem} --workspace {args.workspace}")
    return 0


def _fix(args: argparse.Namespace) -> int:
    workspace = _workspace(args, read_only=TEST_FILES)
    try:
        result = fix_tests(workspace, ollama_chat(args.model, args.host), args.test_cmd, args.rounds,
                           args.max_steps, args.model)
    except OSError as error:
        print(f"Cannot reach Ollama at {args.host}: {error}", file=sys.stderr)
        return 2
    history = " → ".join("?" if n is None else str(n) for n in result["failing"])
    print(f"\n{'PASS' if result['passed'] else 'FAIL'}: {result['reason']} · failing tests {history} · "
          f"net +{result['added']} -{result['removed']} lines")
    for name in result["traces"]:
        print(f"trace: agent-ops replay {Path(name).stem} --workspace {args.workspace}")
    return 0 if result["passed"] else 1


def _runs(args: argparse.Namespace) -> int:
    rows = list_runs(args.workspace.resolve())
    if not rows:
        print("No runs yet.")
    for row in rows:
        print(f"{row['run']}  {row['outcome']:<11} {row['steps']:>3} steps {row['seconds']:>7.1f}s  {row['task'][:70]!r}")
    return 0


def _replay(args: argparse.Namespace) -> int:
    try:
        print(render(load(find_run(args.workspace.resolve(), args.run))))
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def _audit(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        parser.error(f"Cannot read JSON manifest: {error}")

    result = audit_manifest(manifest)
    print(_render(result, args.format))
    return 1 if result["errors"] else 0


def _render(result: dict[str, list[str]], output_format: str) -> str:
    if output_format == "markdown":
        lines = ["# Agent deployment audit", ""]
        for heading, items in (("Errors", result["errors"]), ("Warnings", result["warnings"])):
            lines.extend((f"## {heading}", *([f"- {item}" for item in items] or ["- None"]), ""))
        return "\n".join(lines).rstrip()

    lines = ["Agent deployment audit"]
    for label, items in (("ERROR", result["errors"]), ("WARNING", result["warnings"])):
        lines.extend(f"{label}: {item}" for item in items)
    return "\n".join(lines + (["PASS: no blocking findings"] if not result["errors"] else []))
