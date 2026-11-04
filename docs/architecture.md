# Architecture

```text
agent-ops code "<task>"
        |
        v
cli.py ── builds Workspace(root, approve, dry_run) and an Ollama chat function
        |
        v
agent.py  run_agent: messages → Ollama /api/chat (tools) → tool_calls → Workspace → results → …
        |                                                   stops on a plain reply or max_steps
        v
tools.py  Workspace
  - path jail: every path resolved and checked against the root
  - write_file: unified diff → approve → write; originals kept for the net-lines metric
  - run_command: shlex split, no shell, allowlist, blocked git verbs, approve, 120s timeout

trace.py  Trace: one JSONL file per run in <workspace>/.agent-ops/runs/
  - one event per line (start, model, tool, end), each with "v": 1
  - keys and tokens masked with the auditor's patterns before writing
  - .agent-ops/.gitignore ignores everything, and the agent can't write there

agent-ops fix
        |
        v
fix.py    run tests → failures → run_agent (test files read-only) → rerun
          stops when tests pass, when the failure count doesn't drop, or after --rounds

agent-ops audit <manifest.json>
        |
        v
audit.py  structural checks, approval policy, secret keys and values at every depth
```

Design choices:

- **Standard library only.** Nothing to install beyond Python and Ollama, and every line is reviewable.
- **The chat function is injected.** Tests pass a scripted fake model, so CI runs without a GPU and the loop's behaviour is deterministic under test.
- **Whole-file writes.** This is simpler for a small model than search-and-replace edits, and the diff shown at approval time keeps it reviewable.
- **Benchmark grading restores the original tests** before running them, so a run can't pass by editing its tests.
