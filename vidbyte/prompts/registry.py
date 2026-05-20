from __future__ import annotations

from typing import Protocol


class PromptLike(Protocol):
    name: str

    def export(self) -> str:
        """Return prompt text."""


class PromptRegistry:
    """In-process registry for reusable SDK prompt templates."""

    def __init__(self) -> None:
        self._prompts: dict[str, PromptLike] = {}

    def register(self, prompt: PromptLike) -> PromptLike:
        self._prompts[prompt.name] = prompt
        return prompt

    def get(self, name: str) -> PromptLike:
        return self._prompts[name]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._prompts))


prompt_registry = PromptRegistry()
