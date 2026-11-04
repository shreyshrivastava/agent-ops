"""A minimal local coding agent: Ollama chat + tool calls + approval gates."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable

from .tools import TOOL_SCHEMAS, Workspace
from .trace import Trace

DEFAULT_MODEL = "huihui_ai/qwen3.5-abliterated:9b"
DEFAULT_HOST = "http://127.0.0.1:11434"

SYSTEM_PROMPT = """You are a careful local coding agent working inside one repository.
Write the least code that correctly solves the task:
1. Read the relevant files before changing anything.
2. Prefer, in order: no change, reusing existing code, the standard library, then new code.
3. Never add a dependency, abstraction, or file the task does not need.
4. Keep edits small and in the surrounding style. Do not refactor unrelated code.
5. If tests exist, run them after editing and fix failures. Commands already run in the
   repository root: use `python3 -m unittest`, never `cd`, pipes, or other shell syntax.
When done, reply with a short summary of what you changed and why, and stop calling tools."""

Chat = Callable[[list[dict]], dict]


def ollama_chat(model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST) -> Chat:
    def chat(messages: list[dict]) -> dict:
        body = json.dumps({"model": model, "messages": messages, "tools": TOOL_SCHEMAS,
                           "stream": False, "think": False, "options": {"temperature": 0.2}}).encode()
        request = urllib.request.Request(f"{host}/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.load(response)["message"]
    return chat


def run_agent(task: str, workspace: Workspace, chat: Chat, max_steps: int = 15,
              log: Callable[[str], None] = print, system: str = SYSTEM_PROMPT, trace: Trace | None = None) -> str:
    record = trace.event if trace else (lambda kind, **data: None)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    for _ in range(max_steps):
        reply = chat(messages)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        record("model", content=reply.get("content", ""), tool_calls=len(calls))
        if not calls:
            summary = reply.get("content", "").strip()
            record("end", reason="done", summary=summary)
            return summary
        for call in calls:
            name = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            log(f"→ {name}({', '.join(f'{k}={str(v)[:60]!r}' for k, v in args.items() if k != 'content')})")
            tool = getattr(workspace, name, None) if name in {t["function"]["name"] for t in TOOL_SCHEMAS} else None
            try:
                result = tool(**args) if tool else f"Unknown tool: {name}"
            except Exception as error:  # report tool errors back to the model instead of crashing
                result = f"Error: {error}"
            record("tool", name=name, args=args, result=result)
            messages.append({"role": "tool", "content": result, "tool_name": name})
    summary = f"Stopped after {max_steps} steps without finishing."
    record("end", reason="step_limit", summary=summary)
    return summary
