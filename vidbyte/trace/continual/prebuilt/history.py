"""Context Protocol Header

Description:
    Defines the history-oriented continual trace schema (lossless-log lens).
Purpose:
    Gives developers a ready-made typed schema for an exhaustive chronological
    record of everything the agent has done across the run.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class HistoryTraceModel(BaseModel):
    """History-oriented continual trace: an exhaustive chronological record of the run."""

    goal: str = Field(
        description=(
            "The run's objective, recorded once for orientation. Capture what the agent set out to do so a "
            "reader of the history knows what it was for. Keep this stable across updates."
        ),
    )
    timeline: list[str] = Field(
        default_factory=list,
        description=(
            "The core field: a terse, ordered, one-line-per-event record of everything meaningful that "
            "happened, in sequence. Append every new event; never prune or compress earlier entries, since "
            "this field is meant to be a near-lossless log a successor can replay."
        ),
    )
    iteration_log: list[str] = Field(
        default_factory=list,
        description=(
            "A short summary for each completed agent iteration. Append one entry per iteration capturing "
            "what that iteration accomplished; do not rewrite earlier entries."
        ),
    )
    model_turns: list[str] = Field(
        default_factory=list,
        description=(
            "A brief record of each assistant/model turn (what it said or decided). Append one entry per "
            "turn so the model's contributions are individually visible."
        ),
    )
    tool_invocations: list[str] = Field(
        default_factory=list,
        description=(
            "Each tool call the agent made, with the tool name and a summary of arguments. Append one entry "
            "per invocation in the order they occurred."
        ),
    )
    tool_results: list[str] = Field(
        default_factory=list,
        description=(
            "The result or outcome returned by each tool call. Append one entry per result, paired loosely "
            "with the corresponding invocation."
        ),
    )
    user_messages: list[str] = Field(
        default_factory=list,
        description=(
            "Messages or inputs received from the user or caller during the run. Append each message "
            "verbatim or closely summarized in order."
        ),
    )
    system_events: list[str] = Field(
        default_factory=list,
        description=(
            "Lifecycle and middleware events observed (run start, compaction, policy checks, run end). "
            "Append each system-level event as it occurs."
        ),
    )
    state_changes: list[str] = Field(
        default_factory=list,
        description=(
            "Notable changes to the agent's or environment's state. Append each change so transitions are "
            "individually recorded."
        ),
    )
    errors: list[str] = Field(
        default_factory=list,
        description=(
            "Every error or failure encountered, recorded verbatim enough to diagnose. Append each error in "
            "order; never drop one, since errors are critical to a faithful history."
        ),
    )
    retries: list[str] = Field(
        default_factory=list,
        description=(
            "Each retry attempt after a failure, noting what was retried. Append one entry per retry."
        ),
    )
    decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Decisions made during the run, recorded chronologically. Append each decision as it is made."
        ),
    )
    files_touched: list[str] = Field(
        default_factory=list,
        description=(
            "Files the agent read, created, modified, or deleted, with the action. Append each file event "
            "in order."
        ),
    )
    external_calls: list[str] = Field(
        default_factory=list,
        description=(
            "Calls to external services, APIs, or networks. Append each external interaction so the run's "
            "outward footprint is fully logged."
        ),
    )
    inputs: list[str] = Field(
        default_factory=list,
        description=(
            "Inputs, parameters, or data the agent consumed. Append each distinct input in the order it was "
            "received or fetched."
        ),
    )
    outputs: list[str] = Field(
        default_factory=list,
        description=(
            "Outputs the agent emitted at any point. Append each output as it is produced."
        ),
    )
    checkpoints: list[str] = Field(
        default_factory=list,
        description=(
            "Notable points the run could be resumed from, with enough context to continue. Append each "
            "checkpoint as it is reached."
        ),
    )
    token_usage_log: list[str] = Field(
        default_factory=list,
        description=(
            "Observed token-usage snapshots over the run when visible in the runtime metadata. Append each "
            "reading so cost growth is traceable; do not overwrite earlier readings."
        ),
    )
    notable_quotes: list[str] = Field(
        default_factory=list,
        description=(
            "Short verbatim snippets worth preserving exactly (key model statements, important tool output). "
            "Append each quote; keep them exact rather than paraphrasing."
        ),
    )
    environment_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Observations about the environment the run depends on (OS, services, credentials, sessions). "
            "Append each note as it becomes relevant."
        ),
    )
    current_event: str = Field(
        default="",
        description=(
            "The single most recent event as of this update. Overwrite each update to point at the latest "
            "thing that happened."
        ),
    )
    last_known_state: str = Field(
        default="",
        description=(
            "A snapshot of where everything stands as of the latest event. Overwrite with the most-current "
            "overall state of the run."
        ),
    )
    event_count: int = Field(
        default=0,
        description=(
            "The approximate running count of recorded timeline events. Overwrite with the latest total so "
            "the history's size is visible at a glance."
        ),
    )


HistoryTrace = TraceSchema.from_model(
    HistoryTraceModel,
    name="history_trace",
    description="An exhaustive chronological record of everything the agent has done.",
)

__all__ = [
    "HistoryTrace",
    "HistoryTraceModel",
]
