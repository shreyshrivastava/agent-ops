import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from local_agent_ops.cli import main
from local_agent_ops.review import review_diff


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True, capture_output=True)


class ReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        _git(self.root, "init", "-q")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "init")

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_reviews_the_diff_without_writing(self) -> None:
        (self.root / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        replies = [{"role": "assistant", "content": "", "tool_calls": [{"function": {
                       "name": "write_file", "arguments": {"path": "calc.py", "content": "x", "reason": "r"}}}]},
                   {"role": "assistant", "content": "1. calc.py:2 subtracts instead of adding."}]
        seen = []
        result = review_diff(self.root, "HEAD", lambda m: seen.append(list(m)) or replies.pop(0), log=lambda _: None)
        self.assertIn("-    return a + b", seen[0][-1]["content"])  # the diff is the task
        self.assertIn("calc.py:2", result)
        self.assertEqual((self.root / "calc.py").read_text(), "def add(a, b):\n    return a - b\n")  # review never writes

    def test_no_changes_does_not_call_the_model(self) -> None:
        result = review_diff(self.root, "HEAD", lambda m: self.fail("model should not be called"), log=lambda _: None)
        self.assertIn("No changes", result)

    def _exit_code(self, reply: str) -> int:
        with mock.patch("local_agent_ops.cli.ollama_chat", return_value=lambda m: {"role": "assistant", "content": reply}), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(["review", "--workspace", str(self.root)])

    def test_exit_codes_say_whether_there_are_findings(self) -> None:
        self.assertEqual(self._exit_code("unused"), 0)  # no changes: clean, model not needed
        (self.root / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        self.assertEqual(self._exit_code("No problems found."), 0)
        self.assertEqual(self._exit_code("1. calc.py:2 subtracts instead of adding."), 1)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["review", "--workspace", str(self.root), "--base", "no-such-branch"]), 2)


if __name__ == "__main__":
    unittest.main()
