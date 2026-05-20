# -*- coding: utf-8 -*-
#
# Context Protocol Header:
# - DESCRIPTION: Dataclasses, Enums, Interfaces, and Exception classes for time-based harnesses.
# - PURPOSE: To provide a clean, isolated type foundation for the time-based harness system in the Vidbyte SDK. This allows the harness to operate with robust clock and compaction contracts without dependency conflicts with other features.
# - ARCHITECTURE:
#   - Exceptions: ConfigurationError, ValidationError, HarnessExecutionError (inheriting from VidbyteSdkError).
#   - Tool Contracts: BaseDateTool, SystemDateTool, BaseCompactionTool (inheriting from BaseTool).
#   - Enums: TimeHarnessStatus (active, completed, failed).
#   - Dataclasses: TimeHarnessIterationResult, MinimumTimeHarnessConfig, TimeHarnessState.
# - KEY FUNCTIONS:
#   - BaseDateTool.get_current_time(): Abstract method returning a timezone-aware datetime.
#   - SystemDateTool.get_current_time(): Concrete implementation returning datetime.now(timezone.utc).
#   - BaseCompactionTool.compact_history(state): Abstract method returning a string summary of historical state.
# - RELATION TO CODEBASE: Provides the type contracts and interfaces used by MinimumTimeHarness. It acts as an isolated package boundaries under harnesses/time/, preventing any overlap or conflicts with the advanced tools ecosystem.
# - SIMILAR FILES: vidbyte/strategies/types.py, vidbyte/tools/types.py

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


# =====================================================================
# Custom SDK Exceptions
# =====================================================================

class ConfigurationError(VidbyteSdkError):
    """Raised when the harness or its tools are configured incorrectly."""


class ValidationError(VidbyteSdkError):
    """Raised when runtime inputs or clock values fail sanity checks."""


class HarnessExecutionError(VidbyteSdkError):
    """Raised when the harness execution encounters a fatal safety limit or runtime error."""


# =====================================================================
# Specialized Tool Contracts
# =====================================================================

class BaseDateTool(BaseTool, ABC):
    """Base interface for date tools used by time harnesses."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="date",
            description="Provides the current timezone-aware datetime for loop execution bounds checking.",
        )

    @abstractmethod
    def get_current_time(self) -> dt.datetime:
        """Return the current timezone-aware datetime."""

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a validated tool call."""
        try:
            current_time = self.get_current_time()
            return ToolResult.success(self.name, current_time.isoformat())
        except Exception as error:
            return ToolResult.failure(self.name, str(error))


class SystemDateTool(BaseDateTool):
    """Production implementation of the date tool using the system clock."""

    def get_current_time(self) -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)


class BaseCompactionTool(BaseTool, ABC):
    """Base interface for compaction tools used by time harnesses."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="compaction",
            description="Compacts historical iteration state to maintain a long-running context window.",
        )

    @abstractmethod
    async def compact_history(self, state: TimeHarnessState[Any, Any]) -> str:
        """Return a compact string summary of the current harness history/state."""

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a validated tool call."""
        return ToolResult.failure(self.name, "CompactionTool must be invoked internally via compact_history.")


# =====================================================================
# Time Harness Iteration & Configuration State
# =====================================================================

class TimeHarnessStatus(str, Enum):
    """The execution status of a time harness."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class TimeHarnessIterationResult(Generic[OutputT]):
    """Holds the result output from a single unit-of-work iteration."""

    output: OutputT
    signals_completion: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MinimumTimeHarnessConfig:
    """Configuration options for a MinimumTimeHarness."""

    target_end_time: dt.datetime | None = None
    minimum_duration: dt.timedelta | None = None
    compaction_interval: int = 5
    history_retention: int = 2
    sleep_interval_seconds: float = 0.0
    continue_on_iteration_error: bool = True
    max_iterations: int | None = None

    def __post_init__(self) -> None:
        if self.target_end_time is None and self.minimum_duration is None:
            raise ConfigurationError("Either target_end_time or minimum_duration must be supplied.")
        if self.target_end_time is not None and self.minimum_duration is not None:
            raise ConfigurationError("Cannot supply both target_end_time and minimum_duration.")
        if self.target_end_time is not None:
            if self.target_end_time.tzinfo is None or self.target_end_time.utcoffset() is None:
                raise ConfigurationError("target_end_time must be timezone-aware.")
        if self.minimum_duration is not None and self.minimum_duration <= dt.timedelta(0):
            raise ConfigurationError("minimum_duration must be a positive duration.")
        if self.compaction_interval < 0:
            raise ConfigurationError("compaction_interval must be non-negative.")
        if self.history_retention < 0:
            raise ConfigurationError("history_retention must be non-negative.")
        if self.sleep_interval_seconds < 0.0:
            raise ConfigurationError("sleep_interval_seconds must be non-negative.")


@dataclass(slots=True)
class TimeHarnessState(Generic[InputT, OutputT]):
    """The mutable running state of a time-based harness."""

    input_data: InputT
    start_time: dt.datetime
    target_end_time: dt.datetime
    current_time: dt.datetime
    status: TimeHarnessStatus = TimeHarnessStatus.ACTIVE
    iteration: int = 0
    last_output: OutputT | None = None
    history: list[TimeHarnessIterationResult[OutputT]] = field(default_factory=list)
    compaction_summary: str | None = None
    compaction_count: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> float:
        """Calculate elapsed seconds since start_time."""
        return (self.current_time - self.start_time).total_seconds()

    @property
    def remaining_seconds(self) -> float:
        """Calculate remaining seconds until target_end_time."""
        return max(0.0, (self.target_end_time - self.current_time).total_seconds())
