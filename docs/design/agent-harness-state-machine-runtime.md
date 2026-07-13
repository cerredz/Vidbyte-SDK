# Design Doc: Agent Harness State Machine Runtime

**Status:** Approved
**Author:** Codex
**Created:** 2026-07-12
**Last Updated:** 2026-07-13

---

## 1. Overview

Evolve the validated state-machine runtime introduced by draft PR #268 into a complete agent-harness control plane. The expanded `vidbyte.workflows` package will keep the existing typed stages, validators, guarded transitions, conditional routing, and cycles, then add phase-owned tool visibility, action-level safety, orthogonal run lifecycle state, layered budgets, five-pattern stuck detection, human approval and resumable interrupts, append-only event-sourced state, step checkpoints, reducer-backed state updates, per-stage model routing, isolated subgraphs with bounded fan-out/join, and interrupt-driven validation detours. The compiled graph remains the only authority for legal destinations: a stage may return a `WorkflowCommand` containing an update and a requested `goto`, but that destination must match a statically declared command edge before the runtime will execute it.

---

## 2. Goals & Non-Goals

### Goals

- Preserve PR #268's validate-before-commit state semantics, structural extension protocols, typed errors, and direct `vidbyte.workflows` API.
- Make a named stage's capability profile determine the exact tools an `AgentStage` exposes to its model.
- Enforce action safety independently from tool visibility through argument, command, path, and cumulative edit-impact policies.
- Preserve guarded transitions, first-class conditional routers, arbitrary declared jumps, backward edges, and cycles.
- Add a bounded `WorkflowCommand` primitive that combines reducer updates with a statically authorized `goto`, interrupts, signals, and `Send` requests.
- Track workflow position and execution condition on separate axes through terminal status and `WorkflowLifecycleStatus`.
- Enforce per-stage visit limits, agent-loop limits, model retry limits, global super-step/transition/token/tool/model/cost ceilings, timeout limits, subgraph concurrency, and detour depth.
- Detect the five supplied stuck signatures using normalized action/observation content and force the run lifecycle to `ERROR` with typed evidence.
- Support required edge approvals plus `NeverConfirm`, `AlwaysConfirm`, and `ConfirmRisky` run policies.
- Suspend without holding a Python coroutine, persist the interruption, and resume with a typed human value in a cold process.
- Make the workflow event stream append-only and canonical; runtime projections and result records must be rebuilt from events rather than edited in place.
- Persist an immutable checkpoint after every completed super-step through a pluggable store and resume from the latest compatible checkpoint plus subsequent events.
- Add typed state channels, deterministic reducers, declared stage `reads`/`writes`, and immediate observation channels that survive rejected candidates.
- Route each `AgentStage` to its own provider/model/temperature/thinking configuration and agent-loop profile.
- Run child state machines with separate state, event streams, checkpoints, and context, returning only a declared summary/update to the parent.
- Support deterministic `Send` fan-out and reducer-based join in declaration order under a concurrency limit.
- Support tool- or stage-emitted signals that push a bounded detour frame, run a validation path, and return to the interrupted source or pending continuation.
- Keep compiled definitions immutable and per-run execution state isolated so one machine can serve concurrent callers.
- Keep the feature additive for SDK users who continue using agents, middleware, sessions, pipelines, paradigms, or harness adapters without importing workflows.

### Non-Goals

- Do not make model output, agent validation, or human judgment deterministic; only invocation, allowed values, budgets, and transitions are deterministic.
- Do not allow a model, router, validator, interrupt value, or subgraph to jump to an undeclared destination.
- Do not intercept arbitrary filesystem, subprocess, browser, database, or network work performed directly inside a custom Python stage. Capability enforcement is guaranteed for policy-aware stages, especially `AgentStage`, and compilation rejects a non-default profile on a stage that does not declare policy support.
- Do not promise rollback of external side effects. State updates are transactional; external actions require idempotency keys, staging, compensation, or an appropriate sandbox.
- Do not implement a distributed scheduler, remote worker protocol, queue, cron service, hosted approval UI, or hosted persistence service.
- Do not merge `WorkflowStore` into `SessionStore`. Sessions persist resumable agent conversations; workflow stores persist graph events, reducer state, pending transitions, detour frames, and subgraph lineage.
- Do not depend on the unimplemented local `Harness Execution Contract` draft. A future harness adapter may consume workflow events through observers or store adapters.
- Do not make trace providers the source of truth. LangSmith/Langfuse/debug traces remain optional derived observability.
- Do not automatically serialize live agents, tools, validators, routers, callables, middleware, or compiled child machines. Cold resume re-supplies the same compiled definition and verifies its definition identifier.
- Do not permit unbounded nested detours, recursive subgraphs, fan-out, event history, or retry loops.
- Do not add new automated test files or verification scripts under the explicitly requested no-tests workflow. Existing checks and inline smoke exercises remain required.
- Do not implement before PR #268 is present on the implementation base, either by merging it to `main` first or by an explicitly approved superseding-branch strategy.

---

## 3. Background & Context

PR #268 (`feat(workflows): add validated state machine orchestration`) is an open, clean draft targeting `main`. At audit time it contains four commits, thirteen changed files, approximately 3,890 inserted lines, no review comments, and no reported checks. It introduces `vidbyte.workflows` with `StateGraph`, `StateMachine`, typed `StateT`, callable/agent stages, validators, conditional routers, guarded routes, cycles, retries, transition limits, observers, and validate-before-commit candidate state.

The current draft intentionally lists durable checkpoint/resume, human approvals, subgraphs, graph-level fan-out/reducers, and nested control as non-goals. Its event records are held only in memory, `_RunState` is mutated directly, immutable records are later replaced with `dataclasses.replace`, and `StageContext.ledger` exposes arbitrary nested mutation. Those choices are reasonable for PR #268's v1 scope but cannot provide append-only replay, cold resume, or reducer-governed updates. Because the feature is still a draft and the SDK is alpha, this is the least costly point to correct those foundations.

The audit found adjacent SDK primitives that should be composed rather than duplicated:

- `AgentForkSettings` already supports exact tool replacement, tool deltas, provider/model/temperature overrides, middleware replacement, history isolation, output schemas, runtime selection, and agent-loop settings.
- `BaseAgent.fork()` creates unique lineage-aware run IDs, clones SDK-bound tools, and reconnects MCP servers from configuration instead of sharing live handles.
- `AgentLoopSettings`, `ToolSettings`, `ModelRetryMiddleware`, `TokenBudgetMiddleware`, `RuntimeLimitMiddleware`, and `CostBudgetMiddleware` already enforce several inner-loop ceilings.
- `LoopDetectionMiddleware` already detects repeated tool inputs and repeated outputs, but it does not cover all five requested signatures or change workflow lifecycle state.
- `ToolPolicyMiddleware` and `PermissionPolicy` provide name/permission gates, but do not hide tools per stage or inspect destructive command arguments and cumulative edit impact.
- `Session` and its stores establish useful patterns for schema-versioned serialization, atomic file writes, cold rehydration, and append-only checkpoints, but its `RunState` is agent-conversation-specific.
- `ContextMinimalFanoutParadigm`, `ParallelPipeline`, and `MapReducePipeline` demonstrate fresh child construction, bounded `asyncio` fan-out, and deterministic input-order joins.
- `WorkflowObserver` already provides a clean adapter seam for future harness-run capture and trace integration.

Capability coverage at PR #268's head:

| Requested capability | PR #268 status | Design response |
|----------------------|----------------|-----------------|
| 1. Named phases and capability restriction | Missing | Stage-owned `StageCapabilities`; `AgentStage` exposes an exact filtered tool catalog |
| 2. Guarded transitions | Implemented | Preserve ordered validators and target guards; add approval after guards |
| 3. Conditional routing and Command | Partial | Preserve `Router`; add bounded `WorkflowCommand(update, goto, ...)` |
| 4. Cycles | Implemented | Preserve cycles and bound them at stage, transition, super-step, and budget layers |
| 5. Orthogonal lifecycle | Missing | Add `WorkflowLifecycleStatus` separate from terminal success/failure |
| 6. Layered ceilings | Partial | Add stage visits, super-steps, model/tool/token/cost usage, fan-out, and detour limits |
| 7. Five-pattern stuck detection | Partial outside workflows | Add policy-aware stuck middleware plus a forced `ERROR` lifecycle transition |
| 8. Human approval | Missing | Add required/risk gates, persisted interrupts, and typed resume commands |
| 9. Destructive-action guards | Partial outside workflows | Add stage action policies, command/path rules, and strict edit-impact budgets |
| 10. Append-only event-sourced state | Missing | Make events canonical and rebuild projections from them |
| 11. Step checkpoint/resume | Missing | Add versioned event/checkpoint stores and cold resume |
| 12. Typed state reducers and reads/writes | Partial | Add `StateSchema`, channels, reducers, and compile/runtime write enforcement |
| 13. Per-stage model routing | Indirect | Add `AgentModelRoute` applied through fork settings and runner options |
| 14. Isolated subgraphs and Send | Missing | Add child machines, summary-only return, bounded fan-out, deterministic join |
| 15. Interrupt-driven detours | Missing | Add signal rules, detour stack frames, and explicit return commands |

The implementation should be a follow-up to PR #268 after that PR lands on `main`. This keeps the original foundational review comprehensible and lets this design modify real files from the latest `main`, as required by the selected workflow. If the user instead wants one superseding PR, that branch/base change must be explicitly approved before Phase 3.

---

## 4. Requirements

### Functional Requirements

1. Existing direct transitions, branches, validators, guards, self-loops, backward edges, retries, typed errors, and sync/async entry points from PR #268 must remain supported unless this document explicitly changes their alpha contract.
2. `StateGraph.add_stage(...)` must accept a named stage policy, declared state `reads`/`writes`, optional `StageCapabilities`, and optional `AgentModelRoute`.
3. A stage with a non-default capability or model profile must implement the policy-aware stage protocol; compilation must reject profiles on opaque custom stages that cannot prove enforcement.
4. `AgentStage` must resolve the stage's tool visibility policy before forking the agent and pass only the selected tool objects to `AgentForkSettings.tools`.
5. Tools excluded by a stage policy must be absent from the child's catalog and provider schemas, not merely denied after the model calls them.
6. Tool names declared in an exact visibility policy must resolve uniquely; missing or duplicate names must fail before the model is invoked.
7. Action policies must execute independently from visibility and permission checks, with state-machine policy evaluated before user middleware and before tool execution.
8. `CommandArgumentGuard` must support case-sensitive prefix allowlists and regular-expression denylists over a configured tool argument.
9. `PathActionGuard` must support allowed and denied globs over configured path arguments.
10. `EditBudgetGuard` must reserve estimated changed lines before an instrumented mutating call, commit or release that reservation after the result, and deny an operation that would exceed the stage's cumulative cap.
11. Strict edit-budget mode must deny a mutating tool without a configured impact estimator; permissive mode may allow it but must record that impact was unknown.
12. Built-in estimators must cover `patch_file`, `replace_text`, and `write_text`; custom/MCP tools may register their own estimator by tool name.
13. The existing ordered stage validators and selected-edge guards must still run before a candidate state commits.
14. A transition with guards and approval must run deterministic guards first so users are never asked to approve an already-invalid edge.
15. Conditional routers must continue returning bounded keys that map through a finite compiled branch map.
16. `WorkflowCommand` must let a stage return reducer updates and one of: a semantic outcome, a declared command `goto`, an interrupt request, a detour-return request, or a set of `Send` requests.
17. A command `goto` must resolve only through `StateGraph.add_command_transition(source, target, ...)`; an ordinary outgoing edge does not implicitly authorize command control.
18. A command target that is unknown, ambiguous, or not declared for its source must raise `WorkflowCommandError` before state commit.
19. Direct and command transitions may target any declared stage or terminal, including the source; cycles and backward edges must compile.
20. `WorkflowLifecycleStatus` must include `RUNNING`, `WAITING_FOR_CONFIRMATION`, `INTERRUPTED`, `FINISHED`, and `ERROR`.
21. Lifecycle status must be separate from the existing declared terminal status. A failed terminal is a normal `FINISHED` workflow outcome; an infrastructure, policy, stuck, or unrecoverable budget failure is lifecycle `ERROR`.
22. Every lifecycle change must be represented by an appended typed event and validated against the allowed lifecycle transition table.
23. `StagePolicy.max_visits` must cap entries into one named stage across retries, cycles, detours, and resumes.
24. `StagePolicy.retry` and `timeout_seconds` must retain their current stage-callback semantics.
25. `AgentModelRoute.max_iterations` and model retry policy must be applied to the fresh stage agent without silently weakening a stricter remaining global budget.
26. `StateMachineSettings` must support global ceilings for super-steps, selected transitions, model calls, tool calls, tokens, estimated cost, elapsed time, subgraph concurrency, recursion depth, and detour depth.
27. Every selected transition, rejected guard redirect, approval rejection route, subgraph invocation, and detour entry/return must consume the appropriate deterministic budget counter.
28. Agent stages and agent validators must produce `UsageReport` values from reply/grader metadata when available; generic stages may report usage explicitly.
29. A configured cost ceiling must require a `CostModel` capable of pricing reported usage. Unknown cost must fail closed by default and may be made fail-open only by an explicit setting.
30. Child subgraph usage must be charged to both the child budget and the root run budget.
31. Concurrent fan-out must reserve bounded child budget slices before launch so siblings cannot collectively claim more than the parent's remaining allocation.
32. The default stuck detector must recognize at least: four identical action/observation pairs, three identical action/error cycles, repeated model monologues without tool calls, alternating action ping-pongs, and repeated context-window errors.
33. Stuck fingerprints must normalize tool names, arguments, result/error content, and monologue text while ignoring timestamp-, UUID-, run-id-, and sequence-like fields.
34. Stuck detection must not use embeddings or another model call.
35. When a stuck signature reaches its threshold, the injected agent middleware must abort at the next safe agent boundary, append `STUCK_DETECTED`, set lifecycle `ERROR`, persist a checkpoint, and raise `WorkflowStuckError` carrying the run snapshot.
36. A required transition approval must always suspend regardless of the run's optional risk-confirmation policy.
37. `NeverConfirm` must auto-continue optional risk checks but may not bypass a required approval edge.
38. `AlwaysConfirm` must suspend before every otherwise-valid transition.
39. `ConfirmRisky` must suspend only transitions whose declared risk meets or exceeds its configured threshold.
40. Suspension must append an approval request with a unique request ID, persist the pending candidate/edge in a checkpoint, set lifecycle `WAITING_FOR_CONFIRMATION`, and return a nonterminal `StateMachineResult`.
41. `ResumeCommand.approve(...)` must continue the exact pending edge without rerunning the completed source stage; rejection must route its declared rejection outcome with unchanged committed state.
42. A stale, duplicate, mismatched, or wrong-kind approval response must fail without appending a state commit.
43. `StageContext.interrupt(request)` must support LangGraph-like replay semantics: on first execution it suspends; on resume the stage restarts and the same interrupt ordinal returns the supplied resume value.
44. Stage code before an interrupt must receive a stable `idempotency_key`, and documentation must require that pre-interrupt external work be idempotent because Python coroutine frames are not serialized.
45. Workflow state changes must be represented only by appended events. Runtime projections and result records must not be edited or replaced in place.
46. The default runtime must use `InMemoryWorkflowStore`, so even an ephemeral run has one canonical append-only event stream.
47. Event append failure must fail closed; observers and trace adapters run after the canonical append and remain fail-open.
48. Every event must carry schema version, event ID, definition ID, run ID, monotonic sequence, super-step, event type, timestamp, and a bounded typed payload.
49. Appends must use optimistic expected-sequence checks so two writers cannot silently create the same next event.
50. `WorkflowProjector` must reconstruct lifecycle, workflow position, committed state, observations, budgets, pending approval/interrupt, detour stack, subgraph lineage, records, and terminal/error state from events.
51. `StateMachine.inspect(run_id, through_sequence=...)` must replay without invoking stages, validators, routers, tools, models, observers, or external effects.
52. The graph must have a deterministic `definition_id` derived from its declared structure, policies, stable component names, and caller-supplied definition version.
53. Durable stores must reject execution or resume of an unversioned definition.
54. Resume must reject a checkpoint whose definition ID, schema version, state-schema version, or reducer identifiers differ from the supplied compiled machine.
55. `WorkflowCheckpointPolicy.PER_STEP` must write an immutable checkpoint after every completed super-step, suspension, terminal, and error boundary.
56. Checkpoints must store the last event sequence, committed state, immediate observations, current stage, counters/usage, lifecycle, feedback, pending edge/interrupt, detour stack, and unresolved subgraph sends.
57. Resume must load the newest compatible checkpoint and replay any later events before deciding whether to rerun an incomplete stage or continue from a completed boundary.
58. Stage callbacks must receive stable run, super-step, visit, attempt, and idempotency identifiers so re-execution after a crash can be deduplicated by external systems.
59. `StateSchema` must support Pydantic models, dataclasses, TypedDict-compatible annotations, and a custom validator/codec fallback.
60. A state channel must declare a stable reducer identifier, reducer implementation, default factory, and commit mode.
61. Built-in reducers must include replace, append, mapping merge, and set-union semantics; custom reducers must be synchronous and deterministic.
62. Command updates must contain only channels declared in the current stage's `writes`; unknown or undeclared keys must raise `WorkflowStateError` before validators run.
63. Declared `reads` and `writes` must be exposed by graph introspection and included in the definition fingerprint.
64. A channel with `commit_mode=ON_TRANSITION` must remain a candidate until validators, guards, and approval pass.
65. A channel with `commit_mode=IMMEDIATE` must be updated through `await StageContext.observe(channel, value)`, append its event immediately, and survive stage failure or candidate rejection.
66. PR #268's mutable nested ledger must not remain an untracked mutation escape hatch. `arun(ledger=...)` may initialize immediate channels and `result.ledger` may remain a read-only compatibility projection, but `StageContext.ledger.setdefault(...).add(...)` must be removed from docs and rejected.
67. Whole-state `StageResult(state=...)` must remain available through an implicit root replace channel for simple graphs. Explicit multi-channel schemas with declared writes must use `WorkflowCommand.update`.
68. `AgentModelRoute` must support provider, model name, temperature, runner options (including provider-supported thinking configuration), agent loop settings, model retry policy, and per-invocation middleware factories.
69. Stage model settings must be applied through a fresh history-free fork by default, with a unique child run ID and workflow lineage metadata.
70. Runner options must survive `BaseAgent.fork()`, export/restore, and durable Session serialization; old Session payloads without the additive field must default to an empty mapping.
71. State-machine-injected middleware instances must be created per agent invocation. Caller-provided custom middleware concurrency safety remains caller-owned and documented.
72. `StateGraph.add_subgraph(...)` must bind a named compiled child machine, input mapper, summary mapper, allowed parent update channels, and child budget policy.
73. A child run must use a distinct run ID/event stream/checkpoint lineage and receive only the mapped state slice plus explicit metadata; it must not receive parent stage history or event payloads.
74. The parent and child may share the external workspace, but the workflow API must not claim filesystem isolation or rollback.
75. Parent events must store child run IDs, terminal/lifecycle summaries, usage, and the declared summary only; full child events remain in the child stream.
76. `Send` fan-out must honor a concurrency limit, isolate every child, collect failures according to an explicit fail-fast or collect policy, and apply successful join updates in original send order rather than completion order.
77. If a child waits for confirmation or interrupts, the parent must become `INTERRUPTED` with child references and resume the unresolved child before joining.
78. `StateGraph.add_detour(...)` must register a bounded signal matcher, detour entry stage, return mode, and optional rejection route.
79. Agent-stage detour rules must be evaluated after successful tool calls by injected middleware. A match may abort the current agent invocation at that tool boundary and return a typed detour request to the workflow runtime.
80. Entering a detour must push an immutable return frame containing the interrupted source, signal, resume mode, and continuation metadata.
81. A detour must return only through `WorkflowCommand.return_from_detour(...)`; the runtime must reject return commands when no frame exists.
82. Tool-boundary detours default to rerunning the interrupted source stage with structured feedback; post-stage detours may resume a pending declared continuation.
83. Detours may nest only up to `max_detour_depth`, and every entry/return must be event-sourced and checkpointed.
84. All new public names must be exported from `vidbyte.workflows`; the primary ergonomic names must also be available from root `vidbyte`.
85. Root README, workflow README, agent/tool READMEs, `llms.txt`, and the generated artifact file index must describe the final surface and its layer boundaries.

### Non-Functional Requirements

- **Determinism:** With fixed component outputs and human resume values, reducers, route selection, event order, budget accounting, joins, and lifecycle transitions must be deterministic. Fan-out results merge in input order.
- **Performance:** Graph compilation must remain O(nodes + edges + channels + rules). Runtime overhead must be O(appended events + executed components); checkpoint creation is O(serialized projection size).
- **Concurrency:** One compiled machine must be reentrant. In-memory store mutations, event sequence allocation, budget reservation, and concurrent sends require async locking or optimistic concurrency.
- **Durability:** File events/checkpoints must use atomic per-record writes. A crash may leave a started but incomplete super-step; resume must detect and rerun it rather than invent completion.
- **Security:** The model sees only stage-visible tools. Action policies fail closed where configured. Event/checkpoint stores contain resumable state and therefore require caller-controlled access, retention, and encryption-at-rest decisions.
- **Privacy:** Inspection records still omit optional diagnostic snapshots by default, but canonical event updates/checkpoints necessarily contain the data required for replay. Documentation must make this distinction explicit.
- **Reliability:** Canonical event append is fail-closed; optional observers are fail-open. State/reducer/definition mismatch, stale approvals, unknown usage under a hard cost cap, and unmeasurable strict mutations fail before unsafe progression.
- **Idempotency:** The runtime supplies keys and boundary semantics but cannot make arbitrary external effects idempotent. Stage and tool authors own deduplication or compensation.
- **Observability:** Every lifecycle, budget, stage, validation, route, action-policy, stuck, approval, interrupt, state update, checkpoint, detour, send, child, terminal, and error boundary has a typed event.
- **Compatibility:** Existing non-workflow SDK APIs remain unchanged. PR #268's whole-state stages continue in compatibility mode; its mutable ledger behavior is intentionally tightened before public release.
- **Packaging:** No new third-party dependency is required. Memory/file persistence uses Python 3.11 standard library and existing Pydantic.
- **Verification:** No test files/scripts are added, but compileall, the complete existing unittest suite, import/build checks, and comprehensive inline deterministic/resume/security/fan-out smoke exercises are mandatory.

---

## 5. High-Level Design

The expanded package separates declaration, execution, state reduction, persistence, and agent policy. `StateGraph` remains the mutable declaration surface and compiles an immutable definition. `StateSchema` owns typed channels and reducers. `WorkflowCommand` is the common stage result for partial updates, routing, interrupts, signals, and sends. `StateMachine` executes super-steps but treats the append-only event store as source of truth; a `WorkflowProjector` derives all mutable-looking runtime views from those events. Checkpoints are immutable replay accelerators, never replacements for the event log.

Agent policy remains composed rather than embedded in the generic machine. A stage definition carries `StageCapabilities` and `AgentModelRoute`; policy-aware `AgentStage` converts them into an exact tool list, fresh fork settings, fresh enforcement middleware, and inner-loop limits. This makes the graph the policy authority while preserving an honest boundary: custom Python callbacks that bypass SDK agents/tools cannot be intercepted.

Human approval, explicit interrupts, detours, and child runs all converge on the same persisted suspension model. The runtime appends a request, projects lifecycle to a non-running state, checkpoints the pending continuation, and returns. Cold resume supplies a typed `ResumeCommand`, verifies the request and compiled definition, appends the answer, reconstructs projection, and continues. No coroutine or live agent is serialized.

Subgraphs are separate machines rather than shared call stacks. A parent maps an input slice into a child, the child gets its own run/event/checkpoint context, and only a declared summary/update returns. `Send` repeats this operation concurrently with preallocated budgets and deterministic joins. The external workspace can still be shared, matching current agent-harness behavior without pretending it is isolated.

```text
                                      [StateGraph + StateSchema]
                                                |
                                          compile + fingerprint
                                                v
                                      [Immutable StateMachine]
                                                |
                             start/resume/inspect with WorkflowStore
                                                |
                                                v
     +------------------------- append typed event --------------------------+
     |                                                                       |
     v                                                                       v
[WorkflowProjector] ---> lifecycle / state / budgets / pending work   [Observers/Trace]
     |
     v
[StageContext: typed state, observations, idempotency, policies]
     |
     +--> [AgentStage]
     |      exact tools -> action guards -> detour/stuck middleware
     |      per-stage provider/model/thinking/loop limits
     |
     +--> [Callable/custom policy-aware stage]
     |
     v
[WorkflowCommand: update | outcome/goto | interrupt | sends | signals]
     |
     +--> reducers -> validators -> route -> guards -> approval -> commit
     +--> interrupt/approval -> checkpoint -> return nonterminal result
     +--> detour stack -> validation path -> explicit return
     `--> child StateMachines -> summary-only deterministic join
```

---

## 6. Detailed Design

### 6.1 Public Runtime, Lifecycle, Command, and Budget Contracts

**File(s):** `vidbyte/workflows/contracts.py`, `vidbyte/workflows/budget.py`, `vidbyte/workflows/errors.py`
**Type:** Modified files and new file

#### What it does

Defines the stable public language for lifecycle, commands, suspensions, usage, budgets, results, and new failure families. The current terminal `MachineStatus` remains as a compatibility alias for `TerminalStatus`; lifecycle is a separate field.

#### Interface / API

```python
class WorkflowLifecycleStatus(str, Enum):
    RUNNING = "running"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    INTERRUPTED = "interrupted"
    FINISHED = "finished"
    ERROR = "error"

class TerminalStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class WorkflowCheckpointPolicy(str, Enum):
    PER_STEP = "per_step"
    MANUAL = "manual"

@dataclass(frozen=True, slots=True)
class UsageReport:
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    provider: str | None = None
    model: str | None = None

@dataclass(frozen=True, slots=True)
class WorkflowBudget:
    max_super_steps: int = 100
    max_transitions: int = 100
    max_model_calls: int | None = None
    max_tool_calls: int | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    timeout_seconds: float | None = None
    max_subgraph_concurrency: int = 8
    max_recursion_depth: int = 8
    max_detour_depth: int = 4

@dataclass(frozen=True, slots=True)
class StagePolicy:
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: float | None = None
    max_visits: int | None = None
    error_outcome: str | None = None

@dataclass(frozen=True, slots=True)
class WorkflowInterrupt:
    namespace: str
    prompt: str
    schema: type[BaseModel] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class WorkflowCommand(Generic[StateT]):
    update: Mapping[str, Any] = field(default_factory=dict)
    outcome: str | None = None
    goto: str | None = None
    sends: tuple[Send, ...] = ()
    signals: tuple[WorkflowSignal, ...] = ()
    interrupt: WorkflowInterrupt | None = None
    return_from_detour: str | None = None
    usage: UsageReport | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ResumeCommand:
    request_id: str
    value: Any = None
    approved: bool | None = None

    @classmethod
    def approve(cls, request_id: str, value: Any = None) -> ResumeCommand: ...

    @classmethod
    def reject(cls, request_id: str, value: Any = None) -> ResumeCommand: ...

    @classmethod
    def resume(cls, request_id: str, value: Any) -> ResumeCommand: ...

@dataclass(frozen=True, slots=True)
class StateMachineResult(Generic[StateT]):
    run_id: str
    definition_id: str
    lifecycle: WorkflowLifecycleStatus
    terminal_status: TerminalStatus | None
    terminal: str | None
    state: StateT
    observations: Mapping[str, Any]
    pending: PendingRequest | None
    usage: UsageReport
    checkpoint_id: str | None
    stages: tuple[StageExecution, ...]
    transitions: tuple[TransitionRecord, ...]
    events: tuple[WorkflowEvent, ...]
    observer_errors: tuple[str, ...]
    error: WorkflowErrorRecord | None
    duration_ms: float
```

New public errors extend the existing workflow family: `WorkflowBudgetError`, `WorkflowCommandError`, `WorkflowPersistenceError`, `WorkflowResumeError`, `WorkflowApprovalError`, `WorkflowInterruptError`, `WorkflowStuckError`, `WorkflowCapabilityError`, `WorkflowDetourError`, and `WorkflowSubgraphError`. Execution errors carry a safe `StateMachineResult` or projected snapshot when available.

#### Logic / Algorithm

1. Validate every positive bound and finite monetary/timeout value at construction.
2. Aggregate usage monotonically; unknown token/cost components remain unknown rather than becoming zero.
3. Apply local and remaining-global limits by taking the stricter bound.
4. Keep cancellation as `BaseException`; append/checkpoint cancellation evidence best-effort, then re-raise unchanged.
5. Preserve `.status` as a read-only compatibility alias for terminal status when lifecycle is `FINISHED`.

#### Edge Cases & Error Handling

- A nonterminal result has `terminal=None` and `terminal_status=None`.
- A lifecycle `ERROR` may carry the last committed state and partial records but never a fabricated terminal.
- A hard cost budget with unpriceable usage fails according to `unknown_cost_policy`, defaulting to fail closed.
- A command may select exactly one primary control action; conflicting `goto`, `interrupt`, detour return, or sends fail before updates are applied.

### 6.2 Typed State Channels, Reducers, Codecs, and Observations

**File(s):** `vidbyte/workflows/state.py`, `vidbyte/workflows/contracts.py`
**Type:** New file and modified file

#### What it does

Replaces uncontrolled shared mutation with typed channels. Transition-bound updates remain candidates; immediate observation channels append and reduce at once so facts such as files visited survive rejected work and cold resume.

#### Interface / API

```python
class StateCommitMode(str, Enum):
    ON_TRANSITION = "on_transition"
    IMMEDIATE = "immediate"

class StateReducer(Protocol):
    @property
    def reducer_id(self) -> str: ...

    def reduce(self, current: Any, update: Any) -> Any: ...

class StateCodec(Protocol[StateT]):
    @property
    def codec_id(self) -> str: ...

    def encode(self, state: StateT) -> Mapping[str, Any]: ...

    def decode(self, payload: Mapping[str, Any]) -> StateT: ...

@dataclass(frozen=True, slots=True)
class StateChannel:
    reducer: StateReducer
    default_factory: Callable[[], Any]
    commit_mode: StateCommitMode = StateCommitMode.ON_TRANSITION
    sensitive: bool = False

class StateSchema(Generic[StateT]):
    def __init__(self, state_type: Any, *, channels: Mapping[str, StateChannel], codec: StateCodec[StateT] | None = None, version: str = "1") -> None: ...

    def apply(self, state: StateT, updates: Mapping[str, Any], *, allowed_writes: Collection[str]) -> StateT: ...

    def encode(self, state: StateT) -> Mapping[str, Any]: ...

    def decode(self, payload: Mapping[str, Any]) -> StateT: ...

class StageContext(Generic[StateT]):
    async def observe(self, channel: str, value: Any) -> Any:
        # Appends and reduces one immediate observation before returning its projected value.
        ...

    def interrupt(self, request: WorkflowInterrupt) -> Any:
        # Returns a stored resume value at the same ordinal or raises an internal suspension signal.
        ...
```

Built-ins are classes with stable IDs: `ReplaceReducer`, `AppendReducer`, `MergeMappingReducer`, `SetUnionReducer`, and `CallableReducer`. `StateSchema.root(state_type)` creates PR #268-compatible whole-state replacement semantics.

#### Logic / Algorithm

1. Compile Pydantic `TypeAdapter` support for Pydantic models, dataclasses, and TypedDict-like schemas; use a custom codec/validator for unsupported classes.
2. Convert a command update into a candidate by cloning encoded channel values, running each reducer once in key order, and revalidating `StateT`.
3. Reject writes outside the stage's compiled write set.
4. Append immediate observation intent, reduce it, append the resulting observation event, and update projection before returning to the stage.
5. Include channel names, reducer IDs, commit modes, and schema version in the definition fingerprint.
6. Expose a read-only `result.ledger` alias over observations for transition assistance, but do not expose nested mutable values to stage code.

#### Edge Cases & Error Handling

- Reducers must not mutate their input. The runtime clone-validates the result and raises `WorkflowStateError` on aliasing or invalid output.
- A custom reducer ID/version change makes existing durable checkpoints incompatible by design.
- Immediate observations cannot be rolled back. Use transition-bound channels for candidate business state.
- Durable replay necessarily stores update data. `sensitive=True` removes values from diagnostic summaries, not from the canonical encrypted/access-controlled store needed for resume.

### 6.3 Graph Declaration, Commands, Approvals, Detours, and Compilation

**File(s):** `vidbyte/workflows/graph.py`, `vidbyte/workflows/routing.py`, `vidbyte/workflows/approval.py`, `vidbyte/workflows/detours.py`
**Type:** Modified files and new files

#### What it does

Extends the builder with state data dependencies, command edges, transition risk/approval, detour rules, named child graphs, and a stable definition identity while preserving current direct/branch routes.

#### Interface / API

```python
class StateGraph(Generic[StateT]):
    def __init__(self, state_type: Any, *, name: str = "workflow", version: str | None = None, state_schema: StateSchema[StateT] | None = None, state_validator: Callable[[Any], StateT] | None = None, state_cloner: Callable[[StateT], StateT] = deepcopy) -> None: ...

    def add_stage(self, name: str, stage: Stage[StateT], *, validators: Sequence[Validator[StateT]] = (), policy: StagePolicy | None = None, reads: Collection[str] = (), writes: Collection[str] = (), capabilities: StageCapabilities | None = None, model_route: AgentModelRoute | None = None) -> StateGraph[StateT]: ...

    def add_transition(self, source: str, target: str, *, on: str = "success", guards: Sequence[Validator[StateT]] = (), approval: ApprovalGate | None = None, risk: RiskLevel = RiskLevel.LOW) -> StateGraph[StateT]: ...

    def add_branch(self, source: str, router: Router[StateT], routes: Mapping[str, RouteTarget[StateT]], *, on: str = "success") -> StateGraph[StateT]: ...

    def add_command_transition(self, source: str, target: str, *, guards: Sequence[Validator[StateT]] = (), approval: ApprovalGate | None = None, risk: RiskLevel = RiskLevel.LOW) -> StateGraph[StateT]: ...

    def add_detour(self, rule: DetourRule, *, target: str, return_mode: DetourReturnMode = DetourReturnMode.RETRY_SOURCE, rejection_outcome: str | None = None) -> StateGraph[StateT]: ...

    def add_subgraph(self, name: str, machine: StateMachine[Any], *, input_mapper: SubgraphInputMapper[StateT], summary_mapper: SubgraphSummaryMapper[StateT], writes: Collection[str], budget: ChildBudgetPolicy | None = None) -> StateGraph[StateT]: ...

    def compile(self, *, settings: StateMachineSettings | None = None) -> StateMachine[StateT]: ...
```

`ApprovalGate` distinguishes required approval from optional risk policy and declares a rejection outcome. `DetourRule` contains a stable rule ID plus a deterministic `SignalMatcher`. `RouteTarget` gains risk and approval fields for branch-specific policy.

#### Logic / Algorithm

1. Preserve all PR #268 graph checks.
2. Validate reads/writes against state channels, immediate observation use, command-edge uniqueness, approval rejection routes, detour targets/return routes, subgraph names, join write sets, and recursion depth.
3. Require non-default execution profiles only on policy-aware stages.
4. Build separate lookups for outcome routes and command target routes so one cannot impersonate the other.
5. Include stable component names, stage policies, state schema, routes, guards, approval/risk, capabilities, model routes, detours, subgraphs, settings, and explicit version in canonical definition JSON.
6. Hash that canonical JSON into `wfdef_<sha256>`.
7. Reject a durable store at run time if `version` was omitted.

#### Edge Cases & Error Handling

- Callable bytecode, prompt text hidden inside a custom object, credentials, and live tool instances are not hashed. Durable users must bump `version` whenever such behavior changes.
- A stage with both an outcome edge and a command edge to the same target is legal because the selection mechanisms are distinct.
- A detour rule may match several signals; declaration order wins and the event records all candidate rule IDs.
- Compile-time reachability includes command, branch, detour, and subgraph-continuation edges while still permitting cycles.

### 6.4 Append-Only Events, Projection, Persistence, Checkpoints, and Replay

**File(s):** `vidbyte/workflows/events.py`, `vidbyte/workflows/projection.py`, `vidbyte/workflows/persistence.py`, `vidbyte/workflows/stores/__init__.py`, `vidbyte/workflows/stores/memory.py`, `vidbyte/workflows/stores/file.py`
**Type:** New files

#### What it does

Makes the event stream canonical, defines the projection/replay algorithm, and provides pluggable in-memory and atomic file persistence. Checkpoints cache projections but never supersede or rewrite events.

#### Interface / API

```python
WORKFLOW_SCHEMA_VERSION: int = 1

@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    schema_version: int
    event_id: str
    definition_id: str
    run_id: str
    sequence: int
    super_step: int
    event_type: WorkflowEventType
    occurred_at: str
    payload: WorkflowEventPayload

@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint(Generic[StateT]):
    checkpoint_id: str
    definition_id: str
    run_id: str
    event_sequence: int
    super_step: int
    state_payload: Mapping[str, Any]
    projection_payload: Mapping[str, Any]
    created_at: str

@runtime_checkable
class WorkflowStore(Protocol):
    @property
    def durable(self) -> bool: ...

    async def put_definition(self, definition: WorkflowDefinitionRecord) -> WorkflowDefinitionRecord: ...

    async def begin_run(self, event: WorkflowEvent) -> WorkflowEvent: ...

    async def append(self, event: WorkflowEvent, *, expected_sequence: int) -> WorkflowEvent: ...

    async def events(self, run_id: str, *, after_sequence: int = 0, through_sequence: int | None = None) -> tuple[WorkflowEvent, ...]: ...

    async def put_checkpoint(self, checkpoint: WorkflowCheckpoint[Any]) -> WorkflowCheckpoint[Any]: ...

    async def latest_checkpoint(self, run_id: str) -> WorkflowCheckpoint[Any] | None: ...

class WorkflowProjector(Generic[StateT]):
    def replay(self, definition: CompiledWorkflowDefinition[StateT], events: Sequence[WorkflowEvent], *, checkpoint: WorkflowCheckpoint[StateT] | None = None) -> WorkflowProjection[StateT]: ...

class InMemoryWorkflowStore(WorkflowStore): ...
class FileWorkflowStore(WorkflowStore): ...
```

Typed payload dataclasses cover definition/run start, lifecycle, stage attempts, observations, usage, validation, transition selection/rejection/commit, action authorization/denial, stuck detection, approval/interrupt request/response, checkpoint boundaries, detour frames, sends, child completion, terminal, and error.

File layout:

```text
<root>/
  definitions/<definition_id>.json
  runs/<run_id>/
    events/<sequence>-<event_id>.json
    checkpoints/<event_sequence>-<checkpoint_id>.json
```

#### Logic / Algorithm

1. Append one event through expected-sequence compare-and-set.
2. Notify observers only after the store confirms the append.
3. Reduce the persisted event into the in-memory projection.
4. At a checkpoint boundary, serialize the projection and atomically create a new checkpoint record.
5. On resume, load the latest compatible checkpoint, then replay later events in sequence.
6. On inspection/time travel, replay from the nearest checkpoint at or before the requested sequence without executing user code.
7. File store writes each event/checkpoint to a same-directory temporary file and uses `os.replace`; it never overwrites an existing final record.
8. In-memory store uses one async lock for definitions, runs, event sequences, checkpoints, and budget reservations.

#### Edge Cases & Error Handling

- A crash after `STAGE_STARTED` but before a completed boundary leaves an incomplete attempt; resume appends a restart event and reruns with the same idempotency key.
- A crash after an external effect but before the corresponding event cannot be solved generically; the idempotency contract is mandatory.
- Duplicate event IDs, wrong expected sequences, nonmonotonic checkpoints, definition collisions, and corrupt payloads raise `WorkflowPersistenceError`.
- File-store multiprocess writers are protected only by optimistic file existence and expected sequence; a database adapter is required for stronger distributed concurrency.
- Event/checkpoint retention and deletion are caller-owned. The runtime never silently prunes replay data.

### 6.5 Event-Sourced State Machine Execution and Resume

**File(s):** `vidbyte/workflows/machine.py`, `vidbyte/workflows/contracts.py`
**Type:** Modified files

#### What it does

Refactors the current `_WorkflowRun` loop so events and projections, rather than `_RunState` mutation, drive execution. Adds cold resume, inspect, lifecycle suspension, and checkpoint boundaries.

#### Interface / API

```python
class StateMachine(Generic[StateT]):
    async def arun(self, initial_state: StateT, *, run_id: str | None = None, observations: Mapping[str, Any] | None = None, ledger: Mapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, observers: Sequence[WorkflowObserver] = (), store: WorkflowStore | None = None, checkpoint_policy: WorkflowCheckpointPolicy = WorkflowCheckpointPolicy.PER_STEP, confirmation_policy: ConfirmationPolicy | None = None) -> StateMachineResult[StateT]: ...

    async def aresume(self, run_id: str, *, command: ResumeCommand | None = None, store: WorkflowStore | None = None, observers: Sequence[WorkflowObserver] = (), confirmation_policy: ConfirmationPolicy | None = None) -> StateMachineResult[StateT]: ...

    async def inspect(self, run_id: str, *, store: WorkflowStore | None = None, through_sequence: int | None = None) -> StateMachineResult[StateT]: ...

    def run(self, initial_state: StateT, **kwargs: Any) -> StateMachineResult[StateT]: ...

    def resume(self, run_id: str, **kwargs: Any) -> StateMachineResult[StateT]: ...
```

#### Logic / Algorithm

1. Validate/store the compiled definition and append `RUN_STARTED` containing encoded initial state and initial immediate observations.
2. Project lifecycle `RUNNING`, entry stage, zero counters, and the initial state.
3. Start a super-step by checking global/stage budgets and appending `STAGE_STARTED` with stable IDs.
4. Run the stage against a clone plus event-backed observation/interrupt services.
5. Normalize `StageResult` or `WorkflowCommand`, report usage, create the candidate through reducers, and run state-contract validation.
6. Run stage validators and append each result.
7. Resolve outcome, branch, or declared command route; append selection and consume transition budget.
8. Run guards. On rejection, discard the candidate and follow the declared semantic recovery route using committed state.
9. Evaluate required/risk approval. If needed, append request, checkpoint pending candidate/edge, return `WAITING_FOR_CONFIRMATION`.
10. Evaluate post-stage detour signals. If matched, push a frame and enter the detour without losing the pending continuation.
11. Commit reducer updates only after all gates pass, append state commit, enter target, and checkpoint the completed super-step.
12. On terminal, append terminal/lifecycle events, checkpoint, and return `FINISHED`.
13. On stuck/budget/persistence/unrecoverable execution failure, append safe error/lifecycle evidence when possible, checkpoint, then raise the typed error.
14. Resume validates the definition and request, replays projection, appends the response/restart event, and continues from the exact pending boundary.
15. Inspect performs only store reads and projection.

#### Edge Cases & Error Handling

- Approval resume does not rerun the source stage; explicit stage interrupts do rerun because Python frames are not durable.
- A resume command supplied to a running, finished, error, or wrong-kind pending run fails.
- A run cancelled while children are active cancels in-process tasks, records safe child states where possible, checkpoints the parent interruption, and re-raises cancellation.
- Observer errors are captured as diagnostics but do not become canonical control-flow events unless an explicit observer adapter emits its own event.

### 6.6 Agent Model Routing, Tool Visibility, and Action Safety

**File(s):** `vidbyte/workflows/capabilities.py`, `vidbyte/workflows/stages.py`, `vidbyte/lib/dataclasses/agents.py`, `vidbyte/agents/base.py`, `vidbyte/agents/fork.py`, `vidbyte/lib/dataclasses/sessions.py`, `vidbyte/sessions/serialization.py`
**Type:** New file and modified files

#### What it does

Makes an `AgentStage` enforce the compiled stage profile and extends agent runner configuration so provider-supported thinking options can vary by stage and survive forks/session restore.

#### Interface / API

```python
class ToolVisibilityMode(str, Enum):
    INHERIT = "inherit"
    NONE = "none"
    EXACT = "exact"
    READ_ONLY = "read_only"

@dataclass(frozen=True, slots=True)
class ToolVisibility:
    mode: ToolVisibilityMode
    names: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class StageCapabilities:
    tools: ToolVisibility = field(default_factory=ToolVisibility.inherit)
    action_policy: ActionPolicy = field(default_factory=ActionPolicy)

@dataclass(frozen=True, slots=True)
class AgentModelRoute:
    provider: ModelProvider | str | None = None
    model_name: str | None = None
    temperature: float | None = None
    runner_options: Mapping[str, Any] = field(default_factory=dict)
    max_iterations: int | None = None
    loop_settings: AgentLoopSettings | None = None
    model_retry: ModelRetryPolicy | None = None
    middleware_factories: tuple[Callable[[], AgentMiddleware], ...] = ()

class ActionGuard(Protocol):
    @property
    def guard_id(self) -> str: ...

    def evaluate(self, context: ActionContext) -> ActionDecision: ...

class ActionImpactEstimator(Protocol):
    def estimate(self, call: ToolCall) -> ActionImpact: ...

class AgentStage(Generic[StateT]):
    @property
    def supports_execution_policy(self) -> bool: ...

    async def run(self, context: StageContext[StateT]) -> StageResult[StateT] | WorkflowCommand[StateT]: ...
```

`AgentRunnerConfig` and `AgentForkSettings` gain `runner_options: Mapping[str, Any] | None`. `BaseAgent` accepts `runner_options`, passes them to `Runner.from_model(options=...)`, exports/restores them, and preserves them through forks. Session `RunState` gains an additive defaulted `runner_options` mapping.

#### Logic / Algorithm

1. Resolve the base agent or factory.
2. Inspect its tool objects and specs, resolve the exact stage-visible tuple, and reject policy mismatches.
3. Create fresh state-machine middleware for action guards, detour signals, stuck detection, remaining budgets, and model retry.
4. Merge enforcement middleware before caller middleware; enforcement cannot be reordered behind user policy.
5. Build `AgentForkSettings` with exact tools, fresh history, model/provider/temperature/runner options, stricter loop settings, middleware, and workflow lineage IDs.
6. Run the agent, extract usage and control metadata, and only then invoke the developer's result builder.
7. Convert state-machine middleware abort reasons to typed internal control results instead of letting the result builder accidentally treat a stopped agent as success.

#### Edge Cases & Error Handling

- `READ_ONLY` selects only `SAFE` and `READ` tool specs. A tool whose spec cannot be inspected fails closed.
- Non-linear or aggregate agents that cannot accept the required fork/middleware overrides must use a context-aware factory or fail before invocation.
- Unknown custom middleware may still share mutable instance state; injected middleware is per invocation, and existing SDK concurrency rules remain documented.
- `runner_options` may include `thinking_config`, `extra_body`, output-token limits, or provider-safe config fields; `Runner` continues filtering options to the selected modality's config dataclass.
- Credential-like runner options remain runtime configuration and are scrubbed by Session serialization rules.

### 6.7 Five-Pattern Stuck Detection

**File(s):** `vidbyte/workflows/detection.py`, `vidbyte/workflows/stages.py`
**Type:** New file and modified file

#### What it does

Adds a workflow-owned, agent-runtime middleware detector that covers the supplied signatures and returns typed evidence to the state machine.

#### Interface / API

```python
class StuckPattern(str, Enum):
    IDENTICAL_ACTION_OBSERVATION = "identical_action_observation"
    IDENTICAL_ACTION_ERROR = "identical_action_error"
    REPEATED_MONOLOGUE = "repeated_monologue"
    ACTION_PING_PONG = "action_ping_pong"
    CONTEXT_WINDOW_ERROR = "context_window_error"

@dataclass(frozen=True, slots=True)
class StuckDetectionPolicy:
    identical_action_observation: int = 4
    identical_action_error: int = 3
    repeated_monologue: int = 3
    action_ping_pong_cycles: int = 3
    context_window_errors: int = 3
    history_window: int = 20

class StuckDetectorMiddleware(AgentMiddleware): ...
```

#### Logic / Algorithm

1. Canonicalize tool name/arguments and normalized output or error content after each tool call.
2. Count repeated action/observation and action/error pairs across the bounded window.
3. Track assistant text from iterations with no external tool call; normalize whitespace and volatile identifiers.
4. Detect an alternating `A, B, A, B...` suffix using canonical action keys.
5. Normalize context-window exceptions by type/category and stripped numeric limits.
6. Abort with `stuck_detected` and a safe pattern/fingerprint/count payload at threshold.
7. Let `AgentStage` turn that abort into `WorkflowStuckError`; the machine appends the lifecycle transition.

#### Edge Cases & Error Handling

- Similar but nonidentical content is not merged by an LLM or embedding; “semantic” here means stable content identity after volatile-field normalization.
- Internal completion/tools are excluded by default.
- Detector history is per agent invocation. Workflow-level repeated stage visits are bounded separately by stage/global budgets.
- Raw prompts, large tool outputs, and error bodies are not copied into workflow errors; events store hashes and bounded previews.

### 6.8 Human Approval and Explicit Interrupts

**File(s):** `vidbyte/workflows/approval.py`, `vidbyte/workflows/contracts.py`, `vidbyte/workflows/machine.py`
**Type:** New file and modified files

#### What it does

Defines approval/risk policies and shared persisted suspension contracts for edge gates and stage interrupts.

#### Interface / API

```python
class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class ConfirmationPolicy(Protocol):
    def requires_confirmation(self, context: ApprovalContext) -> bool: ...

class NeverConfirm: ...
class AlwaysConfirm: ...

@dataclass(frozen=True, slots=True)
class ConfirmRisky:
    minimum_risk: RiskLevel = RiskLevel.HIGH

@dataclass(frozen=True, slots=True)
class ApprovalGate:
    required: bool = False
    reason: str = ""
    rejection_outcome: str = "approval_denied"

@dataclass(frozen=True, slots=True)
class PendingRequest:
    request_id: str
    kind: str
    stage: str
    target: str | None
    prompt: str
    schema_name: str | None
    metadata: Mapping[str, Any]
```

#### Logic / Algorithm

1. Evaluate required gate, then the run confirmation policy.
2. Persist a bounded request plus pending continuation; never persist a live callback/coroutine.
3. Validate response kind, request ID, optional Pydantic schema, and approval boolean.
4. Append response before continuing.
5. For explicit stage interrupts, store ordered resume values and rerun the stage; `context.interrupt` returns by ordinal.

#### Edge Cases & Error Handling

- A rejected required approval follows only its declared recovery route.
- Approval values are data, not authorization to choose a target.
- Repeated response submission is rejected through event projection.
- Approval timeouts are optional caller/harness policy; the core does not run a background clock while suspended.

### 6.9 Isolated Subgraphs, Send Fan-Out, and Deterministic Join

**File(s):** `vidbyte/workflows/subgraphs.py`, `vidbyte/workflows/contracts.py`, `vidbyte/workflows/graph.py`, `vidbyte/workflows/machine.py`
**Type:** New file and modified files

#### What it does

Adds child-machine delegation with state/log isolation and a map-reduce-style `Send` primitive.

#### Interface / API

```python
class ChildFailurePolicy(str, Enum):
    FAIL_FAST = "fail_fast"
    COLLECT = "collect"

@dataclass(frozen=True, slots=True)
class Send:
    subgraph: str
    input: Any
    key: str
    budget: WorkflowBudget | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class SubgraphSummary:
    key: str
    child_run_id: str
    lifecycle: WorkflowLifecycleStatus
    terminal: str | None
    update: Mapping[str, Any]
    usage: UsageReport
    error: WorkflowErrorRecord | None = None
```

#### Logic / Algorithm

1. Validate every send key and named subgraph against the compiled definition.
2. Allocate child budgets before launching tasks.
3. Map each input into a child initial state and start a separate child run with parent/root lineage metadata.
4. Limit active tasks with `asyncio.Semaphore`.
5. Gather child outcomes with original indexes.
6. Persist parent child-summary events only; keep child events in child streams.
7. Apply summary mapper updates through the parent stage's declared writes in original send order.
8. Handle fail-fast/collect policy and propagate child suspension as a parent interrupt.

#### Edge Cases & Error Handling

- Duplicate send keys fail before launch.
- A child definition may recurse only within the compiled/global recursion bound.
- Parent cancellation cancels local tasks best-effort but cannot undo child external effects.
- Summary mappers cannot read child event logs implicitly; callers may inspect them separately by child run ID.

### 6.10 Interrupt-Driven Detours

**File(s):** `vidbyte/workflows/detours.py`, `vidbyte/workflows/stages.py`, `vidbyte/workflows/graph.py`, `vidbyte/workflows/machine.py`
**Type:** New file and modified files

#### What it does

Lets deterministic side conditions redirect execution into a validation path and then return without asking the agent to plan the detour.

#### Interface / API

```python
class DetourReturnMode(str, Enum):
    RETRY_SOURCE = "retry_source"
    RESUME_TARGET = "resume_target"

@dataclass(frozen=True, slots=True)
class WorkflowSignal:
    signal_type: str
    source: str
    data: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class DetourRule:
    rule_id: str
    matcher: SignalMatcher

@dataclass(frozen=True, slots=True)
class DetourFrame:
    rule_id: str
    source_stage: str
    target_stage: str
    return_mode: DetourReturnMode
    signal: WorkflowSignal
    continuation: Mapping[str, Any]
```

#### Logic / Algorithm

1. Convert successful tool calls and explicit stage signals into bounded `WorkflowSignal` values.
2. Match compiled rules in declaration order.
3. For a tool-boundary match, abort the agent cleanly, append signal/detour events, push a frame, and enter the detour target.
4. For a post-stage match, persist the pending continuation with the frame.
5. Run the detour through ordinary stage/validator/guard policy.
6. Require explicit detour return, pop the frame, and either retry source with feedback or resume the saved continuation.
7. Checkpoint entry and return boundaries.

#### Edge Cases & Error Handling

- A file-edit matcher reads normalized tool result paths and configured argument fallbacks; missing paths do not match silently.
- A detour may fail through ordinary declared routes or lifecycle `ERROR`.
- Returning with an empty stack, exceeding depth, or resuming a continuation whose definition changed raises `WorkflowDetourError`.

### 6.11 Public Exports, Documentation, and Artifact Index

**File(s):** `vidbyte/workflows/__init__.py`, `vidbyte/workflows/README.md`, `vidbyte/__init__.py`, `README.md`, `llms.txt`, `vidbyte/agents/README.md`, `vidbyte/tools/README.md`, `artifacts/file_index.md`
**Type:** Modified files

#### What it does

Exports the stable surface and documents the security, persistence, lifecycle, replay, subgraph, and idempotency boundaries. The workflow README becomes the primary operational guide and contains one end-to-end coding-harness example.

#### Interface / API

```python
from vidbyte import (
    AgentModelRoute,
    AgentStage,
    AlwaysConfirm,
    ApprovalGate,
    ConfirmRisky,
    FileWorkflowStore,
    InMemoryWorkflowStore,
    Send,
    StageCapabilities,
    StateChannel,
    StateGraph,
    StateSchema,
    ToolVisibility,
    WorkflowBudget,
    WorkflowCommand,
    WorkflowLifecycleStatus,
)
```

#### Logic / Algorithm

1. Export all stable contracts from `vidbyte.workflows`; keep internal compiled definitions, projectors' mutable internals, middleware control channels, and runtime exceptions private.
2. Add only the primary ergonomic contracts to the root package.
3. Document phase profiles (`recon` read-only, `implement` write-enabled), required approval, file-edit detour, per-stage models, resume, and parallel reviewer subgraphs.
4. Replace mutable-ledger examples with immediate observation channels.
5. Regenerate `artifacts/file_index.md` using the repository's existing generator after the final file layout exists.

#### Edge Cases & Error Handling

- Documentation must not imply that event sourcing rolls back external files or makes arbitrary custom stages sandboxed.
- Durable examples must set an explicit graph version and use a caller-owned file-store root.
- Examples must show that child logs are separate and that parent summaries are bounded.

---

## 7. Data Model Changes

### 7.1 Workflow Definition Record

**Change type:** New

```json
{
  "schema_version": 1,
  "definition_id": "wfdef_<sha256>",
  "name": "coding-harness",
  "version": "2.0.0",
  "structure": {
    "stages": [],
    "routes": [],
    "channels": [],
    "policies": {},
    "subgraphs": []
  }
}
```

**Migration strategy:** PR #268 has no persisted definition model. Durable execution is new and requires an explicit version. Rollback leaves caller-owned records inert.

### 7.2 Workflow Event Stream

**Change type:** New canonical append-only model

```json
{
  "schema_version": 1,
  "event_id": "wevt_<uuid>",
  "definition_id": "wfdef_<sha256>",
  "run_id": "wrun_<uuid>",
  "sequence": 18,
  "super_step": 4,
  "event_type": "state_committed",
  "occurred_at": "2026-07-12T00:00:00+00:00",
  "payload": {
    "stage": "implement",
    "updates": {"patches": []}
  }
}
```

**Migration strategy:** Existing in-memory PR #268 `WorkflowEvent` objects are not durable and need no data migration. The runtime changes construction sites and derives legacy record views from the new stream.

### 7.3 Workflow Checkpoint

**Change type:** New immutable projection cache

```json
{
  "schema_version": 1,
  "checkpoint_id": "wck_<uuid>",
  "definition_id": "wfdef_<sha256>",
  "run_id": "wrun_<uuid>",
  "event_sequence": 18,
  "super_step": 4,
  "state_payload": {},
  "projection_payload": {},
  "created_at": "2026-07-12T00:00:00+00:00"
}
```

**Migration strategy:** Additive. A checkpoint can be deleted and rebuilt from retained events; events cannot be rebuilt from a checkpoint.

### 7.4 Typed State Channels

**Change type:** Modified workflow state contract

```python
state_schema = StateSchema(
    HarnessState,
    version="2",
    channels={
        "context": StateChannel(ReplaceReducer()),
        "patches": StateChannel(AppendReducer()),
        "files_visited": StateChannel(SetUnionReducer(), commit_mode=StateCommitMode.IMMEDIATE),
    },
)
```

**Migration strategy:** Whole-state `StageResult` graphs use an implicit root channel and continue to run. Mutable ledger users migrate to `await context.observe(...)` and immutable reducer values.

### 7.5 Agent and Session Runner Options

**Change type:** Modified additive fields

```python
@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    # Existing fields omitted.
    runner_options: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class RunState:
    # Existing fields omitted.
    runner_options: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** Forward serializers write the field. Reads of old version-1 Session payloads default it to `{}`; no Session schema-version bump is required for this optional additive field. Rollback ignores/removes stage thinking overrides but does not rewrite existing session files.

---

## 8. API Changes

### 8.1 Python State Graph Declaration

**Change type:** Modified and additive

**Request:**

```python
graph.add_stage(
    "recon",
    AgentStage(recon_agent, build_recon_prompt, build_recon_result),
    reads={"request", "files_visited"},
    writes={"context"},
    capabilities=StageCapabilities(tools=ToolVisibility.read_only()),
    model_route=AgentModelRoute(provider="openai", model_name="gpt-5-mini"),
)
graph.add_transition("recon", "implement", guards=(context_guard,), risk=RiskLevel.LOW)
graph.add_command_transition("verify", "implement")
```

**Response:**

```python
machine = graph.compile(settings=StateMachineSettings(budget=WorkflowBudget(max_cost_usd=5.0)))
```

**Error cases:**

| Exception | Condition |
|-----------|-----------|
| `WorkflowDefinitionError` | Malformed nodes, routes, channels, command targets, profiles, detours, or subgraphs |
| `WorkflowCapabilityError` | Non-policy-aware stage receives a profile or tool policy cannot resolve safely |
| `WorkflowStateError` | Reducer/schema/read-write declaration is invalid |

### 8.2 Python Run, Suspend, Resume, and Inspect

**Change type:** Modified and additive

**Request:**

```python
store = FileWorkflowStore(".vidbyte/workflows")
result = await machine.arun(initial_state, store=store, confirmation_policy=ConfirmRisky())

if result.lifecycle is WorkflowLifecycleStatus.WAITING_FOR_CONFIRMATION:
    result = await machine.aresume(result.run_id, store=store, command=ResumeCommand.approve(result.pending.request_id))

past = await machine.inspect(result.run_id, store=store, through_sequence=12)
```

**Response:**

```python
StateMachineResult(
    lifecycle=WorkflowLifecycleStatus.FINISHED,
    terminal_status=TerminalStatus.SUCCEEDED,
    terminal="done",
    state=final_state,
    checkpoint_id="wck_...",
    events=(...),
)
```

**Error cases:**

| Exception | Condition |
|-----------|-----------|
| `WorkflowResumeError` | Missing/incompatible checkpoint, definition, lifecycle, or resume boundary |
| `WorkflowApprovalError` | Stale, duplicate, mismatched, or invalid approval response |
| `WorkflowInterruptError` | Invalid interrupt response/schema/ordinal |
| `WorkflowPersistenceError` | Canonical append/checkpoint/store consistency failure |
| `WorkflowBudgetError` | Stage/global/subgraph budget exhausted or required cost unknowable |
| `WorkflowStuckError` | One configured stuck signature reaches threshold |
| `WorkflowDetourError` | Invalid or over-depth detour entry/return |
| `WorkflowSubgraphError` | Child mapping, execution, suspension, or join fails under policy |

### 8.3 Python Workflow Commands and State Updates

**Change type:** New

**Request:**

```python
return WorkflowCommand(
    update={"patches": [patch]},
    goto="verify",
    signals=(WorkflowSignal("file.changed", source=ctx.stage, data={"path": patch.path}),),
)
```

**Response:**

```python
# The runtime reduces only declared writes and resolves "verify" through a
# compiled command edge before validation, approval, and commit.
```

**Error cases:**

| Exception | Condition |
|-----------|-----------|
| `WorkflowCommandError` | Conflicting control fields or undeclared `goto`/send/detour return |
| `WorkflowStateError` | Update key is undeclared or reducer/state validation fails |

### 8.4 Existing APIs

**Change type:** Additive except for mutable ledger tightening

No HTTP endpoint or hosted service changes are introduced. Agents, middleware, sessions, pipelines, paradigms, evals, tools, providers, and harness clients preserve existing behavior. Workflow compatibility notes:

- `StageResult(state=..., outcome=...)` continues through the implicit root reducer.
- `StateMachine.run()`/`arun()` continue; return objects gain lifecycle/persistence fields.
- `MachineStatus` remains an alias for terminal status.
- `ledger=` may initialize immediate observation channels and `result.ledger` remains read-only.
- Direct nested mutation through `StageContext.ledger` is intentionally removed before the draft feature becomes public.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-harness-state-machine-runtime.md` | Approved source of truth for the expanded runtime |
| CREATE | `vidbyte/workflows/events.py` | Typed append-only workflow events and payloads |
| CREATE | `vidbyte/workflows/projection.py` | Pure event projection, replay, and time-travel inspection |
| CREATE | `vidbyte/workflows/state.py` | State schemas, codecs, channels, reducers, and observation handling |
| CREATE | `vidbyte/workflows/budget.py` | Usage aggregation, cost models, budget checks, and child reservations |
| CREATE | `vidbyte/workflows/capabilities.py` | Tool visibility, action guards, impact estimators, and enforcement middleware |
| CREATE | `vidbyte/workflows/approval.py` | Required/risk approval policies and response validation |
| CREATE | `vidbyte/workflows/detection.py` | Five-pattern normalized stuck detector middleware |
| CREATE | `vidbyte/workflows/detours.py` | Signals, matchers, detour frames, and return semantics |
| CREATE | `vidbyte/workflows/subgraphs.py` | Child graph bindings, Send execution, summaries, and joins |
| CREATE | `vidbyte/workflows/persistence.py` | Definition/checkpoint/store protocols and versioned serialization |
| CREATE | `vidbyte/workflows/stores/__init__.py` | Public workflow-store exports |
| CREATE | `vidbyte/workflows/stores/memory.py` | Default concurrent append-only in-memory store |
| CREATE | `vidbyte/workflows/stores/file.py` | Atomic inspectable file event/checkpoint store |
| MODIFY | `vidbyte/workflows/contracts.py` | Add lifecycle, commands, usage, suspension, state, and result contracts |
| MODIFY | `vidbyte/workflows/errors.py` | Add actionable budget/command/persistence/resume/approval/stuck/detour/subgraph errors |
| MODIFY | `vidbyte/workflows/graph.py` | Add profiles, reads/writes, commands, approvals, detours, subgraphs, and definition IDs |
| MODIFY | `vidbyte/workflows/machine.py` | Replace mutable run state with event-sourced execution/resume/inspect |
| MODIFY | `vidbyte/workflows/routing.py` | Expose stable router identity/config for definition fingerprints and command coexistence |
| MODIFY | `vidbyte/workflows/stages.py` | Enforce stage profiles, emit usage/control signals, and support WorkflowCommand |
| MODIFY | `vidbyte/workflows/validation.py` | Report validator usage and operate against reducer-backed validation contexts |
| MODIFY | `vidbyte/workflows/__init__.py` | Export the complete stable workflow surface |
| MODIFY | `vidbyte/workflows/README.md` | Document profiles, state/event semantics, persistence, approval, detours, and subgraphs |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add runner options to agent/fork configuration |
| MODIFY | `vidbyte/agents/base.py` | Accept, apply, export, and restore runner options |
| MODIFY | `vidbyte/agents/fork.py` | Preserve/override runner options for per-stage model routing |
| MODIFY | `vidbyte/lib/dataclasses/sessions.py` | Persist additive runner options in RunState |
| MODIFY | `vidbyte/sessions/serialization.py` | Round-trip additive runner options with backward-compatible default |
| MODIFY | `vidbyte/agents/README.md` | Document per-fork runner options used by workflow model routes |
| MODIFY | `vidbyte/tools/README.md` | Document stage tool visibility versus independent action safety |
| MODIFY | `vidbyte/__init__.py` | Add primary root convenience exports |
| MODIFY | `README.md` | Document the expanded agent-harness workflow surface and layer guide |
| MODIFY | `llms.txt` | Add LLM-readable lifecycle, state, persistence, capability, and subgraph invariants |
| MODIFY | `artifacts/file_index.md` | Regenerate the repository source map for new workflow modules |

No files will be deleted. No test files or verification scripts will be created or modified.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python 3.11+ | Async locks/timeouts/tasks, hashing, UUIDs, JSON, atomic file records, regex/globs, dataclasses | Low; already required |
| Pydantic | Existing `>=2,<3` | TypedDict/Pydantic/dataclass state adapters, interrupt value validation, JSON-safe codecs | Low; already required |
| Vidbyte agents/forks/runners | In-repository API | Per-stage provider/model/thinking/tool/middleware configuration | Medium; additive runner-option persistence touches fork and Session rehydration |
| Vidbyte middleware/tool contracts | In-repository API | Pre/post tool enforcement, stuck detection, detour signals, inner-loop budgets | Medium; only policy-aware/direct agent runtimes can guarantee enforcement |
| Caller-provided `WorkflowStore` | Structural async protocol | Database/remote persistence beyond bundled memory/file stores | Medium; backend consistency, retention, encryption, and distributed locking are provider responsibilities |
| External model providers | Caller configured | Agent stages, agent validators, and graders | Medium; nondeterminism, cost reporting gaps, latency, and outages remain bounded but not eliminated |

No new package dependency, hosted service, credential, database schema, network endpoint, or environment variable is introduced.

---

## 11. Rollout & Deployment

- PR #268 is the prerequisite baseline. Recommended path: review and merge it, update `main`, then implement this design as a follow-up. If it remains open, Phase 3 must stop unless the user explicitly approves a superseding branch strategy.
- After explicit design approval and baseline availability, create `feat/agent-harness-state-machine-runtime` from the latest clean `main` in an isolated worktree.
- Commit this design document before implementation code, as required by the selected workflow.
- Implement in logical commits: event/state foundation; graph/contracts; runtime/checkpoint/resume; capability/model policy; stuck/approval/detours; subgraphs/Send; docs/exports.
- The feature remains opt-in. Existing workflow graphs without durable stores or advanced policies use the in-memory store, root reducer, and current direct routes.
- Mutable ledger examples are migrated before the workflow feature is published. Because PR #268 is still draft and the SDK is alpha, no released-data migration is required.
- Durable users must choose an explicit file/custom store and definition version. `VidbyteSDK()` and ordinary workflow compilation perform no filesystem writes.
- Verification commands:
  - `python -m compileall vidbyte`
  - `python -m unittest discover -s tests -v`
  - root and `vidbyte.workflows` import smoke checks
  - inline state reducer/guard/command/cycle smoke
  - inline tool visibility/action-denial/edit-budget/stuck smoke
  - inline file-store crash-boundary/checkpoint/cold-resume/time-travel smoke
  - inline required/risky approval and explicit interrupt smoke
  - inline detour return and nested-depth smoke
  - inline isolated subgraph/Send ordering/budget/cancellation smoke
  - `python -m build` and `python -m twine check dist/*`
- No new committed tests are allowed by this workflow. This is the largest delivery risk and must be acknowledged during approval; inline smoke output should be included in the draft PR body.
- Rollback is a normal revert of additive modules/exports plus the runner-options field. Event/checkpoint files are caller-owned and are never deleted automatically.
- A later PR may add database workflow-store adapters, harness-store event bridging, a hosted approval UI, or migrate `ContextMinimalFanoutParadigm` onto `Send` after the base contract stabilizes.

---

## 12. Open Questions

- [ ] **Implementation baseline:** Approve merging PR #268 first and building this as a follow-up from `main` (recommended), or explicitly request a superseding PR based on #268's head?
- [ ] **Mutable ledger compatibility:** Approve replacing in-stage mutable ledger access with event-backed immediate observation channels while keeping only input/result compatibility aliases (recommended)? This is required for honest append-only replay.
- [ ] **Custom stage enforcement:** Approve compile-time rejection when a custom stage receives capabilities/model policy but does not declare policy-aware enforcement (recommended), rather than accepting a policy that might be ignored?
- [ ] **Persistence boundary:** Approve a dedicated `WorkflowStore` with bundled memory/file stores (recommended), rather than coupling graph checkpoints to agent-specific `SessionStore` or the unimplemented harness-run store?
- [ ] **Definition versioning:** Approve requiring an explicit graph version for durable stores (recommended), because live callable/prompt code cannot be fingerprinted safely from Python objects alone?
- [ ] **No-tests risk:** Confirm that the explicitly selected no-tests workflow still applies to this unusually large runtime change; approval means relying on the existing suite plus inline smoke evidence rather than adding feature test files.

---

## 13. Alternatives Considered

### Alternative 1: Add Flags Directly to the Existing `machine.py`

- What: Keep `_RunState`, mutable ledger, and in-memory records, then bolt approvals, persistence, and subgraphs into the existing loop.
- Why rejected: Resume and time travel would replay copies of mutable state rather than a canonical history. Record replacement and nested ledger mutation make deterministic reconstruction impossible.

### Alternative 2: Reuse `Session` and `SessionStore`

- What: Encode each workflow super-step as an agent Session checkpoint.
- Why rejected: Session checkpoints serialize one agent conversation. Workflow checkpoints require graph position, reducer state, pending guarded edges, lifecycle, approvals, detours, root/child budgets, and subgraph joins. Forcing those into `RunState` would distort both APIs.

### Alternative 3: Reuse the Draft Harness Execution Store

- What: Make harness events/runs the workflow source of truth.
- Why rejected: That design is not implemented and intentionally excludes checkpoint/resume, approvals, and deterministic replay. A later adapter can mirror canonical workflow events into harness datasets without coupling the core.

### Alternative 4: Keep Whole-State Replacement Only

- What: Persist a full `StateT` after each accepted stage and omit reducers/reads/writes.
- Why rejected: It cannot express append/merge semantics, statically visible dependencies, deterministic fan-in, or immediate observations that survive rejection without reintroducing a mutable ledger.

### Alternative 5: Let `WorkflowCommand.goto` Name Any Stage

- What: Trust a node or model to return an arbitrary target that merely exists.
- Why rejected: Existence is not authorization. Separate compiled command edges preserve Command ergonomics without giving probabilistic code control-plane authority.

### Alternative 6: Enforce Tool Policy Only with `ToolPolicyMiddleware`

- What: Show every tool to the model and deny disallowed calls at execution time.
- Why rejected: Requested phase capability restriction is about visibility as well as execution. Exact fork tool selection removes unavailable schemas, while independent action guards still inspect allowed tools.

### Alternative 7: Block on an Approval Callback Inside `arun()`

- What: Await a user callback while keeping the run coroutine alive.
- Why rejected: It cannot survive process loss, wastes worker lifetime, and provides no cold-resume token. Persisted nonterminal results are explicit and durable.

### Alternative 8: Share Parent State and Event History with Subagents

- What: Invoke child agents as ordinary tools and copy their transcripts into parent context.
- Why rejected: It defeats context isolation and makes fan-out history growth unbounded. Separate child machines plus bounded summaries preserve lineage without contaminating parent context.

### Alternative 9: Merge Fan-Out Results in Completion Order

- What: Apply each child update as soon as it finishes.
- Why rejected: Scheduling would change final state. Input-order reduction is deterministic and matches the existing `asyncio.gather` pipeline convention.

### Alternative 10: Detect Stuck Behavior Only with Global Iteration Caps

- What: Let repeated tool/error/monologue patterns run until a budget expires.
- Why rejected: Budgets bound damage but do not diagnose it. Pattern-specific typed evidence makes the stop actionable and can terminate far earlier.

### Alternative 11: Add a Third-Party Graph Runtime

- What: Wrap LangGraph, Burr, or another state-machine dependency.
- Why rejected: Vidbyte needs stage tool visibility, existing agent forks/middleware, validate-before-commit semantics, SDK-native errors, and a provider-neutral public surface. An adapter would still require most of the control plane while adding another dependency and vocabulary.

### Alternative 12: Split the Fifteen Capabilities into Independently Designed APIs

- What: Add persistence, approval, capabilities, subgraphs, and detours as unrelated follow-up designs.
- Why rejected: Their contracts intersect at lifecycle, event ordering, budgets, suspension, state reducers, and checkpoints. One architectural design prevents incompatible one-off primitives, even though implementation should still use small commits and may be reviewed in slices.
