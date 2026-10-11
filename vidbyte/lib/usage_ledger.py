"""FILE: vidbyte/lib/usage_ledger.py

PURPOSE: Names the usage ledger the current agent run records into, so model calls made below the agent layer reach the run's one ledger.
ROLE IN CODEBASE: JevRuntime opens a scope over its agent's UsageTracker for the whole run; BaseAgent.generate_reply nests a helper agent's own tracker inside it; DecisionModelRunner.arun records every Jev call into whichever ledger is active.
ARCHITECTURE NOTE: The ledger is a structural Protocol satisfied by vidbyte.agents.pricing.UsageTracker, so this shared substrate never imports the agents layer; a ContextVar keeps concurrent runs, and the tasks they spawn, isolated from each other.
COMMON MODIFICATION PATTERNS: A new lib-level model call site records through active_usage_ledger() with its UsageKind; a new recording method is added to the Protocol and UsageTracker together.
KNOWN EDGE CASES: No ledger is active outside a JevAgent run, so plain agents and direct runner use record nothing new; asyncio tasks copy the ledger in effect when they were created.
RELATED DOCS: docs/design/jev-run-usage-ledger.md.
TESTS: tests/test_jev_usage_ledger.py.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol

from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.usage import UsageKind


class UsageLedger(Protocol):
    """The recording surface a run's usage ledger offers to model call sites below the agent layer."""

    def record_call(self, response: object, *, kind: UsageKind = UsageKind.GENERATIVE) -> object:
        """Record and price one model response that reports provider, model, and usage."""
        ...

    def record_billed_failure(self, provider: ModelProvider, model: str, usage: Mapping[str, Any], *, kind: UsageKind) -> object:
        """Record and price the usage a provider billed for a call that then failed."""
        ...

    def mark_recording_corrupted(self) -> None:
        """Flag that a usage record was lost to an internal error."""
        ...


_ACTIVE_LEDGER: ContextVar[UsageLedger | None] = ContextVar("vidbyte_active_usage_ledger", default=None)


def active_usage_ledger() -> UsageLedger | None:
    """Return the ledger the current run records into, or None outside a metered run."""
    return _ACTIVE_LEDGER.get()


@contextmanager
def usage_ledger_scope(ledger: UsageLedger) -> Iterator[UsageLedger]:
    """Make `ledger` the active ledger until the block exits, then restore the previous one."""
    token = _ACTIVE_LEDGER.set(ledger)
    try:
        yield ledger
    finally:
        _ACTIVE_LEDGER.reset(token)


__all__ = ["UsageLedger", "active_usage_ledger", "usage_ledger_scope"]
