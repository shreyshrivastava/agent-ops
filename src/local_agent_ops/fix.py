"""`agent-ops fix`: run the tests, hand the failures to the agent, rerun, and repeat for a few rounds."""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable

from .agent import Chat, run_agent
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


def fix_tests(workspace: Workspace, chat: Chat, test_cmd: str = "python3 -m unittest", rounds: int = 3,
              max_steps: int = 15, model: str = "", log: Callable[[str], None] = print) -> dict:
    code, output = run_tests(workspace, test_cmd)
    failing = count_failures(output, code)
    history = [failing]
    log(f"tests: {_describe(failing)}")
    reason, traces = ("already passing" if code == 0 else "rounds used up"), []

    for number in range(1, rounds + 1):
        if code == 0:
            break
        log(f"\nround {number}/{rounds}")
        task = (f"`{test_cmd}` fails. Fix the code under test so the tests pass. The test files are read-only.\n"
                f"Test output (last part):\n{output[-MAX_FAILURE_OUTPUT:]}")
        trace = Trace(workspace.root, task, model)
        traces.append(trace.path.name)
        run_agent(task, workspace, chat, max_steps, log=log, trace=trace)
        previous = failing
        code, output = run_tests(workspace, test_cmd)
        failing = count_failures(output, code)
        history.append(failing)
        log(f"tests: {_describe(failing)}")
        if code == 0:
            reason = "tests pass"
        elif failing is None or previous is None or failing >= previous:
            reason = "no progress"
            break

    added, removed = workspace.net_lines()
    return {"passed": code == 0, "reason": reason, "failing": history, "added": added, "removed": removed, "traces": traces}


def _describe(failing: int | None) -> str:
    return "passing" if failing == 0 else f"{failing} failing" if failing is not None else "failing (count unknown)"
