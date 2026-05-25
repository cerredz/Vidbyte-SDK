"""Context Protocol Header

Description:
    Defines the public ContextWindow preset namespace.
Purpose:
    Keeps the user-facing `ContextWindow.preset.<name>` API small while
    delegating preset registration and algorithm behavior to dedicated modules.
Architecture:
    - ContextWindow: Namespace wrapper for context-window presets.
Relations:
    Presets live in vidbyte.context.presets; implementations live under
    vidbyte.context.algorithms.
"""

from __future__ import annotations

from vidbyte.context.algorithms import ContextWindowAlgorithm, ToolResultAdmission
from vidbyte.context.presets import ContextWindowPresets, resolve_context_window_algorithm


class ContextWindow:
    """Namespace for context-window algorithm presets."""

    preset = ContextWindowPresets()

    @staticmethod
    def resolve_algorithm(
        algorithm: ContextWindowAlgorithm | str | None,
    ) -> ContextWindowAlgorithm:
        """Normalize a preset object, preset name, or None into an algorithm."""
        return resolve_context_window_algorithm(algorithm, presets=ContextWindow.preset)


__all__ = [
    "ContextWindow",
    "ContextWindowAlgorithm",
    "ToolResultAdmission",
]
