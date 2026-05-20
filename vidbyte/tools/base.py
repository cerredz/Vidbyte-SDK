from __future__ import annotations

from abc import ABC, abstractmethod

from vidbyte.tools.types import ToolSpec


class BaseTool(ABC):
    """Minimal public contract for SDK tool metadata."""

    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return stable public metadata for this tool."""

    @property
    def name(self) -> str:
        """Return the tool's stable registry name."""

        return self.spec().name

