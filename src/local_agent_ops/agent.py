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
0. Start by calling update_plan with short steps. Mark each step done as you finish it, so the
   next run knows what is already done if you run out of steps.
1. Read the relevant files before changing anything. To debug, reproduce the failure first,
   find the root cause, then fix that cause rather than the symptom.
2. Prefer, in order: no change, reusing existing code, the standard library, then new code.
3. Never add a dependency, abstraction, or file the task does not need.
4. Keep edits small and in the surrounding style. Do not refactor unrelated code.
5. If tests exist, run them after editing and fix failures. Commands already run in the
   repository root: use `python3 -m unittest`, never `cd`, pipes, or other shell syntax.
6. Every write_file needs a reason: what the change does and why it is needed.
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


def run_agent(task: str, workspace: Workspace, chat: Chat, max_steps: int = 15,
              log: Callable[[str], None] = print, system: str = SYSTEM_PROMPT, trace: Trace | None = None,
              progress: Progress | None = None, tools: set[str] | None = None) -> str:
    """Loop: model → tool calls → results → model, until a plain reply or max_steps.

    With `progress`, the run starts from what earlier runs did (plan, changes and notes) and saves its
    own plan and changes back after every step, so an interrupted run loses nothing.
    """
    record = trace.event if trace else (lambda kind, **data: None)
    allowed = {t["function"]["name"] for t in TOOL_SCHEMAS} if tools is None else tools
    if progress:
        workspace.plan = [dict(item) for item in progress.plan]
    briefing = progress.briefing() if progress else ""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": f"{task}\n\n{briefing}" if briefing else task}]
    finished, start = (len(progress.changes) if progress else 0), len(workspace.changes)

    def save() -> None:
        if progress:
            progress.plan = workspace.plan
            progress.changes[finished:] = workspace.changes[start:]
            progress.save()

    for _ in range(max_steps):
        reply = chat(messages)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        record("model", content=reply.get("content", ""), tool_calls=len(calls))
        if not calls:
            summary = reply.get("content", "").strip()
            record("end", reason="done", summary=summary)
            save()
            return summary
        for call in calls:
            name = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            log(f"→ {name}({', '.join(f'{k}={str(v)[:60]!r}' for k, v in args.items() if k != 'content')})")
            tool = getattr(workspace, name, None) if name in allowed else None
            try:
                result = tool(**args) if tool else f"Unknown tool: {name}"
            except Exception as error:  # report tool errors back to the model instead of crashing
                result = f"Error: {error}"
            record("tool", name=name, args=args, result=result)
            messages.append({"role": "tool", "content": result, "tool_name": name})
        save()
    summary = f"Stopped after {max_steps} steps without finishing."
    record("end", reason="step_limit", summary=summary)
    if progress:
        progress.note(f"A run stopped at the {max_steps}-step limit before finishing.")
    save()
    return summary
