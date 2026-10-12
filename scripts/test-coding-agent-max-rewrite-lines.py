"""FILE: scripts/test-coding-agent-max-rewrite-lines.py

PURPOSE: Runs every max_rewrite_lines test (the write_text tool cases and the CodingAgent wiring cases) verbosely and prints "X/Y tests passed".
ROLE IN CODEBASE: The Phase 5 verification entrypoint for docs/design/coding-agent-max-rewrite-lines.md; the tests themselves live in tests/test_filesystem_tools.py (WriteTextOverwriteLimitTests) and tests/features/coding_agent/test_coding_agent_max_rewrite_lines.py.
ARCHITECTURE NOTE: A thin pytest runner with a small plugin that counts test outcomes; it adds no test logic of its own.
COMMON MODIFICATION PATTERNS: Add a test to one of the two targets; this script picks it up.
KNOWN EDGE CASES: The repository root is inserted for direct script execution; run with PYTHONPATH=<worktree> so the worktree's vidbyte is the one imported.
RELATED DOCS: docs/design/coding-agent-max-rewrite-lines.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python scripts/test-coding-agent-max-rewrite-lines.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

TARGETS = (
    "tests/test_filesystem_tools.py::WriteTextOverwriteLimitTests",
    "tests/features/coding_agent/test_coding_agent_max_rewrite_lines.py",
)


class OutcomeTally:
    """Pytest plugin that counts one outcome per test."""

    def __init__(self) -> None:
        self.passed = 0
        self.total = 0

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Count a test once: at its call phase, or at setup when setup failed.
        if report.when == "call" or (report.when == "setup" and not report.passed):
            self.total += 1
            self.passed += int(report.passed)


def main() -> int:
    # Runs both targets verbosely and turns pytest's result into the exit status.
    tally = OutcomeTally()
    exit_code = pytest.main(["-v", "-p", "no:cacheprovider", *(str(REPOSITORY_ROOT / target) for target in TARGETS)], plugins=[tally])
    print(f"{tally.passed}/{tally.total} tests passed")
    return 0 if exit_code == 0 and tally.passed == tally.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
