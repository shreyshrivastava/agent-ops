# agent-ops: a local, approval-gated coding agent

[![CI](https://github.com/shreyshrivastava/agent-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/shreyshrivastava/agent-ops/actions/workflows/ci.yml)

A coding agent that runs **entirely on your machine** (Ollama + a 9B Qwen model), asks before every file write and command, and is told to make the **smallest correct change**. It is measured on payments-style tasks instead of being taken on trust.

- **Fully local.** No cloud API, no keys, no code leaves the laptop. Pure Python standard library, zero dependencies.
- **Human in the loop.** Every write shows a diff and every command needs approval. There's a command allowlist, a workspace jail, and a `--dry-run` mode.
- **Measured.** A reproducible benchmark of 8 payments-domain tasks grades every run against the *original* tests, so the agent can't pass by editing them.

![agent-ops fixing a webhook signature check with a local model](docs/demo.png)

*A real run: the agent replaces an MD5 "signature" with HMAC-SHA256 and a constant-time comparison, asks before writing and before running tests, then reports the net line change.*

## Quick start (about 5 minutes)

```bash
# 1. Local model
brew install ollama            # or see ollama.com
ollama pull huihui_ai/qwen3.5-abliterated:9b

# 2. Install
git clone https://github.com/shreyshrivastava/agent-ops && cd agent-ops
pip install .

# 3. Run on a sample task (copy it first: the agent edits files)
cp -r benchmark/tasks/03_webhook_signature /tmp/demo
agent-ops code "$(cat /tmp/demo/task.txt)" --workspace /tmp/demo
```

Any Ollama model with tool calling works, for example `--model qwen2.5-coder:7b`.

| Flag | What it does |
|---|---|
| `--dry-run` | Shows what it would write or run, and changes nothing |
| `--yes` | Auto-approves everything. Use only in a throwaway copy. |
| `--max-steps N` | Hard stop on runaway loops (default 15) |
| `--model`, `--host` | Choose the Ollama model and server |

## How it works

```text
task ──► agent loop (agent.py) ──► Ollama /api/chat with tool schemas
              ▲                         │ tool_calls
              │ tool result             ▼
              └──────────── Workspace (tools.py)
                            • list_files / read_file      (inside workspace only)
                            • write_file  → diff → approve → write
                            • run_command → allowlist → approve → run (120s timeout)
```

1. **Agent loop** ([`agent.py`](src/local_agent_ops/agent.py), about 70 lines). It sends the conversation and four tool schemas to Ollama, executes any tool calls, and feeds the results back. It stops when the model answers without a tool call or hits `--max-steps`. Tool errors go back to the model as text instead of crashing the run.
2. **Minimal-change rules** (the system prompt). Read before editing. Prefer, in order: no change, then existing code, then the standard library, then new code. No new dependencies or unrelated refactors. Run the tests after editing. This follows the "write less code" idea popularised by the Ponytail agent skill.
3. **Safety layer** ([`tools.py`](src/local_agent_ops/tools.py)):
   - every path is resolved and refused if it leaves the workspace;
   - commands run without a shell, and only `python`, `pytest`, `ls`, `cat`, `grep` and read-only `git` are allowed;
   - `git push/commit/reset/clean/rebase` are blocked;
   - every write and command needs a `y`.
4. **Net-lines metric.** It diffs the final state of every touched file against its original, so a rewrite counts once.

## Benchmark

8 payments-style tasks, each with failing tests. Every task was run 2 times in each of 2 modes: **minimal-rules** (the system prompt above) and **baseline** (a plain "complete the task" prompt with the same tools and limits). All runs auto-approve, and a run passes only if the **original** test files pass afterwards.

**Model:** `huihui_ai/qwen3.5-abliterated:9b` (Q4_K_M) on a MacBook, run on 2026-11-04. The raw results are in [`benchmark/results-bugfix.json`](benchmark/results-bugfix.json) and [`benchmark/results-features.json`](benchmark/results-features.json).

**Bug fixes** (paise conversion, GST half-up rounding, webhook HMAC, idempotency keys, partial-refund limits):

| Mode | Pass rate | Avg lines changed | Avg tool calls | Avg time |
|---|---:|---:|---:|---:|
| minimal-rules | **9/10** | 7.2 | **6.7** | **108s** |
| baseline | 7/10 | 7.0 | 8.6 | 200s |

**Small features** (INR lakh/crore formatting, settlement report, retry on gateway timeout):

| Mode | Pass rate | Avg lines changed | Avg tool calls | Avg time |
|---|---:|---:|---:|---:|
| minimal-rules | 3/6 | **19.3** | 10.0 | 236s |
| baseline | 3/6 | 23.0 | 10.5 | 249s |

**What this shows (honestly):**
- On bug fixes the rules did **not** reduce code, because there was little to cut. They did make the agent more reliable: fewer runaway loops, and about half the average time.
- On feature tasks the rules cut code by about **16%** at the same pass rate. That's a real but much smaller effect than the 54% Ponytail reports for frontier models.
- **Every failure looked the same:** the model looped until it hit the step limit. Indian digit grouping (`₹1,23,456.78`) beat the 9B model in all 4 runs.
- These are small samples (2 runs per cell) of a non-deterministic model, so treat them as directional.

To reproduce, which takes about 1 hour:

```bash
PYTHONPATH=src python3 benchmark/run.py --runs 2                    # all tasks
PYTHONPATH=src python3 benchmark/run.py --only feature --out results-features.json
```

## Tests and CI

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

There are 16 unit tests, and none of them need a model, because the model is faked with scripted replies. They cover:
- the workspace jail, rejected writes and dry runs;
- the command allowlist and blocked git commands;
- tool-error recovery and the step limit;
- the manifest auditor.

GitHub Actions runs the tests on Python 3.10 and 3.12.

## Also included: a manifest auditor

`agent-ops audit examples/local-agent.manifest.json` checks an agent config before you share it. It looks for:
- missing sections or approval rules;
- secret-looking keys at any depth;
- secret-looking values: `sk-`, GitHub, Slack, AWS, JWT and `Bearer` tokens.

It exits with code 1 on errors, so it can gate CI.

## Limitations

- A 9B local model is far weaker than frontier models, so the agent is meant for small, well-tested changes.
- Approval is the main safety control. `python` is on the allowlist, so an approved command can run arbitrary code. Read each prompt, or use `--dry-run`.
- The default model is an "abliterated" Qwen variant with its refusal behaviour removed. It's the default because it was the model I already ran locally, and every benchmark number above comes from it. The agent's safety doesn't depend on the model refusing anything: the workspace jail, allowlist and approval gates apply whatever model you run. To use a stock model, pass `--model qwen2.5-coder:7b`.
- It edits by replacing whole files, which is simple and reviewable but slow on big files.

See [SECURITY.md](SECURITY.md) and [architecture notes](docs/architecture.md).
