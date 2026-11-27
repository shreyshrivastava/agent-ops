# Changelog

All notable changes to agent-ops. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - Unreleased

### Added
- `agent-ops review`: a read-only review of `git diff <base>` with numbered findings. Exits 0 when clean, 1 with findings, 2 if it couldn't run.
- `agent-ops fix --json`: prints only the result as JSON on stdout, for CI.
- Loop memory in `.agent-ops/progress.json`: the plan, every change with its reason, and failed approaches. Later rounds and reruns continue from it; `--fresh` resets it.
- Completion gate: the agent can't finish while plan steps are open or its check command fails. `fix` uses your test command as the check.
- Approach switching: when the same command keeps failing without fewer failing tests, the approach is undone and recorded, and the agent must try another. It gives up after 3 (`--retry-limit`, `--max-approaches`).
- A rewrite of the exact file version from an undone approach is refused.
- Decision log `.agent-ops/DECISIONS.md`, and `agent-ops explain` for code or for a past run.
- Minimal edits: `edit_file` snippet edits, a 40-line cap per edit (`--max-diff`), a Python parse check before writes, and trimming of old tool output.
- A benchmark run of this version on a real local model (`benchmark/results-real-9b.json`).

### Changed
- The package is now named `agent-ops`, matching the command (it was `local-agent-operations-toolkit`).

### Fixed
- One slow model reply no longer ends the whole `fix` run. Only that round ends.
- `fix` stops as soon as the agent gives up within a round, instead of running past the approach limit.

## [0.2.0] - 2026-11-04

### Added
- `agent-ops fix`: run the tests, fix the code with test files read-only, and rerun, for several rounds.
- Run traces in `.agent-ops/runs/`, with `agent-ops runs` and `agent-ops replay`. Secrets are masked.
- The payments benchmark (8 tasks) comparing the system prompt with a baseline.

### Fixed
- A file that was only partly read could be written back with content missing.
- Command arguments could reach paths outside the workspace.
- Agent-run commands no longer write bytecode into the workspace.
