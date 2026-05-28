<!-- Context Protocol Header
Description:
    Skill documentation for swappable agent runtimes in the Vidbyte SDK.
Purpose:
    Guides developers on selecting and configuring Linear, MCTS, and Actor Model runtimes,
    explaining topologies, dynamic spawning, and termination safeguards.
Architecture:
    SDK Skill Guide.
Relations:
    Located in skills/agent-runtimes/SKILL.md. Complements the core SDK reference guides.
Similar Files:
    - skills/sdk/SKILL.md: Core SDK paradigms and structures.
-->

# Agent Runtimes Skill Guide

This guide details how developers can configure, select, and utilize the different execution runtimes provided by the Vidbyte SDK.

---

## 1. Overview of Agent Runtimes

The Vidbyte SDK decouples the core `BaseAgent` class from the underlying execution loop (the runtime). When instantiating an agent, developers can select from three paradigms depending on the orchestration and reasoning complexity needed:

| Runtime Type | Description | Key Topologies | Compaction & Middleware Compatibility |
|--------------|-------------|----------------|---------------------------------------|
| **Linear** | Sequential forward-moving loop executing actions one step at a time. | N/A | Fully Compatible |
| **MCTS Search** | Non-linear tree search (Monte Carlo Tree Search) exploring parallel reasoning paths. | Search Tree | Strictly Incompatible (Raises Error) |
| **Actor Model** | Asynchronous, concurrent multi-agent system executing via reactive message-passing. | P2P, Broadcast | Strictly Incompatible (Raises Error) |

---

## 2. Linear Runtime

The standard direct execution model where the agent performs sequential cycles of reasoning, tool calls, and model calls.

### How to use
The Linear runtime is the default configuration.

```python
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.enums import AgentRuntimeType

agent = BaseAgent(
    name="standard_agent",
    system_prompt="You are a helpful assistant.",
    runtime=AgentRuntimeType.LINEAR  # Optional, default value
)

reply = agent.run("Perform search and write a summary.")
```

---

## 3. Branching Search MCTS Runtime

Designed for complex procedural tasks where the agent needs to explore multiple alternative paths, evaluate the outcomes, and perform backtracks or rollbacks to parent states when a path hits a dead end.

### How to use
Set `runtime=AgentRuntimeType.MCTS_SEARCH` (or `"mcts_search"`).

```python
from vidbyte.agents.base import BaseAgent

search_agent = BaseAgent(
    name="tree_explorer",
    system_prompt="Analyze intermediate paths and select the highest value branch.",
    runtime="mcts_search"
)

reply = search_agent.run("Verify all prime numbers between 100 and 150.")
```

---

## 4. Asynchronous Actor Model Runtime

Implements a concurrent multi-agent network where independent "actors" communicate asynchronously via message passing. Each actor has its own private inbox queue (`asyncio.Queue`), message logs, and isolated state dict.

### 4.1 Topology Options
Developers can select from two communication topologies:
1. **Point-to-Point (P2P)** (`actor_model_p2p`): Messages are sent directly from one actor's address to a designated recipient mailbox.
2. **Broadcast** (`actor_model_broadcast`): Every message is replicated and delivered to the mailboxes of *all* registered actors (excluding the sender).

### 4.2 Prebuilt Personas
When an actor runtime is instantiated, the system automatically spawns a set of standardized prebuilt personas with specialized system prompts:
- **`planner`**: Analyzes goals, breaks down tasks, and manages subtask queues.
- **`coder`**: Generates code solutions and automation scripts.
- **`reviewer`**: Performs critiques, identifies edge cases, and reviews code.
- **`generator`**: Synthesizes intermediate results and compiles responses.
- **`critic`**: Evaluates general outputs against constraints.
- **`reasoner`**: Conducts logical analysis and deep reasoning.

### 4.3 Dynamic Actor Spawning
If `dynamic_actors=True` is configured, the broker automatically registers the `spawn_actor` tool. This allows the LLM to dynamically spawn custom actors at runtime:

```json
// Example of tool call executed by the model
{
  "name": "spawn_actor",
  "arguments": {
    "actor_name": "data_parser_3",
    "system_prompt": "You are a specialized parser focusing strictly on regex sanitization.",
    "model_name": "gpt-4o-mini"
  }
}
```

### 4.4 Configurable Parameters

Developers can customize the execution loop through the following constructor options:
* **`dynamic_actors`** (bool): Enables dynamic actor spawning via tool calls.
* **`max_loop`** (int): Safety ceiling specifying the maximum number of routed messages before forcing loop termination (prevents runaway costs).
* **`termination_mode`** (str):
  * `"coordinator"` (Default): Execution terminates as soon as the root coordinator actor completes the task.
  * `"quiescence"`: Swarm mode; runs until all actor mailboxes are empty and no worker tasks remain.
* **`worker_model`** (str): Option to run spawned actors with a different, cheaper model (e.g., `gpt-3.5-turbo`) while reserving the strong orchestrator model for the coordinator.

### Code Example: Configuring Actor Swarms
```python
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.enums import AgentRuntimeType

actor_swarm = BaseAgent(
    name="orchestrator",
    system_prompt="You are the lead manager coordinating sub-actors.",
    runtime=AgentRuntimeType.ACTOR_MODEL_P2P,
    dynamic_actors=True,
    max_loop=30,
    termination_mode="quiescence",
    worker_model="gpt-4o-mini"  # Cheap model for spawned workers
)

reply = actor_swarm.run("Code a snake game and perform an exhaustive security review.")
```

---

## 5. Fail-Fast Safety Guardrails

Because non-linear runtimes (MCTS and Actor Model) bypass sequential pipelines, they are structurally incompatible with:
- **Agent Middleware**: Deterministic pipeline hook code.
- **In-Context Algorithms**: Compaction presets (e.g. reflexion).

Attempting to instantiate an agent combining these options will immediately raise a `ConfigurationError` synchronously during construction, helping developers identify config issues before deploying.
