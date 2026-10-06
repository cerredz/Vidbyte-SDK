# Multi-Agent Teams

Use this reference when building or modifying a Vidbyte team whose manager must own the overall goal, track progress in shared state, and replan after failure.

## Choose The Right Primitive

- Use `BaseAgent` for one model/tool loop.
- Use `SequentialPipeline`, `ParallelPipeline`, `ConditionalPipeline`, or `MapReducePipeline` for fixed string-in/string-out topology.
- Use `vidbyte.workflows` when Python code must own legal non-linear stage transitions and deterministic validation gates.
- Use `MultiAgent` when a probabilistic manager must plan tasks, delegate one ready task per round, observe evidence/blockers/retries, and replace future work after stalls.

`MultiAgent` is inspired by Magentic-One's separation between an overall task ledger and progress ledger. Vidbyte exposes one typed `TaskLedgerSnapshot` containing both planning facts and task progress while keeping all mutation inside `TaskLedger`.

## Basic Team

```python
from vidbyte import BaseAgent, MultiAgent, MultiAgentSettings

manager = BaseAgent(
    name="manager",
    system_prompt="Plan the work, delegate one task at a time, and recover from blockers.",
    provider="openai",
    model_name="gpt-4.1",
)

researcher = BaseAgent(
    name="researcher",
    system_prompt="Research only the assigned task and return useful evidence.",
    provider="openai",
    model_name="gpt-4.1",
)

team = MultiAgent(
    name="research-team",
    system_prompt="Produce a grounded answer and disclose uncertainty.",
    orchestrator=manager,
    agents=[researcher],
    settings=MultiAgentSettings(
        max_rounds=20,
        max_replans=3,
        max_task_attempts=3,
        replan_after_stalls=3,
    ),
)

reply = await team.arun("Investigate the issue and recommend next actions.")
print(reply.content)
print(team.last_result.stop_reason)
print(team.last_ledger.tasks)
```

Passing a schema-free exact `BaseAgent` as `orchestrator=` automatically creates `MagenticOneOrchestrator`. Specialized manager subclasses or schema-bound manager templates require an explicit `manager_agent_factory` on `MagenticOneOrchestrator` so the SDK never silently erases behavior.

## Control What Crosses The Worker Boundary

Wrap a worker in `AgentBinding` and configure `AgentTransfer`:

```python
from vidbyte import AgentBinding, AgentTransfer

binding = AgentBinding(
    agent=researcher,
    transfer=AgentTransfer(
        before_dispatch=authorize_research,
        request_builder=render_research_request,
        report_parser=parse_research_reply,
        report_validator=verify_research_report,
        timeout_seconds=90,
        max_invocation_retries=1,
        reset_on_replan=True,
    ),
    fork_factory=fork_specialized_researcher,
    closer=close_specialized_researcher,
)
```

Callback contracts:

- `before_dispatch(dispatch, ledger)` returns `None` to approve or `TaskBlocker` to deny without calling the worker.
- `request_builder(dispatch, ledger)` returns `str` or `AgentInput` and selects its own immutable ledger projection.
- `report_parser(reply, dispatch, ledger)` returns `AgentReport` with status `COMPLETED`, `FAILED`, or `BLOCKED`.
- `report_validator(report, dispatch, ledger)` returns the accepted or transformed `AgentReport`.
- `fork_factory(agent, settings)` synchronously returns the same behavioral subtype.
- `closer(worker)` releases compound worker resources; without one, the SDK closes MCP servers.
- `manager_agent_closer(manager, phase)` releases custom manager/phase resources when a `MagenticOneOrchestrator` factory is used.

Callbacks may be sync or async except fork factories, which are synchronous because `BaseAgent.fork()` and `MultiAgent.fork()` are synchronous APIs.

Controller callbacks keep the same explicit snapshot discipline:

- `ledger_factory(run_id, request, owners, settings)` receives the normalized `AgentInput` and returns a fresh `TaskLedger`.
- `completion_check(context, finish_decision)` may add a developer-owned completion gate after structural/evidence gates pass.
- `on_event(event, snapshot)` is fail-open telemetry after a commit; callback error types are traced and retained in `MultiAgentResult.metadata`.

## Safe Defaults

The default request builder emits deterministic JSON with only:

- `task_id`
- `goal`
- `owner`
- `acceptance_criteria`
- `instruction`
- `attempt`
- `payload`

The payload must already be JSON-safe. The default renderer never calls `repr()` or `str()` on arbitrary objects.

The default report parser maps non-blank worker text to a completed report and one `TaskEvidence(verified=False)`. Blank text becomes a retryable failed report. Structural acceptance means the transfer accepted the report; it does not prove correctness.

Only a developer-owned parser or validator should set `TaskEvidence.verified=True`. Set `MultiAgentSettings(require_verified_evidence=True)` when every required completed task must carry at least one verified evidence item before full completion.

## Ledger Invariants

`TaskLedger` is the only mutable structural authority. Orchestrators, worker gates, validators, callbacks, and callers receive frozen snapshots.

- Task ids are non-blank and unique.
- Owners must match configured worker names.
- Dependencies must exist, cannot reference self, and must be acyclic.
- A dispatch carries `base_revision`; stale decisions are rejected.
- Starting a task increments its task-attempt counter and stores `IN_PROGRESS`.
- Ordinary post-start failures become `FAILED` while attempts remain or `BLOCKED` when exhausted/non-retryable.
- A replan preserves completed tasks and their original output/evidence.
- Reusing an existing id for different work is rejected.
- Omitted unfinished tasks become `SUPERSEDED`, not deleted.
- Readiness is derived from status, attempts, and completed dependencies.
- Event storage is bounded, but event indexes remain monotonic.

Snapshots freeze SDK-owned mapping/sequence containers. Opaque nested values in `Any` payload, result, evidence, or metadata fields may still alias developer objects; snapshots are not a persistence promise.

## Custom Orchestrators

Implement `MultiAgentOrchestrator` when manager policy should not use a `BaseAgent`:

```python
class MyOrchestrator:
    def fork(self): ...
    async def plan(self, context): ...
    async def decide(self, context): ...
    async def replan(self, context): ...
    async def finalize(self, context): ...
    async def aclose(self): ...
```

Return `OrchestratorPlan` from planning phases and `OrchestratorDecision` from progress. `DELEGATE` requires task id, owner, and instruction. `FINISH` supplies `final_answer`, but the controller still enforces required-task, dependency, evidence, and optional completion-callback gates.

`MagenticOneOrchestrator` uses short-lived structured-output manager forks for plan/progress/replan and a schema-free run manager for final text. Its default renderer includes the request, team instructions, safe worker cards, controller counters, and ledger facts in explicit tags. It excludes caller history and `BaseContext` unless a custom renderer opts in. Tags reduce ambiguity but do not neutralize prompt injection; treat all external content as untrusted.

## Limits, Timeout, And Cleanup

`MultiAgentSettings` bounds rounds, replans, task attempts, stalls, parser retries, events, and optional run/orchestrator/worker timeouts. A hard run timeout skips manager finalization. The controller may return the latest non-blank manager candidate as a `TIMEOUT` result; without one, it raises `MultiAgentExecutionError`.

Completion, explicit partial finish, round limits, and replan limits use the schema-free finalizer. `return_partial_on_limit=False` turns a limit into an error. `allow_partial_finish=True` accepts an explicit manager candidate even when full completion gates are not met and marks the result incomplete.

Every run-local worker and manager is closed in a shielded finalizer. Worker reset on replan closes the old worker before constructing its replacement. Cancellation propagates and may leave the latest observable ledger snapshot in `IN_PROGRESS`; ordinary exceptions do not.

## BaseAgent Compatibility And Restrictions

`MultiAgent` supports `run`, `arun`, sequential runs, queued prompts, `receive`, `behavior`, `as_tool`, `card`, and subtype-preserving `fork` through its `BaseAgent` surface.

The team facade intentionally rejects:

- provider/model/runtime/output-schema configuration
- team-level tools and MCP attachment
- automatic handoff; manual handoff requires `by=HandoffAgent(...)`
- `Session`, `persist`, `bind_session`, `export_state`, and restore

Put provider/model/tool/MCP configuration on manager and worker agents. Individual workers may use sessions outside a team; the team itself cannot be restored from `RunState`.

## Tracing

The root remains `agent.run` with strategy `multi_agent`. Semantic child spans are:

- `multi_agent.run`
- `multi_agent.orchestrator`
- `multi_agent.worker`
- `multi_agent.ledger_update`
- `multi_agent.replan`
- `multi_agent.finalize`

These spans carry identifiers, counters, revisions, status, and reasons only. Do not add raw request, task payload, worker output, evidence value, or manager final answer fields to multi-agent traces.
