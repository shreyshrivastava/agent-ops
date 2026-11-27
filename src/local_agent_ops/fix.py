"""`agent-ops fix`: run the tests, hand the failures to the agent, rerun, and repeat for a few rounds."""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable

from .agent import MAX_APPROACHES, RETRY_LIMIT, Chat, run_agent, switch_approach
from .progress import Progress
from .tools import Workspace
from .tools import NO_BYTECODE
from .trace import Trace

TEST_FILES = ("test_*.py", "*_test.py", "tests/*")
MAX_FAILURE_OUTPUT = 4000


def count_failures(output: str, exit_code: int) -> int | None:
    """Failing tests reported by unittest or pytest, 0 on success, None if the output has no count."""
    if exit_code == 0:
        return 0
    if match := re.search(r"FAILED \(([^)]*)\)", output):  # unittest: FAILED (failures=2, errors=1)
        return sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", match.group(1)))
    counts = re.findall(r"(\d+) (?:failed|errors?)\b", output)  # pytest: 2 failed, 1 error
    return sum(int(n) for n in counts) if counts else None


def run_tests(workspace: Workspace, test_cmd: str) -> tuple[int, str]:
    result = subprocess.run(shlex.split(test_cmd), cwd=workspace.root, capture_output=True, text=True, timeout=300, env=NO_BYTECODE)
    return result.returncode, result.stdout + result.stderr


def fix_tests(workspace: Workspace, chat: Chat, test_cmd: str = "python3 -m unittest", rounds: int = 6,
              max_steps: int = 15, model: str = "", log: Callable[[str], None] = print, fresh: bool = False,
              retry_limit: int = RETRY_LIMIT, max_approaches: int = MAX_APPROACHES) -> dict:
    """Rounds of: agent fixes → tests rerun. After `retry_limit` rounds without fewer failures, the approach is
    recorded as failed, its edits are undone, and the next round must try another way. Stops when the tests
    pass, after `max_approaches` failed approaches, or after `rounds`."""
    code, output = run_tests(workspace, test_cmd)
    failing = count_failures(output, code)
    history = [failing]
    log(f"tests: {_describe(failing)}")
    reason, traces = ("already passing" if code == 0 else "rounds used up"), []
    progress = Progress(workspace.root)
    if progress.begin(f"fix: {test_cmd}", fresh=fresh):  # memory is kept across runs unless fresh
        log(f"resuming: {len(progress.changes)} earlier changes, {len(progress.failed)} failed approaches")
    best, stuck, attempt_start = failing, 0, 0

    for number in range(1, rounds + 1):
        if code == 0:
            break
        log(f"\nround {number}/{rounds}")
        task = (f"`{test_cmd}` fails. Fix the code under test so the tests pass. The test files are read-only.\n"
                f"Test output (last part):\n{output[-MAX_FAILURE_OUTPUT:]}")
        trace = Trace(workspace.root, task, model)
        traces.append(trace.path.name)
        try:
            run_agent(task, workspace, chat, max_steps, log=log, trace=trace, progress=progress,
                      retry_limit=retry_limit, max_approaches=max_approaches)
        except TimeoutError:  # one slow model reply ends this round, not the whole run; its edits are kept
            log("model reply timed out; ending this round")
            progress.note(f"Round {number}: the model timed out.")
        if len(progress.failed) >= max_approaches:  # the agent already gave up inside this round
            reason = f"{max_approaches} approaches failed"
            break
        previous = failing
        code, output = run_tests(workspace, test_cmd)
        failing = count_failures(output, code)
        history.append(failing)
        progress.note(f"After round {number}: tests {_describe(failing)}.")
        progress.save()
        log(f"tests: {_describe(failing)}")
        if code == 0:
            reason = "tests pass"
            progress.decide(f"Round {number} fixed the tests", describe_progress(previous, failing))
            break
        improved = failing is not None and (best is None or failing < best)
        best, stuck = (failing, 0) if improved else (best, stuck + 1)
        if stuck >= retry_limit:  # this approach keeps failing: undo it and make the next round try another way
            switch_approach(workspace, progress, attempt_start, output[-300:], log)
            attempt_start, stuck = len(workspace.changes), 0
            code, output = run_tests(workspace, test_cmd)
            failing = count_failures(output, code)
            best = failing
            if len(progress.failed) >= max_approaches:
                reason = f"{max_approaches} approaches failed"
                break
        progress.save()

    added, removed = workspace.net_lines()
    return {"passed": code == 0, "reason": reason, "failing": history, "added": added, "removed": removed,
            "traces": traces, "changes": workspace.changes}


def _describe(failing: int | None) -> str:
    return "passing" if failing == 0 else f"{failing} failing" if failing is not None else "failing (count unknown)"


def describe_progress(before: int | None, after: int | None) -> str:
    return f"failing tests went from {_describe(before)} to {_describe(after)}"
