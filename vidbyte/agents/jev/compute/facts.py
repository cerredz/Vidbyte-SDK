"""FILE: vidbyte/agents/jev/compute/facts.py

PURPOSE: Read exact tool-call and iteration counts for the mid-run compute checkpoint.
ROLE IN CODEBASE: JevComputeController records these facts alongside each checkpoint's run brief.
ARCHITECTURE NOTE: Counts come from runtime records and do not use a model.
TESTS: tests/test_jev_compute.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.lib.dataclasses.jev import JevRunFacts
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolStatus
from vidbyte.tools._internal import IS_DONE_TOOL_NAME


class JevRunFactsReader:
    """Build run counts from the main agent's live loop state."""

    @classmethod
    def read(cls, responses: Sequence[str], calls: Sequence[ToolCallContext], *, tokens_used: int | None) -> JevRunFacts:
        # @intent checkpoint-facts-come-from-live-loop-state
        # Counts use the exact response and tool-call records supplied by AgentRuntime.
        work_calls = tuple(call for call in calls if call.tool_name != IS_DONE_TOOL_NAME)
        streak = 0
        for call in reversed(work_calls):
            if not cls.failed(call):
                break
            streak += 1
        return JevRunFacts(
            iteration=len(responses),
            tool_calls=len(work_calls),
            error_streak=streak,
            tokens_used=tokens_used,
        )

    @staticmethod
    def failed(call: ToolCallContext) -> bool:
        # @intent failed-calls-include-denied-and-error-results
        # Runtime state and result status both represent failures in the canonical tool-call record.
        return call.state in (ToolCallState.FAILED, ToolCallState.DENIED) or (
            call.result is not None and call.result.status is ToolStatus.ERROR
        )


__all__ = ["JevRunFactsReader"]
