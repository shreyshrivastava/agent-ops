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
  - `cli.py`: the commands `code`, `fix`, `explain`, `review`, `runs`, `replay` and `audit`.
  - `review.py`: `agent-ops review`, a read-only review of `git diff <base>` (explain's read-only tools, its own prompt).
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

- F1: catch only TimeoutError, per round, in fix.py. Rejected: raising the 600s urllib timeout (it only delays the
  same failure) and catching OSError (that would hide a real "Ollama not running" error, which should still exit 2).
  A timed-out round counts as a normal round with no progress, so two of them still trigger an approach switch.

- Niche (2026-11-27 research): agent-ops is the small, auditable local agent: every change has an approved diff, a reason,
  a trace, a decision log and replay, with zero dependencies and no cloud. Big general agents (Aider, OpenCode, Cline,
  OpenHands, goose) win on capability and big models, and PR bots (PR-Agent, Kodus) win on hosted review. The gap that
  sources keep naming is the audit trail for agent changes (who approved what, why, replayable), mostly met by
  enterprise gateways. Rejected: competing as a general agent (can't beat their models or features) and hash-chained
  logs (bigger change; listed as a later idea, not a minor fix).
- Code-reviewer use case: added as `agent-ops review` (plan item 1) by reusing explain's read-only mode, rather than
  building a PR bot with GitHub API calls, which needs tokens and network and breaks the local-only rule.

## Findings from real runs (session 4, to fix in step 6)

- F1, 05 `agent-ops fix`: one Ollama call ran past the 600s urllib timeout in round 2. The OSError catch in cli.py `_fix`
  turns that into "Cannot reach Ollama ... timed out" and exit 2, ending the whole run and losing rounds 3-6.
  Evidence: /tmp/bench/05.log line 1, exit 2.
- F2, 05: the model never called update_plan or set_done_criteria (progress.json: plan 0, done_when 0), so the
  completion gate had nothing to check.
- F3, 05: approach memory didn't stop a repeat. After 2 abandoned approaches, the round-2 edit reason was "Re-apply the
  same logic that was tried before". The real bug: the test wants ValueError for amount <= 0, and the model kept
  exempting non-positive amounts instead.
- F4, 06 `agent-ops fix`: FAIL "3 approaches failed", failing tests 1 → 3 → 1, net 0 lines, about 13 min, exit 1. All 3
  approaches were the same: add the same 29-line format_inr, then a +2/-2 tweak, then undo. So F3 happened again: memory
  of failed approaches doesn't make the model choose a different fix. Undo also throws away the whole 29-line function,
  even though only the decimal formatting was wrong, so every approach starts from zero.
- F5, 06: DECISIONS.md logs "Abandoned approach #4" after the run already gave up on 3 approaches. The extra switch
  undid nothing, so the count looks off by one.
- F2 happened again in 06: plan 0, done_when 0. record_decision was used once. No line-cap or parse refusals.
- Logs: redirected stdout is block-buffered, so use `python -u` or PYTHONUNBUFFERED=1 to watch live.

## Failed approaches

- 05/06 attempt 1, F4 (progress isn't a strike): kept because it is a correct, tested fix, but it did not make 05 or 06 pass
  on the real model (06: 1 → 3 → 1, 05: 2 → 1 → 2 → 2). Don't expect switch-rule changes to fix these two.

## Known limitations

- huihui_ai/qwen3.5-abliterated:9b doesn't pass 05_partial_refunds (1/7 runs ever) or 06_feature_inr_format (0/7): it lets
  non-positive refunds through and gets the decimal part of rupee formatting wrong. This is the model, not the agent loop.
- The model never calls update_plan or set_done_criteria (F2). `fix` now gives the gate the test command anyway (session 5); `code` runs still depend on the model setting one.
- F3 (the model repeats a recorded failed approach) is not fixed by prompting yet.

## Results

- Fake-model unit tests: 53/53 pass (2 review tests and 1 gate test added in session 5); before that 50/50 (3 new tests in session 4: timeout, progress-not-strike, stop on give-up).
- Real model (session 4, huihui_ai/qwen3.5-abliterated:9b, Ollama app 0.40.16, benchmark/run.py, 1 run per mode):
  minimal-rules 6/8 (avg 12.9 net lines, 9.6 calls, 91s), baseline 6/8 (9.2 lines, 10.6 calls, 108s).
  Both modes fail 05_partial_refunds and 06_feature_inr_format. In 06, baseline made no edits at all, so its
  0 lines pull down baseline's average. On tasks both modes passed, minimal-rules changed fewer or equal lines every time.

## Next (start here)

Session 5: niche and minor fixes (from the 2026-11-27 research; see Decisions).

Done when:
- each item below is either done with a test or command that proves it, or moved to Known limitations,
- `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` passes,
- README facts match the code (tool count, test count, line count, install command),
- committed and pushed to this branch.

Plan (smallest first; each is under 30 lines of code):
- [x] 1. (2026-11-27: done. src/local_agent_ops/review.py, 27 lines, plus a `review` subcommand in cli.py. tests/test_review.py: diff passed as task, no
      writes, empty diff skips the model. Suite 52/52 OK. Real model: caught a removed refund-limit check in 29s with a correct
      150-vs-100 example; its second finding was padding. Bad base or not a git repo: one-line error, exit 1.) `agent-ops review [--base main]`: read-only review of `git diff <base>`. Reuse explain mode's READ_ONLY_TOOLS and
      EXPLAIN_PROMPT pattern, and pass the diff as the task. Output: numbered findings with file:line and why.
      This adds the code-reviewer use case without a new loop. Test: fake model, assert no writes and diff in the prompt.
- [x] 2. (2026-11-27: done. fix.py sets progress.check_command = test_cmd unless the model set one. Test
      test_test_command_is_the_done_check_even_if_the_model_sets_none: failed before with 2 != 1, passes now; suite 53/53 OK.
      Real 05 rerun: PASS in round 1, 2 → 0, +4 -2, correct code, graded with the original tests. The gate never fired
      (no 'not done yet'), so this pass is not evidence for the change: one sample of a task that passed 1 of 7 before.)
      F2: in `fix`, set the check command for the model (workspace.check_command = test_cmd) so the completion gate
      always has a check, even when the model never calls set_done_criteria. Test: gate blocks finishing while tests fail.
- [ ] 3. F3: refuse an edit whose new text exactly matches an edit from an undone approach, and tell the model it already
      failed. Test: repeat edit is refused with that message.
- [ ] 4. `--json` on `fix`, and `review` exit codes (0 clean, 1 findings), so it can run in CI or a pre-commit hook.
- [ ] 5. Packaging: rename the dist to `agent-ops` in pyproject.toml, recommend `pipx install .` (system pip is
      PEP 668-blocked on macOS), set the real author, add CHANGELOG.md and CONTRIBUTING.md.
- [ ] 6. benchmark/run.py: print the crash text instead of hiding it as tool_calls: 1, and document `--out` as relative
      to benchmark/.
- [ ] 7. Rerun benchmark/run.py --runs 2 on this branch so its numbers compare with the 2026-11-04 ones.

## Session 4 plan (done)

Done when:
- the unit tests pass,
- every benchmark task has been run with the user's real local model and the results are recorded below,
- each problem the real runs showed is fixed with a test, or recorded as a known limitation,
- README numbers come only from measured runs,
- everything is committed and pushed.

Plan:
- [x] 1. (session 4: Ollama installed at /opt/homebrew/bin, server was not running; start the Ollama app, NOT brew `ollama serve`; model huihui_ai/qwen3.5-abliterated:9b present) Find the local model (`ollama list`; the README default is huihui_ai/qwen3.5-abliterated:9b) and make sure Ollama is running.
- [x] 2. Run the unit tests. (session 4: 47/47 OK in a `.venv`; system pip refuses installs under PEP 668, so use `python3 -m venv .venv && .venv/bin/pip install .`)
- [x] 3. (session 4: DONE, 16 runs, 1 per mode, saved to benchmark/results-real-9b.json. The first attempt failed: the first attempt crashed because I started the stale Homebrew `ollama serve` 0.13.0, which says this model does not support tools. Use the user's Ollama app instead (`open -a Ollama`, 0.40.16), where tools work. Also, benchmark/run.py `--out` is relative to benchmark/, and a crash shows only as `tool_calls: 1`. run.py already prints each result live (flush=True); don't pipe it through `tail`, which holds the output back until the end.) Run every task in a fresh throwaway copy, for example
      `cp -r benchmark/tasks/05_partial_refunds /tmp/bench/05 && agent-ops fix --workspace /tmp/bench/05 --model <model> --yes`.
      Use `--yes` only in throwaway copies. Use `benchmark/run.py` if it fits.
- [x] 4. (session 4: done for the 2 failing tasks; see Findings F1-F5. Passing tasks are graded in benchmark/results-real-9b.json.) For each task, record under Results: pass/fail, rounds, approach switches, whether the model used
      set_done_criteria, update_plan, edit_file and record_decision, edits refused by the line cap or parse check,
      and net lines. Read each run's `.agent-ops/DECISIONS.md`.
- [x] 5. (session 4: The old files (commit f79b71b, 2026-11-04, same 9b model, 2 runs per task) show minimal-rules 12/16, baseline 10/16.
      The new run (1 per task) shows 6/8 for both. 06 has never passed in any of the 6 runs. 05 passed 1 of 6 (old minimal-rules run 1).
      01, 02, 03 and 07 pass every time. The results agree; one new run is too few to call a difference.) Compare against `benchmark/results-*.json`.
- [x] 6. Fix in order F1, then F3/F4 (the user chose this order on 2026-11-27).
      F1 done when: a new FixTests test where the model times out in round 1 keeps going and passes in round 2 (it fails
      before the fix), and `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` passes in full.
      - [x] F1 (2026-11-27): fix.py catches TimeoutError around run_agent; the round ends, its edits are kept, and the
            next round runs. Test test_model_timeout_skips_the_round_instead_of_ending_the_run failed before, passes now; suite 48/48 OK.
      - [x] F4 done (unit-verified). 05/06 recorded as known model limitations by the user's choice (2026-11-27).
      - [x] F4/F3 attempt 1 (2026-11-27): root cause is in agent.py run_agent. Any non-zero exit of the same command
            counts as a strike, even when fewer tests fail, so 2 runs of improving work undo the whole approach (06: the
            same 29-line function written 3 times). Change: count a strike only when count_failures did not drop since
            the previous run of that command.
            Done when: a new test_agent test (failures 3 -> 1 -> 0 over 3 runs, no switch, finishes) fails before and
            passes after; the existing switch tests still pass; the full suite passes; then rerun 06 and 05 with `agent-ops fix`.
            Unit part verified 2026-11-27: new test failed before, passes after; suite 49/49 OK. Real rerun of 06 (2026-11-27): still FAIL, 3 approaches, 1 → 3 → 1, net 0. The change had nothing to act on:
            all 3 tests failed after every edit ('₹0.0', then '₹00.00', where '₹0.00' is expected), so the count never
            dropped. The 06 failure is the model's formatting, not the switch rule. Rerun of 05: FAIL, 2 → 1 → 2 → 2, net 0, no timeout this time.
            Neither benchmark task passes after attempt 1; whether to try more is open. The change stays: it is a real fix with a test,
            and nothing shows it hurt.
      - [x] F5 (2026-11-27): the 05 rerun shows the cause. run_agent gives up at the 3rd approach (returns gave_up), but
            fix.py only checks the limit after its own switch, so it ran round 3 anyway: 4 failed approaches recorded, 5 switches.
            Done when: a new FixTests test (the model never fixes anything, max_approaches=2) ends with exactly 2 failed
            approaches recorded; it fails before and passes after; the full suite passes.
            Verified: failed before with 3 != 2; fix.py now breaks when progress.failed reaches max_approaches after a round; suite 50/50 OK.
      Fix what the real runs show (prompts, limits, tool descriptions, gate behaviour) following the loop, then rerun.
- [x] 7. (README now adds the 2026-11-26 measured run; before/after table given to the user in the session-4 summary.) Give the user a before/after table and what changed and why.
