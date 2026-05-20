from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolSpec


class BaseDateTool(BaseTool):
    """Contract for tools that provide timezone-aware current time."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="date",
            description="Provides the current timezone-aware datetime.",
        )

    @abstractmethod
    def get_current_time(self) -> datetime:
        """Return the current timezone-aware datetime."""


class SystemDateTool(BaseDateTool):
    """Date tool backed by the host system clock in UTC."""

    def get_current_time(self) -> datetime:
        return datetime.now(timezone.utc)

