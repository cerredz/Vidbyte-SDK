"""FILE: vidbyte/agents/jev/motivating_case/evidence.py

PURPOSE: Turns a run's recorded tool calls into immutable, addressable events that handoff refs and quotes are checked against.
ROLE IN CODEBASE: JevRuntime builds a RunEventLedger at each finish attempt; the handoff builder sees its rendering and ScenarioEvidenceChecker resolves refs through it.
ARCHITECTURE NOTE: Events come from ToolCallContext records, which hold the raw ToolResult before model-visible truncation, so a quote can cite output the main model never saw in full.
COMMON MODIFICATION PATTERNS: Add an event field here, render it for the handoff builder, and cover it in tests/test_jev_motivating_case.py.
KNOWN EDGE CASES: Internal tools (isDone and friends) are excluded; retried attempts collapse to the final attempt the runtime recorded.
RELATED DOCS: docs/design/jev-motivating-case.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from vidbyte.agents.jev.motivating_case.state import VerbatimText
from vidbyte.lib.constants.jev import JEV_MOTIVATING_CASE_EVENT_RENDER_CHARS
from vidbyte.lib.dataclasses.tools import ToolPermission
from vidbyte.tools.types import ToolCallContext, ToolCallState

# Argument keys that conventionally name a file; used for staleness and coverage heuristics only.
PATH_ARGUMENT_KEYS: tuple[str, ...] = ("path", "file_path", "filepath", "filename", "file", "target_file")
# A token that looks like a file name with an extension, such as tests/test_export.py.
_FILE_TOKEN = re.compile(r"[\w./\\-]+\.[A-Za-z]{1,5}\b")


@dataclass(frozen=True, slots=True)
class RunEvent:
    """One non-internal tool call as the runtime recorded it."""

    event_id: str
    index: int
    tool_name: str
    permission: ToolPermission | None
    state: ToolCallState
    arguments: Mapping[str, object]
    output: str
    intent: str | None

    def succeeded(self) -> bool:
        # A call counts as run only when the runtime recorded a successful final attempt.
        return self.state is ToolCallState.SUCCEEDED

    def searchable_text(self) -> str:
        # Joins raw string argument values and the output so quotes match regardless of JSON escaping.
        parts = [value for value in self._argument_strings()]
        parts.append(self.output)
        return "\n".join(parts)

    def argument_text(self) -> str:
        # Returns only the argument strings, used to decide which files a command selects.
        return "\n".join(self._argument_strings())

    def paths(self) -> tuple[str, ...]:
        # Returns string values under conventional path argument keys.
        return tuple(value for key, value in self.arguments.items() if key in PATH_ARGUMENT_KEYS and isinstance(value, str) and value.strip())

    def selects_no_file(self) -> bool:
        # True when the arguments name no file at all, as in a bare `pytest` or `npm test` suite run.
        return _FILE_TOKEN.search(self.argument_text()) is None

    def render(self) -> dict[str, object]:
        # Renders a bounded view for the handoff builder; quotes must still come from the full record.
        # @intent render-is-lossy-quotes-are-not
        # Head and tail survive truncation because setups start at the top of a file and runners report results at the end.
        return {
            "event_id": self.event_id,
            "tool": self.tool_name,
            "permission": self.permission.value if self.permission is not None else "unknown",
            "state": self.state.value,
            "intent": self.intent or "",
            "arguments": {key: self._bounded(value) for key, value in self.arguments.items()},
            "output": self._bounded(self.output),
        }

    def _argument_strings(self) -> list[str]:
        # Flattens nested argument values into their raw strings.
        return [text for value in self.arguments.values() for text in _strings_in(value)]

    @staticmethod
    def _bounded(value: object) -> object:
        # Keeps the head and tail of long text so the builder sees both the setup and the final result.
        if not isinstance(value, str) or len(value) <= JEV_MOTIVATING_CASE_EVENT_RENDER_CHARS:
            return value
        half = JEV_MOTIVATING_CASE_EVENT_RENDER_CHARS // 2
        return f"{value[:half]}\n...[{len(value) - JEV_MOTIVATING_CASE_EVENT_RENDER_CHARS} chars omitted]...\n{value[-half:]}"


class RunEventLedger:
    """Ordered, read-only lookup over the events of one finish attempt."""

    def __init__(self, events: Sequence[RunEvent]) -> None:
        # Freezes the event order and indexes events by their public id.
        self._events = tuple(events)
        self._by_id = {event.event_id: event for event in self._events}

    @classmethod
    def from_contexts(cls, contexts: Sequence[ToolCallContext], permission_for: Callable[[str], ToolPermission | None]) -> RunEventLedger:
        # Converts recorded tool calls into events, skipping runtime-internal tools.
        # @intent ledger-from-raw-tool-records
        # ToolCallContext keeps the raw ToolResult, so evidence reflects what ran rather than the truncated view the model saw.
        events: list[RunEvent] = []
        for context in contexts:
            if context.metadata.get("internal"):
                continue
            number = len(events) + 1
            events.append(
                RunEvent(
                    event_id=f"e{number}",
                    index=number,
                    tool_name=context.tool_name,
                    permission=permission_for(context.tool_name),
                    state=context.state,
                    arguments=dict(context.arguments),
                    output=context.output or "",
                    intent=_activity_intent(context),
                )
            )
        return cls(events)

    def events(self) -> tuple[RunEvent, ...]:
        # Returns every event in run order.
        return self._events

    def get(self, event_id: str | None) -> RunEvent | None:
        # Resolves a handoff ref, returning None for blank or unknown ids.
        if not event_id:
            return None
        return self._by_id.get(event_id.strip())

    def has_write_after(self, index: int) -> bool:
        # True when a successful write happened after the given event, which makes an earlier run stale.
        # @intent any-later-write-is-stale
        # Target files are unknown to code, so every later successful write invalidates a run; a false stale costs one re-run.
        return any(event.index > index and event.permission is ToolPermission.WRITE and event.succeeded() for event in self._events)

    def first_literal_match(self, literals: Sequence[str]) -> tuple[RunEvent, str] | None:
        # Finds the first successful write or execute event containing one of the user's exact values.
        # @intent literal-recovery-needs-write-or-execute
        # Only writes and executions can construct an input; a read that merely contains the literal is not a setup.
        for event in self._events:
            if event.permission not in (ToolPermission.WRITE, ToolPermission.EXECUTE) or not event.succeeded():
                continue
            text = event.searchable_text()
            for literal in literals:
                if literal and literal in text:
                    return event, literal
        return None

    def render(self) -> str:
        # Serializes the bounded event list for the handoff builder prompt.
        return json.dumps([event.render() for event in self._events], ensure_ascii=False, indent=1, default=str)

    @staticmethod
    def quote_is_verbatim(event: RunEvent, quote: str) -> bool:
        # Checks that a handoff quote really appears in the event's full arguments or output.
        return VerbatimText.contains(event.searchable_text(), quote)


def _strings_in(value: object) -> list[str]:
    # Collects every string inside a JSON-like value, depth first.
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _strings_in(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings_in(item)]
    return []


def _activity_intent(context: ToolCallContext) -> str | None:
    # Reads the agent's declared intent from a tool-call activity annotation when one was captured.
    # Activity models are caller-defined, so a conventional text key wins and anything else is rendered whole.
    if context.activity is None or not context.activity.payload:
        return None
    for key in ("intent", "summary", "description"):
        value = context.activity.payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return json.dumps(dict(context.activity.payload), ensure_ascii=False, default=str)


__all__ = ["PATH_ARGUMENT_KEYS", "RunEvent", "RunEventLedger"]
