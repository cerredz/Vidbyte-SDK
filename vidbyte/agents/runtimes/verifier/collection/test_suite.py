"""Context Protocol Header

Description:
    Defines TestSuiteVerifier.
Purpose:
    Runs a configured test-suite command and gates on the fraction of tests
    that passed, per the JUnit XML report the command produces. The first
    concrete VerifierKind.CODE_EXECUTION implementation this SDK ships.
Architecture note:
    - _JUnitSummary: total/failed/failing_names parsed out of one report.
    - TestSuiteVerifier: Verifier subclass taking (params, config), following
      the same two-argument shape CallableVerifier already established.
Relations:
    Consumes vidbyte.lib.dataclasses.verifier.TestSuiteVerifierConfig.
    Consumed by vidbyte.agents.runtimes.verifier.collection.VerifierCollection.
Similar Files:
    - vidbyte/agents/runtimes/verifier/target.py: _git_diff, the nearest
      existing "shell out and degrade gracefully" subprocess pattern.
Role in codebase:
    Provides the built-in test-suite command verifier implementation.
Common modification patterns:
    Change command and pass-fraction policy through TestSuiteVerifierConfig.
Known edge cases:
    Missing or malformed JUnit reports become explicit failed verdicts.
Related docs:
    docs/design/verifier-runtime-builtin-verifiers.md
Tests:
    Covered by test-suite verifier tests.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from vidbyte.agents.runtimes.verifier.verifier import Verifier
from vidbyte.lib.dataclasses.verifier import TestSuiteVerifierConfig, VerifierKind, VerifierParams, VerifierTarget, VerifierVerdict
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class _JUnitSummary:
    """One report's parsed test counts and failing test names."""

    total: int
    failed: int
    failing_names: tuple[str, ...]


class TestSuiteVerifier(Verifier):
    """Runs a test-suite command and gates on the fraction of tests that passed, per its JUnit XML report."""

    def __init__(self, params: VerifierParams, config: TestSuiteVerifierConfig) -> None:
        # Validates the verifier is declared as CODE_EXECUTION before storing its test-suite-specific config.
        super().__init__(params)
        self._validate_kind()
        self._config = config

    def _validate_kind(self) -> None:
        # A misdeclared kind would report inaccurately to VerifierCollectionParams and downstream feedback.
        if self.params.kind is not VerifierKind.CODE_EXECUTION:
            raise ConfigurationError(f"TestSuiteVerifier requires kind=VerifierKind.CODE_EXECUTION, got {self.params.kind!r}.")

    def applicable(self, target: VerifierTarget) -> bool:
        """Skips this verifier when the target carries no workspace to run the command in."""
        return target.workspace_root is not None

    async def check(self, target: VerifierTarget) -> VerifierVerdict:
        """Runs the configured test command, parses its JUnit report, and gates on pass_fraction."""
        started = time.monotonic()
        await self._run_command(target.workspace_root)
        summary = self._parse_report(target.workspace_root)
        return self._to_verdict(summary, duration_seconds=time.monotonic() - started)

    # @intent bounded-test-process
    async def _run_command(self, workspace_root: str) -> None:
        # Runs off the event loop; a non-zero exit means "tests failed," not a crash, so check=False.
        env = {**os.environ, **(self._config.env or {})}
        await asyncio.to_thread(subprocess.run, self._config.command, cwd=workspace_root, env=env, capture_output=True, text=True, check=False)

    def _parse_report(self, workspace_root: str) -> _JUnitSummary:
        # Reads the JUnit XML the command was configured to produce; a missing report propagates as a real failure.
        report_path = os.path.join(workspace_root, self._config.report_path)
        root = ET.parse(report_path).getroot()
        total = 0
        failed = 0
        failing_names: list[str] = []
        for case in root.iter("testcase"):
            if self._config.scope_path and not self._in_scope(case):
                continue
            if case.find("skipped") is not None:
                continue
            total += 1
            if case.find("failure") is not None or case.find("error") is not None:
                failed += 1
                failing_names.append(f"{case.get('classname', '')}::{case.get('name', '')}")
        return _JUnitSummary(total=total, failed=failed, failing_names=tuple(failing_names))

    def _in_scope(self, case: ET.Element) -> bool:
        # A testcase is in scope when its classname or file attribute starts with the configured scope_path.
        classname = case.get("classname", "").replace(".", "/")
        file_attr = case.get("file", "")
        return classname.startswith(self._config.scope_path) or file_attr.startswith(self._config.scope_path)

    def _to_verdict(self, summary: _JUnitSummary, *, duration_seconds: float) -> VerifierVerdict:
        # Converts the parsed summary into a verdict; zero collected tests never counts as a pass.
        fraction_passed = (summary.total - summary.failed) / summary.total if summary.total else 0.0
        passed = summary.total > 0 and fraction_passed >= self._config.pass_fraction
        return VerifierVerdict(
            verifier_name=self.params.name,
            tier=self.params.tier,
            blocking=self.params.blocking,
            passed=passed,
            score=fraction_passed,
            diagnostics=self._describe(summary, fraction_passed),
            duration_seconds=duration_seconds,
        )

    def _describe(self, summary: _JUnitSummary, fraction_passed: float) -> str:
        # Human-readable summary, capped to the first ten failing test names.
        if summary.total == 0:
            scope = f" under scope '{self._config.scope_path}'" if self._config.scope_path else ""
            return f"No tests were collected{scope}."
        passed_count = summary.total - summary.failed
        header = f"{passed_count}/{summary.total} passed ({fraction_passed:.0%})"
        if not summary.failing_names:
            return header
        shown = ", ".join(summary.failing_names[:10])
        suffix = "..." if len(summary.failing_names) > 10 else ""
        return f"{header}. Failing: {shown}{suffix}"


__all__ = ["TestSuiteVerifier"]
