"""Run verification tests for the adversarial context-window algorithm."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


class PassFailResult(unittest.TextTestResult):
    """TextTestResult that prints one PASS or FAIL line per test case."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Print a stable PASS line for each successful test case.
        super().addSuccess(test)
        print(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: object) -> None:
        # Print a stable FAIL line for assertion failures.
        super().addFailure(test, err)
        print(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err: object) -> None:
        # Print a stable FAIL line for unexpected errors.
        super().addError(test, err)
        print(f"FAIL {test.id()}")

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        # Treat skips as visible non-pass outcomes in the script output.
        super().addSkip(test, reason)
        print(f"FAIL {test.id()} SKIPPED {reason}")


class PassFailRunner(unittest.TextTestRunner):
    """Test runner that uses PassFailResult."""

    resultclass = PassFailResult


def main() -> int:
    # Load every test module that covers the approved design plan.
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        (
            "tests.test_adversarial_agent_tool",
            "tests.test_adversarial_reflection_algorithm",
            "tests.test_prompts_interface",
        )
    )
    result = PassFailRunner(verbosity=0).run(suite)
    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{total} tests passed")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    sys.exit(main())
