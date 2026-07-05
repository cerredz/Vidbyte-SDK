"""Context Protocol Header

Description:
    Loads the package-local system prompts for the four context-minimal fanout
    pipeline stages.
Purpose:
    Keeps prompt text inspectable and editable as Markdown assets rather than
    inline string literals.
Architecture:
    - ContextMinimalFanoutPrompts: Lazy reader for the four stage prompts.
Relations:
    Consumed by vidbyte.paradigms.context_minimal_fanout.paradigm.
"""

from __future__ import annotations

from importlib import resources


class ContextMinimalFanoutPrompts:
    """Loads package-local prompt assets for the fanout pipeline stages."""

    def context(self) -> str:
        # Returns the system prompt for the context-extraction agent.
        return self._read_asset("context_prompt.md")

    def splitter(self) -> str:
        # Returns the system prompt for the split-planning agent.
        return self._read_asset("split_prompt.md")

    def adversarial(self) -> str:
        # Returns the system prompt for the adversarial de-overlap agent.
        return self._read_asset("adversarial_prompt.md")

    def implementation(self) -> str:
        # Returns the system prompt for each implementation branch agent.
        return self._read_asset("implementation_prompt.md")

    def _read_asset(self, name: str) -> str:
        # Reads one Markdown prompt asset from this package.
        return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


__all__ = [
    "ContextMinimalFanoutPrompts",
]
