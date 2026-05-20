from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
from typing import Generic

from vidbyte.harnesses.time.types import (
    InputT,
    MinimumTimeHarnessConfig,
    OutputT,
    TimeHarnessIterationResult,
    TimeHarnessState,
    TimeHarnessStatus,
)
from vidbyte.lib.errors import ConfigurationError, HarnessExecutionError, ValidationError
from vidbyte.tools import BaseTool
from vidbyte.tools.builtins import BaseCompactionTool, BaseDateTool


class MinimumTimeHarness(ABC, Generic[InputT, OutputT]):
    """Template-method harness that runs until a configured clock deadline."""

    def __init__(
        self,
        *,
        date_tool: BaseDateTool,
        compaction_tool: BaseCompactionTool,
        config: MinimumTimeHarnessConfig,
        tools: Iterable[BaseTool] = (),
        required_tool_names: Iterable[str] = (),
    ) -> None:
        if not isinstance(date_tool, BaseDateTool):
            raise ConfigurationError("MinimumTimeHarness requires a BaseDateTool instance.")
        if not isinstance(compaction_tool, BaseCompactionTool):
            raise ConfigurationError("MinimumTimeHarness requires a BaseCompactionTool instance.")

        self.date_tool = date_tool
        self.compaction_tool = compaction_tool
        self.config = config
        self.tools = tuple(tools)
        self.required_tool_names = frozenset(required_tool_names)

        self._available_tools = (self.date_tool, self.compaction_tool, *self.tools)
        self._validate_tool_names()
        self._validate_required_tools()

    async def run(self, input_data: InputT) -> OutputT | None:
        """Run developer-defined time slices until the configured deadline is reached."""

        start_time = self._get_current_time("start_time")
        target_end_time = self._resolve_target_end_time(start_time)
        if start_time >= target_end_time:
            raise ValidationError("Target end time must be in the future relative to the date tool.")

        state = self.create_state(
            input_data=input_data,
            start_time=start_time,
            target_end_time=target_end_time,
        )

        while state.status == TimeHarnessStatus.ACTIVE:
            state.current_time = self._get_current_time("current_time")
            if state.current_time >= state.target_end_time:
                state.status = TimeHarnessStatus.COMPLETED
                break

            if self.config.max_iterations is not None and state.iteration >= self.config.max_iterations:
                state.status = TimeHarnessStatus.FAILED
                raise HarnessExecutionError("Maximum iteration safety limit reached before target end time.")

            state.iteration += 1
            try:
                if self.should_compact(state):
                    await self.apply_compaction(state)

                await self.before_time_slice(state)
                result = await self.execute_time_slice(state)
                if not isinstance(result, TimeHarnessIterationResult):
                    raise HarnessExecutionError("execute_time_slice must return TimeHarnessIterationResult.")

                state.last_output = result.output
                state.history.append(result)
                await self.after_time_slice(state, result)
            except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                raise
            except Exception as error:
                await self.handle_iteration_error(state, error)

            await self._sleep_if_configured(state)

        return await self.finalize(state)

    def create_state(
        self,
        *,
        input_data: InputT,
        start_time: datetime,
        target_end_time: datetime,
    ) -> TimeHarnessState[InputT, OutputT]:
        """Create the mutable state object used by the loop."""

        return TimeHarnessState(
            input_data=input_data,
            start_time=start_time,
            target_end_time=target_end_time,
            current_time=start_time,
            metadata={
                "required_tool_names": tuple(sorted(self.required_tool_names)),
                "tool_names": tuple(sorted(tool.name for tool in self._available_tools)),
            },
        )

    @abstractmethod
    async def execute_time_slice(
        self,
        state: TimeHarnessState[InputT, OutputT],
    ) -> TimeHarnessIterationResult[OutputT]:
        """Run one developer-controlled unit of work."""

    async def before_time_slice(self, state: TimeHarnessState[InputT, OutputT]) -> None:
        """Hook called before each developer-controlled time slice."""

    async def after_time_slice(
        self,
        state: TimeHarnessState[InputT, OutputT],
        result: TimeHarnessIterationResult[OutputT],
    ) -> None:
        """Hook called after each successful developer-controlled time slice."""

    def should_compact(self, state: TimeHarnessState[InputT, OutputT]) -> bool:
        """Return whether history should be compacted before the current time slice."""

        return (
            self.config.compaction_interval > 0
            and state.iteration > 0
            and state.iteration % self.config.compaction_interval == 0
        )

    async def apply_compaction(self, state: TimeHarnessState[InputT, OutputT]) -> None:
        """Compact history and trim retained iteration results."""

        state.compaction_summary = await self.compaction_tool.compact_history(state)
        state.compaction_count += 1
        if self.config.history_retention == 0:
            state.history.clear()
        else:
            state.history[:] = state.history[-self.config.history_retention :]

    async def handle_iteration_error(
        self,
        state: TimeHarnessState[InputT, OutputT],
        error: Exception,
    ) -> None:
        """Handle a recoverable iteration or compaction error."""

        state.errors.append(f"{type(error).__name__}: {error}")
        if not self.config.continue_on_iteration_error:
            state.status = TimeHarnessStatus.FAILED
            raise error

    async def finalize(self, state: TimeHarnessState[InputT, OutputT]) -> OutputT | None:
        """Return the final output after the clock deadline is reached."""

        return state.last_output

    def _validate_tool_names(self) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for tool in self._available_tools:
            name = tool.name
            if name in seen:
                duplicates.add(name)
            seen.add(name)
        if duplicates:
            joined = ", ".join(sorted(duplicates))
            raise ConfigurationError(f"Duplicate tool names are not allowed: {joined}")

    def _validate_required_tools(self) -> None:
        available = {tool.name for tool in self._available_tools}
        missing = sorted(self.required_tool_names - available)
        if missing:
            raise ConfigurationError(f"Missing required tools: {', '.join(missing)}")

    def _resolve_target_end_time(self, start_time: datetime) -> datetime:
        if self.config.target_end_time is not None:
            target_end_time = self.config.target_end_time
        elif self.config.minimum_duration is not None:
            target_end_time = start_time + self.config.minimum_duration
        else:
            raise ConfigurationError("A target end time or minimum duration is required.")

        self._require_timezone_aware(target_end_time, "target_end_time")
        return target_end_time

    def _get_current_time(self, field_name: str) -> datetime:
        current_time = self.date_tool.get_current_time()
        self._require_timezone_aware(current_time, field_name)
        return current_time

    def _require_timezone_aware(self, value: datetime, field_name: str) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError(f"{field_name} must be timezone-aware.")

    async def _sleep_if_configured(self, state: TimeHarnessState[InputT, OutputT]) -> None:
        if self.config.sleep_interval_seconds <= 0:
            return

        sleep_seconds = min(self.config.sleep_interval_seconds, state.remaining_seconds)
        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

