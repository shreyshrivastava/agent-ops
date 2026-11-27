import importlib.util
import unittest
from pathlib import Path
from unittest import mock

RUN = Path(__file__).parent.parent / "benchmark" / "run.py"
spec = importlib.util.spec_from_file_location("benchmark_run", RUN)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class BenchmarkRunnerTests(unittest.TestCase):
    def test_a_crashed_run_reports_its_error(self) -> None:
        def broken(messages):
            raise RuntimeError("model does not support tools")
        with mock.patch.object(run, "ollama_chat", return_value=broken):
            result = run.run_task(RUN.parent / "tasks" / "02_gst_rounding", run.BASELINE_PROMPT, "fake")
        self.assertFalse(result["passed"])
        self.assertIn("model does not support tools", result["error"])


if __name__ == "__main__":
    unittest.main()
