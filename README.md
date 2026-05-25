# Vidbyte SDK

`vidbyte-sdk` is the root-level home for Vidbyte's Python SDK surface.

This package is intentionally minimal right now. It establishes the SDK package identity and namespace layout without including private Vidbyte service logic.

## Status

This package is not published. It is marked `UNLICENSED` until Vidbyte's release, licensing, and open-source strategy are finalized.

## Usage

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
sdk.harnesses
sdk.agents
sdk.tools
sdk.providers
sdk.strategies
```

## Agents and Modalities

Use agents as the public entry point for model execution. Pick a modality explicitly when the request is not ordinary text; plain string prompts default to text.

```python
from vidbyte import ModelModality, VidbyteSDK

sdk = VidbyteSDK()

image_agent = sdk.agents.base(
    name="asset-generator",
    system_prompt="Create useful product assets.",
    provider="openai",
    model_name="gpt-image-1",
    modality=ModelModality.IMAGE,
)

reply = image_agent.run("A clean product mockup on a white desk")
print(reply.content)
```

Typed inputs can carry modality at call time:

```python
from vidbyte import AgentInput, ModelModality

reply = await image_agent.arun(
    AgentInput("A launch graphic with a simple product silhouette", modality=ModelModality.IMAGE)
)
```

## Multi-Agent Orchestration

Multi-agent execution is modeled as composition:

- `vidbyte.agents` contains actor objects such as `BaseAgent`, `AgentInput`, and `AgentRegistry`.
- `vidbyte.strategies.multi_agent` contains orchestration topologies such as consensus routing, AutoGen-style message passing, VMAO, economic gating, and evolving policy routing.
- Custom harnesses stay outside the base SDK until their public contracts are explicitly defined.

```python
from vidbyte import BaseAgent, ModelModality
from vidbyte.strategies import ReActStrategy

agent = BaseAgent(
    name="researcher",
    system_prompt="Answer directly and cite uncertainty.",
    strategy=ReActStrategy(),
    provider="openai",
    model_name="gpt-4.1",
    modality=ModelModality.TEXT,
)

reply = await agent.arun("Draft a concise release note")
```

For custom agents, pass an explicit `system_prompt`, optional reasoning strategy, modality, model config, runner, and tools into `Agent` or `BaseAgent`; then pass those agents into multi-agent strategies.
Semantic labels such as roles belong in agent metadata when callers need them.

## Strategy Chains

Agents without a strategy run the default agentic tool loop. Agents with `strategy=` or `strategies=[...]` bypass that loop and execute the configured prompt-engineering recipe directly.

Use `strategy=` for one technique:

```python
from vidbyte import Agent
from vidbyte.strategies import StepBackStrategy

agent = Agent(
    name="explainer",
    system_prompt="Explain from first principles.",
    runner=my_runner,
    strategy=StepBackStrategy(),
)
```

Use `strategies=[...]` to run techniques sequentially. Only the previous strategy's output text is passed to the next strategy.

```python
from vidbyte import Agent
from vidbyte.strategies import ChainOfDraftStrategy, StepBackStrategy

agent = Agent(
    name="writer",
    system_prompt="Write precise release notes.",
    runner=my_runner,
    strategies=[
        StepBackStrategy(),
        ChainOfDraftStrategy(),
    ],
)
```

For consensus, voting, or multi-agent orchestration, use explicit multi-agent strategies such as `MultiAgentConsensusStrategy`; a plain `strategies=[...]` list means output-only sequential chaining.

## Context Objects

Context dataclasses are exposed through `vidbyte.context` and centralized internally under `vidbyte.lib.dataclasses`.

```python
from vidbyte.context import ContextBudget, ContextPermissions, StrategyContext
from vidbyte.lib.enums import BudgetPreset, PermissionPreset

context = StrategyContext(
    file_paths=["README.md"],
    strategy_metadata={"phase": "draft"},
    budget=ContextBudget.from_preset(BudgetPreset.BALANCED),
    permissions=ContextPermissions.from_preset(PermissionPreset.READ_ONLY),
)
context.build_context()
```

## Context Management

Use `ContextManager` and context items when you want reusable, structured context
instead of assembling raw prompt strings yourself. Use `ContextWindow` presets
when you want an agent to run with an SDK-provided context-window algorithm.

```python
from vidbyte import Agent, ContextManager, FileContextItem, TaskContextItem

context = ContextManager([
    TaskContextItem(
        goal="Fix failing tests",
        progress="Reviewed the runtime context builder.",
        deterministic_checks=("python -m unittest discover -s tests",),
    ),
    FileContextItem.from_path("README.md", include_content=True),
])

agent = Agent(
    name="repo-analyst",
    system_prompt="Use the supplied context before answering.",
    runner=my_runner,
    context_manager=context,
)
```

Context-window algorithms are attached as a single agent option. The default
keeps existing behavior; presets can change how runtime context grows between
model calls.

```python
from vidbyte import ContextWindow

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    runner=my_runner,
    tools=[lookup_metric],
    algorithm=ContextWindow.preset.no_raw_tool_outputs,
)
```

Per-call context can be supplied with `AgentInput` without mutating the agent's
default context:

```python
from vidbyte import AgentInput, TextContextItem

reply = await agent.arun(
    AgentInput(
        "Review the current task.",
        context_items=(TextContextItem(title="Reviewer note", content="Focus on public API compatibility."),),
    )
)
```

### Tools

The SDK tool path is agent-local: create or import tools, pass them into an agent, and let the agent describe, format, and execute them when the model asks for a tool call.

```python
from vidbyte import Agent, tool
from vidbyte.tools.builtins.code_search import GrepTool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    """Look up one user's metric."""
    return {"user_id": user_id, "score": 94}

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    runner=my_runner,
    tools=[GrepTool(root_dir="."), lookup_metric],
    max_iterations=8,
    max_tokens=16_000,
)

reply = await agent.arun("Find where tools are formatted.")
```

Agents without a configured strategy run direct tool use through an internal runtime loop. The runtime builds the context window, appends a short agentic-loop prompt after the system prompt, sends tool schemas to the model, executes permitted tool calls, appends tool results back into the ordered message context, and repeats until the model calls the internal `isDone` tool. If the model returns ordinary text without a tool call, that text is preserved as assistant history and the loop continues. `max_iterations` and `max_tokens` are optional safeguards; `max_tokens` uses provider-reported usage when available.

### Middleware

Middleware gives direct text agents deterministic runtime hooks for authorization, rate limiting, retry, audit logging, and other policies. Middleware is not model-visible and does not appear in tool specs or agent cards.

```python
from vidbyte import Agent, AgentMiddleware, MiddlewareDecision
from vidbyte.middleware.builtins import ToolPolicyMiddleware

class TenantPermissionMiddleware(AgentMiddleware):
    def __init__(self, db):
        self.db = db

    async def before_run(self, ctx):
        if not await self.db.can_start_agent(ctx.metadata["tenant_id"], ctx.agent_name):
            return MiddlewareDecision.abort("tenant_cannot_start_agent")
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx):
        if not await self.db.can_call_tool(ctx.metadata["tenant_id"], ctx.tool_call.tool_name):
            return MiddlewareDecision.deny_tool("tenant_cannot_call_tool")
        return MiddlewareDecision.continue_()

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    runner=my_runner,
    tools=[lookup_metric],
    middleware=[
        TenantPermissionMiddleware(db),
        ToolPolicyMiddleware(allow_tools={"lookup_metric"}),
    ],
)
```

Subclass `AgentMiddleware` and override only the hooks you need, such as `before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `on_model_error`, `before_tool_call`, `after_tool_call`, `after_iteration`, or `after_run`. Built-ins are available from `vidbyte.middleware.builtins`, including `TokenRateLimitMiddleware`, `RuntimeLimitMiddleware`, `ToolPolicyMiddleware`, `AuditLogMiddleware`, and `ModelRetryMiddleware`.

Advanced built-ins are grouped by category:

- `vidbyte.tools.builtins.code_search`: `GlobTool`, `GrepTool`, `SemanticSearchTool`
- `vidbyte.tools.builtins.editing`: `PatchTool`
- `vidbyte.tools.builtins.context`: `ContextCompactionTool`
- `vidbyte.tools.mcp`: `McpClient`, `McpStdioTransport`, `McpBridgedTool`
- `vidbyte.tools.security`: `PermissionPolicy`, `ToolPermission`, sandbox transport protocols

`Tools` is the catalog/inspection helper for showing the model or a developer which tools are available:

```python
from vidbyte.tools import Tools

catalog = Tools([lookup_metric])
print(catalog.describe())
openai_tools = catalog.provider_schemas("openai")
```

The default permission policy allows `SAFE` and `READ` tools. Mutating or executable tools require an explicit permission policy on the agent:

```python
from vidbyte import Agent
from vidbyte.tools.security import PermissionPolicy

agent = Agent(
    name="trusted-worker",
    system_prompt="Work inside the configured sandbox.",
    runner=my_runner,
    tools=[write_tool],
    permission_policy=PermissionPolicy.allow_all(),
)
```

`ToolRegistry`, `ToolExecutor`, and `vidbyte_tool` remain available for compatibility with older examples and lower-level strategy code. New user-facing code should prefer `Tools`, `@tool`, and agent-local `tools=[...]`.

## Prompts

Prompts are plain text assets exposed through an enum-keyed accessor:

```python
from vidbyte.prompts import Prompts, chain_of_thought_reason_prompt
from vidbyte.lib.enums.prompts import Prompt

prompts = Prompts()
prompt_text = prompts.get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)
assert prompt_text == chain_of_thought_reason_prompt
```

`Prompts().keys()` returns all prompt enum keys, and `Prompts().descriptions()` returns descriptions for each key. Prompt lookup does not accept raw strings and the SDK does not expose runtime prompt overrides.

## Package Structure

```text
vidbyte/
|-- client.py
|-- agents/
|-- context/
|-- harnesses/
|   `-- client.py
|-- prompts/
|   `-- prompts/
|-- providers/
|   `-- client.py
|-- middleware/
|   `-- builtins/
|-- strategies/
|   `-- multi_agent/
|-- tools/
|   |-- client.py
|   |-- catalog.py
|   |-- base.py
|   |-- registry.py
|   |-- executor.py
|   |-- builtins/
|   |-- mcp/
|   `-- security/
|-- shared/
`-- lib/
    |-- dataclasses/
    |-- runners/
    |-- tools/
    |-- enums/
    `-- errors/
```

## Public Boundary

The SDK should contain reusable public namespace scaffolding and developer-facing abstractions.

Private Vidbyte service implementations, proprietary learning evaluations, prompts, scoring logic, adaptive sequencing, and database access should stay outside this package.

## Local Verification

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import Agent, Tools, VidbyteSDK, tool; sdk = VidbyteSDK(); print(Agent.__name__, Tools.__name__, type(sdk.agents).__name__, callable(tool))"
```
