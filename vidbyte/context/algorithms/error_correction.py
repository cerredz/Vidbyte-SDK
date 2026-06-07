"""Context Protocol Header

Description:
    Implements the public Error Correction context-window algorithm.
Purpose:
    Every N iterations, runs an error-correction agent pass that audits the
    context against the original system prompt, prunes its own stale managed
    primitives, and upserts one authoritative correction notice.
Architecture:
    - ErrorCorrectionAlgorithm: Frozen config and inner-loop lifecycle.
Key Functions:
    - after_tool_calls: Coordinates the audit cadence, removals, and notice.
    - run_audit: Invokes the runner and parses the audit JSON result.
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

from vidbyte.context.primitives import ErrorCorrectionContextItem
from vidbyte.context.runtime import ContextWindowPlacement, ContextWindowRunContext, InnerContextWindowAlgorithm
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts.catalog import Prompts

_MAX_NOTICE_CHARS_LIMIT = 100_000
_MAX_FIELD_CHARS_LIMIT = 25_000
_NOTICE_ID = "error_correction:notice"
_STATE_KEY = "_error_correction_state"


@dataclass(frozen=True, slots=True)
class ErrorCorrectionAlgorithm(InnerContextWindowAlgorithm):
    """Inner-loop error-correction algorithm config."""

    interval: int = 4
    max_passes: int = 8
    max_notice_chars: int = 2000
    max_field_chars: int = 600
    max_corrections: int = 12
    include_tool_outputs: bool = True
    removable_prefixes: tuple[str, ...] = ("error_correction:", "problem_space_search:")
    notice_title: str = "Correction Notice"
    auditor_prompt: str | None = None
    placement: ContextWindowPlacement = ContextWindowPlacement.TOP_OF_CONTEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates public config values before runtime execution starts.
        _validate_positive("interval", self.interval)
        _validate_positive("max_passes", self.max_passes)
        _validate_positive("max_corrections", self.max_corrections)
        _validate_limit("max_notice_chars", self.max_notice_chars, _MAX_NOTICE_CHARS_LIMIT)
        _validate_limit("max_field_chars", self.max_field_chars, _MAX_FIELD_CHARS_LIMIT)
        _validate_non_empty("notice_title", self.notice_title)
        _validate_optional_override("auditor_prompt", self.auditor_prompt)
        _validate_prefixes(self.removable_prefixes)
        _validate_metadata_keys(self.metadata)
        object.__setattr__(self, "placement", ContextWindowPlacement(self.placement))
        object.__setattr__(self, "removable_prefixes", tuple(self.removable_prefixes))

    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        # Single inner-loop hook: initializes on the first call, then audits per cadence.
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
        ctx.record("error_correction_iteration", iteration=snapshot.iteration_count)
        passes = state["passes"]
        if self.should_audit(snapshot.iteration_count, len(passes)):
            await self._run_correction_pass(ctx, snapshot, state, pass_index=len(passes) + 1)
        self._publish_metadata(ctx, state)

    async def _run_correction_pass(self, ctx: ContextWindowRunContext, snapshot: AgentIterationSnapshot, state: dict[str, Any], pass_index: int) -> None:
        # Runs one audit, applies removals, and upserts the correction notice.
        parsed = await self.run_audit(ctx, snapshot)
        corrections = self._format_corrections(parsed.get("corrections"))
        summary = _truncate(str(parsed.get("summary") or ""), self.max_field_chars)
        removed, skipped = self.apply_removals(ctx, parsed.get("stale_primitive_ids") or ())
        if corrections or removed:
            item = self.build_notice(snapshot, corrections, summary, pass_index)
            ctx.context_manager.upsert(item, placement=self.placement)
        state["removed"].extend(removed)
        passes = state["passes"]
        passes.append({"pass_index": pass_index, "iteration": snapshot.iteration_count, "correction_count": len(corrections), "removed": tuple(removed), "skipped": tuple(skipped)})
        ctx.record("error_correction_pass", iteration=snapshot.iteration_count, pass_index=pass_index)

    def should_audit(self, iteration_count: int, pass_count: int) -> bool:
        # Returns whether this completed iteration should run an audit pass.
        if pass_count >= self.max_passes:
            return False
        return iteration_count > 0 and iteration_count % self.interval == 0

    async def run_audit(self, ctx: ContextWindowRunContext, snapshot: AgentIterationSnapshot) -> dict[str, Any]:
        # Calls the error-correction agent and parses the audit JSON result.
        try:
            system_prompt = self.auditor_prompt or Prompts().get(Prompt.ERROR_CORRECTION_AUDITOR)
            history_str = self._format_history(ctx.messages)
            managed_str = self._format_managed_primitives(ctx)
            user_message = f"Main Agent System Prompt:\n{ctx.system_prompt or ''}\n\nManaged Context Primitives:\n{managed_str}\n\nMain Agent Conversation History:\n{history_str}"
            if not ctx.runner or not ctx.invoke_runner or not ctx.runner_output_text:
                raise ValueError("Context lacks runner or invoke_runner callable.")
            combined_prompt = f"{system_prompt}\n\n{user_message}"
            response = await ctx.invoke_runner(ctx.runner, combined_prompt, **dict(ctx.options or {}))
            response_text = ctx.runner_output_text(response)
            return self._parse_json_response(response_text)
        except Exception as exc:
            ctx.record("error_correction_failure", error=str(exc))
            raise exc

    def apply_removals(self, ctx: ContextWindowRunContext, stale_ids: Sequence[Any]) -> tuple[list[str], list[str]]:
        # Removes allow-listed managed primitives; returns (removed, skipped) id lists.
        removed: list[str] = []
        skipped: list[str] = []
        for raw_id in stale_ids:
            primitive_id = str(raw_id)
            if primitive_id == _NOTICE_ID:
                skipped.append(primitive_id)
            elif self._is_removable(primitive_id):
                ctx.remove(primitive_id)
                removed.append(primitive_id)
            else:
                skipped.append(primitive_id)
        return removed, skipped

    def build_notice(self, snapshot: AgentIterationSnapshot, corrections: tuple[str, ...], summary: str, pass_index: int) -> ErrorCorrectionContextItem:
        # Builds the single authoritative correction notice for this pass.
        return ErrorCorrectionContextItem(
            primitive_id=_NOTICE_ID,
            iteration=snapshot.iteration_count,
            pass_index=pass_index,
            corrections=corrections,
            summary=summary,
            title=self.notice_title,
            max_chars=self.max_notice_chars,
            metadata={
                "iteration": snapshot.iteration_count,
                "pass_index": pass_index,
                "correction_count": len(corrections),
                **dict(self.metadata),
            },
        )

    def _is_removable(self, primitive_id: str) -> bool:
        # Returns whether a primitive id matches an allow-listed removable prefix.
        return any(primitive_id.startswith(prefix) for prefix in self.removable_prefixes)

    def _publish_metadata(self, ctx: ContextWindowRunContext, state: dict[str, Any]) -> None:
        # Publishes compact error-correction metadata for the final AgentResult.
        ctx.set_metadata(
            "error_correction",
            {
                "interval": self.interval,
                "pass_count": len(state["passes"]),
                "removed_count": len(state["removed"]),
                "placement": self.placement.value,
                "passes": tuple(state["passes"]),
            },
        )

    def _format_corrections(self, value: Any) -> tuple[str, ...]:
        # Normalizes parsed corrections into a bounded tuple of strings.
        if not value:
            return ()
        entries = value if isinstance(value, (list, tuple)) else [value]
        corrections: list[str] = []
        for entry in entries[: self.max_corrections]:
            if isinstance(entry, Mapping):
                claim = str(entry.get("claim") or "").strip()
                why = str(entry.get("why_wrong") or "").strip()
                text = f"{claim} — {why}" if claim and why else (claim or why)
            else:
                text = str(entry)
            corrections.append(_truncate(text, self.max_field_chars))
        return tuple(corrections)

    def _format_managed_primitives(self, ctx: ContextWindowRunContext) -> str:
        # Lists currently-managed primitive ids and titles so the auditor can name stale ids.
        lines = []
        for item in ctx.context_manager.items():
            primitive_id = getattr(item, "primitive_id", None)
            if not primitive_id or not self._is_removable(str(primitive_id)):
                continue
            title = getattr(item, "title", "")
            lines.append(f"- {primitive_id} ({title})")
        return "\n".join(lines) if lines else "None."

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
        # Returns the mutable per-run error-correction state.
        return ctx.state.setdefault(_STATE_KEY, {"seen_iterations": set(), "passes": [], "removed": []})


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


def _validate_prefixes(prefixes: Sequence[str]) -> None:
    # Raises ConfigurationError if the removable-prefix allow-list is empty or malformed.
    if not prefixes:
        raise ConfigurationError("removable_prefixes must contain at least one prefix.")
    for prefix in prefixes:
        if not isinstance(prefix, str) or not prefix.strip():
            raise ConfigurationError("removable_prefixes must be non-empty strings.")


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
    "ErrorCorrectionAlgorithm",
]
