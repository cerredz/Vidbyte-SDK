"""FILE: scripts/test_anthropic_usage_price_modifiers.py

PURPOSE: Runs every Section 10 case of the Anthropic usage price modifiers fix and prints PASS/FAIL per case plus an X/Y summary.
ROLE IN CODEBASE: Provides the offline verification entry point for docs/design/anthropic-usage-price-modifiers.md.
ARCHITECTURE NOTE: Runs the modifier tests and the catalog pricing pack through pytest in process, then the C010 and C005 lint gates as subprocesses; provider key variables are removed first, so no case can reach a paid API.
FUNCTION INVENTORY: CaseReporter (pytest plugin collecting one outcome per case); PriceModifierVerification.run, strip_provider_keys, run_test_pack, run_lint_gate, print_outcomes, exit_code.
COMMON MODIFICATION PATTERNS: Add new cases to the test files, not here; add a lint rule id to LINT_GATES when the feature gains a gate.
WHAT NOT TO DO IN THIS FILE: Do not disable pytest's terminal plugin; it supplies the assertion detail each FAIL line prints. Do not remove the key stripping.
KNOWN EDGE CASES: A failed import, a skipped case or a pytest session error each count as a failure, so an empty run never passes.
RELATED DOCS: docs/design/anthropic-usage-price-modifiers.md and tests/features/sdk_model_usage/FEATURE.md.
TESTS: Run python scripts/test_anthropic_usage_price_modifiers.py; it exits non-zero when any case fails.
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

TEST_PACK = (
    REPO_ROOT / "tests" / "features" / "sdk_model_usage" / "test_anthropic_price_modifiers.py",
    REPO_ROOT / "tests" / "features" / "sdk_model_catalog",
)
LINT_GATES = ("C010", "C005")
PROVIDER_KEY_VARIABLES = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROK_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY", "VIDBYTE_API_KEY")


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


class PriceModifierVerification:
    """Runs the Section 10 cases and reports PASS/FAIL per case."""

    def run(self) -> int:
        # Runs the test pack and lint gates, prints each case, and
        # returns the process exit code.
        # Remove real provider keys so no case can make a paid call.
        self.strip_provider_keys()
        # Run the unit and integration cases through pytest here.
        outcomes = self.run_test_pack()
        # Run the pricebook lint gates, one at a time.
        outcomes += [self.run_lint_gate(rule) for rule in LINT_GATES]
        # Print one line per case, then the summary line.
        self.print_outcomes(outcomes)
        return self.exit_code(outcomes)

    def strip_provider_keys(self) -> None:
        # Deletes provider key variables from this process, which the
        # lint subprocesses inherit.
        for name in PROVIDER_KEY_VARIABLES:
            os.environ.pop(name, None)

    def run_test_pack(self) -> list[tuple[str, bool, str]]:
        # Runs the test pack, one outcome per case; a pytest session
        # error becomes a failing case of its own.
        reporter = CaseReporter()
        # Pytest's report is buffered, not disabled: its terminal
        # plugin fills in the assertion detail a FAIL line prints.
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = pytest.main([*(str(path) for path in TEST_PACK), "-vv", "-p", "no:cacheprovider"], plugins=[reporter])
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
    raise SystemExit(PriceModifierVerification().run())
