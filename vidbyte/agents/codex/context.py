"""Turn-boundary translation of Vidbyte context into Codex input."""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.context.manager import ContextManager
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.dataclasses.codex import (
    CodexContextTranslationRequest,
    CodexPrompt,
    CodexTextInput,
)


class CodexContextTranslator:
    """Renders Vidbyte context sources into native Codex input records."""

    @classmethod
    def translate(
        cls,
        translation: CodexContextTranslationRequest,
    ) -> CodexPrompt:
        # @intent preserve-native-input-shapes
        # Additional Vidbyte context becomes a leading Codex TextInput while the
        # user's original text/media/skill/mention items remain separate.
        request = translation.input
        blocks = [
            translation.static_context,
            cls._render_manager(translation.context_manager),
        ]
        blocks.extend(item.to_context_text() for item in request.context_items)
        blocks.append(cls._render_manager(request.context_manager))
        context = cls._join_unique(blocks)
        items = request.items
        if context:
            items = (
                CodexTextInput(
                    f"<vidbyte_additional_context>\n{context}\n</vidbyte_additional_context>"
                ),
                *items,
            )
        user_prompt = "\n\n".join(
            item.text for item in request.items if isinstance(item, CodexTextInput)
        )
        return CodexPrompt(
            items=items,
            user_prompt=user_prompt,
            recipient=request.recipient,
            metadata=dict(request.metadata),
        )

    @classmethod
    def _render_manager(cls, manager: ContextManager | None) -> str:
        if manager is None:
            return ""
        blocks = [
            cls._render_messages(manager, ContextWindowPlacement.TOP_OF_CONVERSATION),
            manager.render_primitives_zone(),
            *(item.to_context_text() for item in manager.items()),
            cls._render_messages(manager, ContextWindowPlacement.END_OF_CONVERSATION),
        ]
        return cls._join_unique(blocks)

    @staticmethod
    def _render_messages(
        manager: ContextManager, placement: ContextWindowPlacement
    ) -> str:
        return "\n\n".join(
            message["content"]
            for message in manager.render_conversation_messages(placement)
        )

    @staticmethod
    def _join_unique(blocks: Sequence[str]) -> str:
        seen: set[str] = set()
        rendered: list[str] = []
        for block in blocks:
            text = str(block).strip()
            if text and text not in seen:
                seen.add(text)
                rendered.append(text)
        return "\n\n".join(rendered)


__all__ = ["CodexContextTranslator"]
