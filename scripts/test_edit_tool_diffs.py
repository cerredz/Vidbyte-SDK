"""FILE: scripts/test_edit_tool_diffs.py

PURPOSE: Verification runner for the edit-tool-diffs change; runs the edit diff tests with -v, prints "X/Y tests passed", and exits non-zero on any failure.
ROLE IN CODEBASE: Thin pytest wrapper over tests/test_filesystem_tools.py::EditToolDiffTests and the CodingAgent feature-pack test that checks the model sees the diff.
ARCHITECTURE NOTE: Holds no test logic of its own; the cases live in the two test files so CI runs them too.
COMMON MODIFICATION PATTERNS: Add a node id to EDIT_DIFF_TESTS when a new edit diff test is added.
KNOWN EDGE CASES: A failed subTest fails its whole test, so the count is per test method, not per subTest.
RELATED DOCS: docs/design/edit-tool-diffs.md
TESTS: PYTHONPATH=$(pwd) python scripts/test_edit_tool_diffs.py
"""

from __future__ import annotations

import sys

import pytest

EDIT_DIFF_TESTS = (
    "tests/test_filesystem_tools.py::EditToolDiffTests",
    "tests/test_filesystem_tools.py::FileSystemToolErrorPathTests::test_replace_text_search_not_found_returns_error",
    "tests/features/coding_agent/test_coding_agent_acceptance.py::test_model_sees_what_each_edit_changed_in_its_tool_messages",
)


class OutcomeCounter:
    """Counts one outcome per test that pytest runs."""

    def __init__(self) -> None:
        self.passed = 0
        self.total = 0

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Count the call phase, or the setup phase when setup failed.
        if report.when == "call" or (report.when == "setup" and report.failed):
            self.total += 1
            self.passed += int(report.passed)


def main() -> int:
    # Run the edit diff tests verbosely, then print the pass count.
    counter = OutcomeCounter()
    exit_code = pytest.main(["-v", *EDIT_DIFF_TESTS], plugins=[counter])
    print(f"{counter.passed}/{counter.total} tests passed")
    return int(exit_code)


if __name__ == "__main__":
    sys.exit(main())
