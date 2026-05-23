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
sdk.tools
sdk.providers
sdk.strategies
```

## Multi-Agent Orchestration

Multi-agent execution is modeled as composition:

- `vidbyte.agents` contains actor objects such as `BaseAgent` and `AgentRegistry`.
- `vidbyte.strategies.multi_agent` contains orchestration topologies such as consensus routing, AutoGen-style message passing, VMAO, economic gating, and evolving policy routing.
- Custom harnesses stay outside the base SDK until their public contracts are explicitly defined.

```python
from vidbyte.strategies import BaseStrategy, StrategyResult


class FastStrategy(BaseStrategy):
    async def arun(self, prompt, **kwargs):
        return StrategyResult(output="fast answer", strategy_name="fast")


class DeepStrategy(BaseStrategy):
    async def arun(self, prompt, **kwargs):
        return StrategyResult(output="deep answer", strategy_name="deep")


strategy = FastStrategy()
result = await strategy.arun("Solve this task", runner=my_runner)
```

For custom agents, pass an explicit `system_prompt`, optional reasoning strategy, runner, and tools into `Agent` or `BaseAgent`; then pass those agents into multi-agent strategies.
Semantic labels such as roles belong in agent metadata when callers need them.

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
)

reply = await agent.arun("Find where tools are formatted.")
```

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
python -c "from vidbyte import Agent, Tools, tool; print(Agent.__name__, Tools.__name__, callable(tool))"
```
