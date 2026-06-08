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
        title="Goal",
        min_length=1,
        description=(
            "The run's objective, recorded once at the start to orient a reader of the history who may not have access to the original prompt. "
            "Write this as a clear statement of what the agent set out to accomplish, precise enough that someone reading the history log in isolation can understand what each event was in service of. "
            "Keep this field stable across updates, since the goal is the fixed reference point that gives the timeline its meaning and changing it mid-run would corrupt the historical record. "
            "A successor or auditor reading this field can immediately understand the purpose of every event in the timeline without needing external context. "
            "If the goal genuinely changed during the run, record the change as an event in the timeline rather than modifying this field, so the history remains accurate from the original starting point."
        ),
    )
    timeline: list[str] = Field(
        title="Timeline",
        min_length=0,
        default_factory=list,
        description=(
            "The core field of the history trace: a terse, ordered, one-line-per-event record of everything meaningful that happened during the run, in the sequence it occurred. "
            "Append every new event as it happens and never prune, compress, or reorder earlier entries, since this field is meant to be a near-lossless log a successor can replay to reconstruct the full run. "
            "Each entry should be a single line identifying the event type, what happened, and any critical detail, rather than a multi-line narrative, to keep the log scannable. "
            "The timeline is the authoritative chronological record of the run: every other field in this trace is a structured summary derived from or indexed against this log. "
            "If an event is ambiguous, write enough detail to resolve the ambiguity in the same entry rather than adding a follow-up entry, keeping the log dense and self-contained."
        ),
    )
    iteration_log: list[str] = Field(
        title="Iteration Log",
        min_length=0,
        default_factory=list,
        description=(
            "A short summary for each completed agent iteration, capturing what that iteration accomplished and how it advanced the run toward the goal. "
            "Append one entry per iteration in the order they complete, without rewriting or removing earlier entries, so the sequence of iteration-level progress is preserved. "
            "Each entry should synthesize the iteration rather than just listing its events, providing a higher-level view than the timeline while being more compact than the full event log. "
            "This field allows a reviewer to understand the run's progress in coarse iteration-sized chunks without reading the full timeline, which is valuable for auditing long runs. "
            "If an iteration produced no meaningful progress, still record it with a note of why it was unproductive, since unproductive iterations are part of the history and explain pacing."
        ),
    )
    model_turns: list[str] = Field(
        title="Model Turns",
        min_length=0,
        default_factory=list,
        description=(
            "A brief record of each assistant or model turn during the run, capturing what the model said, decided, or produced in that turn at a level of detail sufficient for later review. "
            "Append one entry per turn in the order they occurred, so the model's contributions to the run are individually visible and distinguishable from tool results and system events. "
            "Each entry should identify the turn number or sequence and summarize the key content, not transcribe the full response, to keep the log manageable. "
            "This field allows a reviewer to trace how the model's outputs evolved across the run and identify where its reasoning or actions changed in response to tool results or user input. "
            "If a turn was particularly long or complex, summarize the key action or decision rather than the full content, and note that the summary is condensed so a reader knows to consult other fields for detail."
        ),
    )
    tool_invocations: list[str] = Field(
        title="Tool Invocations",
        min_length=0,
        default_factory=list,
        description=(
            "Each tool call the agent made during the run, recorded with the tool name and a summary of the arguments passed, in the order the calls occurred. "
            "Append one entry per invocation as calls are made, not batched after the fact, so the log reflects the actual sequence of tool usage during execution. "
            "Include enough argument detail that a reader can understand what the tool was asked to do without needing to reconstruct the call from context, but avoid reproducing large argument payloads verbatim. "
            "This field complements tool_results to form a call-result ledger that a reviewer can use to audit whether the agent used tools correctly and efficiently. "
            "If the same tool is called multiple times with different arguments, record each call separately so the full pattern of usage is visible."
        ),
    )
    tool_results: list[str] = Field(
        title="Tool Results",
        min_length=0,
        default_factory=list,
        description=(
            "The result or outcome returned by each tool call, summarized in a way that captures the key information without reproducing large payloads verbatim. "
            "Append one entry per result in the order results were received, paired loosely with the corresponding entry in tool_invocations by position. "
            "Each entry should identify whether the call succeeded or failed and summarize the most important part of the result, so a reader can understand what the agent learned or received from each call. "
            "Together with tool_invocations, this field forms a complete call-result ledger that allows a reviewer to assess whether the agent interpreted tool outputs correctly and acted appropriately on them. "
            "For failed calls, include the error summary in the same entry rather than only recording it in errors, since the call-result pairing is important for understanding the tool interaction sequence."
        ),
    )
    user_messages: list[str] = Field(
        title="User Messages",
        min_length=0,
        default_factory=list,
        description=(
            "Messages or inputs received from the user or caller during the run, recorded verbatim or closely summarized in the order they were received. "
            "Append each message as it arrives and do not paraphrase in a way that loses meaning, since user messages are often the authoritative source for constraints, corrections, and goals. "
            "Include both the initial prompt and any follow-up messages sent during the run, since mid-run user inputs can significantly change the agent's direction. "
            "A reviewer or successor reading this field can reconstruct the user's intentions and instructions without needing access to the original conversation, which is valuable for auditing compliance with user direction. "
            "If a user message contained an instruction that the agent did not follow, note that in decisions or deviations rather than here, keeping this field as a faithful record of what was said."
        ),
    )
    system_events: list[str] = Field(
        title="System Events",
        min_length=0,
        default_factory=list,
        description=(
            "Lifecycle and middleware events observed during the run, such as run start, context compaction, policy checks, middleware triggers, and run end, each recorded in the order they occurred. "
            "Append each system-level event as it occurs, noting the event type and any relevant metadata such as the iteration number or the triggering condition. "
            "These events are distinct from model turns and tool calls in that they are generated by the runtime infrastructure rather than by the model or external services. "
            "This field allows a reviewer to understand the operational context of the run, including when the context was compacted or when middleware modified behavior, which is essential for diagnosing unexpected outcomes. "
            "If a system event caused a change in the agent's behavior or state, note the effect in the same entry so the causal connection is visible without requiring a reader to cross-reference the timeline."
        ),
    )
    state_changes: list[str] = Field(
        title="State Changes",
        min_length=0,
        default_factory=list,
        description=(
            "Notable changes to the agent's internal state or the environment's state during the run, each recorded with enough detail to understand what transitioned and why. "
            "Append each state change as it occurs, distinguishing between changes caused by the agent's actions and changes imposed by external factors such as system events or user input. "
            "Each entry should identify what state changed, what it changed from and to when both values are available, and what triggered the change. "
            "This field is particularly valuable for diagnosing unexpected behavior: a reviewer can trace state transitions to find where the agent's model of the world diverged from reality. "
            "If a state change is reversible, note that explicitly so a successor knows whether restoring the prior state is an option when evaluating how to handle a problem."
        ),
    )
    errors: list[str] = Field(
        title="Errors",
        min_length=0,
        default_factory=list,
        description=(
            "Every error or failure encountered during the run, recorded verbatim enough to diagnose the root cause without needing to re-run the agent. "
            "Append each error in the order it occurred and never drop one, since errors are critical to a faithful history and even minor errors can be relevant for understanding the run's behavior. "
            "Include the error type, message, and the context in which it occurred, such as which tool call or iteration triggered it, so a reviewer can pinpoint the failure without scanning the full timeline. "
            "This field is one of the most important for diagnosing a failed or underperforming run: a complete error log allows a reviewer to identify patterns, root causes, and the agent's recovery behavior. "
            "If the agent recovered from an error, note the recovery in retries or state_changes rather than here, keeping this field as a pure record of what went wrong."
        ),
    )
    retries: list[str] = Field(
        title="Retries",
        min_length=0,
        default_factory=list,
        description=(
            "Each retry attempt the agent made after a failure, recorded with what was retried, what changed on the retry, and whether the retry succeeded. "
            "Append one entry per retry in the order they occurred, pairing each with the corresponding error in the errors field when possible. "
            "Include what the agent did differently on the retry when applicable, since a retry with no change in approach is informative in a different way than one that incorporated a correction. "
            "This field distinguishes resilient agents from fragile ones: a reviewer can see how many times the agent retried, whether retries were intelligent, and how often they succeeded. "
            "If a retry cascade produced many attempts, record each one rather than summarizing them, since the pattern of retry behavior is often more diagnostic than the outcome alone."
        ),
    )
    decisions: list[str] = Field(
        title="Decisions",
        min_length=0,
        default_factory=list,
        description=(
            "Decisions made during the run, recorded chronologically with the choice that was made and the brief reasoning behind it when that reasoning is visible in the context. "
            "Append each decision as it is made in the order it occurred, so the decision history reflects the actual sequence of commitments rather than a post-hoc reconstruction. "
            "State each decision as a specific choice rather than an abstract deliberation, making clear what was decided and what was not chosen as the alternative. "
            "This field in the history trace focuses on chronological ordering rather than the deep rationale captured in the decision trace, serving as a timeline of commitments rather than an ADR log. "
            "A reviewer reading the full history can use this field to correlate decisions with the events that preceded them, checking whether decisions were appropriately responsive to the situation."
        ),
    )
    files_touched: list[str] = Field(
        title="Files Touched",
        min_length=0,
        default_factory=list,
        description=(
            "Files the agent read, created, modified, or deleted during the run, each recorded with the type of action performed so the file interaction log is unambiguous. "
            "Append each file event in the order it occurred, including both the file path and the action, so a reviewer can reconstruct the agent's file-level footprint without re-running the agent. "
            "A file may appear multiple times if it was accessed in different ways at different points, and each appearance should be recorded separately to preserve the sequence. "
            "This field is essential for auditing the agent's side effects: a reviewer can see exactly which files were modified or deleted without needing to compare file system snapshots. "
            "If a file was touched as part of a tool call, cross-reference the tool name in the same entry so the connection between the tool invocation and the file event is explicit."
        ),
    )
    external_calls: list[str] = Field(
        title="External Calls",
        min_length=0,
        default_factory=list,
        description=(
            "Calls to external services, APIs, networks, or databases made during the run, each recorded with the service or endpoint and a summary of the interaction. "
            "Append each external interaction in the order it occurred so the run's outward footprint is fully logged and auditable. "
            "Include both successful and failed calls, since a failed external call is often as informative as a successful one for understanding the run's behavior and outcomes. "
            "This field documents the agent's external dependencies and side effects beyond the local environment, which is important for security audits, cost accounting, and compliance reviews. "
            "If a call involved sensitive data or produced a durable side effect such as creating a record, note that explicitly so the auditor knows the interaction had consequences beyond the run itself."
        ),
    )
    inputs: list[str] = Field(
        title="Inputs",
        min_length=0,
        default_factory=list,
        description=(
            "Inputs, parameters, or data the agent consumed during the run, each recorded specifically enough that a reader can identify the source and reproduce the same input if needed. "
            "Append each distinct input in the order it was received or fetched, including both initial inputs and any data acquired mid-run through tool calls or user messages. "
            "Name file paths, API endpoints, or message identifiers rather than summarizing vaguely, so a successor or auditor can retrieve the same inputs and verify the agent's starting conditions. "
            "This field establishes the complete input surface of the run, which is essential for reproducibility audits and for understanding what the agent was working with at each stage. "
            "If an input was transformed before use, note the transformation alongside the original source so the provenance of derived data is clear."
        ),
    )
    outputs: list[str] = Field(
        title="Outputs",
        min_length=0,
        default_factory=list,
        description=(
            "Outputs the agent emitted at any point during the run, including answers, files, artifacts, API results, or any other deliverable, each recorded in the order it was produced. "
            "Append each output as it is produced, naming it specifically with a file path, identifier, or short description so a reader can locate it without re-running the agent. "
            "Include intermediate outputs as well as final ones, since the full production history is more valuable for auditing than only the final deliverables. "
            "This field gives a reviewer an inventory of everything the agent produced, allowing them to assess completeness, identify redundant outputs, and verify that the expected deliverables were created. "
            "If an output was later superseded or invalidated, note that in the same timeline entry or in state_changes rather than removing the output entry, keeping the production history accurate."
        ),
    )
    checkpoints: list[str] = Field(
        title="Checkpoints",
        min_length=0,
        default_factory=list,
        description=(
            "Notable points in the run from which execution could be resumed, each recorded with enough context to enable a successor to continue without replaying the full history from the start. "
            "Append each checkpoint as it is reached, including the key state variables, files, and decisions that would need to be restored for a valid resume. "
            "A checkpoint should capture the minimal state needed to continue rather than a full copy of everything, since useful checkpoints are compact enough to act on quickly. "
            "This field is the primary mechanism for enabling mid-run handoffs: a successor can read the most recent checkpoint and resume from there rather than replaying the entire timeline. "
            "If a checkpoint is superseded by a later one, leave the earlier entry in place, since a reviewer may want to understand the evolution of the resumable state across the run."
        ),
    )
    token_usage_log: list[str] = Field(
        title="Token Usage Log",
        min_length=0,
        default_factory=list,
        description=(
            "Observed token-usage snapshots collected over the course of the run when that information is visible in the runtime metadata, each recorded with the approximate iteration or time at which it was observed. "
            "Append each reading in the order it is observed and do not overwrite earlier readings, so the growth of token consumption across the run is traceable from start to finish. "
            "Each entry should capture the snapshot values available, such as prompt tokens, completion tokens, and total tokens, along with the context that identifies when in the run it was taken. "
            "This field allows a reviewer to audit cost growth, identify expensive iterations, and determine whether the run was approaching context limits at any point during execution. "
            "If token usage data is not available from the runtime, leave this field empty rather than estimating, since inaccurate token data is worse than absent data for cost auditing purposes."
        ),
    )
    notable_quotes: list[str] = Field(
        title="Notable Quotes",
        min_length=0,
        default_factory=list,
        description=(
            "Short verbatim snippets from model outputs or tool results that are worth preserving exactly because they capture a key decision, conclusion, or piece of information in the agent's own words. "
            "Append each quote in the order it was produced, keeping it exact rather than paraphrasing, since the verbatim text is the point of this field. "
            "Select quotes that would be difficult to locate by scanning the timeline, such as a key inference buried in a long model turn or a critical tool output among many results. "
            "This field makes the most important verbatim content immediately accessible without requiring a reader to search through the full model turn or tool result logs. "
            "If a quote requires context to be interpretable, add a brief one-line note of context alongside the verbatim text rather than paraphrasing the quote itself."
        ),
    )
    environment_notes: list[str] = Field(
        title="Environment Notes",
        min_length=0,
        default_factory=list,
        description=(
            "Observations about the environment the run depends on, such as the operating system, available services, credentials status, active sessions, or configuration values, each noted as they become relevant. "
            "Append each observation in the order it is made, noting both what the environment state was and why it matters to the run's behavior or outputs. "
            "Include observations about environment conditions that may change over time, such as a session that will expire, so a successor knows which environmental dependencies require attention. "
            "This field gives a successor the environmental context it needs to reproduce or continue the run, identifying dependencies that are not captured in the tool or file interaction logs. "
            "If an environment condition caused a failure or unexpected behavior, reference the corresponding error or decision entry so the causal connection is visible across the history."
        ),
    )
    current_event: str = Field(
        title="Current Event",
        min_length=0,
        default="",
        description=(
            "The single most recent event as of the latest update, expressed as the same terse one-line format used in the timeline field so a reader can orient immediately. "
            "Overwrite this field on every update to point at the latest thing that happened, making it a fast indicator of where the run currently stands without requiring a full timeline scan. "
            "Use the same specificity as a timeline entry, naming the event type and key detail, so a reader can understand the current moment without needing prior context. "
            "A successor reading this field can immediately see where the original agent left off and then read the timeline backward from there for more context if needed. "
            "Leave this empty only when the run has completed and all events are final, so an empty value reliably signals that the history is closed."
        ),
    )
    last_known_state: str = Field(
        title="Last Known State",
        min_length=0,
        default="",
        description=(
            "A snapshot of where everything stands as of the latest event, summarizing the key state of files, decisions, blockers, and progress in a few sentences that orient a reader instantly. "
            "Overwrite this field with the most-current overall state of the run on every update, since a stale snapshot here misleads a successor about what actually needs to happen next. "
            "Write in the present tense and be specific, naming files, steps, or conditions rather than describing them abstractly, so the snapshot is actionable rather than just descriptive. "
            "This field is the most important entry point for a human reviewer or successor who needs a quick orientation before diving into the full timeline. "
            "Distinguish between state that is settled, state that is in flux, and state that is blocked, so a reader knows what kind of action is needed upon reading."
        ),
    )
    event_count: int = Field(
        title="Event Count",
        default=0,
        description=(
            "The approximate running count of recorded timeline events, giving a quick sense of the run's size without requiring a reader to count entries in the timeline field. "
            "Overwrite this field with the latest total on every update, keeping it synchronized with the actual number of entries in the timeline field. "
            "Use this count as a rough proxy for run complexity and cost: a very high event count relative to the number of completed steps may indicate inefficiency or an excessive retry loop. "
            "A reviewer seeing an unusually high event count relative to the run's output can use this signal to investigate where the extra events came from without first reading the full timeline. "
            "If the exact count is uncertain due to summarization or compaction, provide the best available approximation rather than leaving this at zero, since an approximate count is more useful than none."
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
