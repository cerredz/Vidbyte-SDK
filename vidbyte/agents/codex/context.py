"""Turn-boundary translation of Vidbyte context into Codex input."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from vidbyte.agents.types import AgentInput
from vidbyte.context.manager import ContextManager
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.errors import AgentExecutionError


@dataclass(frozen=True, slots=True)
class CodexPrompt:
    """Translated Codex input plus metadata retained outside the prompt."""

    text: str
    user_prompt: str
    metadata: dict[str, Any]


class CodexContextTranslator:
    """Renders Vidbyte context sources into one deterministic Codex prompt."""

    @classmethod
    def translate(cls, message: str | AgentInput, *, static_context: str | None, context_manager: ContextManager | None) -> CodexPrompt:
        # Normalizes input and renders every context source without mutation.
        user_prompt, metadata, input_items, input_manager = cls._normalize_message(
            message
        )
        blocks = [static_context, cls._render_manager(context_manager)]
        blocks.extend(item.to_context_text() for item in input_items)
        blocks.append(cls._render_manager(input_manager))
        context = cls._join_unique(blocks)
        text = cls._compose_prompt(user_prompt, context)
        return CodexPrompt(text=text, user_prompt=user_prompt, metadata=metadata)

    @staticmethod
    def _normalize_message(message: str | AgentInput) -> tuple[str, dict[str, Any], tuple[Any, ...], ContextManager | None]:
        # Extracts the prompt and per-call context from either supported input type.
        if isinstance(message, AgentInput):
            prompt = message.prompt.strip()
            metadata = dict(message.metadata)
            items = tuple(message.context_items)
            manager = message.context_manager
        else:
            prompt = str(message).strip()
            metadata = {}
            items = ()
            manager = None
        if not prompt:
            raise AgentExecutionError("CodexHarnessAgent requires a non-empty prompt.")
        return prompt, metadata, items, manager

    @classmethod
    def _render_manager(cls, manager: ContextManager | None) -> str:
        # Preserves the manager's established context and conversation placement order.
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
    def _render_messages(manager: ContextManager, placement: ContextWindowPlacement) -> str:
        # Flattens provider-message context into its content while retaining order.
        return "\n\n".join(
            message["content"]
            for message in manager.render_conversation_messages(placement)
        )

    @staticmethod
    def _join_unique(blocks: Sequence[str | None]) -> str:
        # Deduplicates identical non-empty blocks without reordering them.
        seen: set[str] = set()
        rendered: list[str] = []
        for block in blocks:
            text = str(block or "").strip()
            if text and text not in seen:
                seen.add(text)
                rendered.append(text)
        return "\n\n".join(rendered)

    @staticmethod
    def _compose_prompt(user_prompt: str, context: str) -> str:
        # Keeps context visibly separate from the user's request for Codex.
        if not context:
            return user_prompt
        return f"<vidbyte_additional_context>\n{context}\n</vidbyte_additional_context>\n\n<user_request>\n{user_prompt}\n</user_request>"


__all__ = ["CodexContextTranslator", "CodexPrompt"]
