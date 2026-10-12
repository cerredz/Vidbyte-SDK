#!/usr/bin/env python3
"""FILE: scripts/test-single-content-type-header.py

PURPOSE: Runs the single-content-type-header test cases and prints one labelled result per case plus an X/Y summary.
ROLE IN CODEBASE: Phase-5 verification runner for docs/design/single-content-type-header.md.
ARCHITECTURE NOTE: Drives pytest in-process with a small reporter plugin, so the cases run exactly as the suite runs them.
COMMON MODIFICATION PATTERNS: Add a node id to TESTS when the design's testing plan grows.
KNOWN EDGE CASES: An empty collection or any skipped case counts as a failure.
RELATED DOCS: docs/design/single-content-type-header.md.
TESTS: python scripts/test-single-content-type-header.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

TESTS = ("tests/test_http_transport_content_type.py",)


class _ResultReporter:
    def __init__(self) -> None:
        # Keeps collection order and the final result of each test item.
        self.nodeids: list[str] = []
        self.outcomes: dict[str, str] = {}

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        # Records exactly the cases pytest collected.
        self.nodeids = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Records failures from any phase, and passes or skips from the call phase.
        if report.failed:
            self.outcomes[report.nodeid] = "FAIL"
        elif report.when == "call" and report.passed:
            self.outcomes[report.nodeid] = "PASS"
        elif report.when == "call" and report.skipped:
            self.outcomes[report.nodeid] = "SKIP"

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        # Prints one line per case and fails closed on skips or an empty run.
        del exitstatus
        passed = 0
        for nodeid in self.nodeids:
            result = self.outcomes.get(nodeid, "FAIL")
            print(f"{result}: {nodeid}", flush=True)
            passed += result == "PASS"
        total = len(self.nodeids)
        print(f"{passed}/{total} tests passed", flush=True)
        if total == 0 or passed != total:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


def main() -> int:
    # Runs the content-type cases from the repository root.
    os.chdir(REPO_ROOT)
    return int(pytest.main(["-q", "-s", "-p", "no:cacheprovider", *TESTS], plugins=[_ResultReporter()]))


if __name__ == "__main__":
    raise SystemExit(main())
