"""Shared long-form descriptions for session tools."""

from __future__ import annotations

SESSION_ID_DESCRIPTION = (
    "The session_id identifies one durable agent session stored in the bound SessionStore. "
    "It is the stable id returned by Session.id or by a fork/resume tool result. "
    "Use it when the tool should read, fork, or incorporate a session other than the current bound thread. "
    "The tool checks SessionScope before it uses the id. "
    "Omit it only on tools whose documentation says the current bound session is the default target. "
    "Unknown or out-of-scope ids return an error result instead of raising into the agent loop."
)

CHECKPOINT_ID_DESCRIPTION = (
    "The checkpoint_id identifies one persisted checkpoint in a durable session's DAG. "
    "It is the stable id returned by checkpoint creation, automatic per-turn persistence, fork operations, or resume operations. "
    "Use it when the tool should operate from a specific historical point instead of the session head. "
    "For own-thread rewind operations it must belong to the current bound session. "
    "For cross-thread operations it must be in a session allowed by the current SessionScope. "
    "Unknown, foreign, or inaccessible checkpoint ids return an error result."
)

LABEL_DESCRIPTION = (
    "The label is optional human-readable text saved on a new checkpoint. "
    "Use it to make later checkpoint history easier to inspect. "
    "It does not affect checkpoint ordering, lineage, or resume behavior. "
    "It should be short enough to fit comfortably in logs and session history views. "
    "Omit it when the checkpoint is purely mechanical. "
    "The label is persisted with the checkpoint payload and may be visible to later tools."
)

OPERATION_DESCRIPTION = (
    "The operation selects which combined session action to run. "
    "Use create_checkpoint to snapshot the current bound session. "
    "Use fork_current to branch the current bound session into a new session id. "
    "Use list_my_runs to list visible sessions in the current SessionScope. "
    "Use read_run to read the current trace artifact for an in-scope session. "
    "Unknown operations return an error result so the agent can recover."
)

CHECKPOINT_TOOL_DESCRIPTION = (
    "Write a checkpoint of a durable session. "
    "When session_id is omitted, the tool snapshots the current bound agent thread. "
    "When an in-scope session_id is supplied, the tool copies that session's head state into a new checkpoint on that session. "
    "The new checkpoint records parent lineage, sequence order, and the optional label. "
    "Use this before risky work when a later fork or rewind may be needed. "
    "The tool returns the new checkpoint id as a plain string."
)

FORK_TOOL_DESCRIPTION = (
    "Branch a new durable session from a checkpoint. "
    "With no arguments, the tool forks the current bound thread from its head checkpoint. "
    "With an in-scope session_id or checkpoint_id, it forks the selected stored state instead. "
    "The source session is not mutated by the fork. "
    "The new session records parent_session_id lineage for later audit. "
    "The tool returns the new session id as a plain string."
)

REWIND_TOOL_DESCRIPTION = (
    "Move the current bound session's head back to an earlier checkpoint. "
    "The next agent run will branch from that checkpoint instead of the previous head. "
    "This is own-thread time travel, not a cross-session import. "
    "The checkpoint must belong to the bound session. "
    "The stored checkpoint history remains intact after the rewind. "
    "The tool returns the new head checkpoint id as a plain string."
)

RESUME_APPEND_TOOL_DESCRIPTION = (
    "Resume another agent's thread by appending its checkpointed context to the current one. "
    "The current session history is preserved. "
    "The target history is framed as a resumed-thread block before being added. "
    "Use this when the agent needs background from another session without replacing its own work. "
    "The target session or checkpoint must be allowed by SessionScope. "
    "The tool returns the new head checkpoint id as a plain string."
)

RESUME_REPLACE_TOOL_DESCRIPTION = (
    "Resume a thread by replacing the current context window. "
    "With no session_id, this acts as own-thread rewind to the supplied checkpoint. "
    "With an in-scope session_id, it adopts that session's checkpointed history into the current bound session. "
    "Use this when the current context should become the target thread rather than merely reference it. "
    "The replacement is persisted as a new checkpoint on the bound session. "
    "The tool returns the new head checkpoint id as a plain string."
)

RESUME_OUTPUT_TOOL_DESCRIPTION = (
    "Resume another agent's thread by appending only its final output. "
    "The target session must be marked COMPLETED. "
    "The tool does not append the target's full internal history. "
    "Use this when the current agent only needs the result of another completed run. "
    "An unfinished or inaccessible target session returns an error. "
    "The tool returns the new head checkpoint id as a plain string."
)

SESSION_TOOL_DESCRIPTION = (
    "Operate on durable agent sessions through one combined tool. "
    "It supports checkpoint creation, current-session forking, scoped session listing, and trace-artifact reading. "
    "Use this when a model should choose among several session operations from one tool name. "
    "The tool is permission-gated and honors the bound SessionScope. "
    "Operations that need the current session require the tool to be bound by Session. "
    "Every failure is returned as a ToolResult error instead of escaping the agent loop."
)

__all__ = [
    "SESSION_ID_DESCRIPTION",
    "CHECKPOINT_ID_DESCRIPTION",
    "LABEL_DESCRIPTION",
    "OPERATION_DESCRIPTION",
    "CHECKPOINT_TOOL_DESCRIPTION",
    "FORK_TOOL_DESCRIPTION",
    "REWIND_TOOL_DESCRIPTION",
    "RESUME_APPEND_TOOL_DESCRIPTION",
    "RESUME_REPLACE_TOOL_DESCRIPTION",
    "RESUME_OUTPUT_TOOL_DESCRIPTION",
    "SESSION_TOOL_DESCRIPTION",
]
