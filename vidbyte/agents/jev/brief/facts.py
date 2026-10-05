"""FILE: vidbyte/agents/jev/brief/facts.py

PURPOSE: Reads exact facts from the main agent's run between iterations, with no model involved: iteration and tool-call counts, the current streak of failed tool calls, repeated identical calls, and token growth since the last brief refresh attempt.
ROLE IN CODEBASE: JevRunBriefKeeper reads facts at every checkpoint to decide whether a refresh is due; the facts are also the exact counts a later Jev checkpoint reads beside the brief.
ARCHITECTURE NOTE: Counting belongs to code, not to the writer or to Jev, so every number here is computed from ToolCallContext records and never estimated. A call signature is the tool name plus its arguments serialized with sorted keys, so argument order never hides a repeat.
COMMON MODIFICATION PATTERNS: Add a fact as a field on JevRunFacts and compute it here; keep thresholds that act on facts in JevRunBriefKeeper.
KNOWN EDGE CASES: isDone calls are loop control, not work, and are excluded. A call with no recorded iteration never counts as new since a refresh. A call counts as failed when its state is failed or denied or its result reports an error.
RELATED DOCS: docs/design/jev-run-brief.md.
TESTS: tests/test_jev_run_brief.py.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence

from vidbyte.lib.constants.jev import (
    JEV_RUN_FACTS_ARGUMENTS_PREVIEW_CHARS,
    JEV_RUN_FACTS_REPEAT_MIN,
    JEV_RUN_FACTS_REPEATED_CALLS_MAX,
)
from vidbyte.lib.dataclasses.jev import JevRepeatedCall, JevRunFacts
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolStatus
from vidbyte.tools._internal import IS_DONE_TOOL_NAME

_FAILED_STATES = frozenset({ToolCallState.FAILED, ToolCallState.DENIED})


class JevRunFactsReader:
    """Reads exact counts from the main agent's run, for refresh triggers and for Jev, with no model involved."""

    @classmethod
    def read(
        cls,
        responses: Sequence[str],
        calls: Sequence[ToolCallContext],
        *,
        tokens_used: int | None,
        since_iteration: int,
        tokens_at_refresh: int | None,
    ) -> JevRunFacts:
        """Return the run's facts, counting the `_since_refresh` fields from iteration `since_iteration`."""
        work = tuple(call for call in calls if call.tool_name != IS_DONE_TOOL_NAME)
        recent = tuple(call for call in work if (call.iteration_count or 0) > since_iteration)
        recent_signatures = Counter(cls._signature(call) for call in recent)
        return JevRunFacts(
            iteration=len(responses),
            tool_calls=len(work),
            error_streak=cls._error_streak(work),
            iterations_since_refresh=max(len(responses) - since_iteration, 0),
            errors_since_refresh=sum(1 for call in recent if cls.failed(call)),
            repeats_since_refresh=max(recent_signatures.values(), default=0),
            repeated_calls=cls._repeated(work),
            tokens_used=tokens_used,
            tokens_at_refresh=tokens_at_refresh,
        )

    @staticmethod
    def failed(call: ToolCallContext) -> bool:
        """Return whether a tool call failed: a failed or denied state, or a result that reports an error."""
        return call.state in _FAILED_STATES or (call.result is not None and call.result.status is ToolStatus.ERROR)

    @classmethod
    def _error_streak(cls, calls: Sequence[ToolCallContext]) -> int:
        # Counts consecutive failed calls back from the newest one.
        streak = 0
        for call in reversed(calls):
            if not cls.failed(call):
                break
            streak += 1
        return streak

    @classmethod
    def _repeated(cls, calls: Sequence[ToolCallContext]) -> tuple[JevRepeatedCall, ...]:
        # Lists the most repeated call signatures, most repeated first, with a bounded preview of their arguments.
        counts = Counter(cls._signature(call) for call in calls)
        repeated = [(signature, count) for signature, count in counts.most_common() if count >= JEV_RUN_FACTS_REPEAT_MIN]
        return tuple(
            JevRepeatedCall(tool_name=name, arguments=arguments[:JEV_RUN_FACTS_ARGUMENTS_PREVIEW_CHARS], count=count)
            for (name, arguments), count in repeated[:JEV_RUN_FACTS_REPEATED_CALLS_MAX]
        )

    @staticmethod
    def _signature(call: ToolCallContext) -> tuple[str, str]:
        # Identifies a call by its tool and its exact arguments, serialized with sorted keys.
        return call.tool_name, json.dumps(dict(call.arguments), default=str, sort_keys=True)


__all__ = ["JevRunFactsReader"]
