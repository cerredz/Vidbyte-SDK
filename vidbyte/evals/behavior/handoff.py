"""Context Protocol Header

Description:
    Implements HandoffBehavior — predicates over handoff occurrence (E).
Purpose:
    Exposes boolean methods checking whether a handoff was produced, whether it
    is filled, and whether specific sections exist or contain expected content.
Architecture:
    - HandoffBehavior: reads probe.handoff (the last handoff) and probe.handoffs
      (all handoffs in the run).
    - Delegates to Handoff.is_filled and Handoff.sections for content checks.
Relations:
    Instantiated by Behavior facade and accessed via agent.behavior.handoff.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.evals.behavior.behavior import Behavior


class HandoffBehavior:
    """Predicates over handoff occurrence for a completed agent run."""

    def __init__(self, behavior: Behavior) -> None:
        # Stores a reference to the parent Behavior facade for lazy probe access.
        self._behavior = behavior

    @property
    def _handoff(self) -> Any:
        # Returns the last handoff from the probe (may be None).
        return self._behavior.probe.handoff

    def handoff_occurred(self) -> bool:
        # Returns True if a handoff was produced during the run.
        return self._handoff is not None

    def handoff_is_filled(self) -> bool:
        # Returns True if the last handoff exists and is marked as filled.
        h = self._handoff
        return h is not None and h.is_filled

    def handoff_count(self) -> int:
        # Returns the number of handoffs recorded in the run.
        return len(self._behavior.probe.handoffs)

    def handoff_has_section(self, section_title: str) -> bool:
        # Returns True if the last handoff has a section with the given title.
        h = self._handoff
        return h is not None and section_title in h.sections

    def handoff_section_contains(self, section_title: str, substring: str) -> bool:
        # Returns True if the named section in the last handoff contains the substring.
        h = self._handoff
        if h is None or section_title not in h.sections:
            return False
        return substring in h.sections[section_title]


__all__ = ["HandoffBehavior"]
