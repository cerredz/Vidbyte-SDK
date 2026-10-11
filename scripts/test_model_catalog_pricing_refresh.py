"""Standalone verification script for the model catalog and pricebook refresh.

Runs every Section 10 case of docs/design/model-catalog-pricing-refresh.md:
the tests/features/sdk_model_catalog pack (unit, integration and manual
QA cases) and the S014, C009 and C010 lint gates. Prints PASS/FAIL per
case with a final summary, and exits non-zero if any case fails.

Usage:
    python scripts/test_model_catalog_pricing_refresh.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

TEST_PACK = REPO_ROOT / "tests" / "features" / "sdk_model_catalog"
LINT_GATES = ("S014", "C009", "C010")


class CaseReporter:
    """Pytest plugin that keeps one outcome per test case."""

    def __init__(self) -> None:
        # Starts with no recorded outcomes.
        self.outcomes: list[tuple[str, bool, str]] = []

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Records each call phase, plus any setup or teardown that did
        # not pass, so a skipped case never counts as passed.
        if report.when == "call" or not report.passed:
            crash = getattr(getattr(report.longrepr, "reprcrash", None), "message", None)
            reason = "" if report.passed else (crash or str(report.longrepr)).strip().splitlines()[0]
            self.outcomes.append((report.nodeid.split("::", 1)[-1], report.passed, reason))

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        # Records a module that failed to import and so ran no cases.
        if report.failed:
            self.outcomes.append((f"collect {report.nodeid}", False, str(report.longrepr).strip().splitlines()[-1]))


class CatalogPricingVerification:
    """Runs the Section 10 cases and reports PASS/FAIL per case."""

    def run(self) -> int:
        # Runs the test pack and lint gates, prints each case, and
        # returns the process exit code.
        # Run the unit and integration cases through pytest here.
        outcomes = self.run_test_pack()
        # Run the lint gates the integration plan names, one at a time.
        outcomes += [self.run_lint_gate(rule) for rule in LINT_GATES]
        # Print one line per case, then the summary line.
        self.print_outcomes(outcomes)
        return self.exit_code(outcomes)

    def run_test_pack(self) -> list[tuple[str, bool, str]]:
        # Runs the sdk_model_catalog pack, one outcome per case; a
        # pytest session error becomes a failing case of its own.
        reporter = CaseReporter()
        # Pytest's report is buffered, not disabled: its terminal
        # plugin fills in the assertion detail a FAIL line prints.
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = pytest.main([str(TEST_PACK), "-vv", "-p", "no:cacheprovider"], plugins=[reporter])
        if exit_code not in (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED):
            reporter.outcomes.append(("pytest session", False, f"exit code {int(exit_code)}"))
        return reporter.outcomes

    def run_lint_gate(self, rule: str) -> tuple[str, bool, str]:
        # Runs one lint rule; passes only on a clean verdict and exit 0.
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        completed = subprocess.run([sys.executable, "lint/run.py", "--rule", rule, "--format", "json"], cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        try:
            verdict = json.loads(completed.stdout)["rules"][0]["verdict"]
        except (ValueError, KeyError, IndexError):
            return (f"lint {rule}", False, completed.stderr.strip()[-200:] or "unreadable lint output")
        return (f"lint {rule}", completed.returncode == 0 and verdict == "CLEAN", f"verdict {verdict}")

    def print_outcomes(self, outcomes: list[tuple[str, bool, str]]) -> None:
        # Prints a PASS or FAIL line per case and the X/Y summary line.
        for name, ok, reason in outcomes:
            print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"  -> {reason}"))
        passed = sum(ok for _, ok, _ in outcomes)
        print(f"\n{passed}/{len(outcomes)} tests passed")

    def exit_code(self, outcomes: list[tuple[str, bool, str]]) -> int:
        # Returns 0 only when cases ran and every one of them passed.
        return 0 if outcomes and all(ok for _, ok, _ in outcomes) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(CatalogPricingVerification().run())
