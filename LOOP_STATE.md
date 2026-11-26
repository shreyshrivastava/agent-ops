# LOOP_STATE — read this first, every session

This file is the memory for work on agent-ops. Any Claude Code session working on this repo reads it
before doing anything, works the loop below, and updates it after every step. The conversation is not
memory; this file is.

## Where everything is

- Repo: https://github.com/shreyshrivastava/agent-ops
- Branch: `feature/loop-memory-and-explain`. All the work below is here, and it is not merged to `main`.
  Get it with: `git fetch origin feature/loop-memory-and-explain && git checkout feature/loop-memory-and-explain && pip install .`
- Code: `src/local_agent_ops/`
  - `agent.py`: the agent loop. It holds the system prompt, `EXPLAIN_PROMPT`, the completion gate (`_not_done`),
    approach switching (`switch_approach`, `RETRY_LIMIT=2`, `MAX_APPROACHES=3`), and trimming of old tool output (`_trim`).
  - `tools.py`: the `Workspace` tools: read_file, list_files, edit_file, write_file, run_command, update_plan,
    set_done_criteria and record_decision. It also holds the pre-write checks (Python must parse, `MAX_DIFF=40`,
    read-only tests, user approval) and `undo_attempt`.
  - `progress.py`: loop memory in `<workspace>/.agent-ops/progress.json` and the decision log
    `<workspace>/.agent-ops/DECISIONS.md`.
  - `fix.py`: the `agent-ops fix` rounds. They switch approach after 2 rounds without progress and give up after 3 approaches.
  - `cli.py`: the commands `code`, `fix`, `explain`, `runs`, `replay` and `audit`.
  - `trace.py`: run traces in `.agent-ops/runs/`, and `explain_run`.
- Tests: `tests/` (47 tests, using a scripted fake model). Run them with `PYTHONPATH=src python3 -m unittest discover -s tests`
- Benchmark: `benchmark/tasks/01..08` (5 bug fixes, 3 features), `benchmark/run.py`, and the earlier results in
  `benchmark/results-bugfix.json` and `results-features.json`.
- Docs: `README.md` and `docs/architecture.md` describe all the features below.

## Goal

agent-ops should be a professional local coding agent that codes and debugs other people's code. It should finish tasks
completely, know what done looks like, remember what it did, not repeat a failed approach more than twice, make
minimal changes, and explain step by step what it changed and why.

## Rules (from the user)

- Standard library only. No Kafka, no async, no new dependencies.
- Make minimal changes: touch only the lines that are wrong, with no refactors or reformatting.
- Commit to `feature/loop-memory-and-explain` only, never `main`. Don't open a PR unless the user asks.

## The loop (follow it every session)

1. Read this file. Continue from **Next**.
2. Before working on a task, write its **Done when**: checks you can test, and the commands that prove them.
3. Work one plan step at a time. Mark a step `[x]` only after its check has passed, and update this file after every step.
4. Two strikes: if the same problem survives 2 attempts, revert that attempt, add it to **Failed approaches**
   with the evidence, and try a different approach. Never retry an approach that is listed there. After 3 failed
   approaches on one problem, stop and ask the user.
5. Record each choice that matters under **Decisions**, with why and what you rejected.
6. Never say "done", "fixed" or "passing" without having just run the command that proves it.
7. At the end of a session, update **Results** and **Next**, then commit and push this file with the code.

## Done so far (sessions 1–3, cloud session, verified with the fake-model tests)

- [x] Loop memory: the plan, every change with its reason, and notes are saved after every step. `fix` rounds and
      re-runs of the same `code` task resume from them, and `--fresh` resets. (commit 101f682)
- [x] Every write carries a reason, which is shown at approval. The final answer is a numbered step-by-step
      explanation. `agent-ops explain <file|run>` explains code without editing it, or explains a past run from its trace. (101f682)
- [x] Approach switching: if the same failing command fails twice after edits, or 2 `fix` rounds make no progress,
      the approach is recorded as failed, its edits are undone with the user's approval, and the agent must try a
      different way. It gives up after 3 approaches, and failed approaches are kept in memory. (13292d4)
- [x] Decision log `.agent-ops/DECISIONS.md` (13292d4)
- [x] Minimal changes: `edit_file` snippet edits, a 40-line cap per edit (`--max-diff`), and trimming of old tool
      output to save tokens. A trimmed file can't be rewritten whole until it is read again. (13292d4)
- [x] A clear "done": `set_done_criteria` and a completion gate. The agent can't finish with open plan steps or a
      failing check command. Python files must parse before a write. (da84926)
- [x] 47/47 unit tests pass.

## Decisions

- The progress file and decision log live in `.agent-ops/`, which is gitignored, next to the traces. They are local
  per workspace, and the agent can't edit them.
- Undoing a failed approach goes through user approval, to keep the rule that every write is approved.
- The line cap applies to edits of existing files only. New files and undo restores are exempt.
- A rejected or dry-run check command doesn't block finishing; otherwise the agent would be stuck until the step limit.
- The architecture generator's notifications/Kafka/async template was rejected because it doesn't fit a local,
  dependency-free terminal agent.
- "Ponytail skill" was interpreted as "change the minimum code" and enforced in code (the line cap and edit_file).
  If the user names a concrete skill, match it.

## Failed approaches

(none yet)

## Results

- Fake-model unit tests: 47/47 pass.
- Real model: **never run yet.** The cloud session couldn't reach the user's laptop.

## Next (start here)

Done when:
- the unit tests pass,
- every benchmark task has been run with the user's real local model and the results are recorded below,
- each problem the real runs showed is fixed with a test, or recorded as a known limitation,
- README numbers come only from measured runs,
- everything is committed and pushed.

Plan:
- [ ] 1. Find the local model (`ollama list`; the README default is huihui_ai/qwen3.5-abliterated:9b) and make sure Ollama is running.
- [ ] 2. Run the unit tests.
- [ ] 3. Run every task in a fresh throwaway copy, for example
      `cp -r benchmark/tasks/05_partial_refunds /tmp/bench/05 && agent-ops fix --workspace /tmp/bench/05 --model <model> --yes`.
      Use `--yes` only in throwaway copies. Use `benchmark/run.py` if it fits.
- [ ] 4. For each task, record under Results: pass/fail, rounds, approach switches, whether the model used
      set_done_criteria, update_plan, edit_file and record_decision, edits refused by the line cap or parse check,
      and net lines. Read each run's `.agent-ops/DECISIONS.md`.
- [ ] 5. Compare against `benchmark/results-*.json`.
- [ ] 6. Fix what the real runs show (prompts, limits, tool descriptions, gate behaviour) following the loop, then rerun.
- [ ] 7. Give the user a before/after table and what changed and why.
