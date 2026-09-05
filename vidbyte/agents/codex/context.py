"""FILE: vidbyte/agents/codex/context.py

PURPOSE: Renders complete Vidbyte primitives into Codex instructions and turn input.
ROLE IN CODEBASE: agent.py calls this translator; ContextManager owns rendering,
    registry mutation, freezing, recitation, and placement. config.py emits SDK objects.
ARCHITECTURE NOTE: Context-zone primitives follow the facade's developer prompt;
    conversation placements surround current-turn input as text, not native history.
FUNCTION INVENTORY: translate(request) -> CodexPrompt preserves primitive renderings,
    live source changes, native input identity, and explicit image/skill anchors.
COMMON MODIFICATION PATTERNS: Add provider input anchors to the shared enum and
    resolve their boundary here without changing the shared ContextManager contract.
WHAT NOT TO DO IN THIS FILE: Do not mutate caller managers, rewrite primitive bodies,
    run inner-loop algorithms, or claim insertion into Codex-owned historical messages.
KNOWN EDGE CASES: Missing anchors fail before transport; equal text is not duplicate
    identity. Reusing the same manager renders once with request-local overrides.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/pull/409#discussion_r3939579517
TESTS: Context manager suites and offline adapter regression checks; full run_ci.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.context.manager import ContextManager
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.dataclasses.codex import (
    CodexContextInsertion,
    CodexContextPlacement,
    CodexContextSource,
    CodexContextTranslationRequest,
    CodexImageInput,
    CodexInputItem,
    CodexLocalImageInput,
    CodexPrompt,
    CodexRenderedContext,
    CodexSkillInput,
    CodexTextInput,
)
from vidbyte.lib.enums.codex import CodexContextAnchor
from vidbyte.lib.errors import ConfigurationError


class CodexContextTranslator:
    """Preserves native primitive rendering with explicit provider placement limits."""

    @classmethod
    def translate(cls, translation: CodexContextTranslationRequest) -> CodexPrompt:
        # @intent preserve-context-placement-and-identity
        # Render the live managers each turn so edits/removals are reflected locally.
        # Do not deduplicate equal text: recitations and distinct records are intentional.
        request = translation.input
        rendered = tuple(
            cls._render_manager(source, request.items)
            for source in cls._sources(translation)
        )
        prefix = cls._text_items((translation.static_context,))
        prefix += tuple(item for source in rendered for item in source.before_input)
        prefix += cls._text_items(
            tuple(item.to_context_text() for item in request.context_items)
        )
        body = cls._insert_context(
            request.items,
            tuple(item for source in rendered for item in source.insertions),
        )
        suffix = tuple(item for source in rendered for item in source.after_input)
        return CodexPrompt(
            items=(*prefix, *body, *suffix),
            user_prompt="\n\n".join(
                item.text for item in request.items if isinstance(item, CodexTextInput)
            ),
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
        translation: CodexContextTranslationRequest,
    ) -> tuple[CodexContextSource, ...]:
        # @intent source-identity-not-text-deduplication
        # A manager supplied at both scopes is one source; request overrides win by id.
        request = translation.input
        CodexContextSource(translation.context_manager, translation.context_placements)
        if translation.context_manager is request.context_manager:
            placements = {
                value.primitive_id: value for value in translation.context_placements
            }
            placements.update(
                {value.primitive_id: value for value in request.context_placements}
            )
            return (
                CodexContextSource(request.context_manager, tuple(placements.values())),
            )
        return (
            CodexContextSource(
                translation.context_manager, translation.context_placements
            ),
            CodexContextSource(request.context_manager, request.context_placements),
        )

    @classmethod
    def _render_manager(
        cls, source: CodexContextSource, items: tuple[CodexInputItem, ...]
    ) -> CodexRenderedContext:
        # The manager owns full zone rendering; only explicitly anchored records leave it.
        manager = source.manager
        if manager is None:
            return CodexRenderedContext()
        insertions = tuple(
            cls._render_insertion(manager, placement, items)
            for placement in source.placements
        )
        remaining = cls._remaining_manager(source)
        top = remaining.render_conversation_messages(
            ContextWindowPlacement.TOP_OF_CONVERSATION
        )
        end = remaining.render_conversation_messages(
            ContextWindowPlacement.END_OF_CONVERSATION
        )
        return CodexRenderedContext(
            developer_context=remaining.render_primitives_zone(),
            before_input=cls._text_items(tuple(message["content"] for message in top))
            + cls._text_items(
                tuple(item.to_context_text() for item in manager.items())
            ),
            after_input=cls._text_items(tuple(message["content"] for message in end)),
            insertions=insertions,
        )

    @staticmethod
    def _remaining_manager(source: CodexContextSource) -> ContextManager:
        # Use a private registry view to avoid moving or unfreezing caller-owned records.
        remaining = ContextManager()
        if source.manager is None:
            return remaining
        if not source.placements:
            return source.manager
        moved = {placement.primitive_id for placement in source.placements}
        for primitive_id, item in source.manager.registry_items():
            if primitive_id not in moved:
                placement = (
                    source.manager.placement_for(primitive_id)
                    or ContextWindowPlacement.END_OF_CONTEXT
                )
                remaining.upsert(item, placement=placement)
        return remaining

    @classmethod
    def _render_insertion(
        cls,
        manager: ContextManager,
        placement: CodexContextPlacement,
        items: tuple[CodexInputItem, ...],
    ) -> CodexContextInsertion:
        # Reject unresolved intent instead of silently moving a primitive to a fallback zone.
        primitive = manager.get_by_id(placement.primitive_id)
        if primitive is None:
            raise ConfigurationError(
                f"Codex context placement references missing primitive {placement.primitive_id!r}."
            )
        return CodexContextInsertion(
            index=cls._anchor_index(placement.anchor, items),
            item=CodexTextInput(primitive.to_context_text()),
        )

    @staticmethod
    def _anchor_index(
        anchor: CodexContextAnchor, items: tuple[CodexInputItem, ...]
    ) -> int:
        # Before uses the first matching item; after uses the last, including local images.
        image_anchors = (
            CodexContextAnchor.BEFORE_IMAGES,
            CodexContextAnchor.AFTER_IMAGES,
        )
        kinds = (
            (CodexImageInput, CodexLocalImageInput)
            if anchor in image_anchors
            else (CodexSkillInput,)
        )
        matches = [index for index, item in enumerate(items) if isinstance(item, kinds)]
        if not matches:
            raise ConfigurationError(
                f"Codex context anchor {anchor.value!r} has no matching input item."
            )
        if anchor in (
            CodexContextAnchor.BEFORE_IMAGES,
            CodexContextAnchor.BEFORE_SKILLS,
        ):
            return matches[0]
        return matches[-1] + 1

    @staticmethod
    def _insert_context(
        items: tuple[CodexInputItem, ...], insertions: tuple[CodexContextInsertion, ...]
    ) -> tuple[CodexInputItem, ...]:
        # Original input positions remain stable when several sources share an anchor.
        boundaries: dict[int, list[CodexTextInput]] = {}
        for insertion in insertions:
            boundaries.setdefault(insertion.index, []).append(insertion.item)
        rendered: list[CodexInputItem] = []
        for index, item in enumerate(items):
            rendered.extend(boundaries.get(index, ()))
            rendered.append(item)
        rendered.extend(boundaries.get(len(items), ()))
        return tuple(rendered)

    @staticmethod
    def _text_items(blocks: Sequence[str]) -> tuple[CodexTextInput, ...]:
        # Preserve the exact primitive text, including whitespace, without extra wrappers.
        return tuple(CodexTextInput(block) for block in blocks if block.strip())


__all__ = ["CodexContextTranslator"]
