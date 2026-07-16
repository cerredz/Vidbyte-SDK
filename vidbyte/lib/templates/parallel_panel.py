"""Context Protocol Header

FILE: vidbyte/lib/templates/parallel_panel.py
PURPOSE: Defines the canonical successful-run slot sequence for Parallel Panel.
Runtime review orchestration does not belong in this structural validator.
ROLE IN CODEBASE: Test harnesses and manual verification instantiate this class
to validate recorder output emitted by ParallelPanelRuntimeAlgorithm.
ARCHITECTURE NOTE: Repeated review slots represent deterministic scheduling,
not finding publication. See docs/design/context-window-parallel-panel.md.
FUNCTION INVENTORY: ParallelPanelContextWindowTemplate(reviewer_count) builds
and validates the expected successful-run slot sequence. Existing template
regressions cover the base validator; the approved design adds no test file.
COMMON MODIFICATION PATTERNS: Change slots only when the approved runtime
protocol changes, then update the skill guide and runtime emit points together.
WHAT NOT TO DO: 1. Do not include review bodies in slots. 2. Do not order slots
by completion time. 3. Do not add collection after a failed publication policy.
KNOWN EDGE CASES: Counts below two or above the public safety cap are invalid;
failed runs can end before collection and therefore do not pass this template.
COMMON ERRORS: ValueError reports invalid reviewer_count before construction.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/context-window-parallel-panel.md
TESTS: Existing context-window template regression suite and uncommitted manual
two- and three-reviewer recorder checks required by the design.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate


class ParallelPanelContextWindowTemplate(ContextWindowTemplate):
    """Successful Parallel Panel structure parameterized by reviewer count."""

    def __init__(self, reviewer_count: int = 3) -> None:
        # Validates reviewer_count and stores the deterministic scheduling/barrier slot sequence.
        if isinstance(reviewer_count, bool) or not isinstance(reviewer_count, int) or reviewer_count < 2 or reviewer_count > 16:
            raise ValueError("reviewer_count must be an integer between 2 and 16, inclusive.")
        super().__init__(self._build_slots(reviewer_count))

    @staticmethod
    def _build_slots(reviewer_count: int) -> list[str]:
        # Builds system, producer, index-ordered review scheduling, barrier, and collection slots.
        return ["system_prompt", "parallel_panel_producer", *(["parallel_panel_review"] * reviewer_count), "parallel_panel_barrier", "parallel_panel_collection"]


__all__ = ["ParallelPanelContextWindowTemplate"]
