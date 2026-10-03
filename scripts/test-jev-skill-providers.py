"""FILE: scripts/test-jev-skill-providers.py

PURPOSE: Runs every Jev skill provider and source test with a visible result per case.
ROLE IN CODEBASE: Provides the mandated feature-specific test gate and nonzero exit on failure.
ARCHITECTURE NOTE: Both local/native and remote-source modules use fake provider boundaries and no live credentials.
COMMON MODIFICATION PATTERNS: Add each new feature-specific test module to the explicit unittest suite here.
KNOWN EDGE CASES: A failure reports the individual case and preserves the aggregate passed count.
RELATED DOCS: docs/design/jev-skill-providers.md.
TESTS: Execute this script directly with python scripts/test-jev-skill-providers.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_skill_providers, test_jev_skill_remote_sources


def _flatten(suite: unittest.TestSuite) -> tuple[unittest.TestCase, ...]:
    # Flattens nested unittest suites so every case gets its own visible status.
    tests: list[unittest.TestCase] = []
    for item in suite:
        tests.extend(_flatten(item) if isinstance(item, unittest.TestSuite) else (item,))
    return tuple(tests)


def main() -> int:
    # Runs each discovered case in isolation and returns failure status for CI.
    suite = unittest.TestSuite(
        (
            unittest.defaultTestLoader.loadTestsFromModule(test_jev_skill_providers),
            unittest.defaultTestLoader.loadTestsFromModule(test_jev_skill_remote_sources),
        )
    )
    cases = _flatten(suite)
    failures = 0
    for case in cases:
        result = unittest.TestResult()
        case.run(result)
        if result.wasSuccessful():
            print(f"PASS {case.id()}")
            continue
        failures += 1
        print(f"FAIL {case.id()}")
        for test, error in (*result.failures, *result.errors):
            print(error)
    passed = len(cases) - failures
    print(f"{passed}/{len(cases)} tests passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
