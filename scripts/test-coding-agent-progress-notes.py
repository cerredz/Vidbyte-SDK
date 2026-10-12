"""FILE: scripts/test-coding-agent-progress-notes.py

PURPOSE: Thin Phase-5 runner for docs/design/coding-agent-progress-notes.md: runs the feature's pytest module with -v and prints "X/Y tests passed".
ROLE IN CODEBASE: Runs tests/features/coding_agent/test_coding_agent_progress_notes.py; not imported by any production code.
ARCHITECTURE NOTE: Delegates to pytest in-process, so this script and the suite cannot drift apart.
FUNCTION INVENTORY: Counter.pytest_runtest_logreport counts call-phase outcomes; main runs pytest and prints the summary.
COMMON MODIFICATION PATTERNS: Point TEST_MODULE elsewhere only if the tests move.
WHAT NOT TO DO IN THIS FILE: Do not write assertions here; they belong in the pytest module.
KNOWN EDGE CASES: A skipped test (git missing) counts as passed, matching pytest's exit status.
RELATED DOCS: docs/design/coding-agent-progress-notes.md
TESTS: PYTHONPATH=$(pwd) python scripts/test-coding-agent-progress-notes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TEST_MODULE = Path(__file__).resolve().parent.parent / "tests" / "features" / "coding_agent" / "test_coding_agent_progress_notes.py"


class Counter:
    """Pytest plugin that counts tests and failures."""

    def __init__(self) -> None:
        self.total = 0
        self.failed = 0

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call" or report.skipped:
            self.total += 1
        if report.failed:
            self.failed += 1


def main() -> int:
    # Run the module verbosely, then print the summary line.
    counter = Counter()
    exit_code = pytest.main([str(TEST_MODULE), "-v", "-p", "no:cacheprovider"], plugins=[counter])
    print(f"{counter.total - counter.failed}/{counter.total} tests passed")
    return int(exit_code != 0)


if __name__ == "__main__":
    sys.exit(main())
