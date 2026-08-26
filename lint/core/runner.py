"""FILE: lint/core/runner.py

PURPOSE:
    Orchestrates one lint run end to end: discovery, the single Ruff
    invocation, per-rule collection, baseline comparison, and report
    assembly.
ROLE IN CODEBASE:
    The only component that knows the full pipeline order. lint/run.py
    builds one LintRunner and calls run(); everything else in lint/core/
    is a narrow collaborator this class composes.
ARCHITECTURE NOTE:
    Ruff runs exactly once per invocation with the union of every selected
    rule's selectors (FR-4). Adding a second rule later means one new
    lint/rules/sNNN_*.py module plus one registry entry; this file does not
    change.
WHAT NOT TO DO IN THIS FILE:
    Do not let one rule's find() exception propagate uncaught; convert it
    to an ERRORED outcome so a broken rule is diagnosable, not indistinguishable
    from a passing one and not a crash of the whole CLI.
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
    docs/design/sdk-lint-contract-rules.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lint.core.baseline import BaselineStore, LintVerdict
from lint.core.diagnostic import Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import RuleRegistry
from lint.core.rule import LintRule
from lint.core.ruff import RuffAdapter, RuffFinding


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """One rule's verdict, counts, and findings for a single lint run."""

    rule_id: str
    verdict: LintVerdict
    baseline_count: int
    actual_count: int
    findings: tuple[Finding, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RunReport:
    """The complete result of one lint run across every selected rule."""

    outcomes: tuple[RuleOutcome, ...]
    stale_baseline_keys: tuple[str, ...]
    missing_baseline_keys: tuple[str, ...]

    @property
    def passed(self) -> bool:
        # True only when every outcome is clean/ratcheted/improved and no key mismatch exists.
        failing_verdicts = {LintVerdict.REGRESSED, LintVerdict.ERRORED}
        no_bad_outcome = not any(outcome.verdict in failing_verdicts for outcome in self.outcomes)
        no_key_mismatch = not self.stale_baseline_keys and not self.missing_baseline_keys
        return no_bad_outcome and no_key_mismatch


class LintRunner:
    """Runs discovery, Ruff, per-rule collection, and baseline comparison."""

    def __init__(self, repository_root: Path, package_root: Path, baseline_path: Path) -> None:
        # Retains the roots and baseline file this runner will read/compare against.
        self._repository_root = repository_root
        self._package_root = package_root
        self._baseline_path = baseline_path

    def run(self, *, rule_ids: tuple[str, ...] | None = None) -> RunReport:
        # Runs the selected rules (or every registered rule) and returns the full report.
        selected = self._resolve_rules(rule_ids)
        files = SourceCatalog.python_files(self._repository_root, self._package_root)
        baseline = BaselineStore.load(self._baseline_path)
        all_findings = self._run_ruff_if_needed(selected)
        outcomes = tuple(self._evaluate_rule(rule, files, all_findings, baseline) for rule in selected)
        stale, missing = self._baseline_key_mismatches(baseline)
        return RunReport(outcomes=outcomes, stale_baseline_keys=stale, missing_baseline_keys=missing)

    def _run_ruff_if_needed(self, rules: tuple[type[LintRule], ...]) -> tuple[RuffFinding, ...]:
        # Runs Ruff once with the selected rules' unioned selectors, or skips it when none declare any.
        selectors = self._union_selectors(rules)
        if not selectors:
            return ()
        return RuffAdapter.run(self._package_root, selectors)

    def _resolve_rules(self, rule_ids: tuple[str, ...] | None) -> tuple[type[LintRule], ...]:
        # Returns the requested rule classes, or every registered rule when none are requested.
        if rule_ids is None:
            return RuleRegistry.all_rules()
        return tuple(RuleRegistry.by_id(rule_id) for rule_id in rule_ids)

    def _union_selectors(self, rules: tuple[type[LintRule], ...]) -> tuple[str, ...]:
        # Merges every selected rule's ruff_selectors into one deduplicated tuple.
        merged: set[str] = set()
        for rule in rules:
            merged.update(rule.ruff_selectors)
        return tuple(sorted(merged))

    def _evaluate_rule(self, rule: type[LintRule], files: tuple[Path, ...], all_findings: tuple[RuffFinding, ...], baseline: dict[str, int]) -> RuleOutcome:
        # Runs one rule's find() and compares its finding count against its baseline entry.
        # Broad except is deliberate: a broken rule must become a diagnosable ERRORED
        # outcome, never an uncaught crash of the whole CLI.
        try:
            findings = rule.find(files, all_findings)
        except Exception as exc:
            return RuleOutcome(
                rule_id=rule.rule_id,
                verdict=LintVerdict.ERRORED,
                baseline_count=baseline.get(rule.rule_id, 0),
                actual_count=0,
                findings=(),
                error=repr(exc),
            )
        baseline_count = baseline.get(rule.rule_id, 0)
        verdict = BaselineStore.evaluate(baseline_count, len(findings))
        return RuleOutcome(
            rule_id=rule.rule_id,
            verdict=verdict,
            baseline_count=baseline_count,
            actual_count=len(findings),
            findings=findings,
        )

    def _baseline_key_mismatches(self, baseline: dict[str, int]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        # Compares the full registry's ids against the baseline file's keys, independent of --rule.
        registered_ids = {rule.rule_id for rule in RuleRegistry.all_rules()}
        baseline_ids = set(baseline.keys())
        stale = tuple(sorted(baseline_ids - registered_ids))
        missing = tuple(sorted(registered_ids - baseline_ids))
        return stale, missing


__all__ = ["LintRunner", "RuleOutcome", "RunReport"]
