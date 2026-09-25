"""FILE: vidbyte/agents/jev/compaction/report.py

PURPOSE: Holds one run's dynamic-compaction state (ledger and counters) and the frozen report attached to the run result.
ROLE IN CODEBASE: JevRuntime starts one JevCompactionRun per run; JevDynamicCompaction records boundaries, compactions, Jev calls, and failures on it; the snapshot lands in result.metadata["jev_dynamic_compaction"].
ARCHITECTURE NOTE: The run object is mutable and run-local; JevCompactionReport is the immutable view published after every loop pass, so the result always carries the latest state even when the run ends early.
COMMON MODIFICATION PATTERNS: Add a report field together with the recorder method that fills it and a test that reads it.
KNOWN EDGE CASES: Jev usage is None until a Jev call reports usage; writer model usage is not here because it is recorded on the main agent's usage tracker.
RELATED DOCS: docs/design/jev-dynamic-compaction.md.
TESTS: tests/test_jev_dynamic_compaction.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vidbyte.agents.jev.compaction.ledger import JevUnitLedger
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.enums import (
    JevCompactionDisabledReason,
    JevCompactionRecordSource,
    JevCompactionTriggerKey,
)


@dataclass(frozen=True, slots=True)
class JevUnitBoundary:
    """A boundary a trigger found: the unit before `iteration` closed, and a new unit started at it."""

    iteration: int
    trigger: JevCompactionTriggerKey
    probability: float


@dataclass(frozen=True, slots=True)
class JevUnitCompaction:
    """One closed unit replaced by a record message."""

    unit: int
    first_iteration: int
    last_iteration: int
    messages_removed: int
    estimated_tokens_removed: int
    record_source: JevCompactionRecordSource


@dataclass(frozen=True, slots=True)
class JevCompactionReport:
    """What dynamic compaction saw and did during one run."""

    triggers: tuple[JevCompactionTriggerKey, ...]
    boundaries: tuple[JevUnitBoundary, ...] = ()
    compactions: tuple[JevUnitCompaction, ...] = ()
    jev_calls: int = 0
    jev_errors: int = 0
    jev_usage: JevUsage | None = None
    writer_failures: int = 0
    disabled_reason: JevCompactionDisabledReason | None = None


@dataclass(slots=True)
class JevCompactionRun:
    """Run-local compaction state: the ledger plus everything the report needs."""

    triggers: tuple[JevCompactionTriggerKey, ...]
    ledger: JevUnitLedger = field(default_factory=JevUnitLedger)
    boundaries: list[JevUnitBoundary] = field(default_factory=list)
    compactions: list[JevUnitCompaction] = field(default_factory=list)
    jev_calls: int = 0
    jev_errors: int = 0
    consecutive_jev_errors: int = 0
    jev_input_tokens: int | None = None
    jev_output_tokens: int | None = None
    writer_failures: int = 0
    disabled_reason: JevCompactionDisabledReason | None = None

    def disable(self, reason: JevCompactionDisabledReason) -> None:
        """Stop acting for the rest of the run, keeping the first reason."""
        if self.disabled_reason is None:
            self.disabled_reason = reason

    def active(self) -> bool:
        """Return whether compaction may still act in this run."""
        if self.ledger.disabled_reason is not None:
            self.disable(self.ledger.disabled_reason)
        return self.disabled_reason is None

    def record_jev_call(self, usage: JevUsage | None) -> None:
        """Count one successful Jev request and add its token usage."""
        self.jev_calls += 1
        self.consecutive_jev_errors = 0
        if usage is None:
            return
        if usage.input_tokens is not None:
            self.jev_input_tokens = (self.jev_input_tokens or 0) + usage.input_tokens
        if usage.output_tokens is not None:
            self.jev_output_tokens = (self.jev_output_tokens or 0) + usage.output_tokens

    def record_jev_error(self) -> None:
        """Count one failed Jev request."""
        self.jev_errors += 1
        self.consecutive_jev_errors += 1

    def report(self) -> JevCompactionReport:
        """Return the immutable view of this run so far."""
        usage = None
        if self.jev_input_tokens is not None or self.jev_output_tokens is not None:
            usage = JevUsage.from_usage_payload({"input_tokens": self.jev_input_tokens, "output_tokens": self.jev_output_tokens})
        return JevCompactionReport(
            triggers=self.triggers,
            boundaries=tuple(self.boundaries),
            compactions=tuple(self.compactions),
            jev_calls=self.jev_calls,
            jev_errors=self.jev_errors,
            jev_usage=usage,
            writer_failures=self.writer_failures,
            disabled_reason=self.disabled_reason if self.disabled_reason is not None else self.ledger.disabled_reason,
        )


__all__ = [
    "JevCompactionReport",
    "JevCompactionRun",
    "JevUnitBoundary",
    "JevUnitCompaction",
]
