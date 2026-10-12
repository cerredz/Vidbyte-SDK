"""FILE: vidbyte/agents/coding_context/window.py

PURPOSE: Defines CodingContextWindow, which turns the context sections a CodingAgent loaded into the ContextManager it hands to BaseAgent: the sections first, right after the system prompt and in CodingContextSection order, then the caller's own context.
ROLE IN CODEBASE: Called once by CodingAgent.__init__ (vidbyte/agents/coding.py) with the records the section loaders in this package returned; builds on vidbyte/context/manager.py (ContextManager), vidbyte/context/primitives (TextContextItem), vidbyte/lib/dataclasses/coding.py (CodingContextSectionText), and vidbyte/lib/enums/coding.py (CodingContextSection).
ARCHITECTURE NOTE: AgentRuntime renders the agent's own manager's top-of-context primitives right after the fixed system header, in registry insertion order, so inserting the sections first gives the model system prompt, then the sections in order, then the caller's primitives, then the user message. The window writes only through ContextManager's public API and never changes the caller's manager.
FUNCTION INVENTORY: CodingContextWindow.build is the narrated main function; _present_sections drops missing sections and rejects bad or repeated ones; _check_manager rejects a context_manager that is not a ContextManager; _in_render_order sorts by enum order; _new_manager starts a manager with the caller's unmanaged items and metadata; _place_sections places each section after the system prompt; _carry_over_registry copies the caller's managed primitives after the sections.
COMMON MODIFICATION PATTERNS: A new section needs nothing here: its loader returns a CodingContextSectionText with its CodingContextSection member, and CodingAgent adds that loader to its sections tuple.
WHAT NOT TO DO IN THIS FILE: 1. Do not mutate the caller's context manager; build a new one. 2. Do not list loaders or section titles here; order comes from the enum and text from the records. 3. Do not touch ContextManager's private registry; scripts/check_context_write_paths.py fails CI on it.
KNOWN EDGE CASES: With no sections, the caller's manager object (or None) is returned unchanged, so an agent with nothing to load sends today's exact request. A caller primitive whose id equals a placed section's id is not carried over; the section wins. Tools that write to the caller's manager object keep writing there, and that object is not the one the agent renders once a section is loaded.
RELATED DOCS: docs/design/coding-agent-agents-md.md; vidbyte/agents/coding_context/README.md; vidbyte/context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.dataclasses.coding import CodingContextSectionText
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError


class CodingContextWindow:
    """Builds a CodingAgent's context manager: the loaded sections first, in section order, then the caller's own context."""

    @classmethod
    def build(cls, sections: Sequence[CodingContextSectionText | None], context_manager: ContextManager | None) -> ContextManager | None:
        """Return the manager to hand to BaseAgent, or the caller's own manager (or None) when no section was loaded."""
        # Keep the sections a loader actually produced. A loader returns
        # None when it has nothing to add; anything else that is not a
        # section record, or a section given twice, is a wiring mistake
        # that should fail now rather than render oddly later.
        present = cls._present_sections(sections)
        cls._check_manager(context_manager)

        # With nothing to add, hand the caller's own manager (or None)
        # to BaseAgent untouched, so the request is exactly what a plain
        # BaseAgent would send.
        if not present:
            return context_manager

        # Put the sections in their fixed order, whatever order the
        # loaders were listed in.
        ordered = cls._in_render_order(present)

        # Start a new manager instead of editing the caller's, so one
        # manager shared by several agents never gains this agent's
        # sections. It keeps the caller's plain items and metadata.
        window = cls._new_manager(context_manager)

        # Place each section right after the system prompt, in order.
        cls._place_sections(window, ordered)

        # Add the caller's own managed primitives after the sections,
        # each at the placement the caller chose.
        cls._carry_over_registry(window, context_manager, ordered)
        return window

    @staticmethod
    def _present_sections(sections: Sequence[CodingContextSectionText | None]) -> tuple[CodingContextSectionText, ...]:
        """Return the non-None sections, raising when one is not a section record or a section kind repeats."""
        present = tuple(section for section in sections if section is not None)
        wrong = [type(section).__name__ for section in present if not isinstance(section, CodingContextSectionText)]
        if wrong:
            raise ConfigurationError("CodingAgent context sections must be CodingContextSectionText records or None.", details={"types": wrong})
        kinds = [section.section.value for section in present]
        if len(set(kinds)) != len(kinds):
            raise ConfigurationError(f"CodingAgent context sections must not repeat a section, but got {', '.join(kinds)}.", details={"sections": kinds})
        return present

    @staticmethod
    def _check_manager(context_manager: ContextManager | None) -> None:
        """Raise unless context_manager is None or a ContextManager."""
        if context_manager is not None and not isinstance(context_manager, ContextManager):
            raise ConfigurationError("CodingAgent context_manager must be a ContextManager or None.", details={"parameter": "context_manager", "context_manager_type": type(context_manager).__name__})

    @staticmethod
    def _in_render_order(sections: tuple[CodingContextSectionText, ...]) -> tuple[CodingContextSectionText, ...]:
        """Return the sections sorted by CodingContextSection declaration order."""
        by_kind = {section.section: section for section in sections}
        return tuple(by_kind[kind] for kind in CodingContextSection if kind in by_kind)

    @staticmethod
    def _new_manager(context_manager: ContextManager | None) -> ContextManager:
        """Return an empty manager, or one holding copies of the caller's unmanaged items and metadata."""
        if context_manager is None:
            return ContextManager()
        return ContextManager(context_items=context_manager.items(), metadata=context_manager.metadata)

    @staticmethod
    def _place_sections(window: ContextManager, sections: tuple[CodingContextSectionText, ...]) -> None:
        """Place each section after the system prompt, under its section's primitive id."""
        for section in sections:
            item = TextContextItem(title=section.title, content=section.content, source=section.source, primitive_id=section.section.value)
            window.place_after_system_prompt(item)

    @staticmethod
    def _carry_over_registry(window: ContextManager, context_manager: ContextManager | None, sections: tuple[CodingContextSectionText, ...]) -> None:
        """Copy the caller's managed primitives into window after the sections, keeping each one's placement."""
        if context_manager is None:
            return
        placed = {section.section.value for section in sections}
        for primitive_id, item in context_manager.registry_items():
            # @intent coding-sections-win-their-own-ids
            # A caller manager taken from another CodingAgent already
            # holds that agent's sections under the same ids. This
            # agent's own section is the one that matches its root.
            if primitive_id in placed:
                continue
            placement = context_manager.placement_for(primitive_id) or ContextWindowPlacement.END_OF_CONTEXT
            window.upsert(item, placement=placement)


__all__ = ["CodingContextWindow"]
