from __future__ import annotations

from importlib import resources


class MultiplePromptFanoutPrompts:
    """Loads package-local prompt assets for the multiple-prompts harness."""

    def splitter(self) -> str:
        # Returns the system prompt used by the split-planning agent.
        return self._read_asset("split_prompt.md")

    def implementation(self) -> str:
        # Returns the system prompt used by each implementation branch agent.
        return self._read_asset("implementation_prompt.md")

    def _read_asset(self, name: str) -> str:
        # Reads one Markdown prompt asset from this package.
        return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


__all__ = [
    "MultiplePromptFanoutPrompts",
]
