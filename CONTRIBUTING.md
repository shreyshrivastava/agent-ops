# Contributing to agent-ops

Thanks for helping. agent-ops stays small on purpose, so a few rules apply to every change.

## Rules

- **Standard library only.** No new dependencies, no async.
- **Minimal changes.** Touch only the lines that need to change. No unrelated refactors, renames or reformatting.
- **A test for every behaviour change.** The model is faked with scripted replies, so tests run anywhere without a GPU.
- **Keep the safety model.** Every write and command still needs approval, and every path stays inside the workspace.

## Set up

```bash
git clone https://github.com/shreyshrivastava/agent-ops && cd agent-ops
python3 -m venv .venv && .venv/bin/pip install -e .
```

## Run the tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

To check a change against a real model, run it on a copy of a benchmark task. Use `--yes` only on a throwaway copy:

```bash
cp -r benchmark/tasks/02_gst_rounding /tmp/check && agent-ops fix --workspace /tmp/check --yes
```

## Pull requests

- Describe what changed and why, and paste the test command's output.
- If you ran the benchmark, include the numbers and the model you used.
- Add a line to [CHANGELOG.md](CHANGELOG.md) under the unreleased version.
- Never include credentials, session files or private data. See [SECURITY.md](SECURITY.md).
