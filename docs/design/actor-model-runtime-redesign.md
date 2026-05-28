<!-- Context Protocol Header
Description:
    Design document for Asynchronous Actor Model Runtime redesign.
Purpose:
    Defines the architecture, APIs, workflows, and test plan for swappable Point-to-Point
    and Broadcast Actor Runtimes, prebuilt actors, dynamic actor spawning, and configurable
    orchestrator-spawned model settings in the Vidbyte SDK.
Architecture:
    - Multi-Agent Actor Model.
    - Swappable Point-to-Point vs Broadcast.
    - Prebuilt & Dynamic Actors via spawning tools.
Relations:
    Located in docs/design/. Anchors the implementation of the Actor Model features.
-->

# Design Doc: Asynchronous Actor Model Runtime Redesign

**Status:** Draft
**Author:** Antigravity
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

This design doc details the full refactoring and implementation of the **Asynchronous Actor Model Runtime** for the Vidbyte SDK. Moving beyond simple stubs, we introduce two distinct execution architectures: **Point-to-Point (P2P)** and **Broadcast** message-passing, encapsulating actor execution within a dedicated subpackage (`vidbyte/agents/runtimes/actor/`). 

We define a rich set of prebuilt actor personas (Planner, Coder, Reviewer, Generator, Critic, Reasoner) with standardized system prompts, while also introducing a native tool allowing the orchestrator agent to dynamically spawn custom actors at runtime. The runtime provides configurable LLM runner models (orchestrator vs. spawned workers), parallel execution threads, and custom termination controls (`max_loop` and termination option triggers), offering developer flexibility.

---

## 2. Goals & Non-Goals

### Goals
- Replace the current skeleton `ActorRuntimeComponent` implementation with a fully fledged, swappable concurrent architecture.
- Implement two distinct communication topologies as separate runtime components: `PointToPointActorRuntime` and `BroadcastActorRuntime`.
- Introduce a dedicated `ActorMessage` data structure ensuring complete serialization and propagation of execution context, states, and history between actors.
- Establish a directory-based prebuilt actor persona system under `vidbyte/agents/runtimes/actor/prebuilt/` with standardized prompt assets in `vidbyte/prompts/prompts/actor_runtime/`.
- Provide a `spawn_actor` tool in `vidbyte/tools/dynamic_actor.py` enabling orchestrators or model loops to dynamically instantiate new actors at runtime.
- Support configurable execution parameters:
  - Custom LLM runner selection (using the orchestrator model vs. specialized models for spawned workers).
  - Explicit termination settings (Coordinator Decision vs. Quiescence/Message Counts) paired with `max_loop` safeguards.
- Enforce strict fail-fast validation against incompatible sequential features (middleware and non-default context algorithms).
- Write a comprehensive verification test script under `scripts/test-actor-model-runtime-redesign.py`.

### Non-Goals
- Supporting persistent actor state database migrations or out-of-process RPC communications in this phase (all concurrency runs locally via `asyncio`).
- Virtualized Docker filesystem sandboxes for command executions (rollbacks remain context-only or bounded by standard read-only tool constraints).

---

## 3. Background & Context

Multi-agent coordination in modern AI architectures requires robust concurrency and state containment to avoid context collapse or token budget exhaustion. While the initial PR #66 established a minimal, direct linear/non-linear routing hierarchy, its Actor Model was a non-functional mock that returned hardcoded strings. 

To deliver a developer-ready runtime, we need a complete message broker, structured actor messaging, concurrent event queues, and flexible termination safeguards. Drawing inspiration from distributed frameworks (like Ray and Akka) and multi-agent papers, this redesign implements a decoupled, state-isolated actor ecosystem directly inside the Vidbyte SDK.

---

## 4. Requirements

### Functional Requirements

1. **Topology Swapping**: The developer must be able to configure either `PointToPointActorRuntime` or `BroadcastActorRuntime` via `BaseAgent` settings.
2. **Actor Message Schema**: Messages exchanged between actors must use the `ActorMessage` class, containing unique IDs, sender/recipient addresses, structured string payloads, parent task context, and local state dicts.
3. **Standardized Actor Personas**: The runtime must ship with prebuilt roles: `Planner`, `Coder`, `Reviewer`, `Generator`, `Critic`, and `Reasoner`. Prompts must be loaded via JSON files under `vidbyte/prompts/prompts/actor_runtime/`.
4. **Dynamic Actor Spawning**: The agent must automatically attach a `DynamicActorTool` if `dynamic_actors` is enabled, allowing the LLM to register and spawn custom actors on the fly.
5. **Configurable Runner Assignment**: The system must allow assigning different LLMs (or the same LLM) to the orchestrator agent and spawned worker actors.
6. **Robust Termination Safeguards**: The runtime must support:
   - **Coordinator Termination (Option A)**: Stopping as soon as the orchestrator actor receives a completion signal.
   - **Quiescence (Option B)**: Stopping when all actor mailboxes are empty and no worker tasks are pending.
   - **Max Loop Constraint**: A mandatory `max_loop` integer setting to prevent infinite loops.
7. **Fail-Fast Enforcement**: Instantiating an actor-runtime agent with sequential middleware or custom compaction algorithms must raise a `ConfigurationError`.

### Non-Functional Requirements

- **Concurrency**: Actor loops must run concurrently utilizing Python's `asyncio` event loop.
- **Isolation**: Each actor's local state and context history must be strictly encapsulated, preventing cross-actor namespace contamination.
- **Traceability**: All messages routed through the runtime broker must emit log traces containing message IDs, sender, recipient, and content summaries.

---

## 5. High-Level Design

The redesigned architecture divides the actor runtime into isolated layers: the **Broker (Runtime)**, **Mailboxes (Inboxes)**, **Actors (Workers)**, and the **Prompt Catalog**.

```text
[BaseAgent (Orchestrator)]
        |
        +--> Instantiates: [PointToPointActorRuntime] or [BroadcastActorRuntime]
                               |
                               +--> Manages registry: { actor_id: AgentActor }
                               |
                               +--> Spawns background tasks for all actors
                               |
                               +--> DynamicActorTool (Allows dynamic spawning)
                               |
        +--> Routes messages:  Sender -> Broker -> Recipient Inbox (asyncio.Queue) -> Actor Loop -> LLM/Tools
```

### Key Design Decisions:
- **Broker Topologies**: `PointToPointActorRuntime` routes messages strictly to targeted `recipient` mailboxes. `BroadcastActorRuntime` copies incoming messages and publishes them to *every* registered actor mailbox, allowing actors to react selectively based on their system instructions.
- **Decoupled LLM Calls**: When an actor handles a message, it clones the orchestrator's runner configuration but optionally overrides the provider or model name if worker-specific settings are supplied.
- **Context Compilation**: Prompts are assembled by combining the actor's unique system prompt, its private conversation context, and the incoming `ActorMessage` content.

---

## 6. Detailed Design

### 6.1 [New File] `ActorMessage` Class
**File(s):** `vidbyte/agents/runtimes/actor/message.py`
**Type:** New file

#### What it does
Provides the standardized schema for message exchange between agent actors.

#### Interface / API
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ActorMessage:
    """Represents a structured, serializable message passed between concurrent actors."""
    message_id: str
    sender: str
    recipient: str  # Specific actor_id or "all"
    content: str
    parent_task_id: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
```

---

### 6.2 [New File] `ActorInbox` Class
**File(s):** `vidbyte/agents/runtimes/actor/inbox.py`
**Type:** New file

#### What it does
Implements a thread-safe asynchronous message queue for individual actors.

#### Interface / API
```python
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.actor.message import ActorMessage

class ActorInbox:
    """Manages an incoming message queue for an asynchronous agent actor."""
    def __init__(self) -> None:
        self._queue: asyncio.Queue[ActorMessage] = asyncio.Queue()

    async def put(self, message: ActorMessage) -> None:
        # Enqueue a message payload.
        await self._queue.put(message)

    async def get(self) -> ActorMessage:
        # Dequeue the next message asynchronously.
        return await self._queue.get()
```

---

### 6.3 [New File] `AgentActor` and Prebuilt Personas
**File(s):** `vidbyte/agents/runtimes/actor/actor.py`
**Type:** New file

#### What it does
Encapsulates actor reactive loops, local memories, LLM invocation runners, and defines prebuilt personas (Planner, Coder, etc.).

#### Interface / API
```python
from __future__ import annotations
import asyncio
from typing import Any, Mapping
from vidbyte.agents.runtimes.actor.inbox import ActorInbox
from vidbyte.agents.runtimes.actor.message import ActorMessage

class AgentActor:
    """Represents an isolated agent actor executing in a concurrent background loop."""
    def __init__(self, actor_id: str, system_prompt: str, broker: Any, model_name: str | None = None) -> None:
        self.actor_id = actor_id
        self.system_prompt = system_prompt
        self.broker = broker
        self.model_name = model_name
        self.inbox = ActorInbox()
        self.state: dict[str, Any] = {}
        self.history: list[ActorMessage] = []

    async def start(self) -> None:
        # Infinite event loop polling the inbox queue.
        while True:
            msg = await self.inbox.get()
            self.history.append(msg)
            response = await self.on_receive(msg)
            if response:
                await self.broker.send(self.actor_id, msg.sender, response, parent_task_id=msg.parent_task_id)

    async def on_receive(self, message: ActorMessage) -> str | None:
        # Logic to invoke the LLM runner with the compiled prompt.
        pass
```

---

### 6.4 [New File] `BaseActorRuntime` and Broker Classes
**File(s):** `vidbyte/agents/runtimes/actor/broker.py`
**Type:** New file

#### What it does
Implements the core broker logic, routing protocols (P2P vs. Broadcast), dynamic spawning, and termination loop tracking.

#### Interface / API
```python
from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Mapping, Sequence
from vidbyte.agents.runtimes.actor.actor import AgentActor
from vidbyte.agents.runtimes.actor.message import ActorMessage
from vidbyte.strategies.types import BaseAgentContext, StrategyResult

class BaseActorRuntime(ABC):
    """Abstract base broker orchestrating actor lifecycles, execution, and loops."""
    def __init__(self, *, agent_name: str, system_prompt: str, tools: Any, config: Any, dynamic_actors: bool = False, max_loop: int = 20, termination_mode: str = "coordinator", worker_model: str | None = None) -> None:
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.config = config
        self.dynamic_actors = dynamic_actors
        self.max_loop = max_loop
        self.termination_mode = termination_mode
        self.worker_model = worker_model
        self._actors: dict[str, AgentActor] = {}
        self._message_count = 0
        self._completion_future: asyncio.Future[str] | None = None

    async def spawn(self, actor_id: str, system_prompt: str, model_name: str | None = None) -> AgentActor:
        # Dynamic or prebuilt actor instantiation and loop launch.
        pass

    @abstractmethod
    async def send(self, sender: str, recipient: str, content: str, parent_task_id: str | None = None) -> None:
        """Route message from sender to recipient inbox."""


class PointToPointActorRuntime(BaseActorRuntime):
    """Routes messages strictly to a single targeted recipient inbox."""
    async def send(self, sender: str, recipient: str, content: str, parent_task_id: str | None = None) -> None:
        pass


class BroadcastActorRuntime(BaseActorRuntime):
    """Replicates and broadcasts incoming messages to all registered actor mailboxes."""
    async def send(self, sender: str, recipient: str, content: str, parent_task_id: str | None = None) -> None:
        pass
```

---

### 6.5 [New File] Dynamic Spawning Tool
**File(s):** `vidbyte/tools/dynamic_actor.py`
**Type:** New file

#### What it does
Provides a native tool declaration enabling orchestrator or worker LLMs to programmatically register and spawn custom actors on the fly.

#### Interface / API
```python
from __future__ import annotations
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec

class DynamicActorTool(BaseTool):
    """Allows active agent actors to dynamically spawn and register new sub-actors."""
    def __init__(self, broker: Any) -> None:
        self.broker = broker

    def spec(self) -> ToolSpec:
        pass

    async def execute(self, call: ToolCall) -> ToolResult:
        pass
```

---

### 6.6 [New Files] Prompts and Prompt Enums
**File(s):** `vidbyte/prompts/prompts/actor_runtime/planner.json`, `coder.json`, `reviewer.json`, `generator.json`, `critic.json`, `reasoner.json`
**Type:** New Files

#### What they do
Define standardized system prompts for the prebuilt actor personas.

---

### 6.7 [Modify] Base Agent & Enums
**File(s):** `vidbyte/agents/base.py`, `vidbyte/lib/enums/agent_runtime.py`, `vidbyte/lib/enums/prompts.py`
**Type:** Modified Files

#### What they do
- `base.py`: Accept parameters `dynamic_actors` (bool), `max_loop` (int), `termination_mode` (str), `worker_model` (str), and `actor_topology` (str). Validate configurations and dynamically instantiate `PointToPointActorRuntime` or `BroadcastActorRuntime`.
- `agent_runtime.py`: Add `ACTOR_MODEL_P2P = "actor_model_p2p"` and `ACTOR_MODEL_BROADCAST = "actor_model_broadcast"`.
- `prompts.py`: Register enum values for the new JSON prompts under the `actor_runtime` family.

---

## 7. Data Model Changes

N/A - This feature changes only runtime execution flows and message passing state. No persistent database schemas are modified.

---

## 8. API Changes

### 8.1 BaseAgent Class Constructor
The constructor for `BaseAgent` is modified to accept these configuration parameters:

```python
class BaseAgent:
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR,
        dynamic_actors: bool = False,
        max_loop: int = 20,
        termination_mode: str = "coordinator",  # "coordinator" or "quiescence"
        worker_model: str | None = None,
        # ...
    )
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/runtimes/actor/__init__.py` | Package initializer exporting components |
| CREATE | `vidbyte/agents/runtimes/actor/message.py` | ActorMessage schema definitions |
| CREATE | `vidbyte/agents/runtimes/actor/inbox.py` | Asynchronous thread-safe ActorInbox queue |
| CREATE | `vidbyte/agents/runtimes/actor/actor.py` | AgentActor implementation and prebuilt role catalogs |
| CREATE | `vidbyte/agents/runtimes/actor/broker.py` | BaseActorRuntime, P2P and Broadcast routing engines |
| CREATE | `vidbyte/tools/dynamic_actor.py` | DynamicActorTool allowing spawning via tool calls |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/planner.json` | Prompt assets for Planner actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/coder.json` | Prompt assets for Coder actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/reviewer.json` | Prompt assets for Reviewer actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/generator.json` | Prompt assets for Generator actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/critic.json` | Prompt assets for Critic actor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/reasoner.json` | Prompt assets for Reasoner actor |
| MODIFY | `vidbyte/agents/base.py` | Integrate broker instantiation, parameters, and dynamic routing |
| MODIFY | `vidbyte/lib/enums/agent_runtime.py` | Export new topology enum values |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Register prebuilt actor prompt asset enums |
| DELETE | `vidbyte/agents/runtimes/actor.py` | Removed in favor of full subpackage directory |

---

## 10. Testing Plan

We will implement extensive automated unit and validation checks inside `scripts/test-actor-model-runtime-redesign.py`.

### Unit & Integration Tests

- **`test_p2p_broker_message_routing` [Edge Case]**
  - Verify that a point-to-point broker routes messages strictly to the designated recipient mailbox, and visit counts for non-recipients remain exactly 0.
- **`test_broadcast_broker_message_replication` [Edge Case]**
  - Verify that a broadcast broker duplicates and delivers a single broadcast message to *every* active actor inbox in the registry.
- **`test_middleware_and_algorithms_fail_fast` [Hidden Failure]**
  - Verify that instantiating an actor runtime agent with custom compaction algorithms or middleware immediately raises `ConfigurationError`.
- **`test_max_loop_budget_forcing` [Hidden Failure]**
  - Verify that if actors exchange messages continuously, the system terminates and halts as soon as the execution loop index hits the `max_loop` constraint.
- **`test_coordinator_termination_trigger` [Silent Failure]**
  - Verify that coordinator mode (Option A) halts the broker execution loop as soon as the orchestrator signals task completion, even if worker actor mailboxes contain pending messages.
- **`test_quiescence_termination_trigger` [Silent Failure]**
  - Verify that quiescence mode (Option B) waits until all mailboxes are empty and active operations are completed before resolving the execution run.
- **`test_worker_model_runner_resolution` [Hidden Assumption]**
  - Verify that worker actors resolve to the designated `worker_model` when configured, and fall back to the orchestrator model when left default.
- **`test_dynamic_actor_spawning_via_tool` [Hidden Assumption]**
  - Verify that invoking `DynamicActorTool` adds a new actor to the broker registry and starts its asyncio loop.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio` | Built-in standard library | Asynchronous event loop scheduling | High concurrent execution complexity |

---

## 12. Rollout & Deployment

This is a backward-compatible addition. The default agent runtime is `AgentRuntimeType.LINEAR`, ensuring existing applications and systems remain completely unaffected. The actor topologies are strictly opt-in.

---

## 13. Open Questions

- [x] Should we separate P2P and Broadcast runtimes? Yes, they are modeled as distinct sub-classes.
- [x] Can the prebuilt set and dynamic spawning be used together? Yes, the `spawn_actor` tool is dynamically registered on top of the prebuilt registry when configured.

---

## 14. Alternatives Considered

### Alternative 1: Monolithic Single Broker
- **Why rejected:** Combining Point-to-Point routing and Broadcast message replication into a single `ActorRuntime` class creates a confusing, highly branched execution path with complex conditional logic, reducing maintainability. Implementing them as clean subclasses provides architectural clarity.

### Alternative 2: In-Memory JSON Strings for Actor Prompts
- **Why rejected:** Storing system prompts as plain strings inside Python modules makes them difficult to localize or customize. Utilizing Vidbyte's native JSON prompt catalog ensures centralized management and standardizes on the existing SDK asset loader.
