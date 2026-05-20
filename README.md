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
|-- harnesses/
|   `-- client.py
|-- providers/
|   `-- client.py
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
    `-- errors/
```

## Public Boundary

The SDK should contain reusable public namespace scaffolding and developer-facing abstractions.

Private Vidbyte service implementations, proprietary learning evaluations, prompts, scoring logic, adaptive sequencing, and database access should stay outside this package.

## Local Verification

```bash
python -m compileall vidbyte
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.harnesses).__name__)"
```
