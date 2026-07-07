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

    _ROLE_ASSETS: dict[str, str] = {
        "context": "context_prompt.md",
        "splitter": "split_prompt.md",
        "adversarial": "adversarial_prompt.md",
        "implementation": "implementation_prompt.md",
    }

    def for_role(self, role: str) -> str:
        # Returns the system prompt asset for the given pipeline role.
        name = self._ROLE_ASSETS.get(role)
        if name is None:
            raise ValueError(f"Unknown paradigm role: {role!r}. Expected one of: {', '.join(sorted(self._ROLE_ASSETS))}.")
        return self._read_asset(name)

    def context(self) -> str:
        # Returns the system prompt for the context-extraction agent.
        return self.for_role("context")

    def splitter(self) -> str:
        # Returns the system prompt for the split-planning agent.
        return self.for_role("splitter")

    def adversarial(self) -> str:
        # Returns the system prompt for the adversarial de-overlap agent.
        return self.for_role("adversarial")

    def implementation(self) -> str:
        # Returns the system prompt for each implementation branch agent.
        return self.for_role("implementation")

    def _read_asset(self, name: str) -> str:
        # Reads one Markdown prompt asset from this prompts subpackage.
        return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


__all__ = [
    "ContextMinimalFanoutPrompts",
]
