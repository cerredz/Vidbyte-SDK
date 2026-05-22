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

For custom agents, pass an explicit `system_prompt`, optional reasoning strategy, runner, and tools into `BaseAgent`; then pass those agents into multi-agent strategies.
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

The SDK includes a small, explicit tool registry and executor:

```python
from vidbyte import VidbyteSDK
from vidbyte.tools.builtins.code_search import GrepTool

sdk = VidbyteSDK()
sdk.tools.register(GrepTool(root_dir="."))
```

Advanced built-ins are grouped by category:

- `vidbyte.tools.builtins.code_search`: `GlobTool`, `GrepTool`, `SemanticSearchTool`
- `vidbyte.tools.builtins.editing`: `PatchTool`
- `vidbyte.tools.builtins.context`: `ContextCompactionTool`
- `vidbyte.tools.mcp`: `McpClient`, `McpStdioTransport`, `McpBridgedTool`
- `vidbyte.tools.security`: `PermissionPolicy`, `ToolPermission`, sandbox transport protocols

The default executor allows `SAFE` and `READ` tools. Mutating or executable tools require an explicit permission policy:

```python
from vidbyte.tools.security import PermissionPolicy

sdk = VidbyteSDK()
sdk.tools.executor.permission_policy = PermissionPolicy.allow_all()
```

Provider integrations can format the same `ToolSpec` contract for model-native tool APIs:

```python
from vidbyte import ToolsFormatter

openai_tool = ToolsFormatter.to_openai_tool(sdk.tools.registry.specs()[0])
anthropic_tool = ToolsFormatter.to_anthropic_tool(sdk.tools.registry.specs()[0])
```

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
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.strategies).__name__)"
```
