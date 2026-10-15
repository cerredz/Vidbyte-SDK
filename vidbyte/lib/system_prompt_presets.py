"""FILE: vidbyte/lib/system_prompt_presets.py

PURPOSE: Names the system-prompt presets the current agent run hands to every agent it starts, so a preset set on one agent reaches its specialists, clones, helpers, workers, and forks.
ROLE IN CODEBASE: BaseAgent.generate_reply enters its run's effective presets before the run and exits them in its finally block, as it does for its prompt queue; BaseAgent._runtime reads SystemPromptPresetScope.resolve to pick the presets it composes into the system prompt. It is the prompt counterpart of vidbyte/lib/usage_ledger.py.
ARCHITECTURE NOTE: A ContextVar keeps concurrent runs isolated and is copied into every asyncio task (and asyncio.to_thread call) a run creates, so no spawn path needs its own plumbing. It holds enum members only; the text lives in the prompts layer (vidbyte/prompts/system_prompt_presets.py), which this bottom layer never imports.
COMMON MODIFICATION PATTERNS: A new place that starts agents needs nothing here, as long as it runs inside the parent's run. A new agent that must keep its own prompt passes system_prompt_presets=() to BaseAgent.
KNOWN EDGE CASES: An agent's own value wins over the scope, including an empty tuple, which opts it and its own children out. An agent built and run outside any run, or in a thread or event loop that did not copy the context, inherits nothing.
RELATED DOCS: docs/design/working-principles-preset.md.
TESTS: tests/features/system_prompt_presets/test_system_prompt_presets_units.py and test_system_prompt_presets_propagation.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from vidbyte.lib.enums.prompts import SystemPromptPreset

_ACTIVE_PRESETS: ContextVar[tuple[SystemPromptPreset, ...]] = ContextVar("vidbyte_system_prompt_presets", default=())


class SystemPromptPresetScope:
    """The system-prompt presets the current agent run hands to every agent it starts."""

    @staticmethod
    def active() -> tuple[SystemPromptPreset, ...]:
        """Return the presets of the run executing in this context, or () outside any run."""
        return _ACTIVE_PRESETS.get()

    @staticmethod
    def resolve(own: tuple[SystemPromptPreset, ...] | None) -> tuple[SystemPromptPreset, ...]:
        """Return an agent's effective presets: its own value when set, otherwise the active run's."""
        return own if own is not None else _ACTIVE_PRESETS.get()

    @staticmethod
    def enter(presets: tuple[SystemPromptPreset, ...]) -> Token[tuple[SystemPromptPreset, ...]]:
        """Make `presets` the active presets and return the token that exit() takes to restore the previous ones."""
        return _ACTIVE_PRESETS.set(presets)

    @staticmethod
    def exit(token: Token[tuple[SystemPromptPreset, ...]]) -> None:
        """Restore the presets that were active before the enter() call that returned `token`."""
        _ACTIVE_PRESETS.reset(token)

    @staticmethod
    @contextmanager
    def scope(presets: tuple[SystemPromptPreset, ...]) -> Iterator[tuple[SystemPromptPreset, ...]]:
        """Make `presets` the active presets until the block exits, then restore the previous ones."""
        token = _ACTIVE_PRESETS.set(presets)
        try:
            yield presets
        finally:
            _ACTIVE_PRESETS.reset(token)


__all__ = ["SystemPromptPresetScope"]
