import tempfile
import unittest
from pathlib import Path

from local_agent_ops.agent import run_agent
from local_agent_ops.tools import Workspace


def _scripted(*replies):
    """A fake model that returns canned replies in order."""
    queue = list(replies)
    return lambda messages: queue.pop(0)


def _call(name, **arguments):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


class WorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "a.py").write_text("x = 1\n")

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_blocks_paths_outside_workspace(self) -> None:
        with self.assertRaises(PermissionError):
            Workspace(self.root, lambda _: True).read_file("../etc/passwd")

    def test_rejected_write_leaves_file_unchanged(self) -> None:
        result = Workspace(self.root, lambda _: False).write_file("a.py", "x = 2\n")
        self.assertIn("rejected", result)
        self.assertEqual((self.root / "a.py").read_text(), "x = 1\n")

    def test_approved_write_counts_lines(self) -> None:
        ws = Workspace(self.root, lambda _: True)
        ws.write_file("a.py", "x = 9\nz = 0\n")
        ws.write_file("a.py", "x = 2\ny = 3\n")  # a rewrite counts once, against the original
        self.assertEqual(ws.net_lines(), (2, 1))

    def test_dry_run_never_writes_or_runs(self) -> None:
        ws = Workspace(self.root, lambda _: self.fail("should not ask"), dry_run=True)
        self.assertIn("DRY RUN", ws.write_file("a.py", "x = 2\n"))
        self.assertIn("DRY RUN", ws.run_command("python3 -V"))
        self.assertEqual((self.root / "a.py").read_text(), "x = 1\n")

    def test_blocks_unlisted_and_dangerous_commands(self) -> None:
        ws = Workspace(self.root, lambda _: True)
        self.assertIn("Blocked", ws.run_command("rm -rf ."))
        self.assertIn("Blocked", ws.run_command("git push"))
        self.assertIn("Blocked", ws.run_command("curl http://example.com"))

    def test_command_arguments_cannot_leave_workspace(self) -> None:
        ws = Workspace(self.root, lambda _: self.fail("should not ask"))
        for command in ("cat /etc/passwd", "grep -r key ~/.ssh", "cat ../outside.txt",
                        "grep --file=/etc/hosts x a.py", "git -C /tmp status", "git --git-dir=/tmp/.git log",
                        "git -c x=y push"):
            with self.subTest(command=command):
                self.assertIn("Blocked", ws.run_command(command))

    def test_paths_inside_workspace_are_allowed(self) -> None:
        self.assertIn("exit=0", Workspace(self.root, lambda _: True).run_command(f"cat {self.root}/a.py"))

    def test_truncated_file_cannot_be_written_back(self) -> None:
        big = "x = 1\n" * 30_000
        (self.root / "big.py").write_text(big)
        ws = Workspace(self.root, lambda _: True)
        self.assertIn("TRUNCATED", ws.read_file("big.py"))
        self.assertIn("Refused", ws.write_file("big.py", "x = 2\n"))
        self.assertEqual((self.root / "big.py").read_text(), big)

    def test_runs_allowed_command(self) -> None:
        self.assertIn("exit=0", Workspace(self.root, lambda _: True).run_command("python3 -c \"print(1)\""))


class AgentLoopTests(unittest.TestCase):
    def test_executes_tool_calls_then_returns_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ws = Workspace(Path(directory), lambda _: True)
            chat = _scripted(_call("write_file", path="hello.py", content="print('hi')"),
                             {"role": "assistant", "content": "Added hello.py."})
            self.assertEqual(run_agent("make hello", ws, chat, log=lambda _: None), "Added hello.py.")
            self.assertEqual((Path(directory) / "hello.py").read_text(), "print('hi')\n")

    def test_tool_errors_are_reported_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seen = []
            def chat(messages):
                seen.append(messages[-1])
                return _call("read_file", path="missing.py") if len(seen) == 1 else {"role": "assistant", "content": "done"}
            run_agent("read", Workspace(Path(directory), lambda _: True), chat, log=lambda _: None)
            self.assertTrue(seen[-1]["content"].startswith("Error:"))

    def test_stops_at_step_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chat = lambda messages: _call("list_files")
            result = run_agent("loop", Workspace(Path(directory), lambda _: True), chat, max_steps=3, log=lambda _: None)
            self.assertIn("Stopped after 3 steps", result)


if __name__ == "__main__":
    unittest.main()
