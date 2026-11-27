import subprocess
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
