"""FILE: vidbyte/agents/jev/compaction/ledger.py

PURPOSE: Tracks, for one run, which messages of the canonical history belong to which iteration and which unit of work, and rewrites a closed unit into one record message.
ROLE IN CODEBASE: JevDynamicCompaction calls observe() once per loop pass, split_before() when a trigger finds a boundary, and replace_unit() when the compaction policy fires.
ARCHITECTURE NOTE: The loop appends each iteration's assistant tool-call message and its tool results contiguously, so every iteration is one run of messages; removing whole iterations can never separate a tool call from its result in any provider format.
COMMON MODIFICATION PATTERNS: Keep this class free of Jev and model calls; it only counts, groups, and splices. New triggers reuse split_before unchanged.
KNOWN EDGE CASES: If the list object changes (a model fallback rebuilds history) or its length stops matching the recorded segments, the ledger disables itself rather than guess which messages moved.
RELATED DOCS: docs/design/jev-dynamic-compaction.md.
TESTS: tests/test_jev_dynamic_compaction.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.constants.jev_compaction import JEV_COMPACTION_CHARS_PER_TOKEN
from vidbyte.lib.enums import JevCompactionDisabledReason

_FIRST_ITERATION = 1
_RECORD_LENGTH = 1


@dataclass(slots=True)
class JevWorkUnit:
    """One unit of work: a run of consecutive iterations, open until a boundary closes it."""

    number: int
    first_iteration: int
    last_iteration: int | None = None
    compacted: bool = False

    def is_closed(self) -> bool:
        """Return whether a boundary has closed this unit."""
        return self.last_iteration is not None


@dataclass(slots=True)
class _Segment:
    """A run of messages owned by one iteration, or the single record message that replaced a unit."""

    length: int
    iteration: int | None = None
    unit: int | None = None


class JevUnitLedger:
    """Maps the canonical message list onto iterations and units for one run."""

    def __init__(self) -> None:
        # Starts empty; the first observe() fixes the base offset that earlier history occupies.
        self._messages: list[dict[str, Any]] | None = None
        self._base = 0
        self._segments: list[_Segment] = []
        self._observed = 0
        self.units: list[JevWorkUnit] = []
        self.disabled_reason: JevCompactionDisabledReason | None = None

    def observe(self, messages: list[dict[str, Any]], completed_iterations: int) -> bool:
        """Record the messages the latest iteration added; return True when a new iteration was recorded."""
        # @intent never-guess-which-messages-moved
        # Every later splice trusts these offsets, so any change the ledger did not make disables it for the run.
        if self.disabled_reason is not None:
            return False
        if self._messages is None:
            self._messages, self._base = messages, len(messages)
            if completed_iterations != 0:
                self.disabled_reason = JevCompactionDisabledReason.HISTORY_OUT_OF_SYNC
            return False
        if messages is not self._messages:
            self.disabled_reason = JevCompactionDisabledReason.HISTORY_REPLACED
            return False
        added = len(messages) - self._expected_length()
        if completed_iterations == self._observed:
            return self._extend_latest(added)
        if completed_iterations != self._observed + 1 or added < 0:
            self.disabled_reason = JevCompactionDisabledReason.HISTORY_OUT_OF_SYNC
            return False
        self._segments.append(_Segment(length=added, iteration=completed_iterations))
        self._observed = completed_iterations
        if not self.units:
            self.units.append(JevWorkUnit(number=_FIRST_ITERATION, first_iteration=_FIRST_ITERATION))
        return True

    def open_unit(self) -> JevWorkUnit | None:
        """Return the unit still being worked on, if any."""
        if self.units and not self.units[-1].is_closed():
            return self.units[-1]
        return None

    def split_before(self, iteration: int) -> JevWorkUnit:
        """Close the open unit just before iteration and open a new unit starting at it."""
        current = self.open_unit()
        if current is None or current.first_iteration >= iteration:
            raise ValueError(f"No open unit ends before iteration {iteration}.")
        current.last_iteration = iteration - 1
        new = JevWorkUnit(number=current.number + 1, first_iteration=iteration)
        self.units.append(new)
        return new

    def eligible_units(self, keep_recent: int) -> tuple[JevWorkUnit, ...]:
        """Return closed, uncompacted units, leaving the newest keep_recent closed units raw."""
        closed = [unit for unit in self.units if unit.is_closed()]
        kept = closed[-keep_recent:] if keep_recent > 0 else []
        return tuple(unit for unit in closed if not unit.compacted and unit not in kept)

    def unit_messages(self, messages: list[dict[str, Any]], unit: JevWorkUnit) -> list[dict[str, Any]]:
        """Return the messages a unit currently occupies."""
        start, end = self._span(unit)
        return messages[start:end]

    def estimate_tokens(self, messages: list[dict[str, Any]], unit: JevWorkUnit) -> int:
        """Estimate a unit's tokens at four characters per token over its serialized messages."""
        text = json.dumps(self.unit_messages(messages, unit), default=str)
        return len(text) // JEV_COMPACTION_CHARS_PER_TOKEN

    def replace_unit(self, messages: list[dict[str, Any]], unit: JevWorkUnit, record: Mapping[str, Any]) -> int:
        """Splice a unit's messages out for one record message, in place; return how many messages left."""
        if unit.compacted or not unit.is_closed():
            raise ValueError(f"Unit {unit.number} is not a closed, uncompacted unit.")
        start, end = self._span(unit)
        messages[start:end] = [dict(record)]
        first = self._segment_index(unit.first_iteration)
        last = self._segment_index(unit.last_iteration or unit.first_iteration)
        self._segments[first : last + 1] = [_Segment(length=_RECORD_LENGTH, unit=unit.number)]
        unit.compacted = True
        return end - start

    def _extend_latest(self, added: int) -> bool:
        # A repeated pass without a new model response (for example a retry) may append to the latest iteration.
        if added < 0 or (added > 0 and not self._segments):
            self.disabled_reason = JevCompactionDisabledReason.HISTORY_OUT_OF_SYNC
        elif added > 0:
            self._segments[-1].length += added
        return False

    def _expected_length(self) -> int:
        # The list length the recorded segments account for.
        return self._base + sum(segment.length for segment in self._segments)

    def _span(self, unit: JevWorkUnit) -> tuple[int, int]:
        # Returns [start, end) of a closed unit's iteration segments in the current list.
        first = self._segment_index(unit.first_iteration)
        last = self._segment_index(unit.last_iteration or unit.first_iteration)
        start = self._base + sum(segment.length for segment in self._segments[:first])
        end = start + sum(segment.length for segment in self._segments[first : last + 1])
        return start, end

    def _segment_index(self, iteration: int) -> int:
        # Finds the segment that holds one uncompacted iteration.
        for index, segment in enumerate(self._segments):
            if segment.iteration == iteration:
                return index
        raise ValueError(f"Iteration {iteration} has no uncompacted messages.")


__all__ = ["JevUnitLedger", "JevWorkUnit"]
