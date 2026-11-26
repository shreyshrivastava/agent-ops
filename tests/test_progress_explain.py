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
