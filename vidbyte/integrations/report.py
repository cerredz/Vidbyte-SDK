"""FILE: vidbyte/integrations/report.py

PURPOSE: Records what every selection actually contributed so a run never silently under-delivers on the context it was asked for.
ROLE IN CODEBASE: The observable surface of a Sources resolution, and the only place a developer learns that four of five documents loaded.
ARCHITECTURE NOTE: The report is a frozen projection over per-selection entries; it computes groupings rather than storing them.
COMMON MODIFICATION PATTERNS: Add a grouping as a derived property over entries; never store a redundant counter that can drift from the entries.
KNOWN EDGE CASES: An empty report is complete and still summarizes to readable text, and a summary never renders a credential.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test_sources_access_layer.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.dataclasses.integrations import SelectionReportEntry
from vidbyte.lib.enums.integrations import LoadOutcome


@dataclass(frozen=True, slots=True)
class SourcesReport:
    """Per-selection coverage record for one Sources resolution."""

    entries: tuple[SelectionReportEntry, ...] = ()

    @property
    def loaded(self) -> tuple[SelectionReportEntry, ...]:
        """Return every selection whose content was admitted in full."""
        return self._with_outcome(LoadOutcome.LOADED)

    @property
    def truncated(self) -> tuple[SelectionReportEntry, ...]:
        """Return every selection whose content was cut to fit the token budget."""
        return self._with_outcome(LoadOutcome.TRUNCATED)

    @property
    def skipped(self) -> tuple[SelectionReportEntry, ...]:
        """Return every selection whose content did not fit the token budget at all."""
        return self._with_outcome(LoadOutcome.SKIPPED)

    @property
    def failed(self) -> tuple[SelectionReportEntry, ...]:
        """Return every selection that could not be authorized or loaded."""
        return self._with_outcome(LoadOutcome.FAILED)

    @property
    def tools_only(self) -> tuple[SelectionReportEntry, ...]:
        """Return every selection that contributed tools rather than loaded content."""
        return self._with_outcome(LoadOutcome.TOOLS_ONLY)

    @property
    def complete(self) -> bool:
        """Return True only when nothing failed, was truncated, or was skipped."""
        return not (self.failed or self.truncated or self.skipped)

    def tokens_admitted(self) -> int:
        """Return the total estimated tokens this resolution added to the context window."""
        return sum(entry.tokens_loaded for entry in self.entries)

    def summary(self) -> str:
        """Render one readable block naming each outcome group and its selections."""
        if not self.entries:
            return "no sources requested"
        groups = (
            ("loaded", self.loaded),
            ("tools", self.tools_only),
            ("truncated", self.truncated),
            ("skipped", self.skipped),
            ("failed", self.failed),
        )
        lines = [f"{label}: {', '.join(entry.describe() for entry in entries)}" for label, entries in groups if entries]
        lines.append(f"tokens admitted: {self.tokens_admitted()}")
        return "\n".join(lines)

    def _with_outcome(self, outcome: LoadOutcome) -> tuple[SelectionReportEntry, ...]:
        """Return every entry recorded with one outcome, in resolution order."""
        return tuple(entry for entry in self.entries if entry.outcome is outcome)


__all__ = [
    "SourcesReport",
]
