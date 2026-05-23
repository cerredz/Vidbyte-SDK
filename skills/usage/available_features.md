# Available Features

Features, strategies, and orchestration primitives included out of the box.

## Root SDK Client

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
# sdk.agents       -> AgentClient
# sdk.tools        -> ToolsClient
# sdk.strategies   -> StrategyClient
# sdk.harnesses    -> HarnessClient
# sdk.providers    -> ProvidersClient
```

## Strategies

### Reasoning Strategies

```python
from vidbyte import (
    ChainOfThoughtStrategy,   # explicit reasoning -> final response
    StepBackStrategy,         # extract principles, then answer
    ChainOfDraftStrategy,     # compact draft reasoning steps
    SkeletonOfThoughtStrategy,# skeleton -> expand -> assemble
)
```

Usage:
```python
agent = Agent(
    name="reasoner",
    system_prompt="You reason carefully.",
    strategy=ChainOfThoughtStrategy(),
    provider="openai",
    model_name="gpt-4.1",
)
```

### Sampling Strategies

```python
from vidbyte import (
    SelfConsistencyStrategy,   # multiple samples, pick consistent
    BudgetForcingStrategy,     # bounded retry attempts
    AnswerConvergenceStrategy, # repeat until convergence
)
```

### Agent Loop Strategies

```python
from vidbyte import (
    PlanAndExecuteStrategy,  # plan -> execute steps -> synthesize
    SelfRefinementStrategy,  # create -> critique -> refine
)
```

### Routing Strategies

```python
from vidbyte import ParadigmRouterStrategy  # prompt-guided paradigm selection
```

### Other Single-Agent

```python
from vidbyte import (
    TreeOfThoughtsStrategy,  # branch -> evaluate -> synthesize
    ReActStrategy,           # reason+act loop with tools
    CodeActStrategy,         # code-action extension of ReAct
    ReflexionStrategy,       # reflective retry/refinement
)
```

## Multi-Agent Strategies

Import from `vidbyte.strategies.multi_agent`:

```python
from vidbyte.strategies.multi_agent import (
    MultiAgentConsensusStrategy,       # candidates -> evaluator -> best
    AutoGenConversationStrategy,       # AutoGen-style message passing
    VerifiedMultiAgentOrchestrationStrategy,  # VMAO: plan-execute-verify
    EconomicGateStrategy,              # cost-benefit routing
    EvolvingOrchestrationStrategy,     # policy-driven agent selection
)
```

A multi-agent strategy is used the same way as any strategy - pass it to `Agent(strategy=...)`.

## Pipelines

```python
from vidbyte import (
    SequentialPipeline,    # stages run in order, output -> next input
    ParallelPipeline,      # stages run concurrently, outputs joined
    ConditionalPipeline,   # predicate routes prompt to branch
    BasePipeline,          # abstract base, inherit for custom pipelines
)
```

## Modality Routing

Agents auto-detect and route to the correct runner by modality:

```python
from vidbyte import ModelModality

ModelModality.AUTO   # detect from model name or input
ModelModality.TEXT   # force text generation
ModelModality.IMAGE  # force image generation
ModelModality.VIDEO  # force video generation

# Set default modality on agent
agent = Agent(..., modality=ModelModality.TEXT)

# Override per-call
reply = await agent.arun(AgentInput("Create a logo", modality=ModelModality.IMAGE))
```

## Context Budgets & Permissions

```python
from vidbyte import ContextBudget, ContextPermissions, BudgetPreset, PermissionPreset

# Budget presets control resource consumption
budget = ContextBudget.from_preset(BudgetPreset.BALANCED)
# TIGHT:      3 calls,  4k tokens,  30s
# BALANCED:   8 calls, 16k tokens, 120s
# EXPLORATORY: 20 calls, 64k tokens, 300s

# Permission presets control what the agent can do
permissions = ContextPermissions.from_preset(PermissionPreset.READ_ONLY)
# READ_ONLY:  can read files, no tools, no write
# TOOLS_ONLY: tools allowed, no filesystem
# TRUSTED:    full access
```

## Provider Support

```python
from vidbyte import ModelProvider

ModelProvider.OPENAI      # GPT-4, GPT-4o, O1, etc.
ModelProvider.ANTHROPIC   # Claude 3.5, Claude 3, etc.
ModelProvider.GEMINI      # Gemini 1.5 Pro, Flash, etc.
ModelProvider.XAI         # Grok models
ModelProvider.DEEPSEEK    # DeepSeek models
ModelProvider.GLM         # GLM models
ModelProvider.MINIMAX     # MiniMax models
```

## Agent Forking

Create variant agents from a base without re-declaring all config:

```python
child = agent.fork(name="child", temperature=0.1)                # override any kwarg
child_with_context = agent.fork(include_history=True, name="ctx") # copies message history
```

## MCP Server Attachment

Attach external MCP servers to agents at runtime:

```python
# Async attachment
agent = await Agent(name="mcp-agent", system_prompt="...").attach_mcp_server(
    ["python", "my_server.py"],
    name="my-server",
)

# Sync builder (lazy connection on first arun)
agent = Agent(name="mcp-agent", system_prompt="...").with_mcp_server(
    ["python", "my_server.py"],
    name="my-server",
)

# Cleanup
await agent.close_mcp_servers()
```

## Strategy Composability

`StrategyMixin` allows hosts to compose multiple strategies:

```python
from vidbyte import StrategyMixin

# Harnesses and other hosts use with_strategy() / with_strategies()
# to attach one or more strategies programmatically.
```

## Error Hierarchy

```python
from vidbyte import (
    VidbyteSdkError,             # base
    AgentExecutionError,         # agent failures
    PipelineExecutionError,      # pipeline failures
    StrategyExecutionError,      # strategy failures
    ToolExecutionError,          # tool runtime errors
    PermissionDeniedError,       # policy violations
    ConfigurationError,          # invalid config
    McpError,                    # MCP base error
    # ... and more
)
```
