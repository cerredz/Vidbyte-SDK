from __future__ import annotations

import threading
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# PR15 simple registry — used by agents/base.py and prompts/prompts/__init__.py
# for string-keyed PromptLike objects (AgentRolePrompt, VMAOPrompts).
# ---------------------------------------------------------------------------

class PromptLike(Protocol):
    name: str

    def export(self) -> str:
        """Return prompt text."""


class _SimplePromptRegistry:
    """String-keyed in-process registry for PromptLike objects."""

    def __init__(self) -> None:
        self._prompts: dict[str, PromptLike] = {}

    def register(self, prompt: PromptLike) -> PromptLike:
        self._prompts[prompt.name] = prompt
        return prompt

    def get(self, name: str) -> PromptLike:
        if name not in self._prompts:
            raise KeyError(f"No prompt registered under name: {name!r}")
        return self._prompts[name]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._prompts))


prompt_registry = _SimplePromptRegistry()


# ---------------------------------------------------------------------------
# PR10 comprehensive registry — thread-safe singleton with key-version system,
# used by strategies (ReAct, Reflexion, ToT) and harnesses.
# ---------------------------------------------------------------------------

from vidbyte.prompts.base import BasePrompt, PromptNotFoundError
from vidbyte.prompts.types import PromptKey, PromptVersion, RenderedPrompt


class PromptRegistry:
    """
    Central thread-safe versioned prompt repository.
    Singleton — all calls to PromptRegistry() return the same instance.
    Supports register, override, get (rendered), get_raw, list_all, and clear.
    """

    _instance: PromptRegistry | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> PromptRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._prompts: dict[str, BasePrompt] = {}
                    instance._overrides: dict[str, BasePrompt] = {}
                    cls._instance = instance  # type: ignore[assignment]
                    from vidbyte.prompts.builtins.vidbyte_defaults import register_defaults
                    register_defaults(instance)
        return cls._instance  # type: ignore[return-value]

    def register(self, prompt: BasePrompt) -> PromptRegistry:
        key_str = str(prompt.key())
        with self._lock:
            self._prompts[key_str] = prompt
        return self

    def override(self, prompt: BasePrompt) -> PromptRegistry:
        key_str = str(prompt.key())
        with self._lock:
            self._overrides[key_str] = prompt
        return self

    def get(self, key: PromptKey, **kwargs: Any) -> RenderedPrompt:
        key_str = str(key)
        with self._lock:
            prompt = self._overrides.get(key_str) or self._prompts.get(key_str)
        if not prompt:
            available = list(self._prompts.keys())
            raise PromptNotFoundError(
                f"No prompt registered for key: {key_str!r}. Available: {available}"
            )
        return prompt.render(**kwargs)

    def get_raw(self, key: PromptKey) -> BasePrompt:
        key_str = str(key)
        with self._lock:
            prompt = self._overrides.get(key_str) or self._prompts.get(key_str)
        if not prompt:
            raise PromptNotFoundError(f"No prompt registered for key: {key_str!r}")
        return prompt

    def list_all(self) -> list[PromptVersion]:
        with self._lock:
            return [p.as_version() for p in self._prompts.values()]

    def clear(self) -> None:
        with self._lock:
            self._prompts.clear()
            self._overrides.clear()
