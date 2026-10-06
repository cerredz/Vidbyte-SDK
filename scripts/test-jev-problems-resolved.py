"""FILE: scripts/test-jev-problems-resolved.py

PURPOSE: Runs the focused, network-free Jev problem-repair gate tests and prints a clear result for each case.
ROLE IN CODEBASE: Provides an executable verification entrypoint for the PROBLEMS_RESOLVED done check.
ARCHITECTURE NOTE: The script loads matching cases from tests/test_jev_done.py and returns non-zero if any case fails.
COMMON MODIFICATION PATTERNS: Include every new problem-repair contract case in the focused name filter.
KNOWN EDGE CASES: The repository root is inserted for direct execution from any working directory.
RELATED DOCS: docs/design/jev-mid-run-problem-repair-gate.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md.
TESTS: This script executes the problem-related tests in tests/test_jev_done.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_done


def _flatten(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    """Return the tests nested in a suite in execution order."""
    result = []
    for item in suite:
        result.extend(_flatten(item) if isinstance(item, unittest.TestSuite) else [item])
    return result


def main() -> int:
    """Run problem-repair contract tests and return a shell-friendly status."""
    cases = [case for case in _flatten(unittest.defaultTestLoader.loadTestsFromModule(test_jev_done)) if "problem" in case.id().lower()]
    failures = 0
    for case in cases:
        result = unittest.TestResult()
        case.run(result)
        if result.wasSuccessful():
            print(f"PASS {case.id()}")
            continue
        failures += 1
        print(f"FAIL {case.id()}")
        for test, error in result.errors + result.failures:
            print(error)
    passed = len(cases) - failures
    print(f"{passed}/{len(cases)} tests passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
