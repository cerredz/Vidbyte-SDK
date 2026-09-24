"""FILE: vidbyte/agents/jev/done_criteria/presets.py

PURPOSE: Provides the named public JevPreset factory surface for built-in completion criteria.
ROLE IN CODEBASE: SDK callers use JevPreset; JevAgentSettings stores the returned criterion for JevRuntime.
ARCHITECTURE NOTE: Presets are explicit typed constructors, not string registries or arbitrary callbacks.
FUNCTION INVENTORY: JevPreset.MinimumTime -> MinimumTime; tests/test_jev_done_criteria.py verifies its public contract.
COMMON MODIFICATION PATTERNS: Add a named static factory only when its criterion class and behavior are implemented.
WHAT NOT TO DO: Do not add runtime evaluation or prompt behavior here; those belong in criteria.py and base.py.
KNOWN EDGE CASES: Constructor validation is delegated to MinimumTime so direct and preset construction behave identically.
RELATED DOCS: docs/design/jev-done-criteria.md.
TESTS: tests/test_jev_done_criteria.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.done_criteria.criteria import MinimumTime


class JevPreset:
    """Namespace for named Jev built-in done-criteria factories."""

    @staticmethod
    def MinimumTime(*, seconds: float | None = None, minutes: float | None = None, hours: float | None = None, days: float | None = None) -> MinimumTime:
        # Creates the validated minimum-duration criterion using the caller's selected time unit.
        return MinimumTime(seconds=seconds, minutes=minutes, hours=hours, days=days)


__all__ = ["JevPreset"]
