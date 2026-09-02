# Vidbyte Failure Vocabulary

The code enum is the source of truth:
`vidbyte/lib/enums/failure.py`. This file is the human-readable catalogue.
Use the most specific existing code. Do not create a new code because an error
message has a different wording.

## Configuration

`configuration.invalid`, `configuration.missing_required`,
`configuration.unsupported_combination`, `configuration.unknown_model`,
`configuration.invalid_schema`, `configuration.invalid_provider`,
`configuration.invalid_tool`, `configuration.invalid_middleware`,
`configuration.invalid_runtime`, and `configuration.invalid_argument` describe
deterministic setup or contract mistakes known before useful work begins.

These normally fail closed. They are not candidates for another model fallback.

## Input and output

`input.empty`, `input.invalid`, `input.type_invalid`, `output.missing`,
`output.invalid`, `output.schema_violation`, `contract.unsatisfied`, and
`serialization.invalid` describe malformed input, output, or typed contracts.

Output-contract repair may handle these inside the current loop. Session records
the rejection and routes only when the contract budget is exhausted.

## Model and provider

`model.request_failed`, `model.response_invalid`, `model.timeout`,
`model.rate_limited`, `model.authentication_failed`, `model.not_found`,
`model.unsupported`, `model.context_limit`, `model.content_filtered`,
`model.retry_exhausted`, `model.fallback_exhausted`,
`provider.selection_failed`, and `provider.configuration_invalid` describe
provider-boundary failures.

`AgentFallback` and model retry remain the first owners. A successful fallback is
recorded as `model.request_failed` with `status="recovered"` and
`handled_by="agent_fallback"`.

## Tool and action

Tool-boundary codes are `tool.not_found`, `tool.arguments_invalid`,
`tool.permission_denied`, `tool.disabled`, `tool.timeout`, `tool.rate_limited`,
`tool.execution_failed`, `tool.result_invalid`, `tool.result_missing`,
`tool.retry_exhausted`, `tool.call_limit_reached`,
`tool.calls_per_iteration_limit`, `tool.identical_call_limit`,
`tool.consecutive_failure_limit`, `tool.error_limit`,
`tool.sliding_window_limit`, and `tool.loop_limit`.

The router reads each runtime `ToolCallContext.result.metadata["error"]` when
available, so `unknown_tool`, `permission_denied`, `timeout`, validation,
output-schema, missing-result, and execution errors retain their most specific
tool code instead of collapsing into one generic failed-call count.

Action-level codes describe what the agent attempted rather than what the
transport returned: `action.policy_violation`, `action.unsafe`,
`action.forbidden`, `action.invalid_arguments`, `action.wrong_target`,
`action.out_of_order`, `action.duplicate`, `action.precondition_failed`,
`action.no_progress`, `action.looping`, `action.partial`,
`action.not_applied`, `action.conflict`, `action.idempotency_violation`, and
`action.unexpected_side_effect`.

Action rules are the main extension point for agent behavior. Safety and
permission rules should be fail closed and run before the action.

## Runtime and resources

`runtime.max_iterations`, `runtime.max_tokens`, `runtime.max_tool_calls`,
`runtime.timeout`, `runtime.middleware_abort`, `runtime.middleware_error`,
`runtime.error`, `runtime.cancelled`, `runtime.context_build_failed`,
`runtime.compaction_failed`, `runtime.queue_limit`, and `resource.exhausted`
describe deterministic execution boundaries.

Limit failures normally stop cleanly or route to a continuation strategy. A
middleware implementation error follows that middleware's existing
`fail_closed` setting.

## Session, state, and data

Session codes are `session.not_found`, `session.checkpoint_missing`,
`session.serialization_failed`, `session.version_mismatch`,
`session.persistence_failed`, `session.resume_failed`, `session.fork_failed`,
`session.rewind_invalid`, and `session.scope_denied`.

State/data codes are `state.corrupted`, `state.conflict`, `data.not_found`,
`data.malformed`, `data.incomplete`, `data.stale`, `data.conflict`,
`data.source_unavailable`, and `data.permission_denied`.

Optional checkpoint persistence remains fail open in the current Session API;
the failure is recorded in memory and in mutable reply metadata. Required
durability can be enforced by a future Session policy.

## Workflow and teams

`workflow.definition_invalid`, `workflow.validation_failed`,
`workflow.stage_failed`, `workflow.routing_failed`,
`workflow.transition_limit`, `agent.handoff_failed`, `agent.transfer_failed`,
`team.task_blocked`, `team.replan_limit`, and `team.unrecoverable` describe
deterministic state-machine and multi-agent boundaries.

## Observability and failure infrastructure

`usage.recording_corrupted`, `trace.capture_failed`, `trace.export_failed`,
`recovery.handler_failed`, and `rule.evaluation_failed` describe failures in
measurement, export, or the failure system itself. Telemetry generally fails
open. Safety-critical rule and recovery infrastructure generally fails closed.
