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
        title="Goal",
        min_length=1,
        description=(
            "The objective the tool usage serves, recorded to orient a reader of the tool trace who needs to understand why the agent was making the calls it made. "
            "Write this as a clear statement of what the agent is using its tools to accomplish, precise enough that a reviewer can judge whether each tool call was appropriate and purposeful. "
            "Keep this field stable unless the context redefines the objective, since the goal is the reference point against which the appropriateness of all tool calls is measured. "
            "A successor reading this field can immediately understand the purpose of the tool interaction log and filter for the calls that are most relevant to resuming the work. "
            "If the goal narrows or shifts during execution, record the most current formulation rather than the original one, since the agent's tool usage is organized around what it currently understands as the target."
        ),
    )
    available_tools: list[str] = Field(
        title="Available Tools",
        min_length=0,
        default_factory=list,
        description=(
            "The tools the agent has access to in this run, recorded as a definitive reference for what capabilities were in scope during execution. "
            "Append each tool name as it becomes visible in the context and do not duplicate names already present, since this is a set of distinct capabilities rather than a usage log. "
            "Include all tools the agent could have used, not just the ones it did use, since the unused_tools field uses this list as its reference to identify gaps in utilization. "
            "This field allows a reviewer to assess whether the agent had the right capabilities available for the task and whether it made effective use of what was offered. "
            "If the set of available tools changes mid-run due to a permission change or a new tool being registered, append the new entries with a note of when they became available."
        ),
    )
    calls: list[str] = Field(
        title="Tool Calls",
        min_length=0,
        default_factory=list,
        description=(
            "Each tool call the agent made, recorded as a brief entry in the format toolName: summarized args so a reader can see the full call sequence at a glance. "
            "Append one entry per call in the order the calls occurred, including repeat calls to the same tool with different arguments, so the running call log is complete and chronological. "
            "Summarize the arguments concisely rather than reproducing large payloads verbatim, capturing enough detail that a reader understands what the tool was asked to do without being overwhelmed. "
            "This field is the primary call-sequence log of the tool trace: a reviewer can read it to understand what the agent asked of its tools in order, without cross-referencing other fields. "
            "If a call was made as a retry after a failure, note that in the same entry so the reader can distinguish first attempts from retries without consulting the retries field."
        ),
    )
    successful_calls: list[str] = Field(
        title="Successful Calls",
        min_length=0,
        default_factory=list,
        description=(
            "Calls that completed successfully, each recorded using the same brief format as the calls field so a reader can cross-reference between the two fields by matching entries. "
            "Append each successful call as its success is confirmed, so success and failure are easy to separate without scanning the full call log. "
            "Include a brief note of what the successful result was when that information is informative, since a success with a useful result is different from a success with a trivial one. "
            "This field allows a reviewer to quickly see which tool interactions produced value and build confidence in the parts of the run that worked correctly. "
            "If a call is initially thought to be successful but later found to have produced incorrect results, move it from this field to failed_calls by adding a new entry there rather than modifying this field."
        ),
    )
    failed_calls: list[str] = Field(
        title="Failed Calls",
        min_length=0,
        default_factory=list,
        description=(
            "Calls that failed, each recorded with the tool name and a short reason for the failure so a reader can understand what went wrong without needing to inspect the errors field. "
            "Append each failed call as the failure is confirmed, so that failed and successful calls are easy to separate for a reviewer assessing the agent's tool reliability. "
            "This field has high value for preventing repeated failure: a successor inheriting a run can immediately see which calls have already failed and avoid retrying them with the same arguments. "
            "Include the failure cause at a level of detail sufficient to distinguish a transient error from a permanent one, since the appropriate response differs dramatically between the two. "
            "If the agent recovered from a failure, note the recovery approach in the same entry or in retries so the full failure-recovery cycle is visible without cross-referencing multiple fields."
        ),
    )
    call_results: list[str] = Field(
        title="Call Results",
        min_length=0,
        default_factory=list,
        description=(
            "The result or output of each tool call, summarized to capture the key information without reproducing large payloads verbatim, in the order results were received. "
            "Append one entry per result, paired loosely with the corresponding entry in calls by position, so a reader can match calls and results without losing the chronological structure. "
            "Each entry should identify whether the call succeeded or failed and summarize the most important content of the result, not a full transcript. "
            "Together with calls, this field forms a complete call-result ledger that allows a reviewer to assess whether the agent correctly interpreted tool outputs and acted appropriately on them. "
            "If a result was ambiguous or surprising, note that in the same entry so a reviewer knows the agent had to interpret the output rather than treating it as straightforwardly informative."
        ),
    )
    errors: list[str] = Field(
        title="Errors",
        min_length=0,
        default_factory=list,
        description=(
            "Errors returned by tools during the run, each recorded verbatim enough to diagnose the root cause without needing to re-run the agent or consult external logs. "
            "Append each error in the order it occurred and do not drop any, since even minor tool errors can be relevant for understanding the agent's behavior and the run's outcomes. "
            "Include the tool name, the error type or code, and the message, so a reviewer can identify what kind of failure occurred and which tool produced it. "
            "This field is critical for post-run diagnosis: a complete tool error log allows a reviewer to distinguish errors the agent recovered from, errors it ignored, and errors that caused it to stop. "
            "If the same error type recurred across multiple calls, note the pattern in the same way for each occurrence rather than summarizing, since frequency is itself diagnostic."
        ),
    )
    retries: list[str] = Field(
        title="Retries",
        min_length=0,
        default_factory=list,
        description=(
            "Retried tool calls after a failure, each recorded with the tool name, what changed on the retry, and whether the retry succeeded, in the order they occurred. "
            "Append one entry per retry, pairing it with the corresponding failed call in failed_calls when possible so the failure-retry chain is traceable. "
            "Including what changed on each retry is important: a retry with modified arguments demonstrates adaptive behavior, while an identical retry may indicate the agent was stuck in a loop. "
            "This field distinguishes resilient agents from fragile ones: a reviewer can see how quickly the agent detected and responded to failures and whether its retry strategy was effective. "
            "If a retry cascade produced many attempts, record each one rather than summarizing, since the pattern of retry behavior is often as diagnostic as the final outcome."
        ),
    )
    arguments_used: list[str] = Field(
        title="Arguments Used",
        min_length=0,
        default_factory=list,
        description=(
            "Notable argument values or patterns passed to tools, especially ones that produced successful results and would be worth reusing in a subsequent call or a successor run. "
            "Append each notable argument pattern as it is identified, noting which tool it was used with and why the argument was effective or worth preserving. "
            "This field is intentionally selective rather than exhaustive: include arguments that are non-obvious, discovered through iteration, or critical to success, not every argument passed to every call. "
            "A successor reading this field can benefit from the argument discovery work the original agent did, reusing known-good values rather than re-discovering them through trial and error. "
            "If an argument caused a failure when expected to succeed, note that here as well so the negative result is preserved alongside the positive ones."
        ),
    )
    side_effects: list[str] = Field(
        title="Side Effects",
        min_length=0,
        default_factory=list,
        description=(
            "External effects the tool calls produced beyond their return values, such as records created in a database, messages sent to external services, or shared state mutated. "
            "Append each side effect as it is produced, naming the external system affected and the nature of the change, so the run's external impact is fully auditable. "
            "This field is important for compliance and security reviews: a reviewer can see exactly what durable effects the agent produced outside the local environment without re-running the agent. "
            "Include side effects from both successful and failed calls, since a call can produce an external effect before failing and that effect may need to be rolled back or accounted for. "
            "If a side effect is reversible, note that explicitly so a successor or reviewer knows whether undoing the effect is an option when evaluating how to handle a problem."
        ),
    )
    files_created: list[str] = Field(
        title="Files Created",
        min_length=0,
        default_factory=list,
        description=(
            "Files newly created via tool calls during the run, each recorded with the full path so a reviewer can locate them without scanning the full call log. "
            "Append each created file as it appears, noting the tool that created it and, when relevant, what the file contains at a high level. "
            "A file created by the agent is a durable artifact that persists beyond the run, so recording it here ensures the output is not lost or overlooked in a review. "
            "This field is a subset of the artifact trace's files_created, specialized for the tool trace lens where the focus is on which tool calls produced which files. "
            "If a file is created and then immediately deleted or overwritten in the same run, note both events rather than treating them as canceling out, since the creation still occurred."
        ),
    )
    files_modified: list[str] = Field(
        title="Files Modified",
        min_length=0,
        default_factory=list,
        description=(
            "Files modified via tool calls during the run, each recorded with the full path so a reviewer can identify which files were changed without scanning the full call log. "
            "Append each modified file as the modification is confirmed, and it is correct for a path to appear more than once if it was edited at multiple points during the run. "
            "Note the nature of the modification when possible, such as whether content was appended, replaced, or selectively edited, so a reviewer can assess the scope of the change. "
            "This field gives a reviewer an immediate picture of the agent's write footprint on the file system, which is essential for auditing changes to shared or sensitive files. "
            "If a modification was part of a multi-step transformation, record each step separately rather than only the final state, so the full modification history is visible."
        ),
    )
    files_deleted: list[str] = Field(
        title="Files Deleted",
        min_length=0,
        default_factory=list,
        description=(
            "Files deleted via tool calls during the run, each recorded with the full path so a reviewer can identify what was removed without scanning the full call log. "
            "Append each deleted file as the deletion is confirmed and do not remove entries later, since deleted files are irreversible effects that must remain visible in the audit trail. "
            "Note whether the deletion was intentional and expected or whether it was a side effect of another operation, since the two cases have different implications for a reviewer. "
            "This field is particularly important for security and compliance audits: an unexpected file deletion is a high-severity event that a reviewer needs to be able to identify quickly. "
            "If the deleted file can be restored from a backup or version control, note that in the same entry so a reviewer or successor knows whether the deletion is recoverable."
        ),
    )
    api_calls: list[str] = Field(
        title="API Calls",
        min_length=0,
        default_factory=list,
        description=(
            "Outbound API or network calls made through tools during the run, each recorded with the endpoint or service name and a summary of the outcome. "
            "Append each call in the order it was made, noting whether it succeeded, failed, or produced a partial result, so the run's network interaction log is complete. "
            "Include enough detail about the request and response to distinguish a meaningful API interaction from a trivial one without reproducing full request or response payloads verbatim. "
            "This field is important for cost accounting, rate limit tracking, and compliance: a reviewer can see exactly which external APIs were called and how many times without inspecting raw logs. "
            "If an API call produced a side effect in the external system, note that in side_effects as well so the full impact of the call is visible across both fields."
        ),
    )
    tool_sequence: list[str] = Field(
        title="Tool Sequence",
        min_length=0,
        default_factory=list,
        description=(
            "The ordered sequence of tool names invoked during the run, capturing the workflow shape at a high level without the argument and result detail in the calls and call_results fields. "
            "Append each tool name in the order it was called, including repeats, so the complete pattern of tool usage is visible at a glance. "
            "This field allows a reviewer to identify patterns in tool usage, such as alternating read and write calls or a repeated retry loop, that would be harder to see in the full calls log. "
            "A successor reading this field can understand how the original agent sequenced its tool interactions and decide whether the same workflow applies to the remaining work. "
            "If the tool sequence reveals an anti-pattern such as many failed calls before a successful one, note that in the same sequence rather than cleaning it up, since the pattern itself is diagnostic."
        ),
    )
    most_used_tools: list[str] = Field(
        title="Most Used Tools",
        min_length=0,
        default_factory=list,
        description=(
            "Tools used most frequently during the run, each recorded with an optional count so a reviewer can quickly identify which capabilities the agent relied on most heavily. "
            "Update this field as the run progresses by appending or revising entries to reflect the evolving usage distribution, so it accurately represents the heaviest-used tools as of the latest snapshot. "
            "The intent of this field is to surface the agent's primary tool dependencies, not to provide a precise usage histogram, so approximate counts or ordinal rankings are acceptable. "
            "A reviewer reading this field can immediately see where the agent spent most of its tool interaction budget and assess whether that investment was appropriate for the task. "
            "If a tool that should have been heavily used is absent from this list, that gap may indicate a missed capability or an unexpected constraint that is worth investigating."
        ),
    )
    unused_tools: list[str] = Field(
        title="Unused Tools",
        min_length=0,
        default_factory=list,
        description=(
            "Available tools the agent did not use during the run, drawn from the available_tools list and identified as missing from the calls log. "
            "Append tools that remain unused as the run progresses so this field reflects which capabilities were in scope but not exercised. "
            "This field can reveal missed opportunities: a tool that the agent had access to but never called may represent a more efficient path that was overlooked. "
            "A successor reading this field can quickly identify capabilities that may be applicable to the remaining work and that the original agent did not take advantage of. "
            "If a tool was unused for a deliberate reason, note that in decisions or constraints rather than here, since this field tracks unused tools without judgment about whether the non-use was correct."
        ),
    )
    permission_denials: list[str] = Field(
        title="Permission Denials",
        min_length=0,
        default_factory=list,
        description=(
            "Tool calls blocked by permission or policy during the run, each recorded with the tool name and the reason for the denial so the agent's capability constraints are fully documented. "
            "Append each denial as it occurs and do not remove earlier entries, since the history of what was blocked is important for understanding why certain work was not completed. "
            "Include whether the denial was expected or unexpected, since an unexpected permission denial may indicate a misconfiguration that needs to be resolved before the run can complete. "
            "A successor reading this field knows immediately which capabilities were unavailable to the original agent and can either request the necessary permissions or adapt the approach to work within the constraints. "
            "If a denial caused the agent to take a significantly different approach, reference the corresponding entry in decisions so the causal connection between the denial and the strategy change is clear."
        ),
    )
    pending_calls: list[str] = Field(
        title="Pending Calls",
        min_length=0,
        default_factory=list,
        description=(
            "Tool calls that have been issued but whose results have not yet been received as of the latest update, each recorded with the tool name and a summary of the arguments. "
            "Append each pending call as it is issued and reflect its resolution in call_results rather than by deleting it here, so the history of outstanding calls is preserved. "
            "A pending call that remains unresolved at the end of a run is a potential blocker for a successor, which needs to know whether to wait for the result or re-issue the call. "
            "This field is particularly important for asynchronous runs where multiple tool calls may be in flight simultaneously: a reviewer needs to know the outstanding call state to understand the run's current position. "
            "If a pending call has a timeout or expiry, note that in time_sensitive_notes as well so the urgency is surfaced immediately to a reader who may not read this field in detail."
        ),
    )
    tool_state: dict[str, str] = Field(
        title="Tool State",
        default_factory=dict,
        description=(
            "A map of durable external state established by tool calls during the run, such as session identifiers, open file handles, created resource IDs, or active connections. "
            "Provide only the keys that changed in each update rather than the full state map, since entries are deep-merged into the existing map rather than replacing it wholesale. "
            "Each key should name the state variable specifically and each value should contain enough information to re-establish or verify the state without re-running the tool. "
            "This field is essential for handoffs involving stateful tools: a successor needs to know what state the original agent established before it can safely continue or avoid creating duplicate state. "
            "If a state entry becomes invalid or is cleaned up, update the corresponding value to reflect that so the map does not mislead a successor into trying to use stale state."
        ),
    )
    current_tool: str = Field(
        title="Current Tool",
        min_length=0,
        default="",
        description=(
            "The tool the agent is using right now, if any, identified by name so a reader can immediately understand the current operation without scanning the full call log. "
            "Overwrite this field with the single most-current tool in use on every update, so it always reflects the present moment rather than a past call. "
            "Leave this empty when no tool call is currently in progress, not while waiting for a result, so an empty value reliably signals that the agent is between tool calls. "
            "A successor reading this field can immediately see whether the agent was mid-call when the trace was last updated, which is important for deciding whether to wait for a result or start fresh. "
            "If the current tool call is the last one before a handoff checkpoint, note that in the same entry so a reader understands whether the call needs to complete before the handoff is valid."
        ),
    )
    next_tool_action: str = Field(
        title="Next Tool Action",
        min_length=0,
        default="",
        description=(
            "The next tool call the agent appears about to make, expressed as the tool name and a brief description of the intended arguments and purpose. "
            "Overwrite this field with the most-current intended next tool action on every update, so it always reflects the agent's current intention rather than a stale plan. "
            "Be specific enough that a successor could issue the same call without ambiguity, naming the tool, the key arguments, and the expected outcome. "
            "This field has its highest value during a mid-run handoff where it allows a successor to continue the tool interaction sequence without first re-deriving what call comes next from the call history. "
            "If the next tool action depends on an outstanding result from pending_calls, note that dependency in the same entry so the successor understands the precondition before acting."
        ),
    )
    tool_call_count: int = Field(
        title="Tool Call Count",
        default=0,
        description=(
            "The running total of tool calls made during the run, giving a quick sense of the agent's tool interaction volume without requiring a reader to count entries in the calls field. "
            "Overwrite this field with the latest count on every update, keeping it synchronized with the actual number of entries in the calls field. "
            "Use this count as a rough proxy for run complexity and cost: a very high call count relative to the number of completed goals may indicate inefficiency or an excessive retry loop. "
            "A reviewer seeing an unusually high tool call count relative to the run's output can use this signal to investigate whether the agent was using tools efficiently. "
            "If the count diverges from the length of the calls field due to summarization or compaction, provide the best available approximation with a note rather than leaving this at zero."
        ),
    )
    error_count: int = Field(
        title="Error Count",
        default=0,
        description=(
            "The running total of tool-call errors encountered during the run, giving a quick sense of the agent's error rate without requiring a reader to count entries in the errors field. "
            "Overwrite this field with the latest count on every update, keeping it synchronized with the actual number of entries in the errors field. "
            "An error count that is high relative to the tool_call_count signals a problematic run where many calls are failing, which is a triage signal for a reviewer deciding whether to intervene. "
            "A successor reading a high error count knows to read the errors and failed_calls fields carefully before attempting to continue the run, since the original agent may have been stuck in a failure loop. "
            "If the count diverges from the length of the errors field due to summarization or compaction, provide the best available approximation with a note rather than leaving this at zero."
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
