# Design Doc: Agent Pipelines

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

Pipelines are a composition layer that wires agent inputs and outputs together into
multi-agent topologies. The sole contract is string-in / string-out: one agent's
`generate_reply()` content becomes the next agent's `message`. Three topology types
cover the declared scope — `SequentialPipeline`, `ParallelPipeline`, and
`ConditionalPipeline` — and any `Pipeline` can itself act as a stage inside another
pipeline, enabling arbitrary nesting without additional abstractions.

---

## 2. Goals & Non-Goals

### Goals
- Wire `BaseAgent` instances together so output flows to input with a single `.run()` call.
- Support sequential chaining (A → B → C), parallel fan-out (N agents, same input, joined output), and conditional routing (predicate selects branch).
- Make every `Pipeline` a valid stage inside another `Pipeline` (composability).
- Accept `BaseAgent` directly as a stage — no manual wrapping required.
- Provide both `async run()` and sync `run_sync()` entry points matching the existing `arun` / `run` pattern in the codebase.
- Export all pipeline types from the root `vidbyte` namespace.
- Add `PipelineExecutionError` to the shared SDK error hierarchy.

### Non-Goals
- No pipeline-specific context, budget, or permission objects — each agent carries its own.
- No reducer agents, artifact passing, or structured merge beyond string join.
- No streaming, partial results, or progress callbacks.
- No persistence, serialization, or resumption of pipeline state.
- No retry loops, map-reduce, race, or ensemble topologies (future work).

---

## 3. Background & Context

The vidbyte-sdk has rich single-agent execution (`BaseAgent.generate_reply`) and
multi-agent strategies (`VMAO`, `Consensus`, etc.) that operate at the strategy level
inside a single agent loop. There is no mechanism to chain fully-configured agents
across agent boundaries — routing the output of one agent as the input to another
without writing bespoke orchestration code.

Pipelines fill this gap at the agent composition level. They are intentionally thinner
than strategies: they do not manage context state, budget, or tool calls. They only
move strings.

---

## 4. Requirements

### Functional Requirements

1. `SequentialPipeline(stages)` runs each stage in order; the string output of stage N
   becomes the string input of stage N+1. Returns the final stage's output.
2. `ParallelPipeline(stages)` runs all stages concurrently with the same input string;
   joins all outputs with `"\n\n---\n\n"` and returns the joined string.
3. `ConditionalPipeline(predicate, branches)` calls `predicate(output)` on the incoming
   prompt to select a branch key; runs the selected `PipelineNode` with that same
   prompt; raises `PipelineExecutionError` if the key is not found in `branches`.
4. Each `stages` element may be a `BaseAgent` or any `BasePipeline` instance (nesting).
5. `BasePipeline.run(prompt)` is the async entry point; `BasePipeline.run_sync(prompt)`
   bridges via `asyncio.run()` when no event loop is active, matching the
   `BaseStrategy.run()` pattern.
6. All pipeline types are exported from `vidbyte` root and from `vidbyte.pipelines`.
7. `PipelineExecutionError` is added to `vidbyte.lib.errors.base` and exported from
   the root `vidbyte` namespace.

### Non-Functional Requirements
- No I/O or network calls inside pipeline logic itself — only agents do that.
- `ParallelPipeline` uses `asyncio.gather` with `return_exceptions=False`; any agent
  failure propagates immediately as `PipelineExecutionError`.
- Empty `stages` list raises `PipelineExecutionError` at construction time.
- `ConditionalPipeline` predicate must be a plain sync callable (`Callable[[str], str]`).

---

## 5. High-Level Design

Pipelines introduce one new top-level module (`vidbyte/pipelines/`) with a thin
abstract base class and three concrete topology classes. There are no new dataclasses,
no new context objects, and no changes to `BaseAgent` or `BaseStrategy`.

```
Caller
  |
  v
BasePipeline.run(prompt: str) -> str
  |
  +-- SequentialPipeline   stage1(prompt) -> s1 -> stage2(s1) -> s2 -> ...
  |
  +-- ParallelPipeline     asyncio.gather(stage1(prompt), stage2(prompt), ...) -> join
  |
  +-- ConditionalPipeline  predicate(prompt) -> key -> branches[key](prompt)
```

Every stage is either a `BaseAgent` (called via `generate_reply`) or a `BasePipeline`
(called via `run`). The internal `_invoke` helper on `BasePipeline` dispatches between
the two without requiring callers to wrap agents.

Composability is free: because `BasePipeline` exposes the same `run(prompt) -> str`
contract, any pipeline can be a stage in another pipeline. Example:

```
SequentialPipeline([
    planner_agent,
    ParallelPipeline([solver_a, solver_b, solver_c]),   # nested
    implementer_agent,
])
```

---

## 6. Detailed Design

### 6.1 `vidbyte/pipelines/types.py`

**File:** `vidbyte/pipelines/types.py`
**Type:** New file

#### What it does
Defines the `PipelineNode` type alias used throughout the module. Avoids circular
imports between `base.py` and the concrete pipeline files.

#### Interface / API
```python
from __future__ import annotations
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.pipelines.base import BasePipeline

PipelineNode = Union["BaseAgent", "BasePipeline"]
```

#### Edge Cases & Error Handling
- Type alias only; no runtime logic, no errors.

---

### 6.2 `vidbyte/pipelines/base.py`

**File:** `vidbyte/pipelines/base.py`
**Type:** New file

#### What it does
Defines `BasePipeline`: the abstract base class all pipeline types inherit from.
Implements the shared `_invoke` dispatcher and the sync `run_sync` bridge.

#### Interface / API
```python
class BasePipeline(ABC):
    @abstractmethod
    async def run(self, prompt: str) -> str: ...

    def run_sync(self, prompt: str) -> str:
        """Sync entry point — mirrors BaseStrategy.run() pattern."""

    @staticmethod
    async def _invoke(stage: PipelineNode, prompt: str) -> str:
        """Dispatch to agent.generate_reply or pipeline.run."""
```

#### Logic / Algorithm
1. `run(prompt)` — abstract; each subclass implements.
2. `run_sync(prompt)` — calls `asyncio.get_running_loop()`; if no loop, calls
   `asyncio.run(self.run(prompt))`; if loop exists, raises `PipelineExecutionError`
   (mirrors `BaseStrategy.run()` exactly).
3. `_invoke(stage, prompt)` — if `isinstance(stage, BasePipeline)`, calls
   `await stage.run(prompt)`; otherwise calls `await stage.generate_reply(prompt)`
   and returns `.content`.

#### Edge Cases & Error Handling
- `run_sync` from an active event loop raises `PipelineExecutionError` with message
  directing caller to `await run()`.
- Any exception from `generate_reply` propagates; callers can catch
  `AgentExecutionError` or let it bubble.

---

### 6.3 `vidbyte/pipelines/sequential.py`

**File:** `vidbyte/pipelines/sequential.py`
**Type:** New file

#### What it does
Runs stages one after another, threading output to input.

#### Interface / API
```python
class SequentialPipeline(BasePipeline):
    def __init__(self, stages: Sequence[PipelineNode]) -> None: ...
    async def run(self, prompt: str) -> str: ...
```

#### Logic / Algorithm
1. Constructor raises `PipelineExecutionError` if `stages` is empty.
2. `run(prompt)`:
   - `current = prompt`
   - For each stage: `current = await self._invoke(stage, current)`
   - Return `current`.

#### Edge Cases & Error Handling
- Empty stages → `PipelineExecutionError("SequentialPipeline requires at least one stage.")`.
- Agent failure at any stage propagates immediately; later stages do not run.

---

### 6.4 `vidbyte/pipelines/parallel.py`

**File:** `vidbyte/pipelines/parallel.py`
**Type:** New file

#### What it does
Runs all stages concurrently with the same input; joins outputs with a separator.

#### Interface / API
```python
PARALLEL_JOIN_SEPARATOR = "\n\n---\n\n"

class ParallelPipeline(BasePipeline):
    def __init__(
        self,
        stages: Sequence[PipelineNode],
        *,
        separator: str = PARALLEL_JOIN_SEPARATOR,
    ) -> None: ...
    async def run(self, prompt: str) -> str: ...
```

#### Logic / Algorithm
1. Constructor raises `PipelineExecutionError` if `stages` is empty.
2. `run(prompt)`:
   - `outputs = await asyncio.gather(*[self._invoke(s, prompt) for s in self._stages])`
   - Return `self._separator.join(outputs)`.

#### Edge Cases & Error Handling
- `asyncio.gather` with default `return_exceptions=False`; first exception aborts all.
- Caller may wrap in try/except `PipelineExecutionError` or `AgentExecutionError`.
- `separator` is configurable to support custom merge formats.

---

### 6.5 `vidbyte/pipelines/conditional.py`

**File:** `vidbyte/pipelines/conditional.py`
**Type:** New file

#### What it does
Routes to a branch based on a predicate applied to the incoming prompt.

#### Interface / API
```python
class ConditionalPipeline(BasePipeline):
    def __init__(
        self,
        predicate: Callable[[str], str],
        branches: Mapping[str, PipelineNode],
    ) -> None: ...
    async def run(self, prompt: str) -> str: ...
```

#### Logic / Algorithm
1. Constructor raises `PipelineExecutionError` if `branches` is empty.
2. `run(prompt)`:
   - `key = self._predicate(prompt)`
   - If `key not in self._branches`: raise `PipelineExecutionError` with message
     listing available keys.
   - `return await self._invoke(self._branches[key], prompt)`.

#### Edge Cases & Error Handling
- Unknown branch key → `PipelineExecutionError("ConditionalPipeline: predicate returned key '{key}'; available: {list(self._branches)}")`.
- Predicate exceptions propagate unwrapped (caller's responsibility).

---

### 6.6 `vidbyte/pipelines/__init__.py`

**File:** `vidbyte/pipelines/__init__.py`
**Type:** New file

#### What it does
Public surface for the pipelines module.

#### Interface / API
```python
from vidbyte.pipelines.base import BasePipeline
from vidbyte.pipelines.conditional import ConditionalPipeline
from vidbyte.pipelines.parallel import ParallelPipeline
from vidbyte.pipelines.sequential import SequentialPipeline
from vidbyte.pipelines.types import PipelineNode

__all__ = [
    "BasePipeline",
    "ConditionalPipeline",
    "ParallelPipeline",
    "PipelineNode",
    "SequentialPipeline",
]
```

---

### 6.7 `vidbyte/lib/errors/base.py` (modified)

**File:** `vidbyte/lib/errors/base.py`
**Type:** Modified

#### What it does
Adds `PipelineExecutionError` to the shared SDK error hierarchy.

#### Interface / API
```python
class PipelineExecutionError(VidbyteSdkError):
    """Raised when a pipeline cannot complete execution."""
```

#### Edge Cases & Error Handling
- Inherits `VidbyteSdkError`; carries optional `details` mapping.

---

### 6.8 `vidbyte/__init__.py` (modified)

**File:** `vidbyte/__init__.py`
**Type:** Modified

#### What it does
Exports all pipeline types and `PipelineExecutionError` from the root namespace.

#### Interface / API
New imports and `__all__` entries:
```python
from vidbyte.pipelines import (
    BasePipeline,
    ConditionalPipeline,
    ParallelPipeline,
    PipelineNode,
    SequentialPipeline,
)
from vidbyte.lib.errors import PipelineExecutionError
```

---

### 6.9 `vidbyte/lib/errors/__init__.py` (modified)

**File:** `vidbyte/lib/errors/__init__.py`
**Type:** Modified — add `PipelineExecutionError` to the error package export.

---

### 6.10 `vidbyte/pipelines/` — `skills/vidbyte-sdk/pipelines.md`

**File:** `skills/vidbyte-sdk/pipelines.md`
**Type:** New file — skill reference document

#### What it does
Documents the pipelines paradigm, intent, topology types, usage patterns, and
extension rules for future contributors. Lives alongside `SKILL.md` and
`adding-prompts.md` in the existing vidbyte-sdk skills directory.

---

## 7. Data Model Changes

N/A — pipelines introduce no new dataclasses, database tables, or schema changes.
`PipelineNode` is a type alias, not a runtime dataclass.

---

## 8. API Changes

N/A — pipelines expose Python classes, not HTTP endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/pipelines/__init__.py` | New module public surface |
| CREATE | `vidbyte/pipelines/types.py` | `PipelineNode` type alias |
| CREATE | `vidbyte/pipelines/base.py` | `BasePipeline` abstract class + `_invoke` dispatcher |
| CREATE | `vidbyte/pipelines/sequential.py` | `SequentialPipeline` |
| CREATE | `vidbyte/pipelines/parallel.py` | `ParallelPipeline` |
| CREATE | `vidbyte/pipelines/conditional.py` | `ConditionalPipeline` |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `PipelineExecutionError` |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export `PipelineExecutionError` |
| MODIFY | `vidbyte/__init__.py` | Export all pipeline types + error |
| CREATE | `tests/test_pipelines.py` | Full test suite |
| CREATE | `docs/design/pipelines.md` | This design doc |
| CREATE | `skills/vidbyte-sdk/pipelines.md` | Skill reference doc |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Add pipelines layout entry |

---

## 10. Testing Plan

All tests use `unittest.IsolatedAsyncioTestCase`, matching the existing test suite
convention. Stubs mirror the pattern in `test_multi_agent_consensus.py`.

### Unit Tests — `tests/test_pipelines.py`

**Helpers (defined once at top of file):**
```python
class EchoAgent:
    """Fake BaseAgent that returns its input prefixed by name."""

class PrefixAgent:
    """Fake BaseAgent that prepends a fixed string."""

class FailingAgent:
    """Fake BaseAgent that always raises AgentExecutionError."""
```

**SequentialPipeline:**
- `test_sequential_single_stage` — one agent, output == agent output.
- `test_sequential_chains_output_to_input` — two agents; second receives first's output.
- `test_sequential_three_stages` — verifies full chain threading.
- `test_sequential_empty_stages_raises` — `PipelineExecutionError` on construction.
- `test_sequential_agent_failure_propagates` — failing agent raises through pipeline.
- `test_sequential_nested_pipeline_as_stage` — `SequentialPipeline` containing a `ParallelPipeline`.

**ParallelPipeline:**
- `test_parallel_single_stage` — one agent, output == agent output.
- `test_parallel_joins_outputs` — two agents; output contains both, separated by `---`.
- `test_parallel_all_receive_same_input` — verifies same prompt reaches all stages.
- `test_parallel_empty_stages_raises` — `PipelineExecutionError` on construction.
- `test_parallel_custom_separator` — custom separator appears in output.
- `test_parallel_agent_failure_propagates` — one failing agent raises.

**ConditionalPipeline:**
- `test_conditional_routes_to_correct_branch` — predicate returns key, correct branch runs.
- `test_conditional_unknown_key_raises` — missing key raises `PipelineExecutionError`.
- `test_conditional_empty_branches_raises` — raises on construction.
- `test_conditional_predicate_receives_prompt` — verifies predicate gets the full input.

**run_sync:**
- `test_run_sync_sequential` — runs sequential pipeline from sync context.

**Composability:**
- `test_sequential_wraps_parallel` — `SequentialPipeline([agent_a, ParallelPipeline([b, c])])`.
- `test_parallel_wraps_sequential` — `ParallelPipeline([SequentialPipeline([a, b]), c])`.

### Integration Tests
N/A — no external services. All agent calls are stubbed with fake `BaseAgent`-compatible
classes. Tests exercise the real pipeline logic end-to-end within process.

### Manual / QA Test Cases
1. Given a `SequentialPipeline([planner, solver])`, when `run("build a feature")` is
   called, then solver receives planner's output as its prompt.
2. Given a `ParallelPipeline([solver_a, solver_b])`, when `run("solve this")` is called,
   both agents receive `"solve this"` and the result contains both outputs joined by `---`.
3. Given a `ConditionalPipeline(lambda p: "code" if "code" in p else "research", {...})`,
   when `run("write code")` is called, the code branch agent runs.
4. Given a nested pipeline as a stage, when the outer pipeline runs, the inner pipeline
   executes correctly as a single stage.

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| `asyncio` (stdlib) | 3.11+ | `gather`, `run`, event-loop detection | None — already used throughout codebase |
| `vidbyte.agents.base.BaseAgent` | internal | Stage dispatch | None |
| `vidbyte.lib.errors` | internal | `PipelineExecutionError` | None |

No new third-party packages.

---

## 12. Rollout & Deployment

- Pure additive change — no existing APIs modified (only new exports added).
- No feature flags required.
- Not a breaking change; existing code is unaffected.
- `PipelineExecutionError` added to error module is purely additive.
- Rollback: revert the new `vidbyte/pipelines/` module and remove the three export
  additions from `vidbyte/__init__.py` and `vidbyte/lib/errors/`.

---

## 13. Open Questions

- [ ] Should `ParallelPipeline` expose the individual stage outputs alongside the joined
  string (e.g., a `run_detailed()` returning a list)? Currently out of scope but might
  be useful for downstream conditional routing.
- [ ] Should pipelines support async predicates in `ConditionalPipeline` (e.g., using
  an agent as router)? Currently sync-only to keep the API minimal.

---

## 14. Alternatives Considered

### Alternative 1: `PipelineStage` protocol with `AgentStage` adapter
- **What:** Define a `Protocol` with `async run(prompt) -> str`; wrap `BaseAgent` in
  an `AgentStage` adapter class; require callers to wrap agents explicitly.
- **Why rejected:** Forces callers to write `AgentStage(my_agent)` everywhere. The
  `_invoke` dispatcher on `BasePipeline` handles the same dispatch internally without
  any caller burden.

### Alternative 2: Pipeline as a `BaseStrategy` subclass
- **What:** Implement pipelines as strategies so they can plug into `BaseAgent.strategy`.
- **Why rejected:** Strategies operate inside a single agent loop; pipelines compose
  agents across boundaries. Conflating the two would add unnecessary coupling and
  would violate the architecture rule that strategies live within `vidbyte/strategies/`.

### Alternative 3: `PipelineResult` return type instead of `str`
- **What:** Return a structured dataclass with `output`, `stage_outputs`, `metadata`.
- **Why rejected:** User explicitly wants `pipeline.run([agents]) -> str`. Any
  structured result type would require callers to unpack `.output` everywhere, adding
  friction with no benefit at this scope.
