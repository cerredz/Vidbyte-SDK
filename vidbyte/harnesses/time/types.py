from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Generic, TypeVar

from vidbyte.lib.errors import ConfigurationError

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class TimeHarnessStatus(str, Enum):
    """Runtime status for a time-based harness."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class TimeHarnessIterationResult(Generic[OutputT]):
    """Result produced by one developer-controlled time slice."""

    output: OutputT
    signals_completion: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MinimumTimeHarnessConfig:
    """Configuration for a minimum-time harness run."""

    target_end_time: datetime | None = None
    minimum_duration: timedelta | None = None
    compaction_interval: int = 5
    history_retention: int = 2
    sleep_interval_seconds: float = 0.0
    continue_on_iteration_error: bool = True
    max_iterations: int | None = None

    def __post_init__(self) -> None:
        has_target = self.target_end_time is not None
        has_duration = self.minimum_duration is not None
        if has_target == has_duration:
            raise ConfigurationError(
                "MinimumTimeHarnessConfig requires exactly one of target_end_time or minimum_duration."
            )
        if self.target_end_time is not None and self.target_end_time.tzinfo is None:
            raise ConfigurationError("target_end_time must be timezone-aware.")
        if self.minimum_duration is not None and self.minimum_duration <= timedelta(0):
            raise ConfigurationError("minimum_duration must be greater than zero.")
        if self.compaction_interval < 0:
            raise ConfigurationError("compaction_interval must be greater than or equal to zero.")
        if self.history_retention < 0:
            raise ConfigurationError("history_retention must be greater than or equal to zero.")
        if self.sleep_interval_seconds < 0:
            raise ConfigurationError("sleep_interval_seconds must be greater than or equal to zero.")
        if self.max_iterations is not None and self.max_iterations < 0:
            raise ConfigurationError("max_iterations must be greater than or equal to zero.")


@dataclass(slots=True)
class TimeHarnessState(Generic[InputT, OutputT]):
    """Mutable runtime state shared across time harness hooks."""

    input_data: InputT
    start_time: datetime
    target_end_time: datetime
    current_time: datetime
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
        """Seconds elapsed since the harness started."""

        return max(0.0, (self.current_time - self.start_time).total_seconds())

    @property
    def remaining_seconds(self) -> float:
        """Seconds remaining until the target end time."""

        return max(0.0, (self.target_end_time - self.current_time).total_seconds())

