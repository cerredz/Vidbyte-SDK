"""FILE: scripts/test-coding-agent-setup-commands.py

PURPOSE:
    Thin Phase-5 runner for docs/design/coding-agent-setup-commands.md.
    Runs the feature's pytest module with -v and prints "X/Y tests
    passed"; exits non-zero on any failure.

ROLE IN CODEBASE:
    Runs tests/features/coding_agent/test_coding_agent_setup_commands.py.
    Not imported by any production code.

ARCHITECTURE NOTE:
    The assertions live only in the pytest module, so this runner can
    never drift from the suite.

FUNCTION INVENTORY:
    main() -> int runs pytest and prints the summary.

COMMON MODIFICATION PATTERNS:
    Point TEST_MODULE elsewhere only if the feature's tests move.

WHAT NOT TO DO IN THIS FILE:
    Do not write assertions here.

KNOWN EDGE CASES:
    Skipped tests (no bash on the host) count as passed, matching
    pytest's exit status.

RELATED DOCS:
    docs/design/coding-agent-setup-commands.md

TESTS:
    `PYTHONPATH=$(pwd) python scripts/test-coding-agent-setup-commands.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_MODULE = REPO_ROOT / "tests" / "features" / "coding_agent" / "test_coding_agent_setup_commands.py"


class FailureCounter:
    """Pytest plugin that counts tests and the ones that failed in any phase."""

    def __init__(self) -> None:
        self.tests: set[str] = set()
        self.failed: set[str] = set()

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.tests.add(report.nodeid)
        if report.failed:
            self.failed.add(report.nodeid)


def main() -> int:
    # Run the feature's tests verbosely, then print the one-line summary.
    counter = FailureCounter()
    exit_code = pytest.main([str(TEST_MODULE), "-v", "-p", "no:cacheprovider"], plugins=[counter])
    print(f"{len(counter.tests) - len(counter.failed)}/{len(counter.tests)} tests passed")
    return int(exit_code != 0)


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    sys.exit(main())
