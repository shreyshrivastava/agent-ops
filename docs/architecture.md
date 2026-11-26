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

progress.py  Progress: .agent-ops/progress.json — the plan (update_plan tool) and every change with its reason
  - saved after every step; the next fix round, or a re-run of the same `code` task, is briefed from it

  - failed_approaches: an approach is abandoned after RETRY_LIMIT failures; its edits are undone and it is
    never retried. DECISIONS.md is an append-only log of every decision and why.

agent.py  retries: the same command failing RETRY_LIMIT (2) times after edits → switch_approach
          (record, undo, ask for a different approach); MAX_APPROACHES (3) failed approaches → give up
          tokens: tool results older than the last 6 are trimmed; trimmed files can't be rewritten whole
tools.py  edit_file (exact unique snippet) is the default edit; edits over --max-diff lines are refused

agent-ops explain <file | run>
  - file: run_agent with EXPLAIN_PROMPT and only read_file/list_files exposed
  - run:  trace.explain_run lists the plan and each write with its reason, no model needed

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
