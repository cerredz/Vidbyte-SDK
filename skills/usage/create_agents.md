# Create Agents

Create and manage multiple agents with the `AgentRegistry`. The registry provides discovery, lookup, and capability-based search for agent collections â€” essential for multi-agent workflows, orchestration, and dynamic agent selection.

Use the registry when you have multiple agents that need to discover each other, or when you need to find agents by capability or metadata at runtime.

## Creating Multiple Agents

Define each agent independently with its own name, system prompt, model, tools, and tools. Each agent is a self-contained execution unit:

```python
from vidbyte import Agent

planner = Agent(
    name="planner",
    system_prompt="You create step-by-step plans for software tasks.",
    provider="openai",
    model_name="gpt-4.1",
)

coder = Agent(
    name="coder",
    system_prompt="You write clean, idiomatic Python code.",
    provider="openai",
    model_name="gpt-4.1",
)

reviewer = Agent(
    name="reviewer",
    system_prompt="You review code for correctness, style, and performance.",
    provider="openai",
    model_name="gpt-4.1",
)
```

## Agent Registry

The registry is a centralized container for managing agent collections. Register agents, look them up by name, search by capability, and inspect their cards:

```python
from vidbyte import AgentRegistry

registry = AgentRegistry()

# Register agents
registry.register(planner)
registry.register(coder)
registry.register(reviewer)

# Lookup by name â€” raises AgentRegistryError if not found
agent = registry.get("planner")

# Get all agents
all_agents = registry.all()           # tuple[Agent, ...]

# Get all capability cards for discovery
cards = registry.cards()              # tuple[AgentCard, ...]

# Find by capability tag
code_agents = registry.find(capability="code_generation")
python_agents = registry.find(tool_name="GlobTool")
tagged = registry.find(metadata={"team": "backend", "level": "senior"})
```

**When to use the registry vs. manual wiring:**
- **Registry**: When agents need to discover each other dynamically, or when capabilities and metadata matter for selection.
- **Manual wiring**: For fixed, small pipelines (3-4 agents) where the relationships are known at code time.

## Adding Capability Metadata

Capabilities and metadata make agents discoverable. Attach them at construction time to enable registry-based search:

```python
from vidbyte import Agent

coder = Agent(
    name="coder",
    system_prompt="You write clean, idiomatic code.",
    provider="openai",
    model_name="gpt-4.1",
    capabilities=["code_generation", "code_review", "refactoring"],
    description="Expert Python and TypeScript developer with deep framework knowledge.",
    metadata={"language": "python", "team": "backend", "level": "senior"},
)
```

- **`capabilities`**: A list of string tags that describe what the agent can do. Used by `registry.find(capability=...)`.
- **`description`**: A human-readable description shown in agent cards.
- **`metadata`**: Arbitrary key-value pairs for any custom categorization (team, language, cost tier, etc.).

## Agent Communication (Message Passing)

Agents can receive messages and respond to them. Each agent maintains its own message history, which is used as context for subsequent runs:

```python
from vidbyte import AgentMessage

# Send a message to the agent (adds to its history)
await coder.receive(AgentMessage(
    sender="user",
    recipient="coder",
    content="Write a function that sorts a list of integers.",
))

# Agent generates a reply using its full history as context
reply = await coder.arun("Optimize the sorting function you just wrote.")
```

Message passing enables conversational workflows where agents remember past interactions. Each `AgentMessage` tracks sender, recipient, content, and metadata.

## Multi-Agent Pattern (Manual)

For simple multi-agent workflows with fixed roles, manual wiring is straightforward and explicit:

```python
async def plan_and_code(task: str) -> str:
    # Step 1: Create a plan
    plan = await planner.arun(f"Create a plan for: {task}")

    # Step 2: Implement the plan
    code = await coder.arun(f"Plan:\n{plan.content}\n\nImplement this plan.")

    # Step 3: Review the implementation
    review = await reviewer.arun(f"Code:\n{code.content}\n\nReview for correctness and style.")

    return review.content
```

This pattern works well for linear, fixed-role workflows where you know the exact agents and their order at code time.

## Multi-Agent Orchestration

Wire multiple agents together using pipelines for sequential, parallel, conditional, or map-reduce workflows. See [`skills/usage/create_pipeline.md`](create_pipeline.md) for details.

## Best Practices

- **Use descriptive names and capabilities** â€” they are the primary keys for registry lookups and orchestration selection.
- **Register agents early** â€” in a single setup function before any execution, not lazily during runs.
- **Use pipelines for multi-step workflows** — pipelines wire agents together by output, each carrying its own configuration and tools.
- **Keep agents focused** â€” each agent should have a single, clear responsibility defined by its system prompt and tools.

