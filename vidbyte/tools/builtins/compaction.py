from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolSpec

if TYPE_CHECKING:
    from vidbyte.harnesses.time.types import TimeHarnessState


class BaseCompactionTool(BaseTool):
    """Contract for tools that compact long-running harness state."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="compaction",
            description="Compacts long-running harness state.",
        )

    @abstractmethod
    async def compact_history(self, state: TimeHarnessState[object, object]) -> str:
        """Return a compact summary of the current harness state."""

