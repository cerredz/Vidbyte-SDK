# Design Doc: Non-Linear Agent Runtimes

**Status:** Draft
**Author:** Antigravity
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

This feature designs and integrates advanced **Strictly Non-Linear Agent Runtimes** into the Vidbyte SDK codebase. By transitioning `vidbyte/agents/runtime.py` into a package directory (`vidbyte/agents/runtimes/`), we ship different runtime engines—namely **Linear**, **Branching Search (MCTS)**, and **Asynchronous Actor-Model** runtimes—while keeping the developer-facing `BaseAgent` class fully swappable. Non-linear execution paths cannot safely compose with standard sequential middleware and trial-based context algorithms, so the system enforces a strict fail-fast security gate to reject them upon initialization.

---

## 2. Goals & Non-Goals

### Goals
- Move the current linear runtime (`vidbyte/agents/runtime.py`) into the new `vidbyte/agents/runtimes/` package folder as `linear.py`.
- Define and implement `AgentRuntimeType` enum in `vidbyte/lib/enums/agent_runtime.py` containing `LINEAR`, `MCTS_SEARCH`, and `ACTOR_MODEL`.
- Add `runtime` to `BaseAgent` initializing arguments defaulting to `AgentRuntimeType.LINEAR`.
- Support `vidbyte/agents/runtimes/search.py` (MCTS Branching Search) and `vidbyte/agents/runtimes/actor.py` (Asynchronous Actor-Model) runtimes mimicking the standard `AgentRuntime` interface.
- Implement fail-fast validation in `BaseAgent` to raise configuration errors immediately if `middleware` or `algorithm` presets are supplied for non-linear runtimes.
- Maintain documentation integrity and the Context Protocol Header across all modified and newly created files.

### Non-Goals
- Supporting standard middleware or tracing telemetry integration inside non-linear execution threads in this phase.
- Implementing persistent virtualized workspace sandboxes for MCTS state rollbacks.

---

## 3. Background & Context

Currently, the Vidbyte SDK operates on a single direct execution model/tool loop (`AgentRuntime`), which assumes sequential, forward-moving steps. As advanced orchestration patterns emerge, developer interest shifts toward non-linear loops (such as MCTS branching search and actor networks). However, these non-linear structures fail under standard linear tracing and side-effect tool executions. Decoupling the runtime loop from `BaseAgent` into a swappable package with fail-fast protections allows us to safely ship advanced runtimes without risk of silent memory corruptions, infinite loops, or dirty workspace pollution.

---

## 4. Requirements

### Functional Requirements
1. **Directory Restructure**: Create the folder `vidbyte/agents/runtimes` and make it a package by creating `__init__.py`.
2. **Linear Runtime Relocation**: Relocate `vidbyte/agents/runtime.py` to `vidbyte/agents/runtimes/linear.py`.
3. **Enum Addition**: Add a `AgentRuntimeType` enum containing `linear`, `mcts_search`, and `actor_model`.
4. **Agent Integration**: Expose `runtime` parameter on `BaseAgent` defaulting to `AgentRuntimeType.LINEAR`.
5. **Fail-Fast Validation**: Raise `ConfigurationError` in `BaseAgent.__init__` if `runtime` is non-linear and:
   - `middleware` is not empty.
   - `algorithm` is configured (i.e. resolved to anything other than the `"default"` raw tool output behavior).
6. **Interface Mimicry**: `SearchTreeRuntimeComponent` and `ActorRuntimeComponent` must provide the exact same public method signatures as the linear `AgentRuntime` class: `__init__`, `build_context`, and `arun`.

### Non-Functional Requirements
- **Performance**: Fail-fast validation must be synchronous and evaluate in $O(1)$ time upon agent instantiation.
- **Observability**: Fail-fast errors must emit descriptive reasons indicating why middleware or context algorithms are incompatible with non-linear loops.

---

## 5. High-Level Design

The architecture introduces a dynamic dispatch pattern inside `BaseAgent._runtime()`. When `arun` is called, the agent resolves the requested `AgentRuntimeType` and instantiates the matching runtime component.

```text
[BaseAgent] 
    |-- runtime_type (LINEAR | MCTS_SEARCH | ACTOR_MODEL)
    |
    |-- _runtime() -> Resolves and instantiates:
           |-- [LinearAgentRuntime]      -> Standard sequential execution
           |-- [SearchTreeRuntime]       -> Branching MCTS exploration
           |-- [ActorRuntimeComponent]   -> Async message reactive loop
```

- When `BaseAgent` is constructed, we validate the configuration immediately. If a non-linear runtime is configured but middleware or algorithms are attached, construction fails synchronously.
- All non-linear runtimes provide stub implementations of `arun` and `build_context` that match the linear runtime signatures, allowing safe plug-and-play execution.

---

## 6. Detailed Design

### 6.1 [Enum] AgentRuntimeType
**File(s):** `vidbyte/lib/enums/agent_runtime.py`
**Type:** New file

#### What it does
Exposes the available agent execution runtimes as a string-backed enum.

#### Interface / API
```python
from enum import Enum

class AgentRuntimeType(str, Enum):
    LINEAR = "linear"
    MCTS_SEARCH = "mcts_search"
    ACTOR_MODEL = "actor_model"
```

---

### 6.2 [Package Init] Agent Runtimes Package
**File(s):** `vidbyte/agents/runtimes/__init__.py`
**Type:** New file

#### What it does
Initializes the runtimes package, defining the exports for the Linear, Search, and Actor runtimes.

#### Interface / API
```python
"""Context Protocol Header
...
"""
from vidbyte.agents.runtimes.linear import AgentRuntime as LinearAgentRuntime
from vidbyte.agents.runtimes.search import SearchTreeRuntimeComponent
from vidbyte.agents.runtimes.actor import ActorRuntimeComponent

__all__ = [
    "LinearAgentRuntime",
    "SearchTreeRuntimeComponent",
    "ActorRuntimeComponent",
]
```

---

### 6.3 [Relocate] Linear Agent Runtime
**File(s):** `vidbyte/agents/runtimes/linear.py`
**Type:** New file (Relocated from `vidbyte/agents/runtime.py`)

#### What it does
Maintains the complete, original direct model/tool loop. All internal logic, middleware pipelines, and context-window algorithm adapters remain exactly as they are currently implemented.

---

### 6.4 [New Component] Branching MCTS Runtime
**File(s):** `vidbyte/agents/runtimes/search.py`
**Type:** New file

#### What it does
Implements the MCTS search tree traversal and rollback runtime.

#### Interface / API
```python
from __future__ import annotations
from typing import Any, Mapping, Sequence, Callable
from vidbyte.context.primitives import ContextItem
from vidbyte.context.manager import ContextManager
from vidbyte.strategies.types import BaseAgentContext, StrategyResult, StrategyContext
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.enums import ModelModality
from vidbyte.tools.types import ToolCallContext

class SearchTreeRuntimeComponent:
    def __init__(self, **kwargs: Any) -> None:
        pass

    def build_context(
        self,
        message: str,
        *,
        base_context: StrategyContext | None,
        history: Sequence[AgentMessage],
        agent_history: Sequence[AgentMessage],
        agent_metadata: Mapping[str, Any],
        existing_tool_calls: Sequence[ToolCallContext],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
        agentic_loop: bool = True,
        context_items: Sequence[ContextItem] = (),
        context_manager: ContextManager | None = None,
    ) -> BaseAgentContext:
        # Mimic context construction without using in-context algorithms
        pass

    async def arun(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: Any = None,
    ) -> StrategyResult:
        # Mimic execution, executing branching MCTS logic
        pass
```

---

### 6.5 [New Component] Asynchronous Actor Runtime
**File(s):** `vidbyte/agents/runtimes/actor.py`
**Type:** New file

#### What it does
Implements the asynchronous message-passing actor event loop.

#### Interface / API
Mimics the `SearchTreeRuntimeComponent` public interface exactly.

---

### 6.6 [Modify] Base Agent Class
**File(s):** `vidbyte/agents/base.py`
**Type:** Modified file

#### What it does
Accepts the `runtime` parameter and enforces fail-fast validations at startup. Resolves the runtime class at execution time in `_runtime()`.

#### Logic
1. During `__init__`, check `runtime`. Default to `AgentRuntimeType.LINEAR`.
2. Convert input to `AgentRuntimeType` enum.
3. If `runtime != AgentRuntimeType.LINEAR`:
   - If `middleware` is not empty, raise `ConfigurationError`.
   - If `algorithm` is configured (resolved algorithm name != `"default"`), raise `ConfigurationError`.
4. Inside `_runtime(self)`, resolve `self.runtime_type` to retrieve `LinearAgentRuntime`, `SearchTreeRuntimeComponent`, or `ActorRuntimeComponent`.

---

## 7. Data Model Changes

N/A - This change only affects runtime code execution paths and configurations.

---

## 8. API Changes

### 8.1 BaseAgent Class Initialization
The `BaseAgent.__init__` method accepts the new `runtime` argument:

```python
class BaseAgent:
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR,
        # ...
    )
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/enums/agent_runtime.py` | Add string-backed AgentRuntimeType enum |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export AgentRuntimeType enum |
| CREATE | `vidbyte/agents/runtimes/__init__.py` | Add subpackage init with Context Protocol Header |
| CREATE | `vidbyte/agents/runtimes/linear.py` | Relocate AgentRuntime from runtime.py |
| CREATE | `vidbyte/agents/runtimes/search.py` | Implement SearchTreeRuntimeComponent mimicking linear interface |
| CREATE | `vidbyte/agents/runtimes/actor.py` | Implement ActorRuntimeComponent mimicking linear interface |
| MODIFY | `vidbyte/agents/base.py` | Support runtime parameter, dynamic dispatch, and fail-fast validation |
| MODIFY | `vidbyte/agents/__init__.py` | Update exports for AgentRuntime / runtimes |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Update imports for relocated runtime |
| DELETE | `vidbyte/agents/runtime.py` | Removed in favor of reregistered package runtimes |
| DELETE | `vidbyte/agents/runtime/__init__.py` | Clean up old subpackage directory if present |

---

## 10. Testing Plan

### Unit Tests
- `test_agent_runtime_fail_fast`:
  - `[Edge Case]` Instantiating non-linear runtime (MCTS or Actor) with empty middleware and default algorithm passes successfully.
  - `[Hidden Failure]` Instantiating non-linear runtime with active middleware list raises `ConfigurationError` immediately.
  - `[Silent Failure]` Instantiating non-linear runtime with non-default context-window algorithm (e.g. reflexion) raises `ConfigurationError` immediately.
  - `[Hidden Assumption]` Ensure a string value `"mcts_search"` is correctly coerced into `AgentRuntimeType.MCTS_SEARCH` and triggers validation.
- `test_runtime_dispatch`:
  - `[Edge Case]` Running an agent configured with `LINEAR` uses `LinearAgentRuntime`.
  - `[Edge Case]` Running an agent configured with `MCTS_SEARCH` uses `SearchTreeRuntimeComponent`.
  - `[Edge Case]` Running an agent configured with `ACTOR_MODEL` uses `ActorRuntimeComponent`.

---

## 11. Dependencies & External Services

N/A - Uses existing standard libraries and dependency layers.

---

## 12. Rollout & Deployment

This is a non-breaking internal optimization for core agent execution. The default runtime remains `LINEAR`, ensuring absolute backward compatibility for existing harnesses.

---

## 13. Open Questions

- [x] Should we clean up the previous `vidbyte/agents/runtime/` folder if it exists? Yes, we will delete the old folder if present, replacing it with the new `vidbyte/agents/runtimes/` subpackage.

---

## 14. Alternatives Considered

### Alternative 1: Keeping all runtimes in a single file
- **Why rejected:** Putting MCTS Search, Actor-Model, Blackboard, and Linear runtimes in a single `runtime.py` module creates an extremely large, unmaintainable, and cohesive-less file exceeding 2000 lines of code. Folder modularity guarantees ease of maintenance.
