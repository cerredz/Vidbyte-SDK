"""FILE: vidbyte/agents/browser/usage.py

PURPOSE: Defines BrowserAgentUsage, which makes a BrowserAgent's own UsageTracker the one usage ledger of a whole run (the orchestrator, every episode worker, and every done-criteria and recheck call), fails the run closed when any of that usage cannot be recorded or priced, and returns the run's rollup.
ROLE IN CODEBASE: BrowserAgentRuntime (vidbyte/agents/browser/runtime.py) builds one per run-local runtime, wraps the run in scope(), and hands settle()'s UsageRollup to BrowserResponse.finished, so result.metadata["usage_rollup"], agent.response.usage, and agent.get_usage() are the same rollup.
ARCHITECTURE NOTE: Recording is mechanism, not policy: AgentRuntime records the loop's calls, and BaseAgent records each nested agent's calls into the active ledger. This class only opens the ledger and decides that a gap stops the run. It reuses JevUsageAccount.failures and JevUsageAccount.unpriced rather than copying them (AGENTS.md principle 5).
FUNCTION INVENTORY: scope makes the tracker the active ledger; settle fails closed or returns the rollup.
COMMON MODIFICATION PATTERNS: A new fail-closed reason belongs in JevUsageAccount.failures, which both agents share.
WHAT NOT TO DO IN THIS FILE: 1. Do not create a second tracker; the agent's own tracker is the ledger. 2. Do not return a partial rollup when a call is unpriced.
KNOWN EDGE CASES: settle runs once, after the loop returns, so a run spends its whole budget before an unpriced call is reported. A run that made no model call settles to an empty rollup.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 6.1 INV-21 and 8.1 D-19); vidbyte/agents/jev/usage.py
TESTS: tests/features/browser_agent/test_browser_agent_observability.py
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from vidbyte.agents.jev.usage import JevUsageAccount
from vidbyte.agents.pricing import UsageRollup, UsageTracker
from vidbyte.lib.errors import UsageAccountingError
from vidbyte.lib.usage_ledger import usage_ledger_scope


class BrowserAgentUsage:
    """Owns a BrowserAgent run's one usage ledger: opens it, fails closed on any gap, and returns its rollup."""

    def __init__(self, tracker: UsageTracker, agent_name: str) -> None:
        # Keeps the agent's own tracker, which BaseAgent resets at the
        # start of every run.
        self._tracker = tracker
        self._agent_name = agent_name

    @contextmanager
    def scope(self) -> Iterator[UsageTracker]:
        """Make this agent's tracker the active ledger for every model call and nested agent in the run."""
        with usage_ledger_scope(self._tracker):
            yield self._tracker

    def settle(self) -> UsageRollup:
        """Raise UsageAccountingError when any usage of the run could not be recorded or priced; otherwise return the rollup."""
        # @intent browser-usage-fails-closed
        # The run's reported cost must be whole; a run whose cost is
        # partly unknown is withheld rather than returned with a low
        # total, and the error names each model the pricebook lacks.
        rollup = self._tracker.rollup()
        failures = JevUsageAccount.failures(rollup)
        if failures:
            raise UsageAccountingError(
                f"BrowserAgent '{self._agent_name}' stopped because Vidbyte could not calculate this run's usage. This is an error on our side, not a problem with your request.",
                details={"agent": self._agent_name, "failures": [failure.value for failure in failures], "unaccounted_call_count": rollup.unaccounted_call_count, "unpriced": JevUsageAccount.unpriced(rollup)},
            )
        return rollup


__all__ = ["BrowserAgentUsage"]
