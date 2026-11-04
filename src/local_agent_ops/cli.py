"""Command-line interface: `audit` a manifest or run the local coding agent with `code`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import DEFAULT_HOST, DEFAULT_MODEL, ollama_chat, run_agent
from .audit import audit_manifest
from .tools import Workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-ops", description="Local, approval-gated coding agent and manifest auditor.")
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit", help="Audit a sanitized JSON manifest before sharing it.")
    audit.add_argument("manifest", type=Path)
    audit.add_argument("--format", choices=("text", "markdown"), default="text")

    code = commands.add_parser("code", help="Run the local coding agent on a task.")
    code.add_argument("task")
    code.add_argument("--workspace", type=Path, default=Path("."))
    code.add_argument("--model", default=DEFAULT_MODEL)
    code.add_argument("--host", default=DEFAULT_HOST)
    code.add_argument("--max-steps", type=int, default=15)
    code.add_argument("--dry-run", action="store_true", help="Show intended writes and commands without doing them.")
    code.add_argument("--yes", action="store_true", help="Approve every write and command (use only in a throwaway workspace).")

    args = parser.parse_args(argv)
    return _audit(args, parser) if args.command == "audit" else _code(args)


def _code(args: argparse.Namespace) -> int:
    def approve(prompt: str) -> bool:
        print(f"\n{prompt}")
        if args.yes:
            print("[auto-approved]")
            return True
        return input("Approve? [y/N] ").strip().lower() == "y"

    workspace = Workspace(args.workspace, approve, dry_run=args.dry_run)
    print(f"agent-ops · model={args.model} · workspace={workspace.root}")
    try:
        summary = run_agent(args.task, workspace, ollama_chat(args.model, args.host), args.max_steps)
    except OSError as error:
        print(f"Cannot reach Ollama at {args.host}: {error}", file=sys.stderr)
        return 2
    added, removed = workspace.net_lines()
    print(f"\n{summary}\n\nnet: +{added} -{removed} lines")
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
