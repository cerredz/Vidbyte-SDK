# -*- coding: utf-8 -*-
#
# Context Protocol Header:
# - DESCRIPTION: Unit test suite for MinimumTimeHarness.
# - PURPOSE: Ensures that MinimumTimeHarness correctly handles timing bounds, compaction intervals, safety limits, custom hook overrides, and exception handling policies.
# - ARCHITECTURE: Standard Python unittest test suite utilizing fake clocks (FakeDateTool) and recording compactor (RecordingCompactionTool) mocks to deterministically assert timing and state transitions.
# - KEY FUNCTIONS:
#   - FakeDateTool: Stub date tool advancing on each read.
#   - RecordingCompactionTool: Mocks compaction.
#   - RecordingHarness: Mock harness tracking loop cycles.
# - RELATION TO CODEBASE: Focuses on verifying the correctness of vidbyte.harnesses.time components. Runs under the standard test suite.
# - SIMILAR FILES: tests/test_custom_function_tools.py, tests/test_harness_tool_cascade.py

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from vidbyte import VidbyteSDK
from vidbyte.harnesses.time import (
    BaseCompactionTool,
    BaseDateTool,
    ConfigurationError,
    HarnessExecutionError,
    MinimumTimeHarness,
    MinimumTimeHarnessConfig,
    TimeHarnessIterationResult,
    ValidationError,
)
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec

BASE_TIME = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


class FakeDateTool(BaseDateTool):
    """Stub implementation of the date tool for time-controlled testing."""

    def __init__(self, times: list[datetime]) -> None:
        self.times = times
        self.calls = 0

    def get_current_time(self) -> datetime:
        index = min(self.calls, len(self.times) - 1)
        self.calls += 1
        return self.times[index]


class RecordingCompactionTool(BaseCompactionTool):
    """Stub implementation of the compaction tool that records call intervals."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    async def compact_history(self, state) -> str:
        self.calls.append(state.iteration)
        return f"compact iteration={state.iteration} history={len(state.history)}"


class NamedTool(BaseTool):
    """Stub standard tool to test required tool checks."""

    def __init__(self, name: str) -> None:
        self._name = name

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self._name, description=f"{self._name} tool")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success(self.name, "success")


class RecordingHarness(MinimumTimeHarness[str, str]):
    """Testing harness that simulates iterative work and errors."""

    def __init__(self, *args, fail_on: set[int] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fail_on = fail_on or set()
        self.final_state = None

    async def execute_time_slice(self, state):
        if state.iteration in self.fail_on:
            raise RuntimeError(f"failure at {state.iteration}")
        return TimeHarnessIterationResult(
            output=f"iteration-{state.iteration}",
            signals_completion=True,
            metadata={"iteration": state.iteration},
        )

    async def finalize(self, state):
        self.final_state = state
        return await super().finalize(state)


class MinimumTimeHarnessTests(unittest.TestCase):
    def test_runs_until_target_time_and_ignores_completion_signal(self) -> None:
        harness = RecordingHarness(
            date_tool=FakeDateTool(
                [
                    BASE_TIME,
                    BASE_TIME,
                    BASE_TIME + timedelta(seconds=1),
                    BASE_TIME + timedelta(seconds=2),
                    BASE_TIME + timedelta(seconds=3),
                ]
            ),
            compaction_tool=RecordingCompactionTool(),
            config=MinimumTimeHarnessConfig(
                target_end_time=BASE_TIME + timedelta(seconds=3),
                compaction_interval=0,
            ),
        )

        result = asyncio.run(harness.run("work"))

        self.assertEqual(result, "iteration-3")
        self.assertEqual(harness.final_state.iteration, 3)
        self.assertTrue(all(item.signals_completion for item in harness.final_state.history))

    def test_minimum_duration_computes_deadline_from_start_time(self) -> None:
        harness = RecordingHarness(
            date_tool=FakeDateTool(
                [
                    BASE_TIME,
                    BASE_TIME,
                    BASE_TIME + timedelta(seconds=1),
                    BASE_TIME + timedelta(seconds=2),
                    BASE_TIME + timedelta(seconds=3),
                ]
            ),
            compaction_tool=RecordingCompactionTool(),
            config=MinimumTimeHarnessConfig(
                minimum_duration=timedelta(seconds=3),
                compaction_interval=0,
            ),
        )

        result = asyncio.run(harness.run("work"))

        self.assertEqual(result, "iteration-3")
        self.assertEqual(harness.final_state.target_end_time, BASE_TIME + timedelta(seconds=3))

    def test_rejects_past_target_end_time(self) -> None:
        harness = RecordingHarness(
            date_tool=FakeDateTool([BASE_TIME]),
            compaction_tool=RecordingCompactionTool(),
            config=MinimumTimeHarnessConfig(target_end_time=BASE_TIME - timedelta(seconds=1)),
        )

        with self.assertRaises(ValidationError):
            asyncio.run(harness.run("work"))

    def test_rejects_naive_target_end_time(self) -> None:
        with self.assertRaises(ConfigurationError):
            MinimumTimeHarnessConfig(target_end_time=datetime(2026, 5, 20, 12, 0))

    def test_rejects_naive_date_tool_time(self) -> None:
        harness = RecordingHarness(
            date_tool=FakeDateTool([datetime(2026, 5, 20, 12, 0)]),
            compaction_tool=RecordingCompactionTool(),
            config=MinimumTimeHarnessConfig(minimum_duration=timedelta(seconds=1)),
        )

        with self.assertRaises(ValidationError):
            asyncio.run(harness.run("work"))

    def test_requires_date_tool_contract(self) -> None:
        with self.assertRaises(ConfigurationError):
            RecordingHarness(
                date_tool=object(),
                compaction_tool=RecordingCompactionTool(),
                config=MinimumTimeHarnessConfig(minimum_duration=timedelta(seconds=1)),
            )

    def test_requires_compaction_tool_contract(self) -> None:
        with self.assertRaises(ConfigurationError):
            RecordingHarness(
                date_tool=FakeDateTool([BASE_TIME]),
                compaction_tool=object(),
                config=MinimumTimeHarnessConfig(minimum_duration=timedelta(seconds=1)),
            )

    def test_validates_required_tool_names(self) -> None:
        with self.assertRaises(ConfigurationError):
            RecordingHarness(
                date_tool=FakeDateTool([BASE_TIME]),
                compaction_tool=RecordingCompactionTool(),
                config=MinimumTimeHarnessConfig(minimum_duration=timedelta(seconds=1)),
                tools=[NamedTool("search")],
                required_tool_names={"date", "compaction", "missing"},
            )

        harness = RecordingHarness(
            date_tool=FakeDateTool([BASE_TIME, BASE_TIME + timedelta(seconds=1)]),
            compaction_tool=RecordingCompactionTool(),
            config=MinimumTimeHarnessConfig(minimum_duration=timedelta(seconds=1)),
            tools=[NamedTool("search")],
            required_tool_names={"date", "compaction", "search"},
        )
        self.assertIn("search", harness.required_tool_names)

    def test_calls_compaction_at_configured_interval_and_trims_history(self) -> None:
        compaction_tool = RecordingCompactionTool()
        harness = RecordingHarness(
            date_tool=FakeDateTool(
                [
                    BASE_TIME,
                    BASE_TIME,
                    BASE_TIME + timedelta(seconds=1),
                    BASE_TIME + timedelta(seconds=2),
                    BASE_TIME + timedelta(seconds=3),
                    BASE_TIME + timedelta(seconds=4),
                    BASE_TIME + timedelta(seconds=5),
                ]
            ),
            compaction_tool=compaction_tool,
            config=MinimumTimeHarnessConfig(
                target_end_time=BASE_TIME + timedelta(seconds=5),
                compaction_interval=2,
                history_retention=1,
            ),
        )

        result = asyncio.run(harness.run("work"))

        self.assertEqual(result, "iteration-5")
        self.assertEqual(compaction_tool.calls, [2, 4])
        self.assertEqual(harness.final_state.compaction_count, 2)
        self.assertEqual(harness.final_state.compaction_summary, "compact iteration=4 history=3")
        self.assertEqual([item.output for item in harness.final_state.history], ["iteration-3", "iteration-4", "iteration-5"])

    def test_records_and_continues_recoverable_iteration_errors_by_default(self) -> None:
        harness = RecordingHarness(
            date_tool=FakeDateTool(
                [
                    BASE_TIME,
                    BASE_TIME,
                    BASE_TIME + timedelta(seconds=1),
                    BASE_TIME + timedelta(seconds=2),
                ]
            ),
            compaction_tool=RecordingCompactionTool(),
            config=MinimumTimeHarnessConfig(
                target_end_time=BASE_TIME + timedelta(seconds=2),
                compaction_interval=0,
            ),
            fail_on={1},
        )

        result = asyncio.run(harness.run("work"))

        self.assertEqual(result, "iteration-2")
        self.assertEqual(len(harness.final_state.errors), 1)
        self.assertIn("RuntimeError: failure at 1", harness.final_state.errors[0])

    def test_raises_recoverable_iteration_errors_when_configured(self) -> None:
        harness = RecordingHarness(
            date_tool=FakeDateTool([BASE_TIME, BASE_TIME]),
            compaction_tool=RecordingCompactionTool(),
            config=MinimumTimeHarnessConfig(
                minimum_duration=timedelta(seconds=5),
                compaction_interval=0,
                continue_on_iteration_error=False,
            ),
            fail_on={1},
        )

        with self.assertRaises(RuntimeError):
            asyncio.run(harness.run("work"))

    def test_max_iterations_before_deadline_raises_harness_execution_error(self) -> None:
        harness = RecordingHarness(
            date_tool=FakeDateTool([BASE_TIME]),
            compaction_tool=RecordingCompactionTool(),
            config=MinimumTimeHarnessConfig(
                target_end_time=BASE_TIME + timedelta(seconds=10),
                compaction_interval=0,
                max_iterations=2,
            ),
        )

        with self.assertRaises(HarnessExecutionError):
            asyncio.run(harness.run("work"))

    def test_harness_client_exposes_minimum_time_class(self) -> None:
        sdk = VidbyteSDK()

        self.assertIs(sdk.harnesses.minimum_time, MinimumTimeHarness)


if __name__ == "__main__":
    unittest.main()
