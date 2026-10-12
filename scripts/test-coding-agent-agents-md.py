"""FILE: scripts/test-coding-agent-agents-md.py

PURPOSE:
    Standalone Phase-5 verification script for
    docs/design/coding-agent-agents-md.md. Runs the feature's pytest
    module verbosely, prints one PASS/FAIL/SKIP line per test and a final
    "X/Y tests passed" line, and exits non-zero on any failure.

ROLE IN CODEBASE:
    Runs tests/features/coding_agent/test_coding_agent_agents_md.py, which
    exercises vidbyte/agents/coding.py, vidbyte/agents/coding_context/, and
    the CodingAgentSettings and CodingContextSectionText records. Not
    imported by any production code.

ARCHITECTURE NOTE:
    Delegates to pytest in-process with a small reporting plugin instead
    of duplicating assertions, so this script and the pytest suite can
    never drift apart. Everything runs offline with the feature pack's
    scripted model.

FUNCTION INVENTORY:
    ResultCollector.pytest_runtest_logreport records each test's outcome.
    main() -> int runs pytest and prints the per-test lines and summary.

COMMON MODIFICATION PATTERNS:
    Point TEST_MODULE at a different file only if the feature's tests move.

WHAT NOT TO DO IN THIS FILE:
    1. Do not write assertions here; they belong in the pytest module.
    2. Do not import this script from production code.

KNOWN EDGE CASES:
    A skipped test (the case-sensitive filesystem case on Windows) is
    printed as SKIP and counted as passed, matching pytest's exit status.

RELATED DOCS:
    docs/design/coding-agent-agents-md.md

TESTS:
    This script is itself a test runner; run it with
    `PYTHONPATH=$(pwd) python scripts/test-coding-agent-agents-md.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_MODULE = REPO_ROOT / "tests" / "features" / "coding_agent" / "test_coding_agent_agents_md.py"


class ResultCollector:
    """Pytest plugin that keeps each test's final outcome in run order."""

    def __init__(self) -> None:
        self.outcomes: dict[str, str] = {}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # A failure in any phase fails the test; a skip only counts when nothing failed.
        if report.failed:
            self.outcomes[report.nodeid] = "FAIL"
        elif report.skipped:
            self.outcomes.setdefault(report.nodeid, "SKIP")
        elif report.when == "call":
            self.outcomes.setdefault(report.nodeid, "PASS")


def main() -> int:
    # Run the feature's pytest module and print one line per test plus the summary.
    collector = ResultCollector()
    exit_code = pytest.main([str(TEST_MODULE), "-q", "-p", "no:cacheprovider"], plugins=[collector])
    for node_id, outcome in collector.outcomes.items():
        print(f"{outcome}: {node_id.split('::', 1)[-1]}")
    passed = sum(1 for outcome in collector.outcomes.values() if outcome != "FAIL")
    print(f"{passed}/{len(collector.outcomes)} tests passed")
    return 0 if exit_code == 0 and passed == len(collector.outcomes) else 1


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    sys.exit(main())
