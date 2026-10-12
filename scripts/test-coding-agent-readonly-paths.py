"""FILE: scripts/test-coding-agent-readonly-paths.py

PURPOSE: Runs the offline CodingAgent readonly_paths feature tests and prints how many passed.
ROLE IN CODEBASE: The verification entrypoint for docs/design/coding-agent-readonly-paths.md; the pytest module it runs is the source of truth.
ARCHITECTURE NOTE: The script runs pytest in-process with -v and counts each test's call phase through a small plugin.
COMMON MODIFICATION PATTERNS: Add cases to the pytest module, never here.
KNOWN EDGE CASES: The repository root is inserted for direct script execution from any current directory. Windows-only cases are skipped on other hosts and are not counted.
RELATED DOCS: `docs/design/coding-agent-readonly-paths.md` and `tests/features/coding_agent/FEATURE.md`.
TESTS: `python scripts/test-coding-agent-readonly-paths.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

TEST_MODULE = REPOSITORY_ROOT / "tests" / "features" / "coding_agent" / "test_coding_agent_readonly_paths.py"


class _Tally:
    """Pytest plugin that counts the tests that ran and the tests that passed."""

    def __init__(self) -> None:
        self.ran = 0
        self.passed = 0

    def pytest_runtest_logreport(self, report: Any) -> None:
        # Counts each test once: its call phase, or a failed setup.
        if report.when == "call" or (report.when == "setup" and report.failed):
            self.ran += 1
            self.passed += int(report.passed)


def main() -> int:
    # Runs every readonly_paths test; any failure fails the script.
    tally = _Tally()
    exit_code = pytest.main([str(TEST_MODULE), "-v", "-p", "no:cacheprovider"], plugins=[tally])
    print(f"{tally.passed}/{tally.ran} tests passed")
    return 0 if exit_code == 0 and tally.passed == tally.ran else 1


if __name__ == "__main__":
    raise SystemExit(main())
