"""FILE: scripts/test-jev-agent-profile-routing.py

PURPOSE: Runs every Jev profile-routing, preflight, and tool-selection contract test with a PASS/FAIL line per case.
ROLE IN CODEBASE: Developers run this focused gate before the SDK source/package CI stages; it loads tests without making live provider calls.
ARCHITECTURE NOTE: The executable test pack is described in `tests/features/jev-agent-profile-routing/FEATURE.md`; module tests remain with their existing SDK subsystem suites.
FUNCTION INVENTORY: `ReportingResult` prints one result line per test; `main()` loads all Jev behavior modules, prints a total, and returns a shell exit code.
COMMON MODIFICATION PATTERNS: Add a touched Jev test module to `TEST_MODULES` and update the Feature test-pack map in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not filter tests or skip cases. 2. Do not construct live providers or require credentials; scripted fixtures own external boundaries.
KNOWN EDGE CASES: Skipped tests are excluded from the pass total and cause a non-zero exit; assertion failures and unexpected errors both print FAIL.
RELATED DOCS: `tests/features/jev-agent-profile-routing/FEATURE.md` and `skills/jev-agent/SKILL.md`.
TESTS: Runs `tests/test_jev_agent.py`, `tests/test_jev_preflight.py`, and `tests/test_jev_tool_selector.py`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_agent, test_jev_preflight, test_jev_tool_selector

TEST_MODULES = (test_jev_agent, test_jev_preflight, test_jev_tool_selector)


class ReportingResult(unittest.TextTestResult):
    """Prints a stable PASS or FAIL line for every executed test."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Reports each passing Jev feature contract after unittest records it.
        super().addSuccess(test)
        self.stream.writeln(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Reports assertion failures with the exact test identifier.
        super().addFailure(test, err)
        self.stream.writeln(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Reports unexpected exceptions with the exact test identifier.
        super().addError(test, err)
        self.stream.writeln(f"FAIL {test.id()}")


def main() -> int:
    # Loads the complete Jev profile, preflight, and tool-selector test suites.
    loader = unittest.defaultTestLoader
    suites = tuple(loader.loadTestsFromModule(module) for module in TEST_MODULES)
    suite = unittest.TestSuite(suites)
    runner = unittest.TextTestRunner(verbosity=0, resultclass=ReportingResult)
    result = runner.run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} Jev profile-routing tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
