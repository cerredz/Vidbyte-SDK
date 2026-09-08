# Design Doc: Codex Pipeline Composition

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

The SDK's four pipeline topologies — sequential, parallel fan-out, map-reduce fan-in, and conditional routing — all dispatch through one line: `stage.generate_reply(prompt, **options)`. `CodexHarnessAgent` has no `generate_reply`, and `PipelineNode` is typed as `Union["BaseAgent", "BasePipeline"]`, so a Codex agent cannot be a pipeline stage at all. This change adds a `VidbyteAgent` protocol both agent kinds satisfy, widens `PipelineNode` to it, gives the Codex agent a `generate_reply` accepting the shared input types, and — because fan-out runs stages under `asyncio.gather` — serializes turns per agent so a Codex agent used twice in one concurrent stage list cannot corrupt its own thread id, history, and usage ledger.

---

## 2. Goals & Non-Goals

### Goals

- Add a `VidbyteAgent` protocol declaring `name`, `generate_reply`, and `arun`, satisfied structurally by both `BaseAgent` and `CodexHarnessAgent`.
- Widen `PipelineNode` to that protocol so `_invoke`'s dispatch is type-checked rather than duck-typed against a method name.
- Add `CodexHarnessAgent.generate_reply(message, **options)` accepting `str | AgentInput | CodexRunInput`.
- Reject any `**options` the adapter cannot honor, naming each, rather than silently accepting a knob that does nothing.
- Serialize turns per agent instance with an `asyncio.Lock`, so a fan-out over distinct agents stays concurrent while the same agent used twice runs its turns in sequence.
- Make all four topologies work with a Codex stage, including a Codex agent as the reduce stage of a map-reduce.

### Non-Goals

- Workflows. `vidbyte/workflows/stages.py:106` and `validation.py:231` already call `agent.arun(prompt)`, which works once the input types are accepted; no workflow change is needed here.
- Multi-agent dispatch. `vidbyte/agents/multi/dispatcher.py` routes through `worker_generate_reply` and carries `AgentBinding` state this change does not model; roadmap N05 owns it.
- Concurrent turns on one Codex *thread*. The lock serializes them because a Codex thread is a single conversation; running two turns against it simultaneously is not a performance opportunity the provider offers.
- Native thread forking per stage. A fan-out over one agent could fork a thread per branch instead of serializing — roadmap F04 — but that changes the conversation semantics and needs its own design.
- `AgentCard` or capability declaration. The protocol declares the call contract, not what an agent can do.

---

## 3. Background & Context

`BasePipeline._invoke` is the entire integration surface (`vidbyte/pipelines/base.py`):

```python
@staticmethod
async def _invoke(stage: PipelineNode, prompt: str, **options: Any) -> str:
    """Dispatch to agent.generate_reply or nested pipeline.run."""
    if isinstance(stage, BasePipeline):
        return await stage.run(prompt)
    reply = await stage.generate_reply(prompt, **options)
    return reply.content
```

All four topologies reach it. `SequentialPipeline` threads output to input, `ParallelPipeline` runs `asyncio.gather` over stages with the same prompt and joins the outputs, `MapReducePipeline` fans out then feeds the joined text to a reduce stage, and `ConditionalPipeline` routes to one branch by predicate. A `CodexHarnessAgent` reaching that second branch raises `AttributeError`, and `PipelineNode = Union["BaseAgent", "BasePipeline"]` says so statically.

`BaseAgent` already offers both protocol methods: `generate_reply` at line 586 and `arun(self, message: str | AgentInput, **options)` at line 730. So the protocol is a description of what already exists on one side and a requirement on the other, which is what makes it a contract rather than a new abstraction.

The concurrency problem is specific and real. `CodexHarnessAgent` mutates five pieces of state per turn — `thread_id`, `history`, `last_prompt`, `last_reply`, and the `UsageTracker` merged in PR #413, which is reset at the top of `arun`. `ParallelPipeline` and `MapReducePipeline` both call `asyncio.gather` across their stages. Nothing stops a caller from listing the same agent twice, and nothing today would report the resulting interleaving: two turns would reset each other's usage ledger, append replies in nondeterministic order, and race on `thread_id`. The roadmap names this **L03** ("Control concurrent calls: define a per-thread serialization/rejection policy while allowing independent threads to run concurrently"), and this design implements exactly that.

Two field-guide constraints bind the work. *Class-Bound Helpers → "Audit every surface of a shared abstraction"* (PR #412) requires §9a. *Class-Bound Helpers → "Give each translated surface its own function, but keep a short type dispatch flat"* (PR #412) governs the input normalization: one dispatch function over the three caller shapes, not one per shape and not a pass-through alias.

### Overlap with open PR #412

PR #412 (`feat/codex-agent-input-bridge`) is open and adds `CodexVidbyteTranslator.translate_input()` with exactly this conversion. This change needs the same conversion, because `generate_reply` receives a `str` from every pipeline topology. Rather than invent a second, differently-shaped conversion, this PR adds the same method with the same name and behavior. Whichever of the two merges second will conflict on that one method and should keep either copy — they are intended to be identical. Two divergent conversions would be far worse than one textual conflict.

---

## 4. Requirements

### Functional Requirements

1. A new `VidbyteAgent` protocol declares `name: str`, `generate_reply(message, **options) -> AgentMessage`, and `arun(message, **options) -> AgentMessage`.
2. The protocol is `@runtime_checkable`, so `_invoke` can narrow with `isinstance` where a static check is unavailable.
3. `PipelineNode` is `Union["VidbyteAgent", "BasePipeline"]`.
4. `BaseAgent` satisfies the protocol with no change to `BaseAgent`.
5. `CodexVidbyteTranslator.translate_input(value)` converts `str`, `AgentInput`, and `CodexRunInput` into one `CodexRunInput`, passing an existing request through by identity.
6. `CodexHarnessAgent.arun` and `.run` accept `str | AgentInput | CodexRunInput`.
7. `CodexHarnessAgent.generate_reply(message, **options)` returns the same `AgentMessage` `arun` returns.
8. `generate_reply` raises `CodexAgentError` with `CODEX_RUN_OPTION_UNSUPPORTED` naming every unrecognized keyword, because a pipeline passing `**options` a Codex agent silently drops would make the caller believe a setting applied.
9. Every turn holds a per-agent `asyncio.Lock`, so two concurrent `arun` calls on one agent run in sequence.
10. Two different Codex agents in one `ParallelPipeline` still run concurrently; the lock is per instance, never shared.
11. A serialized second turn observes the first turn's `thread_id`, so the conversation continues rather than forking.
12. `history` after two concurrent calls on one agent holds exactly two replies.
13. The usage rollup after serialized turns describes the last completed turn, matching the per-turn reset PR #413 established.
14. A `CodexHarnessAgent` works as a stage in all four topologies, and as the reduce stage of a map-reduce.
15. An input translation failure raises `CodexAgentError` with `operation="translate_input"` before the transport is touched.

### Non-Functional Requirements

- **Performance:** the lock is uncontended in the common case of one agent per stage, costing one `async with` per turn. Where it is contended, serialization is the correct behavior, not overhead — the alternative is corruption.
- **Scalability:** a fan-out over N distinct agents keeps N-way concurrency; only same-instance reuse serializes.
- **Security:** no new external input surface. Rejecting unknown options prevents a caller from believing an unenforced policy applied.
- **Observability:** an unsupported option names itself in the failure, so the caller learns which knob was refused.
- **Reliability:** the lock is released on every exit path including exceptions and cancellation, because `async with` unwinds on both.

---

## 5. High-Level Design

Three pieces.

**`VidbyteAgent`** (`vidbyte/lib/agents/protocol.py`) is the shared call contract, and it lives in `vidbyte/lib` for a layering reason: `vidbyte/pipelines/types.py` must import it, and while `vidbyte.pipelines` and `vidbyte.agents` are both orchestration-tier — so a direct import would be legal — putting the contract in `vidbyte.lib` keeps `PipelineNode` from depending on either agent implementation. The protocol declares only what `_invoke` actually calls plus `arun`, which workflows call; a protocol listing everything `BaseAgent` offers would exclude the Codex agent for methods no caller needs.

**`generate_reply`** on `CodexHarnessAgent` is a thin alias over `arun` with one addition: it rejects unrecognized `**options`. `BaseAgent.generate_reply` accepts options that configure a Vidbyte-owned loop — context, history, trace metadata — none of which a Codex agent has. Accepting and dropping them is the failure mode PR #415's middleware validator and PR #420's loop-settings validator both exist to prevent, so this follows the same rule: name what you cannot honor.

**The lock** is the part that makes fan-out correct rather than merely possible. `CodexHarnessAgent` holds `asyncio.Lock()` per instance, and `arun` takes it around the whole turn — translation, transport, result, and state mutation. Taking it around only the transport call would leave the five mutable fields racing, which is the actual defect. The lock is created in `__init__` rather than lazily, so two coroutines cannot race to create it.

```
ParallelPipeline.run(prompt)
   |
   |-- asyncio.gather over stages
   |
   +-- stage A (Codex agent #1) ---> _invoke -> generate_reply -> arun
   |                                                               |-- async with agent1._turn_lock
   +-- stage B (Codex agent #2) ---> _invoke -> generate_reply -> arun
   |                                                               |-- async with agent2._turn_lock   (concurrent: different locks)
   +-- stage C (Codex agent #1 again) -> _invoke -> generate_reply -> arun
                                                                     |-- async with agent1._turn_lock (waits for A)
   |
   v  join outputs with the separator
```

---

## 6. Detailed Design

### 6.1 VidbyteAgent protocol

**File(s):** `vidbyte/lib/agents/protocol.py`, `vidbyte/lib/agents/__init__.py`
**Type:** New file, then modified

#### Interface / API

```python
@runtime_checkable
class VidbyteAgent(Protocol):
    """The call contract every Vidbyte agent kind satisfies."""

    @property
    def name(self) -> str: ...

    async def generate_reply(self, message: Any, **options: Any) -> Any: ...

    async def arun(self, message: Any, **options: Any) -> Any: ...
```

#### Logic / Algorithm

1. Declared with loose `Any` parameter and return types, because the two implementations accept different input unions and a narrower protocol would exclude one of them for no benefit — `_invoke` only needs to know the methods exist and are awaitable.
2. `@runtime_checkable` so a caller can `isinstance`-narrow; note that a runtime-checkable protocol checks method presence only, which is exactly the guarantee `_invoke` needs.

#### Edge Cases & Error Handling

- **An object with the methods but wrong semantics.** `runtime_checkable` cannot detect that, and this design does not claim it can. The protocol replaces an `AttributeError` at call time with a type error at check time; it is not a behavioral guarantee.

### 6.2 Input translation

**File(s):** `vidbyte/agents/codex/config.py`, `vidbyte/lib/dataclasses/codex.py`
**Type:** Modified

#### Interface / API

```python
CodexAgentInput = str | AgentInput | CodexRunInput


class CodexVidbyteTranslator:
    def translate_input(self, value: CodexAgentInput) -> CodexRunInput: ...

    @staticmethod
    def _from_agent_input(value: AgentInput) -> CodexRunInput: ...
```

#### Logic / Algorithm

1. A `CodexRunInput` returns unchanged — identity, not a copy, so native image, skill, and mention items survive.
2. A `str` becomes `CodexRunInput.text(value)`.
3. An `AgentInput` maps `prompt`, `metadata`, `context_items`, and `context_manager` across, with the manager passed **by identity** because `CodexContextTranslator._sources` collapses a shared manager with `is`.
4. Anything else raises `ConfigurationError` naming the type.

The three branches live in one ordered dispatch rather than three call sites, per the field guide: it is one decision about one value, and only `_from_agent_input` actually transforms anything.

#### Edge Cases & Error Handling

- **Empty prompt.** `CodexTextInput.__post_init__` rejects it; the bridge does not pre-check, so there is one definition of valid text input.
- **`ContextManager.metadata`.** PR #412's review found this was dropped on every Codex turn. This change carries `context_manager` by identity, so whatever that PR's fix lands remains correct here.

### 6.3 generate_reply and option rejection

**File(s):** `vidbyte/agents/codex/agent.py`
**Type:** Modified

#### Interface / API

```python
class CodexHarnessAgent:
    async def generate_reply(self, message: CodexAgentInput, **options: Any) -> AgentMessage: ...
```

#### Logic / Algorithm

1. Reject every keyword in `options`, naming them all, because this adapter honors none of `BaseAgent`'s run options.
2. Delegate to `arun(message)`.

#### Edge Cases & Error Handling

- **A pipeline passing no options.** The common case; the check is a truthiness test on an empty dict.
- **Why reject rather than accept-and-ignore.** `_invoke` forwards whatever a caller gave `run(**options)`. Silently dropping `context=` or `history=` would produce a plausible answer computed without them.

### 6.4 Per-agent turn serialization

**File(s):** `vidbyte/agents/codex/agent.py`
**Type:** Modified

#### Logic / Algorithm

1. `__init__` creates `self._turn_lock = asyncio.Lock()`.
2. `arun` wraps its entire body in `async with self._turn_lock`, covering translation, transport, result translation, and every field mutation.
3. The lock is per instance, so distinct agents never contend.

#### Edge Cases & Error Handling

- **Cancellation.** `async with` releases on `CancelledError` like any other exception, so a cancelled turn cannot leave the lock held and deadlock every later turn.
- **`run()` from sync code.** Each `asyncio.run` call has its own loop; the guard in `run` still rejects an active loop, so no cross-loop lock reuse occurs.
- **Reentrancy.** `asyncio.Lock` is not reentrant. Nothing in `arun` calls `arun`, and `afork` constructs a new agent with its own lock rather than reentering.

### 6.5 PipelineNode widening

**File(s):** `vidbyte/pipelines/types.py`, `vidbyte/pipelines/base.py`
**Type:** Modified

#### Logic / Algorithm

1. `PipelineNode` becomes `Union["VidbyteAgent", "BasePipeline"]`.
2. `_invoke` is unchanged in behavior; its `stage` parameter is now the protocol, so the `generate_reply` call is checked rather than assumed.

#### Edge Cases & Error Handling

- **Existing `BaseAgent` stages.** Unaffected: `BaseAgent` structurally satisfies the protocol, so every existing pipeline keeps type-checking.

---

## 7. Data Model Changes

N/A - no persisted records, no database, no migration. One `Protocol`, one type alias, and one `asyncio.Lock` per agent instance; none is serialized.

---

## 8. API Changes

N/A - no HTTP endpoints. The public surface gains one protocol, one input alias, one agent method, one `FailureCode` member, and a widened `PipelineNode`. All additive; no existing signature narrows.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-pipelines.md` | This design document |
| CREATE | `vidbyte/lib/agents/protocol.py` | `VidbyteAgent` protocol |
| MODIFY | `vidbyte/lib/agents/__init__.py` | Export the protocol |
| MODIFY | `vidbyte/lib/dataclasses/codex.py` | `CodexAgentInput` alias |
| MODIFY | `vidbyte/lib/enums/failure.py` | `CODEX_RUN_OPTION_UNSUPPORTED` |
| MODIFY | `vidbyte/agents/codex/config.py` | `translate_input` and `_from_agent_input` |
| MODIFY | `vidbyte/agents/codex/agent.py` | Widened entry points, `generate_reply`, the turn lock |
| MODIFY | `vidbyte/pipelines/types.py` | `PipelineNode` accepts the protocol |
| MODIFY | `vidbyte/agents/codex/__init__.py` | Export `CodexAgentInput` |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export on the agents facade |
| MODIFY | `vidbyte/__init__.py` | Re-export for public-export integrity (S015) |
| CREATE | `tests/test_codex_pipelines.py` | Feature tests for the Testing Plan below |
| CREATE | `scripts/test-codex-pipelines.py` | Phase 5 verification script |

Totals: 4 create, 9 modify, 0 delete.

---

## 9a. Abstraction Surface Audit

Required by the field guide's *audit every surface* entry.

`AgentInput` has four fields, all **translated**: `prompt` becomes the single `CodexTextInput`, `metadata` is copied, `context_items` is reused as the immutable tuple it already is, and `context_manager` is passed by identity so the context translator's `is`-based source collapse still works. Nothing is dropped.

`BasePipeline` has three members: `run` (**not a translation** — the pipeline's own entry point), `run_sync` (same), and `_invoke` (**modified** — its `stage` type widens, its body is unchanged).

The four topologies are audited for what a Codex stage changes:

| Topology | Codex-specific consideration |
|---|---|
| `SequentialPipeline` | None — one stage at a time, output threaded to input |
| `ParallelPipeline` | **`asyncio.gather` over stages** — the lock is what makes same-instance reuse safe |
| `MapReducePipeline` | Same gather over map stages, plus a Codex agent may be the reduce stage receiving joined text |
| `ConditionalPipeline` | None — exactly one branch runs |

`CodexHarnessAgent`'s mutable state is enumerated because the lock exists to protect it: `thread_id`, `history`, `last_prompt`, `last_reply`, and `_usage`. `settings` and `_translation` are immutable after construction; the collaborators (`_transport`, `_results`, `_forks`) hold no per-turn state.

---

## 10. Testing Plan

All tests run offline against fake transports. Concurrency tests use an event-gated transport so interleaving is deterministic rather than timing-dependent.

### Unit Tests

- `VidbyteAgent` -> `BaseAgent satisfies the protocol` — [Hidden Assumption] — the protocol is only a contract if the existing implementation already meets it; a mismatch would silently exclude every existing pipeline stage.
- `VidbyteAgent` -> `CodexHarnessAgent satisfies the protocol` — [Edge Case]
- `VidbyteAgent` -> `an object missing generate_reply does not satisfy it` — [Edge Case]
- `translate_input` -> `returns the identical CodexRunInput object` — [Silent Failure] — a copy would drop native image, skill, and mention items while still looking valid.
- `translate_input` -> `converts a string into one text item for the user` — [Edge Case]
- `translate_input` -> `maps every AgentInput field` — [Silent Failure] — asserts prompt, metadata, and context items together, so a dropped field fails.
- `translate_input` -> `preserves context manager identity, not equality` — [Hidden Assumption] — `CodexContextTranslator._sources` collapses a shared manager with `is`; a copy would render every primitive twice.
- `translate_input` -> `rejects None, an int, and a list` — [Hidden Assumption]
- `translate_input` -> `rejects an empty prompt` — [Edge Case]
- `generate_reply` -> `returns the same reply arun returns` — [Edge Case]
- `generate_reply` -> `rejects an unsupported option, naming it` — [Hidden Failure] — a pipeline forwarding `context=` that the adapter drops would produce an answer computed without it.
- `generate_reply` -> `names every unsupported option at once` — [Silent Failure]
- `generate_reply` -> `accepts no options` — [Edge Case]

### Integration Tests

The flow to prove is a real pipeline running a real Codex agent. Only `CodexTransport` is faked; every pipeline class, the real translator, and the real `UsageTracker` run.

- `SequentialPipeline` with two Codex stages threads the first reply into the second's prompt. [Silent Failure] — asserts the second transport request's prompt contains the first reply, so a broken thread would show as the original prompt.
- `ParallelPipeline` with two **distinct** Codex agents runs both and joins their outputs with the separator. [Edge Case]
- `ParallelPipeline` with two distinct agents runs them **concurrently** — an event-gated transport proves both turns are in flight before either completes. [Hidden Failure] — if the lock were per class or module-level, this would deadlock, and the test would catch it.
- `ParallelPipeline` listing **the same agent twice** completes, and `agent.history` holds exactly two replies. [Hidden Failure] — the headline defect: without the lock the two turns interleave, reset each other's usage ledger, and race on `thread_id`.
- The same-agent fan-out's second turn observes the first's `thread_id` in its transport request. [Silent Failure] — proves the turns serialized rather than both starting a fresh thread, which would look like it worked while producing two unrelated conversations.
- `MapReducePipeline` with Codex map stages and a Codex reduce stage passes the joined map output to the reducer. [Edge Case]
- `ConditionalPipeline` routes to a Codex branch by predicate. [Edge Case]
- A mixed pipeline with a `BaseAgent` stage and a Codex stage runs both. [Hidden Assumption] — proves the widened `PipelineNode` did not break the existing type.
- A Codex stage whose transport raises propagates the error out of the pipeline rather than joining an empty string. [Hidden Failure] — a swallowed failure would produce a plausible joined output missing one branch.
- A cancelled Codex turn releases the lock, so a subsequent turn on the same agent still runs. [Hidden Failure] — a lock held through cancellation would deadlock every later turn on that agent.

### Manual / QA Test Cases

1. Given a `ParallelPipeline` over three distinct Codex agents, when it runs, then all three turns are in flight simultaneously and the output joins three replies. — [Edge Case]
2. Given a `ParallelPipeline` listing one Codex agent twice, when it runs, then the agent's history holds two replies and the second turn resumed the first's thread. — [Hidden Failure]
3. Given a pipeline stage passing `generate_reply(prompt, context="x")`, when it runs, then it fails naming `context` rather than answering without it. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | 0.147.0, optional extra | Each stage's turn | A fan-out over N Codex agents opens N app-server connections; the transport already opens and closes one per turn |

No dependency additions.

---

## 12. Rollout & Deployment

No feature flag. Everything is additive: the protocol is new, `PipelineNode` widens rather than narrows, `generate_reply` is a new method, and the lock changes no observable single-threaded behavior.

This branches from `origin/main` at `6b7d848d`. It is PR 3 of three and should merge last, after `feat/codex-failure-recovery` and `feat/codex-output-contracts`, because all three modify `arun` — this one wraps its body in the lock, which is the change most likely to conflict textually with the other two.

**It also overlaps open PR #412**, which adds an identical `translate_input`; see §3. Whichever merges second keeps either copy.

Rollback is a revert of this branch.

---

## 13. Open Questions

- [ ] Should a fan-out over one Codex agent fork the native thread per branch instead of serializing, so the branches are genuinely parallel and independent? That is roadmap F04, and it changes conversation semantics: each branch would see the shared prefix but not each other, which may be what a caller wants or may not.
- [ ] Should `generate_reply` accept and translate `BaseAgent`'s `context=` and `history=` options into context items, rather than rejecting them? They have plausible Codex meanings, but silently different ones — `history` in particular, since Codex owns its own history.
- [ ] `vidbyte/agents/multi/dispatcher.py` routes through `worker_generate_reply` and carries `AgentBinding` state. Should the protocol grow to cover it, or does multi-agent need its own binding translation (roadmap N05)?

---

## 14. Alternatives Considered

### Alternative 1: Add `CodexHarnessAgent` to the `PipelineNode` union directly

- What: `PipelineNode = Union["BaseAgent", "CodexHarnessAgent", "BasePipeline"]`.
- Why rejected: every future agent kind would need another union member and another edit to a module that should not know about agent implementations. The protocol expresses the actual requirement — "has these methods" — and `_invoke` was already relying on exactly that, undeclared.

### Alternative 2: Document that a Codex agent must not appear twice in a concurrent pipeline

- What: Skip the lock; state the constraint in the docstring.
- Why rejected: it pushes a correctness problem onto the caller, and the failure is silent — interleaved turns produce a plausible joined output with a corrupted history and a usage ledger describing neither turn. A lock is a few lines; a corrupted conversation is an incident.

### Alternative 3: Lock only around the transport call

- What: Hold the lock for the provider call, not the whole turn.
- Why rejected: the race is on the five mutable facade fields, which are written *after* the transport returns. Locking only the call would leave exactly the defect the lock exists to prevent.

### Alternative 4: Accept and ignore unknown `generate_reply` options

- What: Match `BaseAgent.generate_reply(**options)` permissively.
- Why rejected: `_invoke` forwards whatever the caller passed. Dropping `context=` silently returns an answer computed without the context the caller supplied — the same failure mode PR #415 and PR #420 both reject, applied to a third surface.
