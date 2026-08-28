"""Context Protocol Header

Description:
    Implements the public Problem-Space Search context-window algorithm.
Purpose:
    Every N iterations, runs an explorer model pass that surfaces angles the
    agent has not yet considered and injects them as a bounded context primitive.
Architecture:
    - ProblemSpaceSearchAlgorithm: Frozen config and inner-loop lifecycle.
Key Functions:
    - after_tool_calls: Coordinates the explorer cadence and note injection.
    - build_item: Invokes the runner, parses JSON, and builds the context item.
Relations:
    Used by ContextWindow presets and the AgentRuntime inner-loop dispatch.
Similar Files:
    - `vidbyte/context/algorithms/trajectory_checkpoints.py`
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives import ProblemSpaceSearchContextItem
from vidbyte.context.runtime import (
    ContextWindowPlacement,
    ContextWindowRunContext,
    InnerContextWindowAlgorithm,
)
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts.catalog import Prompts

_MAX_NOTE_CHARS_LIMIT = 100_000
_MAX_FIELD_CHARS_LIMIT = 25_000
_STATE_KEY = "_problem_space_search_state"


@dataclass(frozen=True, slots=True)
class ProblemSpaceSearchAlgorithm(InnerContextWindowAlgorithm):
    """Inner-loop problem-space search algorithm config."""

    interval: int = 5
    max_notes: int = 6
    max_note_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = False
    note_title: str = "Problem-Space Search"
    explorer_prompt: str | None = None
    placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates public config values before runtime execution starts.
        _validate_positive("interval", self.interval)
        _validate_positive("max_notes", self.max_notes)
        _validate_limit("max_note_chars", self.max_note_chars, _MAX_NOTE_CHARS_LIMIT)
        _validate_limit("max_field_chars", self.max_field_chars, _MAX_FIELD_CHARS_LIMIT)
        _validate_non_empty("note_title", self.note_title)
        _validate_optional_override("explorer_prompt", self.explorer_prompt)
        _validate_metadata_keys(self.metadata)
        object.__setattr__(self, "placement", ContextWindowPlacement(self.placement))

    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        # Single inner-loop hook: initializes on the first call, then explores per cadence.
        state = self._state(ctx)
        snapshot = ctx.iteration
        if snapshot is None:
            ctx.record("system_prompt")
            self._publish_metadata(ctx, state)
            return
        seen = state["seen_iterations"]
        if snapshot.iteration_count in seen:
            return
        seen.add(snapshot.iteration_count)
        ctx.record("problem_space_search_iteration", iteration=snapshot.iteration_count)
        notes = state["notes"]
        if self.should_explore(snapshot.iteration_count, len(notes)):
            item = await self.build_item(ctx, snapshot, note_index=len(notes) + 1)
            self._place_note(ctx, item)
            notes.append(self._note_record(item))
            ctx.record("problem_space_search_injection", iteration=item.iteration, note_index=item.note_index)
        self._publish_metadata(ctx, state)

    def should_explore(self, iteration_count: int, note_count: int) -> bool:
        # Returns whether this completed iteration should run an explorer pass.
        if note_count >= self.max_notes:
            return False
        return iteration_count > 0 and iteration_count % self.interval == 0

    async def build_item(self, ctx: ContextWindowRunContext, snapshot: AgentIterationSnapshot, note_index: int) -> ProblemSpaceSearchContextItem:
        # Calls the explorer model to surface unconsidered angles from current history.
        try:
            system_prompt = self.explorer_prompt or Prompts().get(Prompt.PROBLEM_SPACE_SEARCH_EXPLORER)
            history_str = self._format_history(ctx.messages)
            user_message = f"Main Agent System Prompt:\n{ctx.system_prompt or ''}\n\nMain Agent Conversation History:\n{history_str}"
            if not ctx.runner or not ctx.invoke_runner or not ctx.runner_output_text:
                raise ValueError("Context lacks runner or invoke_runner callable.")
            combined_prompt = f"{system_prompt}\n\n{user_message}"
            response = await ctx.invoke_runner(ctx.runner, combined_prompt, **dict(ctx.options or {}))
            response_text = ctx.runner_output_text(response)
            parsed = self._parse_json_response(response_text)
            return ProblemSpaceSearchContextItem(
                primitive_id=f"problem_space_search:{note_index}",
                iteration=snapshot.iteration_count,
                note_index=note_index,
                unconsidered=self._format_field(parsed.get("unconsidered")),
                blind_spots=self._format_field(parsed.get("blind_spots")),
                next_directions=self._format_field(parsed.get("next_directions")),
                title=self.note_title,
                max_chars=self.max_note_chars,
                metadata={
                    "iteration": snapshot.iteration_count,
                    "note_index": note_index,
                    "tool_call_count": len(snapshot.tool_calls),
                    "tokens_used": snapshot.tokens_used,
                    **dict(self.metadata),
                },
            )
        except Exception as exc:
            ctx.record("problem_space_search_failure", error=str(exc))
            raise exc

    def _place_note(self, ctx: ContextWindowRunContext, item: ProblemSpaceSearchContextItem) -> None:
        # Writes the note through the configured placement using semantic manager methods.
        if self.placement is ContextWindowPlacement.TOP_OF_CONTEXT:
            ctx.place_after_system_prompt(item)
        elif self.placement is ContextWindowPlacement.END_OF_CONTEXT:
            ctx.place_after_tools(item)
        else:
            ctx.context_manager.upsert(item, placement=self.placement)

    def _publish_metadata(self, ctx: ContextWindowRunContext, state: dict[str, Any]) -> None:
        # Publishes compact problem-space search metadata for the final AgentResult.
        ctx.set_metadata(
            "problem_space_search",
            {
                "interval": self.interval,
                "note_count": len(state["notes"]),
                "placement": self.placement.value,
                "notes": tuple(state["notes"]),
            },
        )

    def _format_field(self, value: Any) -> str:
        # Normalizes a parsed JSON field (string or list) into bounded text.
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            text = "\n".join(f"- {str(entry)}" for entry in value)
        else:
            text = str(value)
        return _truncate(text, self.max_field_chars)

    def _format_history(self, messages: Sequence[dict[str, Any]] | None) -> str:
        # Stringifies the main agent's conversation history messages.
        if not messages:
            return "No history."
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content")
            if role == "tool":
                text = _truncate(str(content or ""), self.max_field_chars) if self.include_tool_outputs else "[Tool output omitted]"
            elif isinstance(content, list):
                text = self._format_content_parts(content)
            else:
                text = str(content or "")
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                text += f" [Tool Calls: {tool_calls}]"
            name = msg.get("name")
            name_suffix = f" ({name})" if name else ""
            lines.append(f"{role.capitalize()}{name_suffix}: {text}")
        return "\n".join(lines)

    def _format_content_parts(self, content: list[Any]) -> str:
        # Renders a structured content list into a single bounded string.
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "tool_result":
                    if self.include_tool_outputs:
                        parts.append(_truncate(str(part.get("content") or part.get("output") or ""), self.max_field_chars))
                    else:
                        parts.append("[Tool output omitted]")
                else:
                    parts.append(part.get("text", ""))
            else:
                parts.append(str(part))
        return " ".join(parts)

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        # Robustly extracts and parses a JSON object from a model response.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]
        return json.loads(cleaned)

    def _state(self, ctx: ContextWindowRunContext) -> dict[str, Any]:
        # Returns the mutable per-run problem-space search state.
        return ctx.state.setdefault(_STATE_KEY, {"seen_iterations": set(), "notes": []})

    @staticmethod
    def _note_record(item: ProblemSpaceSearchContextItem) -> dict[str, Any]:
        # Converts one note item into compact final-result metadata.
        return {
            "primitive_id": item.primitive_id,
            "iteration": item.iteration,
            "note_index": item.note_index,
            "metadata": dict(item.metadata),
        }


def _validate_positive(field_name: str, value: int) -> None:
    # Raises ConfigurationError if a numeric field is not positive.
    if value <= 0:
        raise ConfigurationError(f"{field_name} must be greater than zero.")


def _validate_limit(field_name: str, value: int, limit: int) -> None:
    # Raises ConfigurationError if a character limit is outside bounds.
    _validate_positive(field_name, value)
    if value > limit:
        raise ConfigurationError(f"{field_name} exceeds limit of {limit}.")


def _validate_non_empty(field_name: str, value: str) -> None:
    # Raises ConfigurationError if a public string field is blank.
    if not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string.")


def _validate_optional_override(field_name: str, value: str | None) -> None:
    # Raises ConfigurationError if a provided prompt override is blank.
    if value is not None and not value.strip():
        raise ConfigurationError(f"{field_name} override must not be empty or whitespace.")


def _validate_metadata_keys(metadata: Mapping[str, Any]) -> None:
    # Raises ConfigurationError if metadata contains non-string keys.
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found: {type(key).__name__}.")


def _truncate(value: str, max_chars: int) -> str:
    # Returns a string bounded by max_chars including the truncation suffix.
    suffix = "\n...[truncated]"
    if len(value) <= max_chars:
        return value
    if max_chars <= len(suffix):
        return value[:max_chars]
    return value[: max_chars - len(suffix)].rstrip() + suffix


__all__ = [
    "ProblemSpaceSearchAlgorithm",
]
