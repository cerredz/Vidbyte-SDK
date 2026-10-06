"""FILE: lint/core/runner.py

PURPOSE: Executes selected rules and compares full counts with the baseline.
ROLE IN CODEBASE: Owns fail-closed rule isolation and one shared source catalogue.
ARCHITECTURE NOTE: A raising rule is ERRORED, never treated as zero findings.
FUNCTION INVENTORY: RuleRunner.run()/counts() produce result records and baselines.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by every lint command and canonical source CI.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from lint.core.baseline import BaselineStore, Verdict, verdict_for
from lint.core.diagnostic import Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule


@dataclass(frozen=True, slots=True)
class RuleResult:
    """One complete rule outcome before presentation."""

    rule: Rule
    findings: tuple[Finding, ...]
    allowance: int
    verdict: Verdict
    error: str = ""

    def failing(self) -> bool:
        # True when this result must fail the complete lint process.
        return self.verdict in {"REGRESSED", "ERRORED"}


class RuleRunner:
    """Runs selected rules over one source catalogue with baseline comparison."""

    def __init__(self, rules: tuple[Rule, ...], registered_ids: set[str], validate_baseline: bool = True) -> None:
        # Binds a stable selection and validates the complete catalogue when requested.
        self.rules = rules
        self.catalog = SourceCatalog()
        self.store = BaselineStore()
        self.allowances = self.store.load()
        if validate_baseline:
            self.store.validate(registered_ids)

    def run(self) -> tuple[RuleResult, ...]:
        # Executes each rule independently so one engine failure stays visible.
        return tuple(self._run_one(rule) for rule in self.rules)

    def counts(self, results: tuple[RuleResult, ...]) -> dict[str, int]:
        # Returns counts only when every selected rule completed successfully.
        errors = [result.rule.id for result in results if result.error]
        if errors:
            raise RuntimeError(f"Cannot update baseline because rules errored: {errors}.")
        return {result.rule.id: len(result.findings) for result in results}

    def _run_one(self, rule: Rule) -> RuleResult:
        # Sorts findings deterministically and converts unexpected errors to ERRORED.
        allowance = self.allowances.get(rule.id, 0)
        try:
            findings = tuple(sorted(rule.check(self.catalog), key=lambda item: (item.rel_path, item.line, item.symbol)))
        except Exception:
            return RuleResult(rule=rule, findings=(), allowance=allowance, verdict="ERRORED", error=traceback.format_exc())
        return RuleResult(rule=rule, findings=findings, allowance=allowance, verdict=verdict_for(len(findings), allowance))
