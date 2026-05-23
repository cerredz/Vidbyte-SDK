# Create Agents

Create and manage multiple agents with the `AgentRegistry`.

## Creating Multiple Agents

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

```python
from vidbyte import AgentRegistry

registry = AgentRegistry()

# Register agents
registry.register(planner)
registry.register(coder)
registry.register(reviewer)

# Lookup by name
agent = registry.get("planner")       # raises AgentRegistryError if not found

# All agents
all_agents = registry.all()           # tuple[Agent, ...]

# All capability cards
cards = registry.cards()              # tuple[AgentCard, ...]

# Find by capability
code_agents = registry.find(capability="code")
python_agents = registry.find(tool_name="python_executor")
tagged = registry.find(metadata={"team": "backend"})
```

## Adding Capability Metadata

```python
from vidbyte import Agent

coder = Agent(
    name="coder",
    system_prompt="...",
    provider="openai",
    model_name="gpt-4.1",
    capabilities=["code_generation", "code_review", "refactoring"],
    description="Expert Python and TypeScript developer.",
    metadata={"language": "python", "team": "backend", "level": "senior"},
)
```

## Agent Communication (Message Passing)

```python
from vidbyte import AgentMessage

# Agent receives a message (adds to history)
await coder.receive(AgentMessage(
    sender="user",
    recipient="coder",
    content="Write a function that sorts a list of integers.",
))

# Agent generates a reply
reply = await coder.arun("Optimize the sorting function you just wrote.")
```

## Multi-Agent Pattern (Manual)

```python
async def plan_and_code(task: str) -> str:
    # Step 1: plan
    plan = await planner.arun(f"Create a plan for: {task}")

    # Step 2: code
    code = await coder.arun(f"Plan:\n{plan.content}\n\nImplement this plan.")

    # Step 3: review
    review = await reviewer.arun(f"Code:\n{code.content}\n\nReview for correctness.")

    return review.content
```

## Multi-Agent with Strategies

For built-in multi-agent orchestration, use strategies instead of manual wiring:

```python
from vidbyte.strategies.multi_agent import MultiAgentConsensusStrategy
from vidbyte import ChainOfThoughtStrategy

consensus = MultiAgentConsensusStrategy(
    candidates=[coder, reviewer],
    evaluator=planner,
    max_calls=3,
)
# Used as an agent's strategy
agent = Agent(
    name="orchestrator",
    system_prompt="...",
    strategy=consensus,
    provider="openai",
    model_name="gpt-4.1",
)
```
