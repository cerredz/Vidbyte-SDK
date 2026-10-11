"""FILE: scripts/test-coding-agent-map-md.py

PURPOSE: Thin Phase-5 runner for docs/design/coding-agent-map-md.md: runs the feature's pytest module verbosely, then prints "X/Y tests passed" and exits non-zero on any failure.
ROLE IN CODEBASE: Runs tests/features/coding_agent/test_coding_agent_map_md.py. Not imported by any production code.
ARCHITECTURE NOTE: Delegates to pytest in-process, so this script and the pytest suite can never drift apart; pytest's -v output gives the per-test PASSED/FAILED lines.
FUNCTION INVENTORY: SummaryLine.pytest_terminal_summary prints the count line; main() runs pytest.
COMMON MODIFICATION PATTERNS: Point TEST_MODULE at a different file only if the feature's tests move.
WHAT NOT TO DO IN THIS FILE: 1. Do not write assertions here; they belong in the pytest module.
KNOWN EDGE CASES: A skipped test counts as passed, matching pytest's exit status.
RELATED DOCS: docs/design/coding-agent-map-md.md
TESTS: PYTHONPATH=$(pwd) python scripts/test-coding-agent-map-md.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_MODULE = REPO_ROOT / "tests" / "features" / "coding_agent" / "test_coding_agent_map_md.py"


class SummaryLine:
    """Pytest plugin that prints the "X/Y tests passed" line after pytest's own summary."""

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        stats = terminalreporter.stats
        failed = len(stats.get("failed", [])) + len(stats.get("error", []))
        passed = len(stats.get("passed", [])) + len(stats.get("skipped", []))
        terminalreporter.write_line(f"{passed}/{passed + failed} tests passed")


def main() -> int:
    # Run the feature's pytest module verbosely and return its exit status.
    return int(pytest.main([str(TEST_MODULE), "-v", "-p", "no:cacheprovider"], plugins=[SummaryLine()]))


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    sys.exit(main())
