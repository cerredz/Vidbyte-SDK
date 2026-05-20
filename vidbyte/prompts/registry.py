# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the thread-safe singleton PromptRegistry class for the Vidbyte SDK.
# Purpose: Offers a central, versioned, and developer-overrideable prompt store.
# Architecture & Functions:
#   - PromptRegistry (Singleton): Unified entry point to register, override, and retrieve prompts.
#   - PromptRegistry.register(prompt): Adds a default prompt class instance.
#   - PromptRegistry.override(prompt): Transparently replaces a default prompt with a custom one.
#   - PromptRegistry.get(key, **kwargs): Resolves the prompt, checking overrides first, then renders it.
# Codebase Relation:
#   - Relied upon by all harnesses and strategies to obtain agent instructions.
# Similar Files:
#   - vidbyte/tools/registry.py (manages tools, though it's standard-instanced rather than singleton)
# ==============================================================================

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from vidbyte.prompts.base import BasePrompt, PromptNotFoundError
from vidbyte.prompts.types import PromptKey, PromptVersion, RenderedPrompt


class PromptRegistry:
    """
    Central, thread-safe versioned prompt repository.
    Enables runtime overrides and unified access to strategy/harness system prompts.
    Implemented as a thread-safe singleton.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> PromptRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._prompts = {}
                    instance._overrides = {}
                    cls._instance = instance
                    
                    # Auto-register SDK default translations
                    from vidbyte.prompts.builtins.vidbyte_defaults import register_defaults
                    register_defaults(instance)
        return cls._instance

    def register(self, prompt: BasePrompt) -> PromptRegistry:
        """Registers a default prompt class instance. Returns self for chaining."""
        key_str = str(prompt.key())
        with self._lock:
            self._prompts[key_str] = prompt
        return self

    def override(self, prompt: BasePrompt) -> PromptRegistry:
        """
        Overrides an SDK prompt with a custom user implementation.
        Takes precedence over any registered default prompts.
        Returns self for chaining.
        """
        key_str = str(prompt.key())
        with self._lock:
            self._overrides[key_str] = prompt
        return self

    def get(self, key: PromptKey, **kwargs) -> RenderedPrompt:
        """
        Retrieves a registered prompt and renders it with variables.
        Looks up developer overrides first, then defaults.
        """
        key_str = str(key)
        with self._lock:
            prompt = self._overrides.get(key_str) or self._prompts.get(key_str)

        if not prompt:
            available = list(self._prompts.keys())
            raise PromptNotFoundError(
                f"No prompt registered for key: '{key_str}'. "
                f"Available prompts: {available}"
            )

        return prompt.render(**kwargs)

    def get_raw(self, key: PromptKey) -> BasePrompt:
        """Returns the raw prompt instance (unrendered) by key."""
        key_str = str(key)
        with self._lock:
            prompt = self._overrides.get(key_str) or self._prompts.get(key_str)

        if not prompt:
            raise PromptNotFoundError(f"No prompt registered for key: '{key_str}'")
        return prompt

    def list_all(self) -> List[PromptVersion]:
        """Returns a list of all registered prompt metadata specifications."""
        with self._lock:
            return [p.as_version() for p in self._prompts.values()]

    def clear(self) -> None:
        """Resets the prompt and override store (mainly for testing purposes)."""
        with self._lock:
            self._prompts.clear()
            self._overrides.clear()
