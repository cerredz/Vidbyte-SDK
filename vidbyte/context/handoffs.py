"""Context Protocol Header

Description:
    Defines the Handoff context primitive and its prebuilt off-the-shelf variants.
Purpose:
    Gives developers a single object that is simultaneously a context primitive
    (droppable into another agent's context_items), the spec describing a handoff
    document's structure, and the produced, filled handoff document.
Architecture:
    - Handoff: Base sectioned-document primitive implementing the ContextItem protocol.
    - EngineeringHandoff / ResearchHandoff / MinimalHandoff: Prebuilt subclasses that
      preset a curated section mapping of titles to guidance descriptions.
Relations:
    Implements the ContextItem protocol from vidbyte.context.primitives, is consumed by
    vidbyte.agents.handoff.HandoffAgent, and is accepted by BaseAgent(handoff=...) and
    ContextManager. Re-exported through vidbyte.context and the root vidbyte namespace.
Similar Files:
    - vidbyte/context/primitives.py: The other standard context item primitives.
    - vidbyte/agents/handoff.py: The agent that fills a Handoff spec from a run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class Handoff:
    """Sectioned handoff document that doubles as a ContextItem primitive and a HandoffAgent spec."""

    DEFAULT_TITLE: str = "Handoff"
    DEFAULT_INSTRUCTIONS: str = ""

    def __init__(self, *, sections: Mapping[str, str] | None = None, title: str | None = None, instructions: str | None = None, metadata: Mapping[str, Any] | None = None, primitive_id: str | None = None, primitive_frozen: bool = False) -> None:
        # Resolve section map, title, and instructions from arguments or subclass defaults.
        self.sections: dict[str, str] = dict(sections) if sections is not None else self.default_sections()
        self.title: str = title if title is not None else self.DEFAULT_TITLE
        self.instructions: str = instructions if instructions is not None else self.DEFAULT_INSTRUCTIONS
        self.kind: str = "handoff"
        self.metadata: dict[str, Any] = dict(metadata or {})
        self.primitive_id: str | None = primitive_id
        self.primitive_frozen: bool = primitive_frozen

    def default_sections(self) -> dict[str, str]:
        # Return the prebuilt section mapping for this variant; base Handoff has none.
        return {}

    def to_context_text(self) -> str:
        # Render the handoff as a titled, instruction-led, sectioned markdown block for context injection.
        head = self.title if not self.instructions else f"{self.title}\n{self.instructions}"
        if not self.sections:
            return head
        body = "\n\n".join(f"## {title}\n{self._coerce(value)}" for title, value in self.sections.items())
        return f"{head}\n\n{body}"

    def render_section_brief(self) -> str:
        # Render "- Title: description" lines used to instruct the generating model.
        return "\n".join(f"- {title}: {self._coerce(value)}" for title, value in self.sections.items())

    def fill(self, sections: Mapping[str, str]) -> "Handoff":
        # Return a produced copy of the same concrete subclass with content sections and filled metadata.
        return type(self)(
            sections=dict(sections),
            title=self.title,
            instructions=self.instructions,
            metadata={**self.metadata, "filled": True},
            primitive_id=self.primitive_id,
            primitive_frozen=self.primitive_frozen,
        )

    @property
    def is_filled(self) -> bool:
        # Report whether this handoff carries produced content rather than template descriptions.
        return bool(self.metadata.get("filled", False))

    def section_titles(self) -> tuple[str, ...]:
        # Return the ordered section titles for this handoff.
        return tuple(self.sections.keys())

    @staticmethod
    def _coerce(value: Any) -> str:
        # Coerce any section value to a string so rendering never raises on non-string content.
        return value if isinstance(value, str) else str(value)


class EngineeringHandoff(Handoff):
    """Prebuilt handoff for continuing software-engineering work."""

    DEFAULT_TITLE = "Engineering Handoff"

    def default_sections(self) -> dict[str, str]:
        # Sections tuned for a coding agent's work so the next engineer can continue cold.
        return {
            "Objective": "The original goal and what success looks like.",
            "Changes Made": "Files touched and what changed in each, with the reasoning behind the approach.",
            "Verification Status": "What was actually tested or proven versus what is still assumed to work.",
            "Open Threads": "Unfinished work and decisions still in flight.",
            "Risks & Gotchas": "Landmines, fragile areas, and non-obvious constraints for whoever continues.",
            "Next Steps": "Ordered, concrete actions to take next.",
        }


class ResearchHandoff(Handoff):
    """Prebuilt handoff for continuing a research or investigation task."""

    DEFAULT_TITLE = "Research Handoff"

    def default_sections(self) -> dict[str, str]:
        # Sections tuned for an investigative agent so findings and gaps transfer cleanly.
        return {
            "Question": "The question or objective the research set out to answer.",
            "Findings": "The substantive conclusions reached so far, with supporting detail.",
            "Sources": "Where each key finding came from, so it can be re-verified.",
            "Confidence & Gaps": "How sure each finding is and what is still unknown or unverified.",
            "Recommended Next Queries": "The most valuable next questions or searches to pursue.",
        }


class MinimalHandoff(Handoff):
    """Prebuilt minimal handoff; the default spec when none is provided."""

    DEFAULT_TITLE = "Handoff"

    def default_sections(self) -> dict[str, str]:
        # The smallest useful handoff: what happened and what to do next.
        return {
            "Summary": "What was accomplished, in a few sentences.",
            "Next Steps": "Concrete actions for whoever continues the work.",
        }


__all__ = [
    "Handoff",
    "EngineeringHandoff",
    "ResearchHandoff",
    "MinimalHandoff",
]
