"""Context Protocol Header

Description:
    Defines the tool-oriented continual trace schema (tool-call lens).
Purpose:
    Gives developers a ready-made typed schema for a ledger of an agent's tool
    calls, their results, errors, and the external state they established.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class ToolTraceModel(BaseModel):
    """Tool-oriented continual trace: a ledger of tool calls, results, and side effects."""

    goal: str = Field(
        description=(
            "The objective the tool usage serves, for orientation. Capture what the agent is using its "
            "tools to accomplish. Keep this stable unless the context redefines it."
        ),
    )
    available_tools: list[str] = Field(
        default_factory=list,
        description=(
            "The tools the agent has access to in this run. Append each tool name as it becomes visible; "
            "do not duplicate names already present."
        ),
    )
    calls: list[str] = Field(
        default_factory=list,
        description=(
            "Each tool call the agent made, as 'toolName: summarized args'. Append one entry per call in "
            "the order they occurred; this is the running call log."
        ),
    )
    successful_calls: list[str] = Field(
        default_factory=list,
        description=(
            "Calls that completed successfully. Append each successful call so success and failure are easy "
            "to separate."
        ),
    )
    failed_calls: list[str] = Field(
        default_factory=list,
        description=(
            "Calls that failed, with the tool name and a short reason. Append each failed call; this is "
            "high-value for avoiding repeated failing calls."
        ),
    )
    call_results: list[str] = Field(
        default_factory=list,
        description=(
            "The result or output of each call, summarized. Append one entry per result, paired loosely "
            "with the corresponding call."
        ),
    )
    errors: list[str] = Field(
        default_factory=list,
        description=(
            "Errors returned by tools, recorded verbatim enough to diagnose. Append each error as it occurs."
        ),
    )
    retries: list[str] = Field(
        default_factory=list,
        description=(
            "Retried tool calls after a failure, noting what changed on retry. Append one entry per retry."
        ),
    )
    arguments_used: list[str] = Field(
        default_factory=list,
        description=(
            "Notable argument values or patterns passed to tools, especially ones that worked. Append each "
            "so a successor can reuse known-good arguments."
        ),
    )
    side_effects: list[str] = Field(
        default_factory=list,
        description=(
            "External effects the calls produced (records created, messages sent, state mutated). Append "
            "each side effect so the run's external impact is auditable."
        ),
    )
    files_created: list[str] = Field(
        default_factory=list,
        description=(
            "Files created via tool calls. Append each created file path as it appears."
        ),
    )
    files_modified: list[str] = Field(
        default_factory=list,
        description=(
            "Files modified via tool calls. Append each modified file path; a file may appear more than "
            "once across the run if edited repeatedly."
        ),
    )
    files_deleted: list[str] = Field(
        default_factory=list,
        description=(
            "Files deleted via tool calls. Append each deleted file path as it appears."
        ),
    )
    api_calls: list[str] = Field(
        default_factory=list,
        description=(
            "Outbound API or network calls made through tools, with endpoint and outcome. Append each call "
            "in order."
        ),
    )
    tool_sequence: list[str] = Field(
        default_factory=list,
        description=(
            "The ordered sequence of tool names invoked, capturing the workflow shape. Append each tool "
            "name in call order, including repeats, so the pattern of usage is visible."
        ),
    )
    most_used_tools: list[str] = Field(
        default_factory=list,
        description=(
            "Tools used most frequently, optionally with a count. Overwrite-style entries are fine; append "
            "new heavy-use tools as the picture changes."
        ),
    )
    unused_tools: list[str] = Field(
        default_factory=list,
        description=(
            "Available tools the agent has not used. Append tools that remain unused; this can reveal "
            "missed capabilities."
        ),
    )
    permission_denials: list[str] = Field(
        default_factory=list,
        description=(
            "Tool calls blocked by permission or policy, with the reason. Append each denial so blocked "
            "capabilities are visible to a successor."
        ),
    )
    pending_calls: list[str] = Field(
        default_factory=list,
        description=(
            "Tool calls issued but not yet resolved (awaiting results). Append each pending call; resolution "
            "is reflected in call_results rather than by deleting here."
        ),
    )
    tool_state: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "A map of durable external state established by tool calls (for example a session id, an open "
            "handle, or a created resource id). Provide only the keys that changed; entries are deep-merged "
            "into the existing map rather than replacing it wholesale."
        ),
    )
    current_tool: str = Field(
        default="",
        description=(
            "The tool the agent is using right now, if any. Overwrite with the single most-current tool in "
            "use."
        ),
    )
    next_tool_action: str = Field(
        default="",
        description=(
            "The next tool call the agent appears about to make and why. Overwrite with the most-current "
            "intended next tool action."
        ),
    )
    tool_call_count: int = Field(
        default=0,
        description=(
            "The running total of tool calls made. Overwrite with the latest count so call volume is "
            "visible at a glance."
        ),
    )
    error_count: int = Field(
        default=0,
        description=(
            "The running total of tool-call errors. Overwrite with the latest count."
        ),
    )


ToolTrace = TraceSchema.from_model(
    ToolTraceModel,
    name="tool_trace",
    description="A ledger of the agent's tool calls, results, errors, and side effects.",
)

__all__ = [
    "ToolTrace",
    "ToolTraceModel",
]
