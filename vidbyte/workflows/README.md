# Workflows

`vidbyte.workflows` is the SDK control plane for agent harnesses whose legal
phases, permissions, budgets, validation gates, suspensions, and recovery paths
must be owned by Python rather than prompt instructions. Graphs may branch and
cycle. A compiled graph is immutable and reusable; every run has an isolated,
append-only event stream and projected lifecycle.

Use a pipeline for simple string-in/string-out composition. Use a workflow when
the harness needs typed shared state, deterministic transition authority,
durable resume, per-phase agent policy, or human approval.

## Mental model

A workflow has two independent axes:

- `current_stage` is the workflow position, such as `recon`, `implement`, or
  `verify`.
- `WorkflowLifecycleStatus` is the execution condition: `RUNNING`,
  `WAITING_FOR_CONFIRMATION`, `INTERRUPTED`, `FINISHED`, or `ERROR`.

A stage receives an isolated state snapshot and proposes a `WorkflowCommand`.
Reducers build a candidate. Stage validators, a bounded route, transition
guards, and any approval gate run before that candidate becomes committed
state. Only the compiled graph maps outcomes, router keys, or declared command
targets to a destination.

Every control-changing fact is first appended as a `WorkflowEvent`. A
`WorkflowProjection` derives the current state from those events. Checkpoints
are disposable projection caches; the retained event stream is canonical.

## Core invariants

- Agent output, routers, validators, interrupt values, and child graphs cannot
  introduce an undeclared destination.
- Transition-bound state is committed only after all applicable gates pass.
- Immediate observations are appended through `await ctx.observe(...)`; the
  `ctx.observations` and compatibility `ctx.ledger` views are read-only.
- Every retry receives the same stage-visit `ctx.idempotency_key`.
- Cycles are legal and consume stage-visit, super-step, transition, time, usage,
  recursion, and detour budgets as applicable.
- Tool visibility and execution-time action guards are separate enforcement
  layers.
- Human waits do not consume execution timeout, and approval resumes do not
  rerun the completed source stage.
- Filesystem, network, model, and tool side effects are not transactional and
  are never claimed to roll back with candidate state.

## Quickstart: typed state and reducers

Declare every state channel, reducer, commit mode, and stage read/write set.
`StageResult` remains available for whole-state compatibility graphs;
`WorkflowCommand.update` is the channel-oriented API.

```python
from typing_extensions import TypedDict

from vidbyte.workflows import (
    AppendReducer,
    CallableStage,
    ReplaceReducer,
    StateChannel,
    StateCommitMode,
    StateGraph,
    StateMachineSettings,
    StateSchema,
    WorkflowBudget,
    WorkflowCommand,
)


class HarnessState(TypedDict):
    request: str
    findings: list[str]


schema = StateSchema(
    HarnessState,
    channels={
        "request": StateChannel(ReplaceReducer(), str),
        "findings": StateChannel(AppendReducer(), list),
        "files_seen": StateChannel(
            AppendReducer(),
            list,
            commit_mode=StateCommitMode.IMMEDIATE,
        ),
    },
    version="1",
)


async def recon(ctx):
    await ctx.observe("files_seen", "vidbyte/workflows/graph.py")
    return WorkflowCommand(update={"findings": ["Graph routes are bounded."]})


graph = StateGraph(
    HarnessState,
    name="coding-harness",
    version="2026-07-13",
    state_schema=schema,
)
graph.add_stage(
    "recon",
    CallableStage(recon),
    reads={"request"},
    writes={"findings", "files_seen"},
)
graph.add_terminal("done")
graph.set_entry("recon")
graph.add_transition("recon", "done")

machine = graph.compile(
    settings=StateMachineSettings(
        budget=WorkflowBudget(max_super_steps=20, max_transitions=20),
    )
)
result = await machine.arun({"request": "Inspect routing", "findings": []})
```

`capabilities` and `model_route` require a policy-aware stage such as
`AgentStage`; ordinary `CallableStage` callbacks do not receive agent policy.

## Routes, guards, commands, and cycles

Stages return semantic outcomes. Direct and conditional edges resolve those
outcomes through a finite compiled map. `WorkflowCommand(goto="verify")` is
accepted only when `add_command_transition(source, "verify")` declared that
exact jump.

```python
graph.add_transition("implement", "verify", on="ready", guards=(tests_exist,))
graph.add_transition("verify", "implement", on="revise")  # a legal cycle
graph.add_branch(
    "triage",
    severity_router,
    {"small": "implement", "large": "plan"},
    on="classified",
)
graph.add_command_transition("implement", "verify")
```

Routers return branch keys, never stage names with implicit authority. Name
callable routers explicitly so their stable identity participates in the graph
definition fingerprint.

## Per-stage agent policy

`AgentStage` creates an isolated fork for each invocation. The graph can remove
tool schemas before the model call, guard every visible action before execution,
and select a stage-specific model and loop policy.

```python
from vidbyte.workflows import (
    ActionPolicy,
    AgentModelRoute,
    AgentStage,
    CommandArgumentGuard,
    EditBudgetGuard,
    ModelRetryPolicy,
    PathActionGuard,
    StageCapabilities,
    ToolVisibility,
)

implement_policy = StageCapabilities(
    tools=ToolVisibility.exact("read_text", "patch_file", "run_shell"),
    action_policy=ActionPolicy(
        guards=(
            CommandArgumentGuard(
                frozenset({"run_shell"}),
                allow_prefixes=("git diff", "python -m"),
                deny_patterns=(r"\brm\s+-rf\b", r"\bsed\s+-i\b"),
            ),
            PathActionGuard(
                frozenset({"read_text", "patch_file"}),
                allowed_globs=("vidbyte/**", "docs/**"),
                denied_globs=("**/.env", "**/*secret*"),
            ),
            EditBudgetGuard(max_changed_lines=400),
        )
    ),
)

graph.add_stage(
    "implement",
    AgentStage(coder, build_prompt, build_result),
    capabilities=implement_policy,
    model_route=AgentModelRoute(
        provider="openai",
        model_name="gpt-5",
        runner_options={"reasoning_effort": "high"},
        model_retry=ModelRetryPolicy(max_attempts=2),
    ),
)
```

`ToolVisibility.none()`, `.read_only()`, and `.exact(...)` change what schemas
the model sees. They are not an operating-system sandbox. Action guards are a
second, pre-execution layer; workspace/container policy remains the outermost
security boundary. Runner options are preserved on agent/session forks, while
credential-like keys are omitted from exported state and graph fingerprints.

All `AgentStage` invocations install stuck detection. It recognizes repeated
action/observation pairs, repeated action/error cycles, monologues without tool
calls, action ping-pong, and repeated context-window errors. A threshold match
appends safe evidence and terminates the workflow lifecycle with
`WorkflowStuckError`.

## Budgets and failure

`StagePolicy` owns per-stage retry, timeout, and visit limits. `WorkflowBudget`
owns run-wide ceilings for super-steps, transitions, model calls, tool calls,
tokens, cost, execution time, child concurrency, recursion depth, and detour
depth. Usage is additive through `UsageReport`; unknown cost is fail-closed by
default when a cost ceiling is configured.

Budget, timeout, stuck, persistence, and unhandled execution failures append an
`ERROR` lifecycle event and attach a `StateMachineResult` to the raised
`WorkflowError`. Cancellation and other `BaseException` control signals are
not swallowed.

## Human approval and replayable interrupts

Approval is an edge property. Every confirmation-capable edge declares a
rejection outcome so denial has a bounded recovery route.

```python
from vidbyte.workflows import ApprovalGate, ConfirmRisky, ResumeCommand, RiskLevel

graph.add_transition(
    "implement",
    "publish",
    approval=ApprovalGate(
        required=False,
        reason="Publish the generated change?",
        rejection_outcome="approval_denied",
    ),
    risk=RiskLevel.HIGH,
)
graph.add_transition("implement", "revise", on="approval_denied")

result = await machine.arun(
    initial_state,
    confirmation_policy=ConfirmRisky(),
    store=store,
)
result = await machine.aresume(
    result.run_id,
    command=ResumeCommand.approve(result.pending.request_id),
    store=store,
)
```

`NeverConfirm`, `AlwaysConfirm`, and `ConfirmRisky` are available. A policy can
pause only an edge that has an `ApprovalGate`, because the gate defines denial
semantics. Approving resumes the persisted candidate and does not rerun the
source stage.

A Python stage can request typed input with
`ctx.interrupt(WorkflowInterrupt(...))`. The runtime persists the call ordinal,
returns an `INTERRUPTED` result, and injects `ResumeCommand.resume(...)` as that
call's return value when the stage replays. Because replay re-enters the stage,
external effects before the interrupt must use `ctx.idempotency_key` or be
otherwise idempotent. A command-level interrupt persists a completed candidate
and resumes without rerunning its source.

## Signals and interrupt-driven detours

Detours turn bounded side conditions into declared control flow. A matching
signal pushes an immutable return frame, checkpoints, enters the detour stage,
and returns only through `WorkflowCommand(return_from_detour="rule-id")`.

```python
from vidbyte.workflows import DetourRule, FileSignalMatcher, WorkflowCommand

graph.add_detour(
    DetourRule("validate-python-edit", FileSignalMatcher(("**/*.py",))),
    target="validate",
)

async def validate(ctx):
    # Run deterministic validation, then return to the interrupted source.
    return WorkflowCommand(return_from_detour="validate-python-edit")
```

Signals may be returned explicitly in `WorkflowCommand.signals`. For
`AgentStage`, successful built-in `patch_file`, `replace_text`, and `write_text`
calls also produce file-change evidence. A matching tool-bound rule aborts the
current agent invocation immediately, enters the detour, and retries the source
after return. The same stage-visit idempotency boundary applies; no tool side
effect is rolled back.

## Isolated child graphs

Register child machines with `add_subgraph(...)`, then fan out deterministic
`Send` values from a command. Each child has its own run ID, event stream,
state, context, and intersected budget. The child run ID is derived from the
parent visit and `Send` key, so parent crash replay inspects or resumes the same
child instead of duplicating it. Children share only caller-managed external
resources such as the workspace. Results join in original `Send` order,
regardless of completion order.

Child failure policy is `FAIL_FAST` or `COLLECT`. A child approval or interrupt
suspends the parent with a `SUBGRAPH` pending request. Resume advances that
exact child, preserves completed siblings, and runs the parent join only once
all children finish.

## Persistence, resume, and time travel

Use `InMemoryWorkflowStore` for process-local execution or
`FileWorkflowStore` for caller-owned JSON persistence. Durable stores require an
explicit graph `version`; Python callback bodies, prompts, credentials, and live
agent objects cannot be safely fingerprinted. Cold resume must supply the same
compiled definition, whose definition and state-schema IDs are checked before
replay.

```python
from vidbyte.workflows import FileWorkflowStore

store = FileWorkflowStore(".vidbyte/workflows")
result = await machine.arun(initial_state, run_id="issue-268", store=store)
current = await machine.inspect("issue-268", store=store)
earlier = await machine.inspect("issue-268", store=store, through_sequence=12)
resumed = await machine.aresume("issue-268", store=store)
```

`inspect()` is read-only replay: it never invokes stages, validators, routers,
models, tools, observers, or child graphs. Returned event, definition, and
checkpoint containers are recursively immutable; reducers and serializers
receive detached copies. The file adapter uses immutable JSON records,
same-directory atomic no-overwrite publication, and optimistic sequence checks.
A database-backed store is required for transactional distributed writers.

Workflow persistence is separate from `vidbyte.sessions`: sessions persist one
agent's conversation/checkpoint DAG, while workflow stores persist a graph's
control-plane events and projection checkpoints.

## Security and idempotency boundaries

- Treat event stores as sensitive. State channels can be marked `sensitive` for
  schema metadata, but the built-in stores do not encrypt or redact payloads.
- Keep secrets out of workflow state, observations, command metadata, signals,
  feedback, and child inputs.
- Use idempotency keys for every external write that may be replayed after a
  crash or stage interrupt.
- Prefer candidate artifacts or explicit compensation when an external action
  must be validated before becoming authoritative.
- Tool filtering controls model visibility; action guards control SDK tool
  execution; neither replaces host filesystem, process, or network isolation.
- File-store optimistic checks do not provide multi-process transactions.

## Package map

- `contracts.py`: commands, contexts, policies, lifecycle, results, and records.
- `state.py`: typed schemas, codecs, reducers, and commit modes.
- `graph.py`: declarations, static validation, definition fingerprints, and
  immutable compilation.
- `machine.py`: event-sourced execution, validation, routing, suspension,
  resume, detours, children, and terminal/error handling.
- `events.py`, `projection.py`, `persistence.py`, `stores/`: canonical events,
  replay, checkpoints, and storage adapters.
- `capabilities.py`: tool visibility, model routing, and action guards.
- `approval.py`, `detours.py`, `detection.py`, `subgraphs.py`, `budget.py`:
  focused harness policies.
- `stages.py`, `routing.py`, `validation.py`: adapters for agents, callbacks,
  routers, schemas, graders, and verifier agents.

## Related documentation

- [Agent harness state-machine runtime design](../../docs/design/agent-harness-state-machine-runtime.md)
- [Agents](../agents/README.md)
- [Tools](../tools/README.md)
- [Middleware](../middleware/README.md)
- [Pipelines](../pipelines/README.md)
- [Sessions](../sessions/README.md)
