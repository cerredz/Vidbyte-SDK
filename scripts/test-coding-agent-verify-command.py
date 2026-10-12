"""FILE: scripts/test-coding-agent-verify-command.py

PURPOSE: Verification script for CodingAgent's verify_command (docs/design/coding-agent-verify-command.md): runs the feature-pack test module that holds every case in the design doc's testing plan, prints PASS or FAIL per test case, and ends with "X/Y tests passed".
ROLE IN CODEBASE: A thin runner over tests/features/coding_agent/test_coding_agent_verify_command.py, which is the source of truth for the cases; this script adds no cases of its own.
ARCHITECTURE NOTE: The module runs in a pytest subprocess with PYTHONPATH set to this checkout, so the code under test is this worktree's vidbyte package, never an installed copy. The verbose report is parsed line by line into one PASS, FAIL, or SKIP label per case.
FUNCTION INVENTORY: main runs pytest, prints the labels and the summary, and returns the exit code; _labelled_cases parses pytest's verbose report.
COMMON MODIFICATION PATTERNS: Add a case to the test module, not here.
WHAT NOT TO DO IN THIS FILE: Do not copy test cases into this script; two copies drift apart.
KNOWN EDGE CASES: A collection error yields no case lines, so the script reports 0/0 and fails on pytest's exit code. Skipped cases count toward neither side.
RELATED DOCS: docs/design/coding-agent-verify-command.md; tests/features/coding_agent/FEATURE.md
TESTS: python scripts/test-coding-agent-verify-command.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_MODULE = "tests/features/coding_agent/test_coding_agent_verify_command.py"
CASE_LINE = re.compile(r"^(?P<case>\S+::\S+) (?P<outcome>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
LABELS = {"PASSED": "PASS", "XFAIL": "PASS", "SKIPPED": "SKIP"}


def _labelled_cases(report: str) -> list[tuple[str, str]]:
    """Return (label, case name) for each test case line in pytest's verbose report."""
    cases = []
    for line in report.splitlines():
        match = CASE_LINE.match(line)
        if match is not None:
            cases.append((LABELS.get(match["outcome"], "FAIL"), match["case"].split("::", 1)[1]))
    return cases


def main() -> int:
    """Run the verify_command test module, print one label per case and the summary, and return the exit code."""
    # Run the module against this checkout's source, not an installed
    # copy of vidbyte, and keep pytest's own report for the failures.
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    completed = subprocess.run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", TEST_MODULE], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)

    # Print one PASS, FAIL, or SKIP line per case, then the summary.
    cases = _labelled_cases(completed.stdout)
    for label, case in cases:
        print(f"{label} {case}")
    passed = sum(label == "PASS" for label, _ in cases)
    counted = sum(label != "SKIP" for label, _ in cases)
    print(f"{passed}/{counted} tests passed")

    # On any failure, show pytest's report so the cause is visible.
    if completed.returncode != 0 or passed != counted:
        print(completed.stdout[-20_000:])
        print(completed.stderr[-5_000:], file=sys.stderr)
        return completed.returncode or 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
