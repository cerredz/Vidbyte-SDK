# Workflows

## Folder Description / Intent

`vidbyte.workflows` is the SDK's reusable control-flow layer for typed, gated,
non-linear agent workflows. It exists for harnesses where Python code must own
the legal stage graph, validate candidate state before commit, bound retries and
cycles, and preserve structured execution evidence. Use this folder when a
simple string pipeline is too weak but a concrete paradigm would be too
opinionated.

The package treats stages, validators, and routers as replaceable protocols.
Vidbyte agents, eval graders, Pydantic schemas, and ordinary Python callables
enter through adapters; the compiled state machine remains the authority for
where execution may go. This separation keeps a probabilistic agent useful for
work or judgment without giving it permission to invent a stage destination.

Candidate workflow state is transactional only in memory: a stage receives a
clone, validators inspect its result, and the runtime commits it only after an
allowed transition passes. The run ledger is intentionally non-transactional so
mechanical observations such as `files_visited` can survive a rejected attempt.
External filesystem, tool, and network side effects are never rolled back by
this package.

This folder is not an agent runtime, prompt catalog, persistence service, or
ready-made software-engineering harness. Those responsibilities remain in their
existing SDK packages; a workflow composes them.

## Blast Radius

The package is imported by the root `vidbyte` convenience surface and directly
by SDK users. Changes to result records, validator normalization, route lookup,
or candidate commit semantics can alter every harness built on a compiled
`StateMachine`, so public contract changes require a design update and explicit
compatibility review. Agent and grader adapters also depend on the stable
contracts in `vidbyte.agents` and `vidbyte.evals`.

## Core Invariants

- A stage, router, or verifier emits a bounded semantic code; only the compiled
  graph maps that code to a target.
- A stage always starts from a clone of the latest committed state.
- A candidate becomes committed state only after stage validators and selected
  transition guards permit it.
- Rejection and handled stage errors route with unchanged committed state and
  structured feedback.
- Every selected transition attempt consumes the run's transition budget,
  including attempts rejected by guards.
- The run ledger survives rejection and is never presented as rollback-safe.
- Compiled graph definitions are immutable snapshots and keep per-run mutation
  inside the execution call.
- Agent verifier failure blocks progression by default; this does not make the
  verifier's substantive judgment deterministic.

## Non-Goals

- Do not implement model calls, tool loops, or conversation history here; those
  belong in `vidbyte.agents`.
- Do not add model-callable filesystem or service capabilities here; tools
  belong in `vidbyte.tools`.
- Do not implement context placement, compaction, or repository-context data
  models here; those belong in `vidbyte.context` or the consuming paradigm.
- Do not add agent-loop budgets, tool authorization, or model-call retry policy
  here; those belong in `vidbyte.middleware`. Workflow retries cover stage
  invocation as a graph operation.
- Do not expand this package into string fan-out, join, or map/reduce helpers;
  simple topology composition belongs in `vidbyte.pipelines`.
- Do not ship a ready-made context/spec/implementation recipe here; opinionated
  harnesses belong in `vidbyte.paradigms`.
- Do not add launcher configuration, discovery, or external harness adapters
  here; those belong in `vidbyte.harnesses`.
- Do not add durable checkpoints, artifact stores, or run databases here;
  persistence belongs in `vidbyte.sessions` or a future harness execution
  envelope.

## Choosing the Right Layer

| Need | Use |
|------|-----|
| Chain or fan out string-producing agents | `vidbyte.pipelines` |
| Enforce typed state, validation gates, loops, and declared jumps | `vidbyte.workflows` |
| Run an opinionated reusable agentic recipe | `vidbyte.paradigms` |
| Adapt SDK objects to an external execution harness | `vidbyte.harnesses` |
| Enforce policy inside one agent loop | `vidbyte.middleware` |

## Usage

```python
from dataclasses import dataclass, replace

from vidbyte import CallableStage, CallableValidator, MachineStatus
from vidbyte import StageResult, StateGraph, ValidationResult


@dataclass(frozen=True)
class HarnessState:
    request: str
    context: str = ""
    spec: str = ""


async def gather_context(ctx):
    # A real stage can be AgentStage; this callable keeps the example local.
    visited = ctx.ledger.setdefault("files_visited", set())
    visited.add("vidbyte/agents/base.py")
    return StageResult(replace(ctx.state, context="agent and tool contracts"))


def context_is_sufficient(ctx):
    if ctx.candidate_state.context:
        return ValidationResult.passed()
    return ValidationResult.rejected("needs_more_context", "No relevant context was selected.")


async def write_spec(ctx):
    return StageResult(replace(ctx.state, spec=f"Implement using {ctx.state.context}"))


graph = StateGraph(HarnessState, name="software-engineering-harness")
graph.add_stage("context", CallableStage(gather_context), validators=(CallableValidator(context_is_sufficient),))
graph.add_stage("spec", CallableStage(write_spec))
graph.add_terminal("done", status=MachineStatus.SUCCEEDED)
graph.set_entry("context")
graph.add_transition("context", "spec")
graph.add_transition("context", "context", on="needs_more_context")
graph.add_transition("spec", "done")

result = await graph.compile().arun(HarnessState(request="Add a state machine"))
```

## Agent-Verifier Guardrail

An agent verifier uses the same boundary. Its structured verdict maps to a
semantic validation result, and the graph maps that result to a recovery stage.
The verifier never receives a method that changes the machine's current stage.

```python
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from vidbyte import AgentStage, AgentValidator, SchemaValidator
from vidbyte import StageResult, StateGraph, StateMachineSettings, ValidationResult


@dataclass(frozen=True)
class EngineeringState:
    request: str
    context: str = ""
    spec: str = ""
    implementation: str = ""


class ContextVerdict(BaseModel):
    decision: Literal["enough_context", "needs_more_context"]
    feedback: str
    missing: list[str] = Field(default_factory=list)


context_verifier = AgentValidator(
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

context_schema = SchemaValidator(
    str,
    selector=lambda ctx: ctx.candidate_state.context,
)

graph = StateGraph(EngineeringState, name="software-engineering-harness")
graph.add_stage(
    "context",
    AgentStage(context_agent_factory, build_context_prompt, build_context_result),
    validators=(context_schema, context_verifier),
)
graph.add_stage("spec", AgentStage(spec_agent, build_spec_prompt, build_spec_result))
graph.add_stage(
    "implementation",
    AgentStage(implementation_agent, build_implementation_prompt, build_implementation_result),
)
graph.add_stage("verify", AgentStage(verification_agent, build_verification_prompt, build_verification_result))
graph.add_terminal("done")
graph.set_entry("context")
graph.add_transition("context", "spec")
graph.add_transition("context", "context", on="needs_more_context")
graph.add_transition("spec", "implementation")
graph.add_transition("implementation", "verify")
graph.add_transition("verify", "done", on="approved")
graph.add_transition("verify", "implementation", on="revise")

machine = graph.compile(settings=StateMachineSettings(max_transitions=12))
result = await machine.arun(
    EngineeringState(request="Add a state machine"),
    ledger={"files_visited": set()},
)
```

The names ending in `_agent`, `_prompt`, and `_result` above are application
components. A result builder converts the agent reply into a typed `StageResult`
and a semantic outcome such as `approved` or `revise`; it does not choose a
destination.

For a context-gathering harness, construct the context agent through an
`AgentStage` factory that closes tracking read tools over
`StageContext.ledger`. Keep every file ever read in the ledger, keep only the
selected compact `RepositoryContext` in candidate workflow state, and use the
existing `ContextManager` when the agent's active model context needs pruning.

## File Index

- `README.md` - Explains the folder boundary, invariants, layer-selection rules,
  and end-to-end usage. Open this first when deciding whether a new orchestration
  behavior belongs in workflows, pipelines, paradigms, middleware, or harnesses.
- `__init__.py` - Defines the stable public package surface. Open it when adding
  or deprecating a public workflow contract; keep `__all__`, root exports, the
  root README, and `llms.txt` aligned in the same change.
- `contracts.py` - Owns public enums, policies, contexts, protocols, records,
  feedback, and results. Open it for data-shape changes, not for execution or
  routing algorithms.
- `errors.py` - Owns typed workflow definition, state, validation, stage,
  routing, and transition-limit failures. Open it when a new distinct public
  failure mode needs safe structured details.
- `validation.py` - Adapts callables, Pydantic schemas, eval graders, verifier
  agents, and validator composites. Open it for gate behavior; destination
  lookup must remain in `graph.py` and `machine.py`.
- `stages.py` - Adapts callables and Vidbyte agents into stage execution. Open
  it for agent fork/input/result behavior; retry and commit policy remain in the
  compiled runtime.
- `routing.py` - Adapts synchronous or asynchronous branch functions to the
  router protocol. Open it for router invocation only; branch-key declarations
  belong in `graph.py`.
- `graph.py` - Owns the mutable builder, immutable compiled definitions, state
  contract, reachability checks, and route ambiguity checks. Open it for static
  graph policy; do not put run counters or current state here.
- `machine.py` - Owns per-run stage execution, validation normalization,
  transition guards, candidate commit, records, observer events, and terminal
  results. Open it for runtime semantics; do not mutate compiled definitions.

## Logs

- 2026-07-12 - Separated committed state from the non-transactional run ledger - prevents rejected agent output from contaminating workflow state while preserving mechanical observations.
- 2026-07-12 - Kept semantic codes separate from target names - prevents model or verifier output from acquiring control-plane authority.

## Related Documentation

- [Validated State Machine Workflows design](../../docs/design/validated-state-machine-workflows.md)
- [Pipelines](../pipelines/README.md)
- [Paradigms](../paradigms/README.md)
- [Harnesses](../harnesses/README.md)
- [Middleware](../middleware/README.md)
