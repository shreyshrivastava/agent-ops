"""A minimal local coding agent: Ollama chat + tool calls + approval gates."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable

from .progress import Progress
from .tools import TOOL_SCHEMAS, Workspace
from .trace import Trace

DEFAULT_MODEL = "huihui_ai/qwen3.5-abliterated:9b"
DEFAULT_HOST = "http://127.0.0.1:11434"

SYSTEM_PROMPT = """You are a careful local coding agent working inside one repository.
Write the least code that correctly solves the task:
0. Start with set_done_criteria (what done means, and the test command that proves it), then
   update_plan with short steps. Mark each step done as you finish it, so the
   next run knows what is already done if you run out of steps.
1. Read the relevant files before changing anything. To debug, reproduce the failure first,
   find the root cause, then fix that cause rather than the symptom.
2. Prefer, in order: no change, reusing existing code, the standard library, then new code.
3. Never add a dependency, abstraction, or file the task does not need.
4. Make the minimal change: touch only the lines that are wrong. Use edit_file for existing files;
   use write_file only to create a file. Never reformat, rename, or refactor unrelated code.
   Edits over the line limit are refused.
5. If tests exist, run them after editing and fix failures. Commands already run in the
   repository root: use `python3 -m unittest`, never `cd`, pipes, or other shell syntax.
6. Every edit needs a reason: what it does and why it is needed. Use record_decision for bigger
   choices, such as which approach you take and what you rejected.
7. If a fix fails twice, do not keep tweaking it: you will be asked to try a different approach.
When done, stop calling tools and explain your work step by step as a numbered list: for each
change, what you changed, why, and what you considered and rejected."""

EXPLAIN_PROMPT = """You explain code to a developer who has not seen it before. You can only read files.
1. Read the code you were asked about, and any file it imports from this repository that you need.
2. Reply with a numbered, step-by-step walkthrough in the order the code runs: for each step say
   what it does and why it is written that way (the problem it solves, the edge case it guards).
3. Point out anything that looks like a bug or a risk, with the line it is on. Do not invent
   behaviour you have not read; say when you are unsure."""

Chat = Callable[[list[dict]], dict]


def ollama_chat(model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST, tools: set[str] | None = None) -> Chat:
    schemas = [t for t in TOOL_SCHEMAS if tools is None or t["function"]["name"] in tools]

    def chat(messages: list[dict]) -> dict:
        body = json.dumps({"model": model, "messages": messages, "tools": schemas,
                           "stream": False, "think": False, "options": {"temperature": 0.2}}).encode()
        request = urllib.request.Request(f"{host}/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.load(response)["message"]
    return chat


RETRY_LIMIT = 2      # failed attempts at one approach before switching to another
MAX_APPROACHES = 3   # different approaches to try before giving up
KEEP_RECENT = 6      # tool results kept in full; older ones are trimmed to save tokens
TRIMMED = 200


def describe_attempt(changes: list[dict]) -> str:
    """One line naming what an approach did, built from the reasons the agent gave for its edits."""
    return "; ".join(f"{c['path']}: {c['reason'] or 'no reason'}" for c in changes)[:300] or "investigated without editing"


def switch_approach(workspace: Workspace, progress: Progress | None, start: int, evidence: str,
                    log: Callable[[str], None]) -> str:
    """Record the current approach as failed, undo its edits, and return the instruction to try another way."""
    approach = describe_attempt(workspace.changes[start:])
    if progress:
        progress.fail_approach(approach, evidence)
    restored = workspace.undo_attempt()
    log(f"↺ approach failed, switching. undone: {', '.join(restored) or 'nothing'}")
    failed = progress.failed if progress else [{"approach": approach}]
    tried = "\n".join(f"  {n}. {f['approach']}" for n, f in enumerate(failed, 1))
    return (f"That approach did not fix the problem after {RETRY_LIMIT} tries, so its edits were undone"
            f"{' (' + ', '.join(restored) + ')' if restored else ''}.\nApproaches already tried and failed:\n{tried}\n"
            "Re-read the code and the error, find a different root cause or a fundamentally different fix, "
            "call record_decision with the new approach and why it should work, then make the smallest change.")


def _not_done(workspace: Workspace) -> str:
    """Why the task is not finished yet, or "" if every plan step is done and the check command passes."""
    gaps = [f"plan step not done: {item['step']}" for item in workspace.plan if item["status"] != "done"]
    if workspace.check_command and not gaps:
        result = workspace.run_command(workspace.check_command)
        if result.startswith("exit=") and not result.startswith("exit=0"):  # a refused or dry run can't block finishing
            gaps.append(f"`{workspace.check_command}` does not pass:\n{result[-1500:]}")
    return "\n".join(gaps)


def _trim(messages: list[dict], workspace: Workspace, read_paths: dict[int, str]) -> None:
    """Shorten old tool results so long runs don't resend everything. Trimmed files must be re-read before a rewrite."""
    tools = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    for i in tools[:-KEEP_RECENT]:
        if len(messages[i]["content"]) > TRIMMED:
            messages[i]["content"] = messages[i]["content"][:TRIMMED] + "\n[trimmed to save tokens; read again if needed]"
            if i in read_paths:
                workspace.stale.add(workspace._path(read_paths[i]))


def run_agent(task: str, workspace: Workspace, chat: Chat, max_steps: int = 15,
              log: Callable[[str], None] = print, system: str = SYSTEM_PROMPT, trace: Trace | None = None,
              progress: Progress | None = None, tools: set[str] | None = None,
              retry_limit: int = RETRY_LIMIT, max_approaches: int = MAX_APPROACHES) -> str:
    """Loop: model → tool calls → results → model, until a plain reply or max_steps.

    With `progress`, the run starts from what earlier runs did (plan, changes, failed approaches) and saves
    back after every step. When the same command keeps failing `retry_limit` times, the current approach is
    recorded as failed, its edits are undone, and the model is told to try a different one.
    """
    record = trace.event if trace else (lambda kind, **data: None)
    allowed = {t["function"]["name"] for t in TOOL_SCHEMAS} if tools is None else tools
    if progress:
        workspace.plan = [dict(item) for item in progress.plan]
        workspace.done_when, workspace.check_command = list(progress.done_when), progress.check_command
    briefing = progress.briefing() if progress else ""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": f"{task}\n\n{briefing}" if briefing else task}]
    finished, start = (len(progress.changes) if progress else 0), len(workspace.changes)
    logged_decisions, logged_changes = len(workspace.decisions), len(workspace.changes)
    attempt_start, failures, read_paths = len(workspace.changes), {}, {}

    def save() -> None:
        nonlocal logged_decisions, logged_changes
        if progress:
            for d in workspace.decisions[logged_decisions:]:
                progress.decide(d["decision"], d["why"])
            for c in workspace.changes[logged_changes:]:
                progress.decide(f"Changed {c['path']} (+{c['added']} -{c['removed']})", c["reason"] or "no reason given")
            progress.plan = workspace.plan
            progress.done_when, progress.check_command = workspace.done_when, workspace.check_command
            progress.changes[finished:] = workspace.changes[start:]
            progress.save()
        logged_decisions, logged_changes = len(workspace.decisions), len(workspace.changes)

    def end(reason: str, summary: str) -> str:
        record("end", reason=reason, summary=summary)
        save()
        return summary

    for _ in range(max_steps):
        _trim(messages, workspace, read_paths)
        reply = chat(messages)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        record("model", content=reply.get("content", ""), tool_calls=len(calls))
        if not calls:
            if gaps := _not_done(workspace):  # completion gate: no finishing until done is proven
                record("gate", gaps=gaps)
                log(f"✗ not done yet: {gaps.splitlines()[0]}")
                messages.append({"role": "user", "content": f"You are not done yet:\n{gaps}\nKeep working until this is fixed."})
                continue
            return end("done", reply.get("content", "").strip())
        switch = ""
        for call in calls:
            name = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            log(f"→ {name}({', '.join(f'{k}={str(v)[:60]!r}' for k, v in args.items() if k not in ('content', 'old', 'new'))})")
            tool = getattr(workspace, name, None) if name in allowed else None
            try:
                result = tool(**args) if tool else f"Unknown tool: {name}"
            except Exception as error:  # report tool errors back to the model instead of crashing
                result = f"Error: {error}"
            record("tool", name=name, args=args, result=result)
            if name == "read_file" and "path" in args:
                read_paths[len(messages)] = args["path"]
            messages.append({"role": "tool", "content": result, "tool_name": name})
            if name == "run_command" and result.startswith("exit="):
                command = args.get("command", "")
                if result.startswith("exit=0"):
                    failures.pop(command, None)
                else:
                    failures[command] = failures.get(command, 0) + 1
                    edited_since = len(workspace.changes) > attempt_start
                    if failures[command] >= retry_limit and edited_since:
                        switch = result
        if switch:
            if progress and len(progress.failed) + 1 >= max_approaches:
                switch_approach(workspace, progress, attempt_start, switch, log)
                return end("gave_up", f"Tried {max_approaches} different approaches and none fixed it. "
                                      f"See .agent-ops/DECISIONS.md for what was tried and why.")
            messages.append({"role": "user", "content": switch_approach(workspace, progress, attempt_start, switch, log)})
            record("switch", evidence=switch[-300:])
            attempt_start, failures = len(workspace.changes), {}
        save()
    if progress:
        progress.note(f"A run stopped at the {max_steps}-step limit before finishing.")
    return end("step_limit", f"Stopped after {max_steps} steps without finishing.")
