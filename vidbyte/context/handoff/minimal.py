"""Context Protocol Header

Description:
    Defines the minimal handoff preset.
Purpose:
    Provides the smallest useful handoff shape for generic continuation.
Architecture:
    - MinimalHandoff: Handoff subclass with compact default sections.
Relations:
    Default handoff spec for HandoffAgent when no custom spec is provided.
Similar Files:
    - vidbyte/context/handoff/base.py: Base handoff primitive.
"""

from __future__ import annotations

from vidbyte.context.handoff.base import Handoff


class MinimalHandoff(Handoff):
    """Prebuilt minimal handoff; the default spec when none is provided."""

    DEFAULT_TITLE = "Handoff"

    def default_sections(self) -> dict[str, str]:
        """Return the smallest useful continuation handoff section set."""
        return {
            "Summary": (
                "Describe what happened in the completed run in a concise but operationally useful way. "
                "Include the original task, the main work performed, and the final state the previous agent reached. "
                "Call out any facts that are verified versus inferred so the reader does not mistake a guess for evidence. "
                "Keep this section focused on context the next worker needs to continue, not a transcript recap."
            ),
            "Next Steps": (
                "List the concrete actions the next worker should take to continue or finish the task. "
                "Order the actions by dependency or urgency so the sequence can be followed without re-planning. "
                "Include commands, files, artifacts, or questions when those details are known from the run. "
                "State any blockers or missing information that must be resolved before progress can continue."
            ),
        }


__all__ = [
    "MinimalHandoff",
]
