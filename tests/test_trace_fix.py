import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from local_agent_ops.agent import run_agent
from local_agent_ops.cli import main
from local_agent_ops.fix import TEST_FILES, count_failures, fix_tests
from local_agent_ops.tools import Workspace
from local_agent_ops.trace import Trace, list_runs, load, mask, render

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
TEST = "import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"


def _call(name, **arguments):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def _done(text="done"):
    return {"role": "assistant", "content": text}


class TraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_run_writes_a_replayable_trace(self) -> None:
        trace = Trace(self.root, "make hello", "fake")
        replies = [_call("write_file", path="hello.py", content="print('hi')"), _done("Added hello.py.")]
        run_agent("make hello", Workspace(self.root, lambda _: True), lambda m: replies.pop(0), log=lambda _: None, trace=trace)
        events = load(trace.path)
        self.assertEqual([e["kind"] for e in events], ["start", "model", "tool", "model", "end"])
        self.assertTrue(all(e["v"] == 1 for e in events))
        self.assertIn("→ write_file(path='hello.py')", render(events))
        self.assertEqual(list_runs(self.root)[0]["outcome"], "done")

    def test_step_limit_is_recorded(self) -> None:
        trace = Trace(self.root, "loop")
        run_agent("loop", Workspace(self.root, lambda _: True), lambda m: _call("list_files"), max_steps=2,
                  log=lambda _: None, trace=trace)
        self.assertEqual(load(trace.path)[-1]["reason"], "step_limit")

    def test_traces_are_gitignored_and_agent_cannot_edit_them(self) -> None:
        Trace(self.root, "x")
        self.assertEqual((self.root / ".agent-ops/.gitignore").read_text(), "*\n")
        self.assertIn("Refused", Workspace(self.root, lambda _: True).write_file(".agent-ops/runs/x.jsonl", "{}"))

    def test_secrets_are_masked(self) -> None:
        masked = mask({"result": "key = 'sk-abcdefgh12345678' and Bearer abc.def"})
        self.assertNotIn("sk-abcdefgh", masked["result"])
        self.assertNotIn("abc.def", masked["result"])

    def test_cli_runs_and_replay(self) -> None:
        trace = Trace(self.root, "demo task")
        trace.event("end", reason="done", summary="ok")
        out = io.StringIO()
        with redirect_stdout(out):
            main(["runs", "--workspace", str(self.root)])
            main(["replay", trace.path.stem, "--workspace", str(self.root)])
        self.assertIn("demo task", out.getvalue())
        self.assertIn("end (done)", out.getvalue())


class FixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "calc.py").write_text(BUGGY)
        (self.root / "test_calc.py").write_text(TEST)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def _workspace(self):
        return Workspace(self.root, lambda _: True, read_only=TEST_FILES)

    def test_counts_unittest_and_pytest_failures(self) -> None:
        self.assertEqual(count_failures("FAILED (failures=2, errors=1)", 1), 3)
        self.assertEqual(count_failures("=== 2 failed, 5 passed in 0.1s ===", 1), 2)
        self.assertEqual(count_failures("anything", 0), 0)
        self.assertIsNone(count_failures("Segmentation fault", 139))

    def test_fixes_failing_tests_and_stops_when_green(self) -> None:
        replies = [_call("write_file", path="calc.py", content=FIXED), _done()]
        result = fix_tests(self._workspace(), lambda m: replies.pop(0), log=lambda _: None)
        self.assertTrue(result["passed"])
        self.assertEqual(result["failing"], [1, 0])
        self.assertEqual(len(result["traces"]), 1)

    def test_test_files_are_read_only(self) -> None:
        result = self._workspace().write_file("test_calc.py", "")
        self.assertIn("read-only", result)
        self.assertEqual((self.root / "test_calc.py").read_text(), TEST)

    def test_stops_when_nothing_improves(self) -> None:
        result = fix_tests(self._workspace(), lambda m: _done("I could not fix it."), rounds=3, log=lambda _: None)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "no progress")
        self.assertEqual(len(result["traces"]), 1)

    def test_already_passing_does_not_call_the_model(self) -> None:
        (self.root / "calc.py").write_text(FIXED)
        result = fix_tests(self._workspace(), lambda m: self.fail("model should not be called"), log=lambda _: None)
        self.assertEqual(result["reason"], "already passing")


if __name__ == "__main__":
    unittest.main()
