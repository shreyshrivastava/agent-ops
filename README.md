<h1 align="center">agent-ops</h1>

<p align="center"><b>A coding agent that runs on your laptop and asks before it changes a file or runs a command.</b></p>

<p align="center">
  <a href="https://github.com/shreyshrivastava/agent-ops/actions/workflows/ci.yml"><img src="https://github.com/shreyshrivastava/agent-ops/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/dependencies-0-brightgreen" alt="Zero dependencies">
  <img src="https://img.shields.io/badge/runs-100%25%20local-8957e5" alt="Runs 100% local">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT license"></a>
</p>

<p align="center">
  <a href="#quick-start-about-5-minutes">Quick start</a> ·
  <a href="#benchmark">Benchmark</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#limitations">Limitations</a>
</p>

<p align="center">
  <img src="docs/demo.png" alt="agent-ops fixing a webhook signature check with a local model" width="820">
</p>
<p align="center"><i>A real run on Qwen 3.5 9B: the agent replaces an MD5 "signature" with HMAC-SHA256 and a constant-time comparison, asks before each write and command, and reports the net change.</i></p>

## Highlights

- It runs on Ollama with a 9B Qwen model, so it needs no API key and your code stays on your machine.
- You see a diff before every write and approve every command with `y`. `--dry-run` shows the plan without changing anything.
- File access and command arguments are limited to the workspace. Only allowlisted commands run, and `git push`, `commit` and `reset` are blocked.
- The system prompt tells the model to read first and to reuse existing code or the standard library before writing new code.
- A [benchmark](#benchmark) of 8 payments tasks (paise, GST, webhooks, idempotency, refunds) grades each run against the original tests.
- The whole agent is about 300 lines of standard-library Python. Its 19 tests run without a model.

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

## Benchmark

<p align="center"><img src="docs/benchmark.svg" alt="Benchmark results: minimal-rules vs baseline" width="760"></p>

There are 8 payments-style tasks, each starting with failing tests. I ran every task twice in each of two modes: **minimal-rules** (the [minimal-change system prompt](#how-it-works)) and **baseline** (a plain "complete the task" prompt with the same tools and limits). All runs auto-approve, and a run passes only if the original test files pass afterwards.

The model was `huihui_ai/qwen3.5-abliterated:9b` (Q4_K_M) on a MacBook, run on 2026-11-04. Raw results are in [`benchmark/results-bugfix.json`](benchmark/results-bugfix.json) and [`benchmark/results-features.json`](benchmark/results-features.json).

Bug fixes (paise conversion, GST half-up rounding, webhook HMAC, idempotency keys, partial-refund limits):

| Mode | Pass rate | Avg lines changed | Avg tool calls | Avg time |
|---|---:|---:|---:|---:|
| minimal-rules | **9/10** | 7.2 | **6.7** | **108s** |
| baseline | 7/10 | 7.0 | 8.6 | 200s |

Small features (INR lakh/crore formatting, settlement report, retry on gateway timeout):

| Mode | Pass rate | Avg lines changed | Avg tool calls | Avg time |
|---|---:|---:|---:|---:|
| minimal-rules | 3/6 | **19.3** | 10.0 | 236s |
| baseline | 3/6 | 23.0 | 10.5 | 249s |

On bug fixes the rules didn't reduce code, because there was little to cut. They did cut runaway loops, and runs took about half as long on average. On feature tasks they reduced code by about 16% at the same pass rate, much less than the 54% Ponytail reports for frontier models.

Every failure happened the same way: the model looped until it hit the step limit. None of the 4 runs got Indian digit grouping (`₹1,23,456.78`) right. With 2 runs per cell and a non-deterministic model, read these numbers as a direction, not a precise measurement.

Reproducing the benchmark takes about an hour:

```bash
PYTHONPATH=src python3 benchmark/run.py --runs 2                    # all tasks
PYTHONPATH=src python3 benchmark/run.py --only feature --out results-features.json
```

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

1. The agent loop ([`agent.py`](src/local_agent_ops/agent.py), about 70 lines). It sends the conversation and four tool schemas to Ollama, executes any tool calls, and feeds the results back. It stops when the model answers without a tool call or hits `--max-steps`. Tool errors go back to the model as text instead of crashing the run.
2. The system prompt tells the model to read before editing and to prefer, in order, no change, existing code, the standard library, and only then new code. It forbids new dependencies and unrelated refactors, and asks for the tests to be run after each edit. The idea comes from the Ponytail agent skill.
3. The safety checks live in [`tools.py`](src/local_agent_ops/tools.py):
   - every path is resolved and refused if it leaves the workspace, including path arguments to commands (`cat /etc/passwd`, `grep ~/.ssh`, `git -C /elsewhere`);
   - commands run without a shell, and only `python`, `pytest`, `ls`, `cat`, `grep` and read-only `git` are allowed;
   - `git push/commit/reset/clean/rebase` are blocked;
   - every write and command needs a `y`.
4. The net-lines count diffs the final state of every touched file against its original, so a rewrite counts once.

## Tests and CI

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The 19 unit tests replace the model with scripted replies, so they run anywhere. They cover:
- the workspace jail (for both file tools and command arguments), rejected writes and dry runs;
- refusing to rewrite a file that was too large to read in full;
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

## How this was built

I built this with Claude Code as a pair programmer. I:
- chose the scope: local only, with approval for every action, and small enough to read in full;
- defined the safety model and wrote the payments benchmark tasks;
- ran all 32 benchmark runs on my own machine;
- reviewed the results, including the ones that didn't support the "less code" claim.

A review before release found two bugs. Truncated files could be written back with content missing, and command arguments could reach outside the workspace. Both were fixed, with tests, before I shared the project.

## Limitations

- A 9B local model is much weaker than frontier models, so use the agent for small changes in code that has tests.
- `python` is on the allowlist, so an approved command can run any code. Read each approval prompt, or use `--dry-run`.
- The default model is an "abliterated" Qwen variant with its refusal behaviour removed. I use it because it was already on my machine, and every benchmark number above comes from it. The agent doesn't rely on the model refusing anything: the workspace limits, allowlist and approval prompts apply whatever model you run. To use a stock model, pass `--model qwen2.5-coder:7b`.
- The agent edits by rewriting whole files, which keeps diffs easy to review but is slow on big files. It can't write to files over 100,000 characters, because it can only read part of them.

See [SECURITY.md](SECURITY.md) and [architecture notes](docs/architecture.md).
