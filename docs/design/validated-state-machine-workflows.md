# Design Doc: Validated State Machine Workflows

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-12
**Last Updated:** 2026-07-12

---

## 1. Overview

Add a reusable `vidbyte.workflows` state-machine abstraction for agent harnesses whose control flow must be enforced by code rather than by an orchestrator agent's prompt. Developers will declare typed stages, named outcomes, conditional branches, cycles, direct jumps, stage-output validators, and transition guards; compile that mutable graph into an immutable `StateMachine`; and run agents or ordinary Python callables inside each stage. The machine will treat stage output as a candidate state, run deterministic and/or agent-based verification before changing stages, and commit the candidate only after an allowed transition passes its guards. This gives probabilistic agents a deterministic execution envelope without claiming that an LLM verifier's judgment is itself deterministic.

---

## 2. Goals & Non-Goals

### Goals

- Provide a typed, reusable `StateGraph[StateT]` builder and compiled `StateMachine[StateT]` runtime under `vidbyte.workflows`.
- Make Python code—not an LLM system prompt—the authority for stage order, legal destinations, validation timing, retries, terminal states, and execution limits.
- Support non-linear graphs: self-loops, backward transitions, conditional branches, and direct jumps to any declared stage or terminal.
- Make transitions outcome-driven so stages and verifier agents emit bounded semantic codes such as `success`, `needs_more_context`, or `revise`; they never choose arbitrary stage names.
- Validate a stage's candidate output before it can be committed or used to enter another stage.
- Support transition-specific guards after routing selects a target but before the transition commits.
- Let developers implement custom validators and compose built-in callable, schema, grader, and agent validators.
- Provide an `AgentValidator` that runs a verifier agent with a structured verdict contract and maps the verdict to `PASS`, `REJECT`, `ABSTAIN`, or `ERROR`.
- Preserve validator feedback across recovery transitions so a rejected context result can return to the context stage with a precise explanation of what is missing.
- Preserve a clearly non-transactional per-run ledger for mechanical facts such as files visited, tool observations, and attempt counters even when a candidate workflow state is rejected.
- Provide adapters for Vidbyte `BaseAgent` instances and ordinary synchronous/asynchronous callables while keeping the graph runtime independent of any one harness paradigm.
- Compile-time reject malformed or ambiguous graphs and runtime bound cycles with transition and timeout limits.
- Return structured stage, validation, transition, event, and terminal records for inspection and observer integration.
- Keep the addition backward compatible and dependency-free beyond the SDK's existing Python, Pydantic, agent, and eval layers.

### Non-Goals

- Do not make LLM decisions deterministic. The machine deterministically enforces that an agent verifier runs and that only declared verdict codes are honored; the verdict remains probabilistic.
- Do not replace simple `vidbyte.pipelines`, whose intentionally narrow contract remains string-in/string-out composition.
- Do not rewrite `ContextMinimalFanoutParadigm` or any existing paradigm to use the new abstraction in this change.
- Do not turn `vidbyte.harnesses` into the graph runtime. Harness configuration, run persistence, artifact stores, and external launch integration remain a separate outer execution concern.
- Do not implement multiple simultaneously active graph states, graph-level fan-out/fan-in reducers, or distributed workers. A stage may still use existing `asyncio`, pipeline, aggregate-agent, or paradigm facilities internally.
- Do not implement nested/hierarchical statecharts, subgraph composition, durable checkpoint/resume, queues, cron scheduling, or human approval services.
- Do not promise rollback of filesystem, network, tool, or other external side effects. Only the in-memory candidate workflow state is transactional.
- Do not automatically instrument repository read tools or define the domain-specific `RepositoryContext` schema. A context stage can use existing tools/middleware and the run ledger to implement that harness-specific behavior.
- Do not allow a stage, router, or verifier model to return an undeclared target stage and bypass graph policy.
- Do not add a `VidbyteSDK().workflows` client: graph construction is a direct Python API, not a service-style namespace.
- Do not add new test files or verification scripts in this no-tests workflow. Existing repository checks and inline smoke commands will be used during implementation.

---

## 3. Background & Context

The motivating harness has context, specification, implementation, and verification work performed by different agents. A prompt-only orchestrator can ask those agents to run in sequence or expose each agent as an `AgentTool`, but the model remains free to skip a handoff, call a tool twice, ignore a failed check, or choose an undeclared destination. Passing one agent's output directly to the next has the same limitation: it provides data flow, not an enforceable transition boundary.

The repository already contains several adjacent abstractions, but none owns this contract:

- `vidbyte.pipelines` intentionally accepts a string and returns a string. It provides sequential, parallel, conditional, and map/reduce topologies without shared typed state, validation gates, retries, transition records, or recovery loops.
- `ContextMinimalFanoutParadigm` is a concrete, opinionated four-stage harness. Its procedural `arun()` and `PromptSplitPlan.validate()` demonstrate both the need for typed intermediate artifacts and the current cost of hard-coding orchestration per paradigm.
- `vidbyte.paradigms` is the correct home for ready-made harness recipes, not reusable control-flow primitives.
- `vidbyte.harnesses` currently marks the external harness-integration boundary. A separate local draft explores an outer execution envelope; the state machine can later be wrapped by that envelope but must not depend on an unimplemented design.
- `AgentTool` exposes an agent as a zero-parameter child tool and forwards the parent agent's live prompt/history. That is useful for model-selected delegation, but it is deliberately not a deterministic graph controller and offers no typed stage input.
- `vidbyte.evals` already supplies deterministic and LLM-backed `BaseGrader` implementations returning `GraderResult`. A small adapter can reuse those graders without coupling the workflow core to `EvalCase` as its native validation model.
- `BaseAgent` already supports fresh forks, `AgentInput`, output schemas, and validated structured content in `AgentMessage.metadata["structured"]`. `AgentStage` and `AgentValidator` should compose those capabilities instead of creating another agent runtime.

The SDK targets Python 3.11+, uses frozen slotted dataclasses for many public value contracts, derives public errors from `VidbyteSdkError`, uses asynchronous primary APIs with explicit synchronous bridges, and has Pydantic 2 available. The new package will follow those conventions. The compiled machine will be immutable and keep all execution state local to a run so one compiled definition can be reused concurrently; stateful custom stages and validators remain the developer's responsibility.

The key semantic distinction is between three kinds of data:

1. **Committed workflow state:** the last state accepted by stage validators and transition guards.
2. **Candidate state:** a cloned, attempt-local state proposed by a stage and discarded if validation or a guard rejects it.
3. **Run ledger:** explicitly non-transactional scratch data that survives failed attempts and recovery loops. It is suitable for a `files_visited` set or tool-call ledger, but not for business state that requires rollback.

---

## 4. Requirements

### Functional Requirements

1. `StateGraph` must accept a declared state type, an optional custom state validator, and an optional state-cloning function.
2. Developers must be able to add uniquely named stages, select exactly one entry stage, add named terminal nodes with success/failure status, and declare outcome-based routes.
3. A direct transition's target may be any declared stage or terminal, including its source; declaration order must not imply adjacency.
4. A branch must run a declared `Router`, map its bounded branch key to a declared target, and reject any key not present in the branch map.
5. A source/outcome pair must resolve to exactly one direct transition or one conditional branch. Ambiguous route definitions must fail compilation.
6. Compilation must reject missing entries, duplicate names, name collisions between stages and terminals, unknown sources/targets, empty route codes, unreachable stages, definitions with no reachable terminal, nonterminal stages with no outgoing route, and a configured `StagePolicy.error_outcome` with no route from that stage.
7. Compilation must permit cycles and backward edges.
8. `StateMachine.arun()` must validate and clone the initial state before the first stage runs.
9. Before every stage attempt, the runtime must clone the last committed state and expose the clone through `StageContext` so ordinary in-place mutations cannot modify the committed object by alias.
10. A stage must return `StageResult[StateT]` containing a candidate state, a semantic outcome code, and optional metadata.
11. The runtime must normalize/validate every candidate against the graph's state contract before custom stage validators run.
12. Stage validators must run in declaration order after a stage returns and before its outcome is routed. Developers can place cheap deterministic validators before agent validators.
13. A validator must return `ValidationResult` with one of `PASS`, `REJECT`, `ABSTAIN`, or `ERROR`, plus a bounded code, feedback, optional score, and structured details.
14. `REJECT` must discard the candidate state, convert the result into structured recovery feedback, and resolve a declared route using the validator's code from the current source stage.
15. `ABSTAIN`, `ERROR`, and raised validator exceptions must be recorded and normalized according to `ValidatorErrorPolicy`: fail closed, fail open, or raise.
16. After stage validation passes, the runtime must use the stage outcome to select a direct transition or conditional branch.
17. Transition guards must run in declaration order after a target is selected and before state commit.
18. A guard rejection must discard the candidate, retain structured feedback, and resolve another declared outcome route from the same source stage.
19. Only after all applicable validation and guards pass may the machine atomically replace the committed in-memory state and enter the selected target.
20. Reaching a terminal target must return `StateMachineResult` containing terminal name/status, final committed state, a snapshot of the run ledger, and ordered execution records.
21. Missing outcome routes, undeclared branch keys, unknown validator codes, and exhausted guard redirects must raise typed workflow errors rather than choosing a fallback stage implicitly.
22. Every selected transition attempt—including one rejected by guards—must count toward `max_transitions` so graph loops and redirect chains are bounded.
23. `StateMachineSettings.timeout_seconds` must optionally bound the full run. `StagePolicy.timeout_seconds` must optionally bound one stage attempt.
24. `RetryPolicy` must support a deterministic maximum-attempt count, delay, backoff multiplier, and retryable exception tuple without random jitter.
25. A stage exception must be retried only by its policy; after exhaustion it must either emit the stage's declared `error_outcome` from the last committed state or raise `StageExecutionError`.
26. `asyncio.CancelledError`, keyboard interrupts, and other `BaseException` cancellation/control-flow signals must propagate immediately and must never be converted into a retry or workflow outcome.
27. `StateMachine.run()` must bridge to `arun()` only when no event loop is active and otherwise instruct callers to use `await arun()`.
28. A custom class implementing the `Stage`, `Validator`, or `Router` protocol must be accepted without inheritance from a Vidbyte base class.
29. `CallableStage`, `CallableValidator`, and `CallableRouter` must adapt synchronous or asynchronous callables to those protocols.
30. `SchemaValidator` must validate a selected candidate value using Pydantic `TypeAdapter` and return a configurable rejection code/feedback instead of leaking a raw Pydantic exception.
31. `GraderValidator` must adapt an existing `BaseGrader` by building an `EvalCase` and actual string from `ValidationContext`, preserving the grader score/reason in `ValidationResult`.
32. `AllOfValidator`, `AnyOfValidator`, and `WeightedValidator` must provide explicit, deterministic composite semantics and ordered child records.
33. `AgentStage` must run a supplied `BaseAgent` or context-aware agent factory, build its input from `StageContext`, and map its `AgentMessage` to `StageResult`.
34. `AgentStage` must use a fresh history-free agent fork by default so concurrent runs and repeated stage visits do not accidentally share conversation history.
35. `AgentValidator` must run a supplied verifier agent or validation-context-aware agent factory with a developer-supplied prompt builder, output schema, and verdict mapper.
36. `AgentValidator` must require a Pydantic verdict model, prefer the runtime-validated model in `AgentMessage.metadata["structured"]`, revalidate it against that model contract, and only then invoke the verdict mapper.
37. An `AgentValidator` verdict mapper may emit a semantic validation code but may not select a target; the graph remains the only authority that maps codes to stages.
38. Agent-verifier timeout, agent execution failure, invalid structured output, or verdict-mapper failure must be retried only up to `max_attempts`; exhaustion must produce a fail-closed rejection by default.
39. The next stage invocation after a rejection or handled stage error must receive `WorkflowFeedback` containing source, code, message, and structured details.
40. Every run must expose one mutable `ledger` mapping to stages, validators, and routers; the machine must not roll it back, and the final result must return a shallow immutable snapshot of its top-level mapping.
41. The runtime must record ordered `StageExecution`, `ValidationRecord`, `TransitionRecord`, and `WorkflowEvent` objects with durations and error summaries.
42. Callers must be able to attach asynchronous `WorkflowObserver` objects per run; observers receive ordered events, observer failures are fail-open, and those failures are included in the final result.
43. State snapshots must be excluded from execution records by default and included only when `record_state_snapshots=True` to reduce accidental sensitive-data and context-volume exposure.
44. Significant verification that needs its own tools, retries, state output, or branch history must be representable as an ordinary explicit stage; validators remain the ergonomic boundary checks.
45. The package must be publicly importable from both `vidbyte.workflows` and the repository's root `vidbyte` convenience surface.

### Non-Functional Requirements

- **Determinism:** With fixed stage/router/validator outputs, route selection, validation order, commit behavior, retry timing, event order, and terminal outcome must be deterministic. No random retry jitter or implicit route selection is permitted.
- **Performance:** Runtime overhead outside user callbacks must be linear in executed stages, validators, and selected transitions. Graph compilation must be linear in nodes plus declared routes. The runtime must not perform network I/O on its own.
- **Concurrency:** A compiled machine must keep run state in method-local runtime objects and be safe to invoke concurrently. Fresh agent forks are the default adapter behavior. Custom components that mutate shared internal state must document and own their synchronization.
- **Scalability:** `max_transitions` defaults to 100 to bound history growth. The graph may be reused for many runs, while each run owns independent state, records, feedback, events, and ledger.
- **Security/privacy:** State snapshots are disabled by default. Errors and records contain summaries rather than raw prompts or secrets unless the developer deliberately puts them in metadata/details. No arbitrary target supplied by a model is executed.
- **Observability:** Structured records and ordered observer events cover run, stage, validation, transition, terminal, and failure boundaries. Agent-internal traces continue to use existing Vidbyte tracing.
- **Reliability:** Candidate state is clone-isolated and only committed after all gates pass. Compile-time validation catches static graph faults; timeouts, retries, transition limits, fail-closed verifier behavior, and typed errors bound runtime faults.
- **Compatibility:** The feature is additive, preserves pipeline/paradigm/harness contracts, targets Python 3.11+, and adds no required service or package dependency.
- **Documentation:** Public contracts, transactional boundaries, probabilistic-verifier caveat, and a context/spec/implementation example must be documented in the package README, root README, and `llms.txt`.

---

## 5. High-Level Design

Create a self-contained `vidbyte.workflows` package. `contracts.py` owns public enums, frozen record/value dataclasses, and structural protocols. `stages.py`, `validation.py`, and `routing.py` adapt Vidbyte agents, eval graders, schemas, and arbitrary callables. `graph.py` owns a mutable builder and compile-time definition checks. `machine.py` owns the immutable compiled definition and asynchronous execution algorithm. `errors.py` provides a feature-local error hierarchy rooted at `VidbyteSdkError`. The package `__init__.py` and root `vidbyte/__init__.py` expose the stable surface.

The graph is an outcome-addressed directed graph, not a linear list. A stage emits an outcome, a validator may replace that outcome with a rejection code, or a conditional router may map an outcome to a branch key. Only the compiled definition maps those bounded values to targets. A direct edge can target any stage, so cycles, backtracking, and jumps that skip intermediate stages need no special runtime command. Skipped stages do not execute.

Each stage attempt begins from a clone of committed state. Its returned state is a candidate. The runtime validates the candidate's type, runs stage validators, selects a declared route, and runs target-specific guards. A successful guard chain commits the candidate and enters the target. Any rejection discards it, records feedback, and follows a separately declared recovery outcome using the pre-attempt committed state. The run ledger is intentionally outside this transaction so facts such as `files_visited` survive a rejected context attempt.

Agent support is composition rather than a second orchestration engine. `AgentStage` calls `BaseAgent.arun()` directly and maps the reply to a typed stage result. `AgentValidator` gives a verifier agent a structured output schema, validates the structured verdict, and maps it to a `ValidationResult`. The model cannot call the graph or return a stage name. Existing `AgentTool` remains available inside any stage for model-selected delegation, but the state machine is the authoritative outer orchestrator.

```text
                                      declared outcome/code only
                                                |
                                                v
[committed StateT] --clone--> [Stage] --> [candidate StateT]
                                            |
                                  state contract + stage validators
                                            |
                         REJECT ------------+------------- PASS
                           |                                  |
                    discard candidate                 route / branch
                           |                                  |
                 structured feedback                transition guards
                           |                         |              |
                 recovery edge <------------- REJECT              PASS
                           |                                        |
                 [next/repeated stage]                   commit candidate
                                                                    |
                                                        [stage or terminal]

[per-run ledger: files_visited, attempt facts, tool observations]
    persists across every path above and is never transactionally rolled back
```

---

## 6. Detailed Design

### 6.1 Workflow Contracts and Error Hierarchy

**File(s):** `vidbyte/workflows/contracts.py`, `vidbyte/workflows/errors.py`
**Type:** New files

#### What it does

Defines the stable public language of a workflow: statuses, settings, stage/validation/routing contexts, results, feedback, records, events, structural protocols, route targets, and typed errors. Public data records use frozen slotted dataclasses where their fields are immutable by contract. `StageContext.ledger` and related context views deliberately reference one mutable per-run mapping and document that exception.

#### Interface / API

```python
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Protocol, TypeVar

StateT = TypeVar("StateT")

class ValidationPhase(str, Enum):
    STAGE = "stage"
    TRANSITION = "transition"

class ValidationStatus(str, Enum):
    PASS = "pass"
    REJECT = "reject"
    ABSTAIN = "abstain"
    ERROR = "error"

class ValidatorErrorPolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"
    FAIL_OPEN = "fail_open"
    RAISE = "raise"

class MachineStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class WorkflowEventType(str, Enum):
    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    STAGE_FINISHED = "stage_finished"
    VALIDATION_FINISHED = "validation_finished"
    TRANSITION_SELECTED = "transition_selected"
    TRANSITION_REJECTED = "transition_rejected"
    STATE_COMMITTED = "state_committed"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"

@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    delay_seconds: float = 0.0
    backoff_multiplier: float = 1.0
    retry_for: tuple[type[Exception], ...] = (Exception,)

@dataclass(frozen=True, slots=True)
class StagePolicy:
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: float | None = None
    error_outcome: str | None = None

@dataclass(frozen=True, slots=True)
class StateMachineSettings:
    max_transitions: int = 100
    timeout_seconds: float | None = None
    validator_error_policy: ValidatorErrorPolicy = ValidatorErrorPolicy.FAIL_CLOSED
    validation_error_outcome: str = "validation_error"
    record_state_snapshots: bool = False

@dataclass(frozen=True, slots=True)
class WorkflowFeedback:
    kind: str
    source: str
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class StageResult(Generic[StateT]):
    state: StateT
    outcome: str = "success"
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ValidationResult:
    status: ValidationStatus
    code: str = ""
    feedback: str = ""
    score: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def passed(cls, *, code: str = "pass", feedback: str = "", score: float | None = None, details: Mapping[str, Any] | None = None) -> "ValidationResult": ...

    @classmethod
    def rejected(cls, code: str, feedback: str, *, score: float | None = None, details: Mapping[str, Any] | None = None) -> "ValidationResult": ...

    @classmethod
    def abstained(cls, code: str, feedback: str, *, details: Mapping[str, Any] | None = None) -> "ValidationResult": ...

    @classmethod
    def errored(cls, code: str, feedback: str, *, details: Mapping[str, Any] | None = None) -> "ValidationResult": ...

@dataclass(frozen=True, slots=True)
class StageContext(Generic[StateT]):
    run_id: str
    stage: str
    state: StateT
    visit: int
    attempt: int
    transition_count: int
    feedback: tuple[WorkflowFeedback, ...]
    history: tuple["StageExecution", ...]
    ledger: MutableMapping[str, Any]
    metadata: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class ValidationContext(Generic[StateT]):
    run_id: str
    phase: ValidationPhase
    stage: str
    state_before: StateT
    candidate_state: StateT
    stage_result: StageResult[StateT]
    outcome: str
    target: str | None
    feedback: tuple[WorkflowFeedback, ...]
    ledger: MutableMapping[str, Any]
    metadata: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class RoutingContext(Generic[StateT]):
    run_id: str
    stage: str
    candidate_state: StateT
    stage_result: StageResult[StateT]
    feedback: tuple[WorkflowFeedback, ...]
    ledger: MutableMapping[str, Any]
    metadata: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class ValidationRecord:
    phase: ValidationPhase
    validator: str
    result: ValidationResult
    duration_ms: float
    target: str | None = None

@dataclass(frozen=True, slots=True)
class StageExecution:
    stage: str
    visit: int
    attempt: int
    outcome: str | None
    accepted: bool
    duration_ms: float
    metadata: Mapping[str, Any]
    validations: tuple[ValidationRecord, ...]
    error_type: str | None = None
    error_message: str | None = None
    state_before: Any | None = None
    candidate_state: Any | None = None

@dataclass(frozen=True, slots=True)
class TransitionRecord:
    sequence: int
    source: str
    target: str
    outcome: str
    accepted: bool
    trigger: str
    validations: tuple[ValidationRecord, ...]
    duration_ms: float

@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    sequence: int
    event_type: WorkflowEventType
    run_id: str
    stage: str | None
    occurred_at: datetime
    elapsed_ms: float
    payload: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class StateMachineResult(Generic[StateT]):
    run_id: str
    status: MachineStatus
    terminal: str
    state: StateT
    ledger: Mapping[str, Any]
    metadata: Mapping[str, Any]
    stages: tuple[StageExecution, ...]
    transitions: tuple[TransitionRecord, ...]
    events: tuple[WorkflowEvent, ...]
    observer_errors: tuple[str, ...]
    duration_ms: float

class Stage(Protocol[StateT]):
    async def run(self, context: StageContext[StateT]) -> StageResult[StateT]: ...

class Validator(Protocol[StateT]):
    @property
    def name(self) -> str: ...
    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult: ...

class Router(Protocol[StateT]):
    @property
    def name(self) -> str: ...
    async def route(self, context: RoutingContext[StateT]) -> str: ...

class WorkflowObserver(Protocol):
    async def on_event(self, event: WorkflowEvent) -> None: ...

@dataclass(frozen=True, slots=True)
class RouteTarget(Generic[StateT]):
    target: str
    guards: tuple[Validator[StateT], ...] = ()

class WorkflowError(VidbyteSdkError): ...
class WorkflowDefinitionError(WorkflowError): ...
class WorkflowExecutionError(WorkflowError): ...
class WorkflowStateError(WorkflowExecutionError): ...
class WorkflowValidationError(WorkflowExecutionError): ...
class StageExecutionError(WorkflowExecutionError): ...
class WorkflowRoutingError(WorkflowExecutionError): ...
class TransitionLimitError(WorkflowExecutionError): ...
```

#### Logic / Algorithm

1. Dataclass `__post_init__` methods reject empty codes/names, nonpositive attempt/transition limits, negative delays/timeouts, invalid backoff, scores outside `[0, 1]`, and invalid exception tuples.
2. Record mappings are copied at construction so callers cannot mutate top-level record contents through an original dictionary reference.
3. `ValidationResult` constructors normalize the common pass/reject/abstain/error cases without forcing custom validators to call them.
4. Workflow errors derive from `VidbyteSdkError` and populate its existing `details` mapping with run, stage, outcome, target, and exception-type identifiers when available.
5. Raw exception tracebacks, prompts, state, and verifier output are not copied into error messages automatically.

#### Edge Cases & Error Handling

- A mutable object nested inside a mapping or state remains mutable; the runtime guarantees top-level candidate cloning, not deep immutability of every external object after it has been returned to a caller.
- `record_state_snapshots=False` stores `None` for `state_before` and `candidate_state`; enabling it stores cloned snapshots and is explicitly opt-in.
- The ledger's top-level result snapshot prevents later key insertion/removal through the returned mapping, but nested objects are not deep-frozen.
- Invalid policy values fail at graph construction/compilation, before an agent or callback is invoked.

### 6.2 Validator System

**File(s):** `vidbyte/workflows/validation.py`
**Type:** New file

#### What it does

Implements custom-callable, schema, eval-grader, agent-verifier, and composite validators behind the single `Validator` protocol. All adapters expose stable names for records. They return structured results rather than deciding graph destinations.

#### Interface / API

```python
class CallableValidator(Generic[StateT]):
    def __init__(self, callback: Callable[[ValidationContext[StateT]], ValidationResult | bool | Awaitable[ValidationResult | bool]], *, name: str | None = None, reject_code: str = "validation_failed", reject_feedback: str = "Validator returned false.") -> None: ...
    @property
    def name(self) -> str: ...
    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult: ...

class SchemaValidator(Generic[StateT]):
    def __init__(self, schema: Any, *, selector: Callable[[ValidationContext[StateT]], Any] | None = None, strict: bool = True, name: str | None = None, reject_code: str = "invalid_schema") -> None: ...
    @property
    def name(self) -> str: ...
    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult: ...

class GraderValidator(Generic[StateT]):
    def __init__(self, grader: BaseGrader, case_builder: Callable[[ValidationContext[StateT]], EvalCase], actual_builder: Callable[[ValidationContext[StateT]], str], *, name: str | None = None, reject_code: str = "grader_rejected") -> None: ...
    @property
    def name(self) -> str: ...
    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult: ...

class AgentValidator(Generic[StateT]):
    def __init__(self, agent: BaseAgent | Callable[[ValidationContext[StateT]], BaseAgent], prompt_builder: Callable[[ValidationContext[StateT]], str | AgentInput], verdict_schema: type[BaseModel], verdict_mapper: Callable[[BaseModel, ValidationContext[StateT]], ValidationResult], *, fresh_fork: bool = True, max_attempts: int = 1, timeout_seconds: float | None = None, fail_closed: bool = True, error_code: str = "agent_validator_error", name: str | None = None) -> None: ...
    @property
    def name(self) -> str: ...
    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult: ...

class AllOfValidator(Generic[StateT]):
    def __init__(self, validators: Sequence[Validator[StateT]], *, name: str | None = None) -> None: ...
    @property
    def name(self) -> str: ...
    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult: ...

class AnyOfValidator(Generic[StateT]):
    def __init__(self, validators: Sequence[Validator[StateT]], *, name: str | None = None, reject_code: str = "no_validator_passed") -> None: ...
    @property
    def name(self) -> str: ...
    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult: ...

class WeightedValidator(Generic[StateT]):
    def __init__(self, validators: Sequence[tuple[float, Validator[StateT]]], *, threshold: float, name: str | None = None, reject_code: str = "weighted_threshold_not_met") -> None: ...
    @property
    def name(self) -> str: ...
    async def validate(self, context: ValidationContext[StateT]) -> ValidationResult: ...
```

#### Logic / Algorithm

1. `CallableValidator` awaits awaitables, accepts `ValidationResult` directly, maps `True` to pass, and maps `False` to its configured rejection.
2. `SchemaValidator` applies its selector (or uses `candidate_state`), validates with a prebuilt Pydantic `TypeAdapter`, and converts `ValidationError` into a concise rejection with structured error details.
3. `GraderValidator` builds its case/actual values, awaits `BaseGrader.agrade()`, and maps `passed`, `score`, and `reason` without distinguishing deterministic graders from LLM graders.
4. `AgentValidator` resolves an agent instance or factory for each attempt. With `fresh_fork=True`, it forks with history excluded and always overrides the fork's output schema with the supplied `verdict_schema`. With `fresh_fork=False`, the supplied agent is expected to be configured for structured output, and local model revalidation still fails closed if it is not.
5. The verifier prompt is built entirely by the developer so the abstraction does not silently inject full workflow state or history.
6. `AgentValidator` invokes `agent.arun()`, reads `reply.metadata["structured"]`, revalidates that value with the Pydantic verdict model, and calls `verdict_mapper` only on a valid model instance. Requiring a model avoids pretending that the SDK's provider-request JSON Schema mapping is also a complete local JSON Schema validator.
7. Agent execution, timeout, structured-output, and mapping failures retry with deterministic attempt bounds. After exhaustion, fail-closed mode returns `REJECT/error_code`; fail-open mode returns `ERROR/error_code` for the machine policy to normalize.
8. `AllOfValidator` evaluates children in order and returns the first non-pass result; it passes only if all pass.
9. `AnyOfValidator` evaluates children in order and returns on the first pass. If none pass, it returns `ERROR` when any child errored and no child passed, `ABSTAIN` when all non-rejections abstained, or its configured aggregate rejection otherwise.
10. `WeightedValidator` evaluates every child. Any child error yields an aggregate `ERROR`, and any abstention yields `ABSTAIN` when there is no error, allowing machine policy to remain authoritative. Otherwise explicit scores must already be in `[0, 1]`; absent scores map to `1.0` for pass and `0.0` for reject. It computes a positive-weight normalized mean and compares it to `threshold`; child details and the aggregate score are preserved.
11. Composite child outcomes are included in their aggregate `details` so the enclosing machine still creates one ordered top-level `ValidationRecord` without losing diagnostic data.

#### Edge Cases & Error Handling

- Empty composite validator lists, nonpositive weights, thresholds outside `[0, 1]`, empty error/rejection codes, and nonpositive agent attempts fail during construction.
- A custom validator exception is not swallowed by the adapter unless the adapter's contract explicitly turns it into `ValidationResult.ERROR`; the machine always records and applies `ValidatorErrorPolicy`.
- A missing `metadata["structured"]`, schema mismatch, invalid verdict status, or verdict mapper exception is a verifier failure, never a pass.
- `fail_closed=True` does not make the verifier correct; it makes verifier infrastructure failure block progression.
- An LLM-backed `GraderValidator` is probabilistic for the same reason as `AgentValidator` and is documented as such.

### 6.3 Stage Adapters

**File(s):** `vidbyte/workflows/stages.py`
**Type:** New file

#### What it does

Adapts ordinary Python functions and Vidbyte agents into the `Stage` protocol. A stage owns work; it does not own route lookup or state commit.

#### Interface / API

```python
class CallableStage(Generic[StateT]):
    def __init__(self, callback: Callable[[StageContext[StateT]], StageResult[StateT] | Awaitable[StageResult[StateT]]], *, name: str | None = None) -> None: ...
    async def run(self, context: StageContext[StateT]) -> StageResult[StateT]: ...

class AgentStage(Generic[StateT]):
    def __init__(self, agent: BaseAgent | Callable[[StageContext[StateT]], BaseAgent], prompt_builder: Callable[[StageContext[StateT]], str | AgentInput], result_builder: Callable[[AgentMessage, StageContext[StateT]], StageResult[StateT] | Awaitable[StageResult[StateT]]], *, fresh_fork: bool = True, fork_settings: AgentForkSettings | None = None, name: str | None = None) -> None: ...
    async def run(self, context: StageContext[StateT]) -> StageResult[StateT]: ...
```

#### Logic / Algorithm

1. `CallableStage` invokes the callback and awaits only when its return is awaitable.
2. `AgentStage` resolves the fixed agent or context-aware factory. A factory can construct run-specific tracking tools that close over `context.ledger`.
3. Unless disabled, `AgentStage` forks the resolved agent with history excluded. Explicit `fork_settings` are copied with `include_history=False`; a conflicting request to include history fails construction because it would violate the adapter default's isolation guarantee. Other explicit settings, including a stage output schema, are preserved.
4. It builds `str | AgentInput`, awaits `agent.arun()`, and passes the reply plus the same stage context to the result builder.
5. The machine—not the adapter—validates the returned `StageResult` and candidate state.

#### Edge Cases & Error Handling

- A callback/result builder returning the wrong type causes `StageExecutionError` at the machine boundary.
- Agent errors propagate to the stage retry policy; the adapter does not add an independent hidden retry loop.
- `fresh_fork=False` is allowed for intentionally conversational stages, but the caller then owns history isolation and concurrent safety.
- A context-aware agent factory that returns the same mutable agent repeatedly has the same caller-owned risk.

### 6.4 Conditional Routing and Graph Compilation

**File(s):** `vidbyte/workflows/routing.py`, `vidbyte/workflows/graph.py`
**Type:** New files

#### What it does

Provides callable routing and the mutable graph-definition API. `compile()` snapshots stages, policies, validators, terminals, direct transitions, and branches into immutable mappings consumed by the runtime.

#### Interface / API

```python
class CallableRouter(Generic[StateT]):
    def __init__(self, callback: Callable[[RoutingContext[StateT]], str | Awaitable[str]], *, name: str | None = None) -> None: ...
    @property
    def name(self) -> str: ...
    async def route(self, context: RoutingContext[StateT]) -> str: ...

class StateGraph(Generic[StateT]):
    def __init__(self, state_type: type[StateT], *, name: str = "workflow", state_validator: Callable[[Any], StateT] | None = None, state_cloner: Callable[[StateT], StateT] = deepcopy) -> None: ...
    def add_stage(self, name: str, stage: Stage[StateT], *, validators: Sequence[Validator[StateT]] = (), policy: StagePolicy | None = None) -> "StateGraph[StateT]": ...
    def set_entry(self, name: str) -> "StateGraph[StateT]": ...
    def add_terminal(self, name: str, *, status: MachineStatus = MachineStatus.SUCCEEDED) -> "StateGraph[StateT]": ...
    def add_transition(self, source: str, target: str, *, on: str = "success", guards: Sequence[Validator[StateT]] = ()) -> "StateGraph[StateT]": ...
    def add_branch(self, source: str, router: Router[StateT], routes: Mapping[str, str | RouteTarget[StateT]], *, on: str = "success") -> "StateGraph[StateT]": ...
    def compile(self, *, settings: StateMachineSettings | None = None) -> "StateMachine[StateT]": ...
```

#### Logic / Algorithm

1. Builder methods normalize names/codes, reject immediate duplicates, and return `self` for fluent declaration.
2. A direct transition stores one target and ordered guards for `(source, on)`.
3. A branch stores one router and a finite branch-key mapping for `(source, on)`; a `RouteTarget` attaches target-specific guards while a bare string means no guards.
4. `compile()` validates the complete graph, including stage/terminal reachability and existence of at least one terminal path from entry.
5. Reachability analysis treats every branch target as an edge and permits revisiting nodes.
6. The state contract is compiled once. The default state validator uses Pydantic `TypeAdapter` where supported and a strict `isinstance` fallback for ordinary classes; an explicit `state_validator` takes precedence.
7. Stages, validator sequences, route maps, terminals, and settings are copied into immutable tuples/mapping proxies. Later builder mutations cannot affect an already compiled machine.

#### Edge Cases & Error Handling

- A branch key or outcome may be any nonempty string, but whitespace-only values are rejected and values are not silently lowercased.
- A target may be declared after a transition is added; unknown targets are therefore reported at compile time.
- A stage may route to itself or an earlier declaration. Static reachability must terminate through a visited set.
- A graph with a reachable infinite cycle but also a reachable terminal compiles; runtime limits protect individual runs.
- A graph whose only terminal is unreachable fails compilation.
- Routers returning empty or undeclared keys raise `WorkflowRoutingError`; the runtime does not fall back to a `default` branch unless the developer explicitly declares and returns that key.

### 6.5 Compiled State Machine Runtime

**File(s):** `vidbyte/workflows/machine.py`
**Type:** New file

#### What it does

Executes an immutable graph definition, owns candidate-state transaction semantics, applies validator policy, follows declared routes, emits ordered records/events, and exposes async/sync run entry points.

#### Interface / API

```python
class StateMachine(Generic[StateT]):
    @property
    def name(self) -> str: ...
    @property
    def entry(self) -> str: ...
    @property
    def stages(self) -> tuple[str, ...]: ...
    @property
    def terminals(self) -> Mapping[str, MachineStatus]: ...
    async def arun(self, initial_state: StateT, *, run_id: str | None = None, ledger: MutableMapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, observers: Sequence[WorkflowObserver] = ()) -> StateMachineResult[StateT]: ...
    def run(self, initial_state: StateT, *, run_id: str | None = None, ledger: MutableMapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, observers: Sequence[WorkflowObserver] = ()) -> StateMachineResult[StateT]: ...
```

#### Logic / Algorithm

1. Generate a UUID run id when absent, copy run metadata, initialize or reuse the caller's ledger, validate/clone initial state, and emit `RUN_STARTED`.
2. Enter the graph's entry stage with no feedback.
3. For each stage visit, increment that stage's visit counter, clone committed state, build `StageContext`, and execute under its timeout/retry policy. Retry attempts share the visit number and receive one-based attempt numbers; a recovery loop creates a new visit. Record every failed and successful attempt.
4. Validate the returned object is `StageResult`, normalize its outcome, and validate/normalize its candidate state through the graph state contract.
5. Build `ValidationContext(phase=STAGE)` and run stage validators in order.
6. Normalize raised/`ABSTAIN`/`ERROR` outcomes using `ValidatorErrorPolicy`. Fail-open results permit continued validation but stay visible in records; fail-closed results become a rejection using their code or `validation_error_outcome`; raise policy throws `WorkflowValidationError` with partial record details.
7. On stage rejection, mark the execution unaccepted, discard the candidate, replace the prior stage's one-hop feedback with a new `WorkflowFeedback`, and resolve the rejection code from the same source using the committed state.
8. On stage pass, select the route for the stage result's outcome. For a branch, run its router against the candidate and look up the returned key.
9. Increment the transition-attempt count and emit `TRANSITION_SELECTED` before guards run. Enforce `max_transitions` against selections, not only committed edges.
10. Build `ValidationContext(phase=TRANSITION, target=...)` and run the selected target's guards.
11. On guard rejection, record an unaccepted transition, discard the candidate, append feedback for that guard to the current redirect chain, and resolve the guard's code from the original source. This redirect also consumes the next transition count and can itself have guards.
12. On guard pass, clone the candidate into committed state, record an accepted transition, emit `STATE_COMMITTED`, clear one-hop recovery feedback, and enter the target.
13. If the target is a terminal, emit `RUN_FINISHED` and return the immutable result. A failure terminal is a declared workflow outcome, not an infrastructure exception.
14. If a stage exhausts retries and has `error_outcome`, record structured stage-error feedback and route that outcome using unchanged committed state. Otherwise emit `RUN_FAILED` and raise `StageExecutionError`.
15. Wrap the full async loop in the optional global timeout. Global timeout, state clone/validation failure, transition-limit exhaustion, missing route, and observer-independent runtime faults emit `RUN_FAILED` and raise the corresponding typed error.
16. Dispatch each event to observers in declaration order. Observer exceptions are captured as short strings and never alter routing, validation, commit, or terminal status.
17. The synchronous bridge uses `asyncio.run()` only when no loop is active.

#### Edge Cases & Error Handling

- `BaseException` subclasses bypass retry and normalization; cancellation propagates after a best-effort failure event.
- If state cloning fails, execution stops before passing an aliased committed object to user code.
- An `error_outcome` or rejection code with no declared route raises `WorkflowRoutingError`; recovery is always explicit.
- Feedback applies to the immediately entered recovery stage and is then cleared after a successful commit. Durable attempt facts belong in state, history metadata, or the run ledger.
- The machine can run concurrently because runtime counters and records are local variables. Observer and component thread safety is not inferred.
- Event payloads contain identifiers and summaries by default, not state snapshots.
- The machine does not undo files written or network calls made before validation; developers must use dry-run/candidate artifacts, idempotent operations, or explicit compensation stages where external reversibility matters.

### 6.6 Public Exports and Documentation

**File(s):** `vidbyte/workflows/__init__.py`, `vidbyte/workflows/README.md`, `vidbyte/__init__.py`, `README.md`, `llms.txt`
**Type:** New package files and modified public documentation/export files

#### What it does

Creates the public import surface and documents when to use workflows instead of pipelines, paradigms, harness integrations, or prompt-enforced handoffs. The package README includes the motivating context/spec/implementation harness with an agent context verifier and recovery loop.

#### Interface / API

```python
from vidbyte import (
    AgentStage,
    AgentValidator,
    CallableRouter,
    CallableStage,
    CallableValidator,
    MachineStatus,
    RouteTarget,
    SchemaValidator,
    StagePolicy,
    StageResult,
    StateGraph,
    StateMachine,
    StateMachineSettings,
    ValidationResult,
    ValidationStatus,
    ValidatorErrorPolicy,
    WorkflowObserver,
)

from vidbyte.workflows import StateGraph, StateMachine
```

Representative usage documented in `vidbyte/workflows/README.md`:

```python
class ContextVerdict(BaseModel):
    decision: Literal["enough_context", "needs_more_context"]
    feedback: str
    missing: list[str] = []

context_validator = AgentValidator(
    verifier_agent,
    prompt_builder=build_context_check_prompt,
    verdict_schema=ContextVerdict,
    verdict_mapper=lambda verdict, _: (
        ValidationResult.passed(feedback=verdict.feedback)
        if verdict.decision == "enough_context"
        else ValidationResult.rejected(
            "needs_more_context",
            verdict.feedback,
            details={"missing": tuple(verdict.missing)},
        )
    ),
)

graph = StateGraph(HarnessState, name="software-engineering-harness")
graph.add_stage("context", AgentStage(context_agent, build_context_prompt, build_context_result), validators=(context_schema, context_validator))
graph.add_stage("spec", AgentStage(spec_agent, build_spec_prompt, build_spec_result), validators=(spec_schema,))
graph.add_stage("implementation", AgentStage(implementation_agent, build_implementation_prompt, build_implementation_result))
graph.add_stage("verify", AgentStage(verification_agent, build_verification_prompt, build_verification_result))
graph.add_terminal("done", status=MachineStatus.SUCCEEDED)
graph.add_terminal("failed", status=MachineStatus.FAILED)
graph.set_entry("context")
graph.add_transition("context", "spec", on="success")
graph.add_transition("context", "context", on="needs_more_context")
graph.add_transition("spec", "implementation", on="success")
graph.add_transition("implementation", "verify", on="success")
graph.add_transition("verify", "done", on="approved")
graph.add_transition("verify", "implementation", on="revise")
machine = graph.compile(settings=StateMachineSettings(max_transitions=12))

result = await machine.arun(
    HarnessState(request=request),
    ledger={"files_visited": set()},
)
```

The README will explicitly explain that a file-read wrapper/middleware updates `context.ledger["files_visited"]`, while the context stage returns a compact `RepositoryContext` in candidate state. Rejected candidate context is discarded, but the visited-file ledger and verifier feedback remain available to the repeated context stage.

#### Logic / Algorithm

1. `vidbyte.workflows.__init__` re-exports every supported public contract, adapter, graph/runtime class, and workflow error; private compiled-definition classes stay private.
2. Root `vidbyte.__init__` mirrors the primary public surface in its imports and `__all__` without adding a client property.
3. The root README adds workflows to the feature map and a short decision guide: pipeline for simple strings/topologies, workflow for typed gated state, paradigm for an opinionated recipe, harnesses for external execution integration.
4. `llms.txt` adds a concise machine-readable package summary, core invariants, imports, and example.
5. Package documentation emphasizes deterministic enforcement versus probabilistic judgment and shows deterministic validators before the agent verifier.

#### Edge Cases & Error Handling

- Documentation will not imply external side-effect rollback, durable resume, or deterministic LLM grading.
- Examples will use only names exported by this change and existing SDK/Pydantic APIs.
- Root import smoke checks will detect missing or cyclic re-exports before the PR is opened.

---

## 7. Data Model Changes

### 7.1 In-Memory Workflow Contracts

**Change type:** New

```python
# No database schema is introduced. The durable shape is the public Python
# contract family described in section 6.1:
#
# RetryPolicy, StagePolicy, StateMachineSettings
# WorkflowFeedback, StageResult, ValidationResult
# StageContext, ValidationContext, RoutingContext
# ValidationRecord, StageExecution, TransitionRecord, WorkflowEvent
# RouteTarget, StateMachineResult
```

**Migration strategy:**

- Forward migration: N/A - callers opt into a new additive package and construct new in-memory objects.
- Rollback plan: Remove workflow imports/package usage from callers; no stored records or database migrations need reversal.
- Serialization: V1 does not define a stable JSON persistence schema. Mappings/details may contain arbitrary developer values, and the run ledger is only shallow-snapshotted.

### 7.2 User-Supplied `StateT`

**Change type:** New generic contract, no repository-owned schema

```python
StateT = TypeVar("StateT")

# Accepted through StateGraph(state_type=...), normalized by either:
# 1. the developer's state_validator,
# 2. Pydantic TypeAdapter for supported types, or
# 3. strict isinstance fallback for ordinary classes.
```

**Migration strategy:**

- Forward migration: Developers define a dataclass, Pydantic model, or other explicit state class for each workflow.
- Rollback plan: The same state can continue to be passed manually between agents or pipelines.
- Constraint: State should contain data, not live agents/tools; graph components own executable objects. This keeps cloning and candidate rollback tractable.

---

## 8. API Changes

### 8.1 Public Python Workflow API

**Change type:** New

N/A - no HTTP endpoint, request body, response body, or network status codes are introduced. The complete constructor/method contracts are specified in sections 6.1-6.6. The stable import surfaces are `vidbyte.workflows` and root `vidbyte`.

**Request:**

```python
result = await compiled_machine.arun(
    initial_state,
    run_id=None,
    ledger=None,
    metadata=None,
    observers=(),
)
```

**Response:**

```python
StateMachineResult[StateT](
    run_id="...",
    status=MachineStatus.SUCCEEDED,
    terminal="done",
    state=final_committed_state,
    ledger={...},
    metadata={...},
    stages=(...),
    transitions=(...),
    events=(...),
    observer_errors=(),
    duration_ms=...,
)
```

**Error cases:**

| Exception | Condition |
|-----------|-----------|
| `WorkflowDefinitionError` | Graph is incomplete, ambiguous, or statically unreachable |
| `WorkflowStateError` | Initial/candidate validation or state cloning fails |
| `WorkflowValidationError` | Validator policy is `RAISE` and validation abstains/errors/throws |
| `StageExecutionError` | A stage exhausts retries without a declared error route |
| `WorkflowRoutingError` | Outcome/code/branch key has no declared route |
| `TransitionLimitError` | Selected transition attempts exceed the configured maximum |
| `WorkflowExecutionError` | Full-run timeout or another machine-level execution failure occurs |
| `asyncio.CancelledError` | Caller cancels the run; cancellation propagates unchanged |

### 8.2 Existing APIs

**Change type:** Modified only by additive exports/documentation

N/A - no existing method signatures, endpoint contracts, clients, pipelines, paradigms, graders, agents, or harness clients change behavior. Root `vidbyte` gains new import names only.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/validated-state-machine-workflows.md` | Approved source of truth for the feature |
| CREATE | `vidbyte/workflows/__init__.py` | Stable public package exports |
| CREATE | `vidbyte/workflows/README.md` | Package role, semantics, decision guide, and end-to-end examples |
| CREATE | `vidbyte/workflows/contracts.py` | Public statuses, settings, contexts, protocols, feedback, records, and results |
| CREATE | `vidbyte/workflows/errors.py` | Feature-local typed error hierarchy rooted at `VidbyteSdkError` |
| CREATE | `vidbyte/workflows/validation.py` | Callable, schema, grader, agent, and composite validator implementations |
| CREATE | `vidbyte/workflows/stages.py` | Callable and `BaseAgent` stage adapters |
| CREATE | `vidbyte/workflows/routing.py` | Callable conditional-router adapter |
| CREATE | `vidbyte/workflows/graph.py` | Mutable graph builder and compile-time validation/snapshot logic |
| CREATE | `vidbyte/workflows/machine.py` | Immutable compiled runtime and deterministic transition algorithm |
| MODIFY | `vidbyte/__init__.py` | Add root convenience imports and `__all__` entries |
| MODIFY | `README.md` | Add workflows to SDK feature documentation and layer-selection guidance |
| MODIFY | `llms.txt` | Add LLM-readable workflow API and invariants |

No files will be deleted. No test files or verification scripts will be created or modified.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python 3.11+ | `asyncio`, protocols/generics, dataclasses, UUIDs, timing, mapping proxies, deep copy | Low; already required by the project |
| Pydantic | Existing `>=2,<3` | Compile user state/verdict/schema adapters and normalize validation failures | Low; already a required dependency, but arbitrary custom classes may need the documented `state_validator` fallback |
| Vidbyte `BaseAgent` / `AgentForkSettings` | In-repository API | Fresh agent stages and verifier agents with structured output | Medium; adapters must avoid circular imports and preserve current fork/output-schema semantics |
| Vidbyte `BaseGrader` / `EvalCase` | In-repository API | Reuse deterministic and LLM graders as validation gates | Low; narrow adapter only |
| External model provider | Developer configured; no new endpoint | Used only when the developer supplies `AgentStage`, `AgentValidator`, or an LLM grader | Medium; latency, cost, outage, and nondeterministic verdicts are bounded but not removed by this feature |

No new package dependency, database, queue, service, credential, environment variable, or network endpoint is introduced.

---

## 11. Rollout & Deployment

- No feature flag is required; the package is additive and unused until imported and instantiated.
- There is no breaking migration. Existing agents, tools, pipelines, paradigms, evals, sessions, and harness integrations retain their behavior.
- Implementation will begin only after explicit approval, in `feat/validated-state-machine-workflows`, created from the latest `main` in an isolated worktree.
- The design document will be the first commit in that worktree, followed by logical implementation and documentation commits.
- Verification will use existing repository checks rather than new test/script files: `python -m compileall vidbyte`, `python -m unittest discover -s tests -v`, root/public import smoke checks, an inline deterministic graph smoke covering pass/reject/loop/branch/guard behavior, and package build/wheel inspection commands from `CONTRIBUTING.md`/the publish workflow.
- Rollout risk is primarily public-contract breadth without feature-specific committed tests, as requested by the no-tests workflow. The inline smoke must exercise the core candidate-discard and recovery semantics, and the post-implementation adversarial self-review must reconcile every numbered requirement.
- Rollback is one additive-code revert: remove root exports/docs and the `vidbyte.workflows` package. No data migration or external resource cleanup is required. The design doc may remain as historical rationale or be reverted with the feature.
- A later PR may migrate `ContextMinimalFanoutParadigm` or an outer harness implementation onto this primitive only after the base API has been reviewed independently.

---

## 12. Open Questions

N/A - the prior architecture discussion and repository audit resolve the v1 namespace, transactional semantics, validator placement, agent-verifier behavior, direct-import API, and non-goals. Approval of this document confirms those decisions. Durable persistence, graph-level parallelism, nested graphs, human approvals, and migration of an existing paradigm are explicitly deferred follow-up designs rather than blockers for this implementation.

---

## 13. Alternatives Considered

### Alternative 1: Prompt-Enforced Orchestrator with Agent Tools

- What: Put “first context, then spec, then implementation” in a main agent's system prompt and expose child agents through `AgentTool`.
- Why rejected: The model still chooses whether and when to call tools, can skip checks, and receives no typed candidate/commit boundary. It is useful inside a stage but does not meet the core deterministic-enforcement premise.

### Alternative 2: Manual Agent-to-Agent Handoffs

- What: Run separate agents in application code and pass each output directly to the next.
- Why rejected: It works for one linear harness but repeats routing/retry/validation bookkeeping, lacks a reusable graph contract, and does not standardize rejection feedback, cycles, branches, records, or compile-time checks.

### Alternative 3: Extend `vidbyte.pipelines`

- What: Add shared state, validators, loops, and guarded transitions to `BasePipeline` and existing topology classes.
- Why rejected: The package explicitly promises small string-in/string-out composition with no implicit shared state or retries. Expanding it would blur a deliberately simple abstraction and create incompatible semantics for existing users.

### Alternative 4: Put the Runtime in `vidbyte.paradigms`

- What: Implement one context/spec/implementation stateful paradigm and make its internal classes reusable.
- Why rejected: Paradigms are opinionated recipes. The requested validator/transition machinery is a general control-flow primitive that multiple paradigms and harness implementations should compose.

### Alternative 5: Put the Runtime in `vidbyte.harnesses`

- What: Treat the state graph as the harness abstraction itself.
- Why rejected: Harnesses are the external execution/configuration boundary, while this graph defines an internal algorithm. Keeping them separate allows a future loaded harness to wrap any state machine without making graph users adopt persistence or launcher contracts.

### Alternative 6: Make Every Verification Check a Stage

- What: Model context checking, schema checking, and transition permission exclusively as explicit graph nodes.
- Why rejected: Substantial verification should be a stage, but small boundary predicates become noisy, duplicate state plumbing, and obscure the invariant that output is checked before commit. Stage validators and transition guards provide the right first-class entry points while explicit verification stages remain available.

### Alternative 7: Let Routers or Verifier Agents Return Stage Names

- What: Allow an agent verdict such as `go_to="implementation"` to jump directly.
- Why rejected: That gives the probabilistic component control-plane authority and makes typo/prompt-injection behavior a route. Bounded semantic codes mapped by the compiled graph preserve deterministic policy and still allow arbitrary declared jumps.

### Alternative 8: Commit Candidate State Before Validation

- What: Let stage mutations take effect immediately and use validation only to choose the next node.
- Why rejected: A failed check could contaminate later attempts and make “go back” semantics ambiguous. Clone-first, validate, then commit gives the state machine a real deterministic gate. The separately named run ledger handles observations that intentionally survive rejection.

### Alternative 9: Add a Third-Party State-Machine/Graph Dependency

- What: Build on a package such as `transitions` or an agent-graph framework.
- Why rejected: The necessary runtime is small, its transactional validator semantics are specific to Vidbyte, and a new dependency would expose provider/framework concepts or require an adapter nearly as complex as the core. The design uses only existing SDK/Pydantic contracts and standard Python.
