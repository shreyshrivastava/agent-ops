import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from local_agent_ops.agent import run_agent
from local_agent_ops.cli import main
from local_agent_ops.fix import fix_tests
from local_agent_ops.progress import Progress
from local_agent_ops.tools import READ_ONLY_TOOLS, Workspace
from local_agent_ops.trace import Trace, explain_run, load

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
TEST = "import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"


def _call(name, **arguments):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def _done(text="done"):
    return {"role": "assistant", "content": text}


class ProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_plan_and_changes_are_saved_with_reasons(self) -> None:
        progress = Progress(self.root)
        progress.begin("make hello")
        replies = [_call("update_plan", steps=[{"step": "write hello.py", "status": "done"}]),
                   _call("write_file", path="hello.py", content="print('hi')", reason="the task asks for a greeting"),
                   _done()]
        run_agent("make hello", Workspace(self.root, lambda _: True), lambda m: replies.pop(0), log=lambda _: None, progress=progress)
        saved = Progress(self.root)
        self.assertEqual(saved.plan, [{"step": "write hello.py", "status": "done"}])
        self.assertEqual(saved.changes[0]["reason"], "the task asks for a greeting")

    def test_second_run_on_same_task_is_told_what_is_done(self) -> None:
        first = Progress(self.root)
        first.begin("task")
        replies = [_call("update_plan", steps=[{"step": "a", "status": "done"}, {"step": "b", "status": "pending"}])]
        run_agent("task", Workspace(self.root, lambda _: True), lambda m: replies[0], max_steps=1, log=lambda _: None, progress=first)
        second = Progress(self.root)
        self.assertTrue(second.begin("task"))
        seen = []
        run_agent("task", Workspace(self.root, lambda _: True), lambda m: seen.append(m) or _done(), log=lambda _: None, progress=second)
        briefing = seen[0][1]["content"]
        self.assertIn("[done] a", briefing)
        self.assertIn("[pending] b", briefing)
        self.assertIn("step limit", briefing)

    def test_new_task_or_fresh_resets_memory(self) -> None:
        progress = Progress(self.root)
        progress.begin("one")
        progress.note("x")
        progress.save()
        self.assertFalse(Progress(self.root).begin("two"))
        self.assertFalse(Progress(self.root).begin("one", fresh=True))

    def test_fix_rounds_share_memory_without_duplicates(self) -> None:
        (self.root / "calc.py").write_text(BUGGY)
        (self.root / "test_calc.py").write_text(TEST)
        replies = [_call("write_file", path="calc.py", content=FIXED, reason="add must add, not subtract"), _done()]
        result = fix_tests(Workspace(self.root, lambda _: True), lambda m: replies.pop(0), log=lambda _: None)
        self.assertTrue(result["passed"])
        saved = Progress(self.root)
        self.assertEqual(len(saved.changes), 1)
        self.assertIn("After round 1: tests passing.", saved.notes)

    def test_bad_plan_status_is_reported(self) -> None:
        self.assertTrue(Workspace(self.root, lambda _: True).update_plan([{"step": "a", "status": "maybe"}]).startswith("Error"))


class ExplainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_explain_mode_cannot_write(self) -> None:
        replies = [_call("write_file", path="x.py", content="x", reason="r"), _done("walkthrough")]
        seen = []
        run_agent("explain", Workspace(self.root, lambda _: True), lambda m: seen.append(m[-1]) or replies.pop(0),
                  log=lambda _: None, tools=READ_ONLY_TOOLS)
        self.assertFalse((self.root / "x.py").exists())
        self.assertIn("Unknown tool", seen[-1]["content"])

    def test_explain_run_lists_changes_with_reasons(self) -> None:
        trace = Trace(self.root, "make hello", "fake")
        replies = [_call("write_file", path="hello.py", content="print('hi')", reason="needed a greeting"), _done("1. Added hello.py")]
        run_agent("make hello", Workspace(self.root, lambda _: True), lambda m: replies.pop(0), log=lambda _: None, trace=trace)
        text = explain_run(load(trace.path))
        self.assertIn("1. hello.py", text)
        self.assertIn("why: needed a greeting", text)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["explain", trace.path.stem, "--workspace", str(self.root)]), 0)
        self.assertIn("why: needed a greeting", output.getvalue())


if __name__ == "__main__":
    unittest.main()


class RetryAndMinimalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "calc.py").write_text(BUGGY)
        (self.root / "test_calc.py").write_text(TEST)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_same_error_twice_undoes_the_approach_and_asks_for_another(self) -> None:
        replies = [_call("edit_file", path="calc.py", old="a - b", new="a * b", reason="try multiply"),
                   _call("run_command", command="python3 -m unittest"),
                   _call("run_command", command="python3 -m unittest"),
                   _call("edit_file", path="calc.py", old="a - b", new="a + b", reason="add, not subtract"),
                   _call("run_command", command="python3 -m unittest"), _done()]
        seen = []
        progress = Progress(self.root)
        progress.begin("fix add")
        workspace = Workspace(self.root, lambda _: True)
        run_agent("fix add", workspace, lambda m: seen.append(list(m)) or replies.pop(0), log=lambda _: None, progress=progress)
        switch_message = seen[3][-1]
        self.assertEqual(switch_message["role"], "user")
        self.assertIn("different", switch_message["content"])
        self.assertIn("try multiply", switch_message["content"])
        self.assertEqual((self.root / "calc.py").read_text(), FIXED)  # the multiply edit was undone, then the real fix made
        self.assertEqual(Progress(self.root).failed[0]["approach"], "calc.py: try multiply")
        log = progress.log_path.read_text()
        self.assertIn("Abandoned approach #1", log)
        self.assertIn("add, not subtract", log)

    def test_gives_up_after_max_approaches(self) -> None:
        def chat(messages):
            n = len(messages)
            return (_call("write_file", path="calc.py", content=f"def add(a, b):\n    return {n}\n", reason=f"guess {n}")
                    if n % 3 == 2 else _call("run_command", command="python3 -m unittest"))
        progress = Progress(self.root)
        progress.begin("fix add")
        result = run_agent("fix add", Workspace(self.root, lambda _: True), chat, max_steps=40, log=lambda _: None,
                           progress=progress, max_approaches=2)
        self.assertIn("2 different approaches", result)
        self.assertEqual(len(Progress(self.root).failed), 2)
        self.assertEqual((self.root / "calc.py").read_text(), BUGGY)

    def test_large_edits_are_refused(self) -> None:
        workspace = Workspace(self.root, lambda _: True, max_diff=3)
        result = workspace.write_file("calc.py", "".join(f"x{i} = {i}\n" for i in range(10)), reason="rewrite")
        self.assertIn("smallest change", result)
        self.assertEqual((self.root / "calc.py").read_text(), BUGGY)
        self.assertTrue(workspace.edit_file("calc.py", "a - b", "a + b", reason="fix").startswith("Wrote"))

    def test_edit_file_needs_a_unique_match(self) -> None:
        workspace = Workspace(self.root, lambda _: True)
        self.assertIn("matched 0 times", workspace.edit_file("calc.py", "nope", "x"))
        self.assertIn("matched 2 times", workspace.edit_file("calc.py", "b", "x"))

    def test_old_tool_output_is_trimmed_and_marks_files_stale(self) -> None:
        (self.root / "big.py").write_text("y = 1\n" * 200)
        replies = [_call("read_file", path="big.py")] + [_call("list_files")] * 7 + [_done()]
        seen = []
        workspace = Workspace(self.root, lambda _: True)
        run_agent("look", workspace, lambda m: seen.append([dict(x) for x in m]) or replies.pop(0), log=lambda _: None)
        self.assertIn("trimmed", seen[-1][3]["content"])
        self.assertIn("trimmed from memory", workspace.write_file("big.py", "y = 2\n"))

    def test_memory_and_decisions_survive_between_fix_runs(self) -> None:
        fix_tests(Workspace(self.root, lambda _: True), lambda m: _done("no idea"), rounds=2, log=lambda _: None)
        self.assertEqual(len(Progress(self.root).failed), 1)
        seen = []
        replies = [_call("edit_file", path="calc.py", old="a - b", new="a + b", reason="add, not subtract"), _done()]
        fix_tests(Workspace(self.root, lambda _: True), lambda m: seen.append(m) or replies.pop(0), log=lambda _: None)
        self.assertIn("FAILED", seen[0][1]["content"])
        self.assertIn("Round 1 fixed the tests", Progress(self.root).log_path.read_text())


class DoneAndCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "calc.py").write_text(BUGGY)
        (self.root / "test_calc.py").write_text(TEST)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_cannot_finish_until_check_command_passes(self) -> None:
        replies = [_call("set_done_criteria", criteria=["add returns the sum"], check_command="python3 -m unittest"),
                   _done("all done"),  # premature: tests still fail
                   _call("edit_file", path="calc.py", old="a - b", new="a + b", reason="add, not subtract"),
                   _done("fixed")]
        seen = []
        result = run_agent("fix", Workspace(self.root, lambda _: True), lambda m: seen.append(list(m)) or replies.pop(0),
                           log=lambda _: None)
        self.assertEqual(result, "fixed")
        self.assertIn("not done yet", seen[2][-1]["content"])

    def test_cannot_finish_with_open_plan_steps(self) -> None:
        replies = [_call("update_plan", steps=[{"step": "fix add", "status": "pending"}]), _done("done?"),
                   _call("update_plan", steps=[{"step": "fix add", "status": "done"}]), _done("done")]
        seen = []
        run_agent("t", Workspace(self.root, lambda _: True), lambda m: seen.append(list(m)) or replies.pop(0), log=lambda _: None)
        self.assertIn("plan step not done: fix add", seen[2][-1]["content"])

    def test_rejected_check_does_not_trap_the_agent(self) -> None:
        workspace = Workspace(self.root, lambda prompt: not prompt.startswith("Run"))
        replies = [_call("set_done_criteria", criteria=["x"], check_command="python3 -m unittest"), _done("ok")]
        self.assertEqual(run_agent("t", workspace, lambda m: replies.pop(0), log=lambda _: None), "ok")

    def test_python_that_does_not_parse_is_never_written(self) -> None:
        result = Workspace(self.root, lambda _: True).edit_file("calc.py", "a - b", "a +", reason="typo")
        self.assertIn("would not parse", result)
        self.assertEqual((self.root / "calc.py").read_text(), BUGGY)

    def test_done_criteria_are_remembered(self) -> None:
        progress = Progress(self.root)
        progress.begin("t")
        replies = [_call("set_done_criteria", criteria=["sum is right"])]
        run_agent("t", Workspace(self.root, lambda _: True), lambda m: replies[0], max_steps=1, log=lambda _: None, progress=progress)
        saved = Progress(self.root)
        saved.begin("t")
        self.assertIn("sum is right", saved.briefing())
