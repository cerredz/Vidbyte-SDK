"""FILE: vidbyte/agents/codex/context.py

PURPOSE: Renders complete Vidbyte primitives into Codex instructions and turn input.
ROLE IN CODEBASE: agent.py calls this translator; ContextManager owns rendering,
    registry mutation, freezing, recitation, and placement. config.py emits SDK objects.
ARCHITECTURE NOTE: Context-zone primitives follow the facade's developer prompt;
    conversation placements surround current-turn input as text, not native history.
FUNCTION INVENTORY: translate(request) -> CodexPrompt preserves primitive renderings,
    live source changes, native input identity, and explicit image/skill anchors. One
    _render_* function per translated ContextManager surface: conversation placements,
    unmanaged items, anchored insertions, and manager metadata.
COMMON MODIFICATION PATTERNS: Add provider input anchors to the shared enum and
    resolve their boundary here without changing the shared ContextManager contract.
    Translating a further ContextManager surface adds one _render_* function.
WHAT NOT TO DO IN THIS FILE: Do not mutate caller managers, rewrite primitive bodies,
    run inner-loop algorithms, or claim insertion into Codex-owned historical messages.
KNOWN EDGE CASES: Missing anchors fail before transport; equal text is not duplicate
    identity. Reusing the same manager renders once with request-local overrides.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/pull/409#discussion_r3939579517
TESTS: Context manager suites and offline adapter regression checks; full run_ci.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

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
            metadata=cls._merge_metadata(rendered, request.metadata),
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
        # @intent one-function-per-translated-manager-surface
        # The manager owns full zone rendering; only explicitly anchored records leave it.
        # Each translated ContextManager surface has its own function below, so covering
        # a newly translated surface adds one function instead of another inline branch.
        # Placement-scoped surfaces read the remaining view; whole-manager surfaces read
        # the caller's manager, because the remaining view carries no unmanaged items or
        # metadata of its own.
        manager = source.manager
        if manager is None:
            return CodexRenderedContext()
        remaining = cls._remaining_manager(source)
        return CodexRenderedContext(
            developer_context=remaining.render_primitives_zone(),
            before_input=cls._render_conversation(
                remaining, ContextWindowPlacement.TOP_OF_CONVERSATION
            )
            + cls._render_unmanaged_items(manager),
            after_input=cls._render_conversation(
                remaining, ContextWindowPlacement.END_OF_CONVERSATION
            ),
            insertions=cls._render_insertions(manager, source.placements, items),
            metadata=cls._render_metadata(manager),
        )

    @classmethod
    def _render_conversation(
        cls, manager: ContextManager, placement: ContextWindowPlacement
    ) -> tuple[CodexTextInput, ...]:
        # Conversation-placed primitives surround turn input as text, not native history.
        messages = manager.render_conversation_messages(placement)
        return cls._text_items(tuple(message["content"] for message in messages))

    @classmethod
    def _render_unmanaged_items(
        cls, manager: ContextManager
    ) -> tuple[CodexTextInput, ...]:
        # Unmanaged items hold no placement, so they render ahead of current-turn input.
        return cls._text_items(
            tuple(item.to_context_text() for item in manager.items())
        )

    @classmethod
    def _render_insertions(
        cls,
        manager: ContextManager,
        placements: tuple[CodexContextPlacement, ...],
        items: tuple[CodexInputItem, ...],
    ) -> tuple[CodexContextInsertion, ...]:
        # Anchored primitives are the only registry records that leave the zone.
        return tuple(
            cls._render_insertion(manager, placement, items) for placement in placements
        )

    @staticmethod
    def _render_metadata(manager: ContextManager) -> Mapping[str, Any]:
        # @intent do-not-drop-manager-metadata
        # ContextManager.metadata reaches provider metadata through to_context() on the
        # generic agent path. Codex builds no BaseContext, so without this translation a
        # caller who set metadata on the manager silently loses it for the whole turn.
        return dict(manager.metadata)

    @staticmethod
    def _merge_metadata(
        rendered: tuple[CodexRenderedContext, ...], request_metadata: Mapping[str, Any]
    ) -> dict[str, Any]:
        # @intent most-specific-metadata-wins-last
        # Merge order is the contract: sources in render order, then per-turn input
        # metadata. _sources emits the agent-scoped manager before the request-scoped
        # one, so the request scope overrides the agent scope and explicit turn input
        # overrides both. Reordering these updates would let a stale agent-level key
        # silently outrank the value a caller set for this turn.
        metadata: dict[str, Any] = {}
        for source in rendered:
            metadata.update(source.metadata)
        metadata.update(request_metadata)
        return metadata

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
