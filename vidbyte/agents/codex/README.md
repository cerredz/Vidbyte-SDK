# Codex agent integration

This folder translates Vidbyte inputs and outputs around Codex-owned execution.
Live observation uses the native turn stream and invokes awaited callbacks in
arrival order. It does not pause Codex between internal model calls.

```python
from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings, CodexObservationSettings, Trace

agent = CodexHarnessAgent(CodexHarnessAgentSettings(
    name="observed", system_prompt="Complete the task.",
    observation=CodexObservationSettings(tracer=Trace.langsmith_default()),
))
```

Supply `observers=(async_callback,)` to consume reviewed native item events.
Callbacks are awaited and failures abort collection. Unknown notifications retain
their method and identity only. Reasoning content is excluded before callbacks;
reviewed item fields can still contain task data, so callbacks own storage policy.
Tracing exports identity metadata only and remains fail-open. No model-call spans
are inferred from assistant messages. Forks inherit settings; an empty observation
settings override disables them.

## File Index

- `agent.py`: Public facade and middleware/metrics orchestration.
- `acceptance.py`: Required final artifacts and application checks before success.
- `control.py`: Native live steering/interruption with per-turn handle lifetime.
- `capture.py`: Bounded native observations and required trajectory-sink acknowledgment.
- `capture_format.py`: Shared TrajectoryRecord projection and mandatory export redaction.
- `config.py`: Shared settings resolution and native argument serialization.
- `continual.py`: Native trace updates and deterministic completed-item scheduling.
- `context.py`: Context zone and native input placement translation.
- `fork.py`: Validated child construction and native lineage.
- `metrics.py`: Usage snapshot and local cost accounting.
- `middleware.py`: Enforceable outer lifecycle hooks.
- `observation.py`: Reviewed event translation and optional tracing.
- `stream.py`: One-consumer native streaming and result collection.
- `result.py`: Native snapshot serialization and output validation.
- `transport.py`: Native client lifecycle, lazy imports, and error boundaries.
- `native_tools.py`: Public low-level SDK lifecycle for registered Vidbyte functions.
- `tool_dispatch.py`: Native callback authorization, validation, and execution.
- `tool_wire.py`: Generated native parameters and experimental tool declarations.
- `__init__.py`: Public facade exports.

## Non-Goals

Generic tool execution belongs in `vidbyte/tools`; provider trace export belongs in
`vidbyte/providers`; shared records belong in `vidbyte/lib/dataclasses`. This
adapter does not replace native context management or expose private reasoning.

## Logs

- 2026-09-08 - Added optional native streaming - awaited event callbacks do not establish a native execution barrier.

## Continual artifacts

Pass `continual_trace=CodexContinualTraceSettings(schema=TraceSchema.coerce(MyModel), every_n_completed_items=5)` on harness settings. A separate native Codex turn generates each trace patch using the same model/client configuration. `continual.py` owns the updater and scheduler. Updates cost additional Codex calls; the configured timeout and attempt cap bound each update attempt.

Read artifacts from `reply.metadata["trace"]` or `agent.last_trace`, and inspect `reply.metadata["trace_metadata"]` for failures and window truncation. The default is fail-open. This cadence counts completed native items, not model iterations. The artifact stays out of the main context. Evidence windows are bounded; exact deduplication retains one ID per completed item. Native updater threads use read-only filesystem sandboxing and deny approvals, but those settings do not guarantee that every externally configured tool is side-effect-free. The update prompt instructs the model to use only the supplied snapshot.

## Native Vidbyte tools

Set `tool_bridge=CodexToolBridgeSettings(tools=Tools([...]), permission_policy=policy)`
on harness settings and enable `codex.client.experimental_api`. The native
`item/tool/call` request waits for Vidbyte's existing ToolExecutor, including its
permission policy and tool validation. Existing bound reasoning tools retain their
context references. Tool arguments and successful outputs enter Codex's context.

This option currently requires a fresh thread. Resumed threads and forks reject
before native execution because the pinned protocol cannot register replacement
dynamic tools there. Create a fresh agent for another tool-enabled run. Codex's
built-in shell, file, hosted, and MCP tools do not pass through this dispatcher.
Native approval requests reaching this client are declined; configure the native
sandbox and approval mode separately. Registration does not force model tool use.

The callback waits up to `timeout_seconds` (default 60). Timeout or cancellation
cancels cooperative async tool execution but cannot undo completed effects. Tools
must not synchronously block their event loop or issue native requests on the same
Codex connection, whose reader is waiting for their result.

## Final acceptance

Set `acceptance=CodexAcceptanceSettings(require_trace=True, trace_schema=FinalTrace)`
alongside continual tracing to require a successful final-boundary update and a
valid final artifact. `trace_schema` uses the shared output-schema validator. With
acceptance enabled, native status must be `completed` by default.

Use `checks=(async_check,)` for application requirements such as verifying saved
artifacts. Each check receives its own `CodexAcceptanceRequest` snapshot and must
return exactly `True`; false/missing returns, exceptions, or timeout reject the
candidate with `codex.acceptance_failed`. Successful replies include an
`acceptance` receipt. Rejected replies are not appended to history, while native
thread identity and usage remain available. This gate cannot undo native effects
and never automatically retries them. Forks inherit the settings; an explicit
`CodexAcceptanceSettings(require_completed=False)` override disables requirements.

## Live control

Set `control=CodexControlSettings(on_ready=async_callback)` to receive a
`CodexRunControl` when the native turn starts. Retain the handle and return from
the callback; then use `await handle.steer("New feedback")` or
`await handle.interrupt()` while `handle.active` is true. The readiness callback
can also issue immediate commands, but must not wait for the turn to finish.

Both operations call the native SDK. Steering adds text to the current turn and
checks its acknowledgment; it does not replace native context or guarantee which
action happens next. Interrupt acknowledgment does not undo effects. Commands and
readiness callbacks have a configurable timeout (default 60 seconds). Completion,
failure, or cancellation deactivates the handle, including before terminal event
observers run. Closed handles and late acknowledgments fail with
`codex.control_failed`. Forks inherit settings and create their own run handles.

## Trajectory capture for distillation

Opt in with `capture=CodexCaptureSettings(sink=FileTrajectorySink("dataset.jsonl"))`.
This uses the existing `vidbyte.harnesses.stores` sink contract and TrajectoryRecord
format. Required export (the default) must be acknowledged before the reply enters
history; set `required=False` for fail-open export with an explicit failed receipt.
Read `reply.metadata["capture"]` or `agent.last_capture` for the run ID, storage
acknowledgment, and discarded-event count. Sinks determine physical durability;
timeout does not prove a write was rolled back, so no automatic retry occurs.

Records contain reviewed native events, actual translated input, candidate output,
trace artifact, and selected behavior settings. Hidden reasoning, internal model
prompts, full native context, and unreported deltas are explicitly unavailable.
This remains an observed trajectory, not a resumable Vidbyte Session. Failed and
cancelled runs receive best-effort diagnostic export without replacing their error.

The event window defaults to 100 snapshots; configure `max_observations` as needed.
Client environment and arbitrary process config are excluded. Existing credential
key and common text-assignment redaction always runs, after any custom `redactor`.
This does not guarantee exhaustive secret or PII detection. No rewards are invented
and no training job is started. Configuring capture explicitly authorizes export
to the selected sink; omitting it performs no export.
