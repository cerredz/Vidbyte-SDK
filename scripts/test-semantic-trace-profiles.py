from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class SemanticTraceVerification:
    """Runs the semantic trace profile verification suite with PASS/FAIL output."""

    MODULES = (
        "tests.test_semantic_tracing",
        "tests.test_tracing",
        "tests.test_trace_facade",
        "tests.test_aggregate_agent",
    )

    def run(self) -> int:
        # Loads all verification tests, executes them, and prints one status line per case.
        suite = unittest.defaultTestLoader.loadTestsFromNames(self.MODULES)
        result = _RecordingResult()
        suite.run(result)
        result.print_report()
        return 0 if result.wasSuccessful() else 1


class _RecordingResult(unittest.TestResult):
    """Collects unittest outcomes and renders script-friendly status lines."""

    def __init__(self) -> None:
        # Initializes status storage before unittest execution.
        super().__init__()
        self.statuses: list[tuple[str, str, str]] = []

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Records one passing test case.
        super().addSuccess(test)
        self.statuses.append(("PASS", self._test_name(test), ""))

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        # Records one skipped optional-provider test case.
        super().addSkip(test, reason)
        self.statuses.append(("PASS", self._test_name(test), f"skipped: {reason}"))

    def addFailure(self, test: unittest.case.TestCase, err: object) -> None:
        # Records one assertion failure with formatted traceback.
        super().addFailure(test, err)
        self.statuses.append(("FAIL", self._test_name(test), self._exc_info_to_string(err, test)))

    def addError(self, test: unittest.case.TestCase, err: object) -> None:
        # Records one unexpected error with formatted traceback.
        super().addError(test, err)
        self.statuses.append(("FAIL", self._test_name(test), self._exc_info_to_string(err, test)))

    def print_report(self) -> None:
        # Prints PASS/FAIL rows and a final summary.
        passed = 0
        for status, name, detail in self.statuses:
            if status == "PASS":
                passed += 1
            suffix = f" - {detail}" if detail else ""
            print(f"{status}: {name}{suffix}")
        total = len(self.statuses)
        print(f"{passed}/{total} tests passed")

    @staticmethod
    def _test_name(test: unittest.case.TestCase) -> str:
        # Returns a stable test identifier for verification output.
        return test.id()


if __name__ == "__main__":
    sys.exit(SemanticTraceVerification().run())
