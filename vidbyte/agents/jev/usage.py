"""FILE: vidbyte/agents/jev/usage.py

PURPOSE: Implements JevUsageAccount, which makes a JevAgent's own UsageTracker the one usage ledger for a whole run, fails the run closed when any of its usage cannot be recorded or priced, and reports the run's totals.
ROLE IN CODEBASE: JevRuntime builds one per run-local runtime, wraps the run in scope(), calls require_accounted() at every phase boundary, and hands settle()'s JevUsageReport to JevResponse, which stores it on JevAgent.response.usage.
ARCHITECTURE NOTE: Recording is mechanism, not policy: DecisionModelRunner (decision calls), AgentRuntime (the main loop), and BaseAgent.generate_reply (nested helper, fresh, and specialist agents) record into the active ledger, and every price comes from the SDK pricebook through UsageTracker. Only this class decides that a gap in the ledger stops the run.
COMMON MODIFICATION PATTERNS: A new fail-closed reason adds a UsageAccountingFailure member and one check in failures(); a new model kind adds a UsageKind member and one rollup in report().
KNOWN EDGE CASES: Checks run at phase boundaries, so one main-loop pass can spend before the error; a call with no recorded usage, an unpriced call or operation, and a corrupted ledger each fail the run, while a run that made no calls passes.
RELATED DOCS: docs/design/jev-run-usage-ledger.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_usage_ledger.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from vidbyte.agents.pricing import UsageRollup, UsageTracker
from vidbyte.agents.pricing.records import UsageRecordingIntegrity
from vidbyte.lib.dataclasses.jev import JevUsageReport
from vidbyte.lib.enums.usage import UsageAccountingFailure, UsageKind
from vidbyte.lib.errors import UsageAccountingError
from vidbyte.lib.usage_ledger import usage_ledger_scope


class JevUsageAccount:
    """Owns a JevAgent run's one usage ledger: opens it, enforces its fail-closed policy, and reports its totals."""

    def __init__(self, tracker: UsageTracker, agent_name: str) -> None:
        # Keeps the agent's own tracker, which BaseAgent resets at the start of every run.
        self._tracker = tracker
        self._agent_name = agent_name

    @contextmanager
    def scope(self) -> Iterator[UsageTracker]:
        """Make this agent's tracker the active ledger for every model call and nested agent in the run."""
        with usage_ledger_scope(self._tracker):
            yield self._tracker

    def require_accounted(self) -> None:
        """Raise UsageAccountingError when any usage recorded so far could not be recorded or priced."""
        # @intent jev-usage-fails-closed
        # JevAgent reports what a run cost; an answer whose cost is partly unknown is withheld rather than returned
        # with a silently low total, and the error says the failure is ours so the user does not retry their request.
        rollup = self._tracker.rollup()
        failures = self.failures(rollup)
        if not failures:
            return
        raise UsageAccountingError(
            f"JevAgent '{self._agent_name}' stopped because Vidbyte could not calculate this run's usage. "
            + "This is an error on our side, not a problem with your request.",
            details={
                "agent": self._agent_name,
                "failures": [failure.value for failure in failures],
                "unaccounted_call_count": rollup.unaccounted_call_count,
                "unpriced": self.unpriced(rollup),
                "recording_integrity": rollup.recording_integrity.value,
            },
        )

    def report(self) -> JevUsageReport:
        """Return the run's total, generative, and decision rollups from the one ledger."""
        return JevUsageReport(
            total=self._tracker.rollup(),
            generative=self._tracker.rollup(UsageKind.GENERATIVE),
            decision=self._tracker.rollup(UsageKind.DECISION),
        )

    def settle(self) -> JevUsageReport:
        """Fail closed on any accounting gap, then return the run's report."""
        self.require_accounted()
        return self.report()

    @classmethod
    def failures(cls, rollup: UsageRollup) -> tuple[UsageAccountingFailure, ...]:
        """Return every reason this rollup cannot be trusted as the run's full, priced usage."""
        checks = (
            (UsageAccountingFailure.RECORDING_ERROR, rollup.recording_integrity is UsageRecordingIntegrity.CORRUPTED),
            (UsageAccountingFailure.UNREPORTED_USAGE, rollup.unaccounted_call_count > 0),
            (UsageAccountingFailure.UNPRICED_CALL, bool(cls.unpriced(rollup))),
        )
        return tuple(failure for failure, failed in checks if failed)

    @staticmethod
    def unpriced(rollup: UsageRollup) -> list[str]:
        """Name each model and operation the pricebook could not price, once each, in sorted order."""
        # @intent unpriced-means-missing-from-the-pricebook
        # A None cost is the one signal that the SDK pricebook has no rate for that call; naming the provider and
        # model (never raw usage) tells the user exactly which pricebook entry is missing.
        calls = {f"{record.provider}:{record.model}" for record in rollup.calls if record.cost_usd is None}
        operations = {f"{record.provider}:{record.operation}:{record.mode}" for record in rollup.operations if record.cost_usd is None}
        return sorted(calls | operations)


__all__ = ["JevUsageAccount"]
