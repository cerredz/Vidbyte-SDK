# Design Doc: Advanced Runtimes and Registries

**Status:** Draft  
**Author:** Antigravity  
**Created:** 2026-05-28  
**Last Updated:** 2026-05-28  

---

## 1. Overview

This feature refactors the Vidbyte SDK runtime initialization and registry topology to improve modularity and developer control. 

First, all scattered registry classes (Agent, Model, Prompt, and Tool registries) will be moved into a single consolidated subpackage under `vidbyte/lib/registries/`. 

Second, the flat, multi-argument runtime configuration in `BaseAgent` will be replaced by a structured `runtime` parameter accepting runtime configuration objects (`LinearRuntime`, `MctsSearchRuntime`, and `ActorRuntime`). 

Third, we will implement a subclass-based `PrebuiltActor` hierarchy (such as `PlannerActor`, `CoderActor`) and a new `ActorRegistry` supporting dynamic lookup, registration, and instantiation. This enables developers to selectively import and include specific actor subsets in the `ActorRuntime` constructor. 

Finally, all prebuilt actor prompts (including 9 new specialized personas: summarization, decomposer, explorer, tradeoff, hypothesis generator, refiner, formatter, safety, and final answer) will be significantly enhanced to have comprehensive, world-class system instructions while completely removing the context protocol headers to comply with the code review comments on PR #66.

---

## 2. Goals & Non-Goals

### Goals
- Consolidate all SDK registry layers into `vidbyte/lib/registries/`.
- Replace flat agent constructor runtime settings (`dynamic_actors`, `max_loop`, `termination_mode`, `worker_model`) with runtime-specific classes (`LinearRuntime`, `MctsSearchRuntime`, `ActorRuntime`).
- Enable selective actor spawning by allowing developers to pass a list of prebuilt actor classes to the `ActorRuntime` constructor.
- Add 9 new specialized prebuilt actors (`SummarizationActor`, `DecomposerActor`, `ExplorerActor`, `TradeoffActor`, `HypothesisGeneratorActor`, `RefinerActor`, `FormatterActor`, `SafetyActor`, `FinalAnswerActor`) to the registry and JSON catalog.
- Expand all 15 actor system prompts to include 6-8 sentence identity sections, 6-8 sentence goal descriptions, and 15-20 bullet point checklists, with no protocol headers inside prompt files.
- Ensure all existing and new test suites pass with 100% correctness.

### Non-Goals
- Modifying the underlying JSON-RPC communications or protocol details of MCP servers.
- Adding database schema updates or persistence layers for actor histories (this remains in-process memory).
- Replacing standard linear runner callbacks or modality routing engines.

---

## 3. Background & Context

During the review of PR #66, several limitations in the actor runtime design were identified:
1. Flat constructor properties on `BaseAgent` clutter the core namespace and scale poorly when adding features to specific runtimes.
2. Spawning all 6 prebuilt actors by default consumes substantial memory and results in high LLM token costs when only a few actors are needed.
3. System prompts were too brief and lacked the rigorous boundary/checklist instructions needed for high-quality LLM performance.
4. Scattered registries made codebase navigation difficult.

By consolidating registries, parameterizing runtime configs, adding class-first actor definitions, and detailing prompts, we establish a clean foundation for multi-agent workflows.

---

## 4. Requirements

### Functional Requirements
1. **Registry Consolidation**: All registry modules must reside in `vidbyte/lib/registries/`, and all import references in the codebase and test files must be updated.
2. **Encapsulated Runtimes**: `BaseAgent` must receive a single `runtime` parameter which can be a string, enum, or runtime config object. Flat settings like `dynamic_actors` must be moved to the `ActorRuntime` config.
3. **Selective Actor Swarms**: Developers must be able to specify a list of prebuilt actor classes (e.g. `[PlannerActor, CoderActor]`) to `ActorRuntime`. If empty, only those specified are spawned. If `None`, it defaults to the standard set.
4. **Prebuilt Actor Catalog**: Provide 15 prebuilt actor classes subclassing a common `PrebuiltActor` base.
5. **Prebuilt Actor Registry**: `ActorRegistry` must support registering custom actor classes, listing prebuilt keys, getting classes, and creating instances.
6. **Detailed Prompts**: Enhance all 15 prompt files to have an identity section (6-8 sentences), goal section (6-8 sentences), and checklist (15-20 items). Remove context protocol headers from all prompt files in `vidbyte/prompts/prompts/actor_runtime/`.

### Non-Functional Requirements
- **Performance**: Broker initialization and local actor registration must complete in under 5ms.
- **Fail-Fast Safety**: Invalid configurations (e.g. passing Linear runtime with middleware and context compaction, but non-linear with either) must throw `ConfigurationError` synchronously.
- **Backward Compatibility**: Passing string/enum keys to `runtime` (like `"linear"`) must remain fully supported for backward compatibility.

---

## 5. High-Level Design

The refined SDK architecture utilizes a clean, decoupled design where runtimes are encapsulated configs:

```text
[ Developer Configuration ]
         |
         v
   [ BaseAgent ] --------------> [ runtime: ActorRuntime ]
         |                                | (extracts configs, include_actors)
         |                                v
         +--------------------> [ Broker / Runtime Loop ]
                                          |
                                          v
                                   [ ActorRegistry ]
                                          |
                      +-------------------+-------------------+
                      |                   |                   |
               [ PlannerActor ]     [ CoderActor ]     [ CustomActor ]
```

### Key Design Decisions
1. **Runtime Configuration Inheritance**: We will implement `LinearRuntime`, `MctsSearchRuntime`, and `ActorRuntime` as dataclasses or standard objects that encapsulate runtime-specific options.
2. **Subclass-Based Actors**: Each prebuilt actor (e.g., `PlannerActor`) inherits from a common `PrebuiltActor` class. This class resolves its own ID, role key, and loads its prompt automatically from the catalog using standard Prompts catalogs.
3. **ActorRegistry**: Centrally manages all prebuilt and custom actors. Moving all registries to `vidbyte/lib/registries/` consolidates the modular architecture of the codebase.

---

## 6. Detailed Design

### 6.1 [New Package] Registries Namespace
**File(s):**
- `vidbyte/lib/registries/__init__.py`
- `vidbyte/lib/registries/agents.py`
- `vidbyte/lib/registries/models.py`
- `vidbyte/lib/registries/prompts.py`
- `vidbyte/lib/registries/tools.py`
- `vidbyte/lib/registries/actors.py`

**Type:** New package and relocated files

#### What it does
- Consolidates all registry implementations.
- `actors.py` provides the brand new registry for multi-agent execution loops.

#### Interface / API
##### `vidbyte/lib/registries/actors.py`
```python
"""Context Protocol Header

Description:
    Actor registry mapping prebuilt actor roles to their corresponding classes.
Purpose:
    Allows developers to discover, list, and instantiate prebuilt and custom actors.
Architecture:
    - ActorRegistry: Centralized registry managing prebuilt actor classes.
Relations:
    Located in vidbyte/lib/registries/actors.py. Imported by ActorRuntime and BaseAgent.
Similar Files:
    - vidbyte/lib/registries/agents.py: Agent registry.
"""
from __future__ import annotations
from typing import Any
from vidbyte.agents.runtimes.actor.actor import PrebuiltActor, AgentActor
from vidbyte.lib.errors import ConfigurationError

class ActorRegistry:
    def __init__(self) -> None:
        # Dictionary of registered prebuilt actor classes.
        self._actors: dict[str, type[PrebuiltActor]] = {}

    def register(self, role_name: str, actor_cls: type[PrebuiltActor]) -> None:
        # Registers a prebuilt actor class.
        self._actors[role_name.strip().lower()] = actor_cls

    def get(self, role_name: str) -> type[PrebuiltActor]:
        # Returns the actor class or raises ConfigurationError.
        key = role_name.strip().lower()
        if key not in self._actors:
            raise ConfigurationError(f"Actor {role_name} not found in registry.")
        return self._actors[key]

    def list(self) -> list[str]:
        # Returns the list of registered role names.
        return sorted(list(self._actors.keys()))

    def all(self) -> dict[str, type[PrebuiltActor]]:
        # Returns the entire map of registered classes.
        return dict(self._actors)
```

---

### 6.2 [New File] Runtime Configurations
**File(s):** `vidbyte/agents/runtimes/configs.py`
**Type:** New file

#### What it does
Defines encapsulated configuration classes for Linear, MCTS, and Actor runtimes.

#### Interface / API
```python
"""Context Protocol Header

Description:
    Runtime configuration objects for swappable agent loops.
Purpose:
    Provides developers with a clean, class-first API to configure runtime settings
    without cluttering the main agent constructor.
Architecture:
    - LinearRuntime: Configuration block for linear runloops.
    - MctsSearchRuntime: Configuration block for branching search trees.
    - ActorRuntime: Configuration block for concurrent multi-agent systems.
Relations:
    Located in vidbyte/agents/runtimes/configs.py. Imported by vidbyte.agents.base.
Similar Files:
    - vidbyte/lib/dataclasses/agents.py: Internal data models.
"""
from __future__ import annotations
from typing import Any, Sequence
from vidbyte.lib.enums import AgentRuntimeType

class LinearRuntime:
    def __init__(self) -> None:
        self.runtime_type = AgentRuntimeType.LINEAR

class MctsSearchRuntime:
    def __init__(self) -> None:
        self.runtime_type = AgentRuntimeType.MCTS_SEARCH

class ActorRuntime:
    def __init__(
        self,
        *,
        topology: AgentRuntimeType | str = AgentRuntimeType.ACTOR_MODEL_P2P,
        dynamic_actors: bool = False,
        max_loop: int = 20,
        termination_mode: str = "coordinator",
        worker_model: str | None = None,
        include_actors: Sequence[type] | None = None,
    ) -> None:
        self.runtime_type = AgentRuntimeType(topology)
        self.dynamic_actors = dynamic_actors
        self.max_loop = max_loop
        self.termination_mode = termination_mode
        self.worker_model = worker_model
        self.include_actors = include_actors
```

---

### 6.3 [Modify] Prebuilt Actor Class Hierarchy
**File(s):** `vidbyte/agents/runtimes/actor/actor.py`
**Type:** Modified file

#### What it does
Refactors `actor.py` to define explicit class representations for all 15 prebuilt actors inheriting from a common `PrebuiltActor` base.

#### Interface / API
```python
class PrebuiltActor(AgentActor):
    """Base class for all prebuilt actors resolving their prompts automatically."""
    role_name: str
    system_prompt_key: Any

    def __init__(
        self,
        broker: Any,
        model_name: str | None = None,
    ) -> None:
        # Load persona and call parent constructor
        prompt = PrebuiltActorFactory.load_persona(self.role_name)
        super().__init__(
            actor_id=self.role_name,
            system_prompt=prompt,
            broker=broker,
            model_name=model_name,
        )

# Example prebuilt class declarations
class PlannerActor(PrebuiltActor):
    role_name = "planner"
    system_prompt_key = Prompt.ACTOR_RUNTIME_PLANNER

class CoderActor(PrebuiltActor):
    role_name = "coder"
    system_prompt_key = Prompt.ACTOR_RUNTIME_CODER
```

---

### 6.4 [Modify] Asynchronous Broker Dispatch
**File(s):** `vidbyte/agents/runtimes/actor/broker.py`
**Type:** Modified file

#### What it does
Spawns actors selectively based on the configuration's `include_actors` list. If the list is empty, only the root coordinator is spawned. If the list is `None`, the default prebuilt actor set is spawned.

#### Logic
1. When booting up, retrieve the configuration's `include_actors` property.
2. If `include_actors` is `None`, load the standard set of 6 prebuilt actors.
3. If `include_actors` is a sequence of classes, spawn exactly those classes.
4. If `include_actors` is empty, do not spawn any prebuilt actors.

---

### 6.5 [Modify] BaseAgent Configuration
**File(s):** `vidbyte/agents/base.py`
**Type:** Modified file

#### What it does
Refactors `BaseAgent` constructor to extract runtime settings from the `runtime` parameter if it is an instance of `LinearRuntime`, `MctsSearchRuntime`, or `ActorRuntime`.

#### Logic
1. If `isinstance(runtime, (LinearRuntime, MctsSearchRuntime, ActorRuntime))`:
   - Bind `self.runtime_type` to `runtime.runtime_type`.
   - For `ActorRuntime`, extract `dynamic_actors`, `max_loop`, `termination_mode`, `worker_model`, and `include_actors`.
2. Keep direct parameters as backward-compatible fallback checks.
3. Throw validation errors for incompatible parameters.

---

### 6.6 [New Prompt Files] Prompt Catalogs
**File(s):**
`vidbyte/prompts/prompts/actor_runtime/*.md` (15 total)
`vidbyte/prompts/prompts/actor_runtime/actor_runtime.json` (Catalog map)

**Type:** Create/Modify prompt assets

#### Structure Guidelines
No context protocol headers. Every prompt consists of:
1. **Identity** (6-8 sentences aligning the actor with world-class execution).
2. **Goal** (6-8 sentences specifying the output structure and intent).
3. **Checklist** (15-20 comprehensive bullet points).

---

## 7. Data Model Changes

N/A - Runtime-specific configurations only.

---

## 8. API Changes

The core agent initialization supports both string types and structured objects:

```python
# Option A: Configured Actor Swarm
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.runtimes.configs import ActorRuntime
from vidbyte.agents.runtimes.actor import PlannerActor, CoderActor

actor_config = ActorRuntime(
    topology="actor_model_p2p",
    dynamic_actors=True,
    include_actors=[PlannerActor, CoderActor] # spawn only planner and coder
)

agent = BaseAgent(
    name="orchestrator",
    runtime=actor_config,
    system_prompt="Manage tasks."
)
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/registries/__init__.py` | Package exports for registries |
| CREATE | `vidbyte/lib/registries/agents.py` | Relocate AgentRegistry |
| CREATE | `vidbyte/lib/registries/models.py` | Relocate ProviderModelRegistry |
| CREATE | `vidbyte/lib/registries/prompts.py` | Relocate Prompts |
| CREATE | `vidbyte/lib/registries/tools.py` | Relocate ToolRegistry |
| CREATE | `vidbyte/lib/registries/actors.py` | Prebuilt actor class registry |
| CREATE | `vidbyte/agents/runtimes/configs.py` | Encapsulate Linear, Search, Actor runtimes |
| MODIFY | `vidbyte/agents/runtimes/__init__.py` | Export configurations and prebuilt classes |
| MODIFY | `vidbyte/agents/runtimes/actor/actor.py` | Define class-first prebuilt actors |
| MODIFY | `vidbyte/agents/runtimes/actor/broker.py` | Support selective actor list spawning |
| MODIFY | `vidbyte/agents/base.py` | Resolve runtime config objects & validation |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add Prompt enum keys for 9 new actors |
| MODIFY | `vidbyte/prompts/prompts/actor_runtime/actor_runtime.json` | Catalog mapping for all 15 actors |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/summarization.md` | Prompts for new Summarization actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/decomposer.md` | Prompts for new Decomposer actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/explorer.md` | Prompts for new Explorer actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/tradeoff.md` | Prompts for new Tradeoff actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/hypothesis_generator.md` | Prompts for new Hypothesis Generator actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/refiner.md` | Prompts for new Refiner actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/formatter.md` | Prompts for new Formatter actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/safety.md` | Prompts for new Safety actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/final_answer.md` | Prompts for new Final Answer actor |
| DELETE | `vidbyte/agents/registry.py` | Relocated |
| DELETE | `vidbyte/lib/models/registry.py` | Relocated |
| DELETE | `vidbyte/prompts/registry.py` | Relocated |
| DELETE | `vidbyte/tools/registry.py` | Relocated |

---

## 10. Testing Plan

### Unit Tests
- `test_registries_relocation`
  - `[Edge Case]` Verify all relocated registry classes load correctly from the new registries subpackage.
- `test_runtime_config_objects`
  - `[Edge Case]` Validate agent instantiation with `LinearRuntime`, `MctsSearchRuntime`, and `ActorRuntime` instances.
- `test_selective_actor_spawning`
  - `[Edge Case]` Spawning an empty `include_actors` list registers 0 prebuilt actors.
  - `[Edge Case]` Spawning with `[PlannerActor, CoderActor]` spawns only those two in the registry.
  - `[Hidden Failure]` Spawning with `None` defaults and spawns the standard 6 prebuilt actors.
- `test_actor_registry_methods`
  - `[Edge Case]` Check `ActorRegistry.list()`, `get()`, and `create()` work perfectly with both prebuilt and custom actors.
- `test_fail_fast_runtime_validation`
  - `[Hidden Failure]` Verify `ConfigurationError` when trying to configure non-linear runtimes with active middleware.

### Integration Tests
- Run an E2E concurrent point-to-point task routing using a selective `[PlannerActor, CoderActor]` actor swarm, verifying that communication completes successfully.

---

## 11. Dependencies & External Services

N/A - Standard libraries.

---

## 12. Rollout & Deployment

This is completely backward-compatible. String-based runtime configurations (e.g. `"linear"`) and original registries imports will continue to function normally or raise clear deprecated notices.

---

## 13. Open Questions

None.

---

## 14. Alternatives Considered

### Alternative 1: Dict-based Configurations
- **Why rejected:** Dicts are not typed, making it easy to introduce typos or incorrect options. Config classes provide static compilation safety and autocompletion in standard IDEs.
