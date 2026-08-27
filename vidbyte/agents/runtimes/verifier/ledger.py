"""Context Protocol Header

Description:
    Defines VerifierLedger and VerifierLedgerStatistics.
Purpose:
    VerifierLedger records every verification attempt this run has made and
    exposes only ledger/metadata read-back (history, last, report).
    VerifierLedgerStatistics is the subclass that derives history-aware
    statistics from that record: score trend, regressions, flakiness, a
    tamper baseline, and the ContextItem flattening every other pillar reads.
Architecture:
    - VerifierLedger: record()/history()/last()/report() — ledger and
      metadata only, no derived statistics.
    - VerifierLedgerStatistics(VerifierLedger): score_trend(),
      regressions_since(), flaky_verifiers(), baseline_snapshot(),
      tamper_check(), and to_context_items(), which flattens ledger state
      into the eight vidbyte.context.primitives.verifier ContextItems.
    VerifierLedgerParams (validated dataclass: run_id + whether to publish
    state into the agent's ContextManager) lives in
    vidbyte.lib.dataclasses.verifier, not here, per review feedback on
    PR #349.
Relations:
    Records vidbyte.agents.runtimes.verifier.types.VerificationAttempt.
    Read by VerifierRuntimeGate.decide() and VerifierRuntimeBudget via
    duck-typed access (type-hinted only, to avoid an import cycle). The
    concrete instance every pillar is actually handed is a
    VerifierLedgerStatistics, constructed by AgentVerifierRuntime.
Similar Files:
    - vidbyte/agents/contract.py: AgentLoopSettingsOutputContract.report(),
      the nearest existing "read-back state for a result's metadata" shape.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.context.primitives.verifier import (
    VerifierBudgetContextItem,
    VerifierDiagnosticContextItem,
    VerifierFlakeContextItem,
    VerifierHistoryContextItem,
    VerifierRegressionContextItem,
    VerifierScopeContextItem,
    VerifierTamperContextItem,
    VerifierTrendContextItem,
)
from vidbyte.lib.dataclasses.verifier import RepairOutcome, VerificationAttempt, VerifierLedgerParams, VerifierTarget

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.budget import VerifierRuntimeBudget
    from vidbyte.context.primitives import ContextItem


class VerifierLedger:
    """Append-only record of every verification attempt this run has made, plus metadata read-back."""

    def __init__(self, params: VerifierLedgerParams) -> None:
        # Stores the already-validated configuration and starts an empty attempt history.
        self.params = params
        self._attempts: list[VerificationAttempt] = []

    def record(self, attempt: VerificationAttempt) -> None:
        """Appends one completed verification attempt to this run's history."""
        self._attempts.append(attempt)

    def history(self) -> tuple[VerificationAttempt, ...]:
        """Returns every recorded attempt, oldest first."""
        return tuple(self._attempts)

    def last(self) -> VerificationAttempt | None:
        """Returns the most recently recorded attempt, or None if nothing has been recorded yet."""
        return self._attempts[-1] if self._attempts else None

    def report(self) -> list[dict[str, Any]]:
        """Returns one record per verifier verdict across every attempt, mirroring contract_evaluations' shape."""
        return [
            {
                "attempt_number": attempt.attempt_number,
                "verifier_name": verdict.verifier_name,
                "passed": verdict.passed,
                "score": verdict.score,
                "blocking": verdict.blocking,
            }
            for attempt in self._attempts
            for verdict in attempt.aggregated.verdicts
        ]


class VerifierLedgerStatistics(VerifierLedger):
    """Derives history-aware statistics and ContextItems from a VerifierLedger's recorded attempts."""

    def __init__(self, params: VerifierLedgerParams) -> None:
        # Adds the tamper-check baseline cache on top of the base ledger's attempt history.
        super().__init__(params)
        self._baseline: dict[str, str] = {}

    def score_trend(self, verifier_name: str) -> list[float]:
        """Returns every graded score verifier_name has reported across this run's attempts, in order."""
        return [
            verdict.score
            for attempt in self._attempts
            for verdict in attempt.aggregated.verdicts
            if verdict.verifier_name == verifier_name and verdict.score is not None
        ]

    def regressions_since(self, attempt_number: int) -> list[str]:
        """Returns verifier names that passed at attempt_number but are failing in the latest attempt."""
        baseline_attempt = self._attempt_by_number(attempt_number)
        latest = self.last()
        if baseline_attempt is None or latest is None:
            return []
        baseline_status = {v.verifier_name: v.passed for v in baseline_attempt.aggregated.verdicts}
        latest_status = {v.verifier_name: v.passed for v in latest.aggregated.verdicts}
        return [name for name, was_passing in baseline_status.items() if was_passing and not latest_status.get(name, True)]

    def flaky_verifiers(self, min_flips: int = 2) -> list[str]:
        """Returns verifier names whose pass/fail result flipped at least min_flips times across attempts."""
        per_verifier: dict[str, list[bool]] = {}
        for attempt in self._attempts:
            for verdict in attempt.aggregated.verdicts:
                per_verifier.setdefault(verdict.verifier_name, []).append(verdict.passed)
        return [name for name, sequence in per_verifier.items() if self._flip_count(sequence) >= min_flips]

    def baseline_snapshot(self, target: VerifierTarget) -> Mapping[str, str]:
        """Hashes every file in target.file_paths once and caches the result as this run's tamper baseline."""
        if self._baseline:
            return self._baseline
        self._baseline = {path: digest for path in target.file_paths if (digest := self._hash_file(path)) is not None}
        return self._baseline

    def tamper_check(self, target: VerifierTarget, baseline: Mapping[str, str]) -> list[str]:
        """Returns baseline paths whose current content hash no longer matches the recorded baseline."""
        del target
        return [path for path, digest in baseline.items() if self._hash_file(path) != digest]

    def to_context_items(self, *, budget: "VerifierRuntimeBudget", last_repair: RepairOutcome | None) -> tuple["ContextItem", ...]:
        """Builds the eight ledger-facing ContextItems from current state, skipping any with no data yet."""
        items: list[Any] = []
        self._append_history_item(items)
        self._append_regression_item(items)
        self._append_diagnostic_item(items)
        items.append(VerifierBudgetContextItem(remaining_attempts=budget.remaining_attempts(self), max_attempts=budget.params.max_attempts))
        self._append_trend_item(items)
        self._append_scope_item(items, last_repair)
        self._append_tamper_item(items)
        self._append_flake_item(items)
        return tuple(items)

    def _append_history_item(self, items: list[Any]) -> None:
        # Omitted entirely on the first attempt, before any history exists.
        if not self._attempts:
            return
        entries = tuple(f"Attempt {attempt.attempt_number}: {'PASSED' if attempt.aggregated.passed else 'FAILED'}" for attempt in self._attempts)
        items.append(VerifierHistoryContextItem(entries=entries))

    def _append_regression_item(self, items: list[Any]) -> None:
        # Compares the first recorded attempt against the latest — the run's own opening baseline.
        if len(self._attempts) < 2:
            return
        regressed = self.regressions_since(self._attempts[0].attempt_number)
        if regressed:
            items.append(VerifierRegressionContextItem(regressed_names=tuple(regressed)))

    def _append_diagnostic_item(self, items: list[Any]) -> None:
        # Only the latest attempt's failures are surfaced — earlier failures are already in the history item.
        last = self.last()
        if last is None or last.aggregated.passed:
            return
        diagnostics = tuple(f"{v.verifier_name}: {v.diagnostics}" for v in last.aggregated.verdicts if not v.passed)
        items.append(VerifierDiagnosticContextItem(diagnostics=diagnostics))

    def _append_trend_item(self, items: list[Any]) -> None:
        # One rendered line per verifier that has reported at least one numeric score.
        names = sorted({v.verifier_name for attempt in self._attempts for v in attempt.aggregated.verdicts if v.score is not None})
        if not names:
            return
        lines = tuple(f"{name}: {self.score_trend(name)}" for name in names)
        items.append(VerifierTrendContextItem(trend_lines=lines))

    def _append_scope_item(self, items: list[Any], last_repair: RepairOutcome | None) -> None:
        # Only present once a repair strategy has actually derived a scope constraint.
        if last_repair is not None and last_repair.scope_lock:
            items.append(VerifierScopeContextItem(scope=last_repair.scope_lock))

    def _append_tamper_item(self, items: list[Any]) -> None:
        # Only present once baseline_snapshot() has actually been called and found file-backed targets.
        if self._baseline:
            items.append(VerifierTamperContextItem(protected_paths=tuple(self._baseline.keys())))

    def _append_flake_item(self, items: list[Any]) -> None:
        # Only present once at least one verifier has actually flip-flopped.
        flaky = tuple(self.flaky_verifiers())
        if flaky:
            items.append(VerifierFlakeContextItem(flaky_names=flaky))

    def _attempt_by_number(self, attempt_number: int) -> VerificationAttempt | None:
        # Linear scan is fine here — a verification run's attempt count is bounded by its own budget.
        for attempt in self._attempts:
            if attempt.attempt_number == attempt_number:
                return attempt
        return None

    @staticmethod
    def _flip_count(sequence: list[bool]) -> int:
        # Counts adjacent pass/fail transitions in one verifier's result sequence across attempts.
        return sum(1 for i in range(1, len(sequence)) if sequence[i] != sequence[i - 1])

    @staticmethod
    def _hash_file(path: str) -> str | None:
        # Returns None for a path that cannot be read, so tamper checking degrades instead of crashing.
        try:
            with open(path, "rb") as handle:
                return hashlib.sha256(handle.read()).hexdigest()
        except OSError:
            return None


__all__ = ["VerifierLedger", "VerifierLedgerParams", "VerifierLedgerStatistics"]
