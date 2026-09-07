"""FILE: vidbyte/agents/claude/context.py

PURPOSE: Renders complete Vidbyte context primitives into one Claude text prompt.
ROLE IN CODEBASE: agent.py calls this translator; ContextManager owns rendering and zones.
ARCHITECTURE NOTE: Claude accepts one prompt string, so context concatenates rather than anchors.
COMMON MODIFICATION PATTERNS: Add a zone by rendering it here; never reorder caller input.
KNOWN EDGE CASES: Equal text is not duplicate identity; one manager at both scopes renders once.
RELATED DOCS: docs/design/claude-harness-agent.md; https://code.claude.com/docs/en/agent-sdk/python.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.context.manager import ContextManager
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.dataclasses.claude import (
    ClaudeContextSource,
    ClaudeContextTranslationRequest,
    ClaudePrompt,
    ClaudeRenderedContext,
)


class ClaudeContextTranslator:
    """Preserves primitive rendering within the provider's single-prompt control surface."""

    @classmethod
    def translate(cls, translation: ClaudeContextTranslationRequest) -> ClaudePrompt:
        # @intent preserve-live-context-and-recitation
        # Render the live managers each turn so edits and removals are reflected, and
        # do not deduplicate equal text: recitations and distinct records are intentional.
        request = translation.input
        rendered = tuple(
            cls._render_manager(source) for source in cls._sources(translation)
        )
        blocks = cls._blocks((translation.static_context,))
        blocks += tuple(block for source in rendered for block in source.before_input)
        blocks += cls._blocks(
            tuple(item.to_context_text() for item in request.context_items)
        )
        blocks += cls._blocks((request.prompt,))
        blocks += tuple(block for source in rendered for block in source.after_input)
        return ClaudePrompt(
            user_prompt="\n\n".join(blocks),
            recipient=request.recipient,
            metadata=dict(request.metadata),
            developer_context="\n\n".join(
                source.developer_context
                for source in rendered
                if source.developer_context
            ),
        )

    @staticmethod
    def _sources(
        translation: ClaudeContextTranslationRequest,
    ) -> tuple[ClaudeContextSource, ...]:
        # @intent source-identity-not-text-comparison
        # A manager supplied at both construction and run scope is one source; two
        # distinct objects are two sources, even when their rendered text matches.
        request = translation.input
        if translation.context_manager is request.context_manager:
            return (ClaudeContextSource(request.context_manager),)
        return (
            ClaudeContextSource(translation.context_manager),
            ClaudeContextSource(request.context_manager),
        )

    @classmethod
    def _render_manager(cls, source: ClaudeContextSource) -> ClaudeRenderedContext:
        # Reads every zone the manager owns without mutating the caller's registry.
        manager = source.manager
        if manager is None:
            return ClaudeRenderedContext()
        return ClaudeRenderedContext(
            developer_context=manager.render_primitives_zone(),
            before_input=cls._conversation_blocks(
                manager, ContextWindowPlacement.TOP_OF_CONVERSATION
            )
            + cls._blocks(tuple(item.to_context_text() for item in manager.items())),
            after_input=cls._conversation_blocks(
                manager, ContextWindowPlacement.END_OF_CONVERSATION
            ),
        )

    @classmethod
    def _conversation_blocks(
        cls, manager: ContextManager, placement: ContextWindowPlacement
    ) -> tuple[str, ...]:
        # Renders one conversation zone as current-turn text, not as native history.
        messages = manager.render_conversation_messages(placement)
        return cls._blocks(tuple(message["content"] for message in messages))

    @staticmethod
    def _blocks(values: Sequence[str]) -> tuple[str, ...]:
        # Preserves each block's exact text while dropping empty and whitespace-only ones.
        return tuple(value for value in values if value.strip())


__all__ = ["ClaudeContextTranslator"]
