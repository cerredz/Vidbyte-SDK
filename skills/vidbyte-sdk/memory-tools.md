<!--
Context Protocol Header

Description:
    Reference for the Vidbyte SDK memory provider tools.
Purpose:
    Helps developers attach external long-term memory providers (Cognee, Letta,
    Mem0, Supermemory, Zep) to agents as tools, and add new memory providers.
Architecture:
    - BaseMemoryTool: shared base for all memory provider tools.
    - One tool family per provider under vidbyte/tools/builtins/memory/.
Relations:
    Implementation under vidbyte/tools/builtins/memory/. Listed in
    skills/usage/available_tools.md. See skills/sdk/update-skill-files.md.
-->

# Memory Tools

Use this guide for the external memory provider tools under
`vidbyte/tools/builtins/memory/`. These tools let an agent store and retrieve
long-term memories across runs by calling a third-party memory service. Each
provider has its own tool family; all subclass `BaseMemoryTool`.

## Providers and Tools

```python
from vidbyte.tools.builtins.memory import (
    # Mem0
    Mem0AddMemoryTool, Mem0SearchMemoryTool, Mem0GetMemoriesTool, Mem0DeleteMemoryTool,
    # Zep
    ZepAddMemoryTool, ZepSearchMemoryTool, ZepGetMemoryTool, ZepDeleteSessionTool,
    # Supermemory
    SupermemoryAddMemoryTool, SupermemorySearchMemoryTool, SupermemoryDeleteMemoryTool,
    # Letta
    LettaAddArchivalMemoryTool, LettaSearchArchivalMemoryTool, LettaGetMemoryBlockTool, LettaDeleteArchivalMemoryTool,
    # Cognee
    CogneeAddTool, CogneeCognifyTool, CogneeSearchTool, CogneeDeleteTool,
)
```

| Provider | Tools |
|----------|-------|
| Mem0 | `Mem0AddMemoryTool`, `Mem0SearchMemoryTool`, `Mem0GetMemoriesTool`, `Mem0DeleteMemoryTool` |
| Zep | `ZepAddMemoryTool`, `ZepSearchMemoryTool`, `ZepGetMemoryTool`, `ZepDeleteSessionTool` |
| Supermemory | `SupermemoryAddMemoryTool`, `SupermemorySearchMemoryTool`, `SupermemoryDeleteMemoryTool` |
| Letta | `LettaAddArchivalMemoryTool`, `LettaSearchArchivalMemoryTool`, `LettaGetMemoryBlockTool`, `LettaDeleteArchivalMemoryTool` |
| Cognee | `CogneeAddTool`, `CogneeCognifyTool`, `CogneeSearchTool`, `CogneeDeleteTool` |

## Credentials and Construction

Memory tools talk to an external service, so each is constructed with the
provider's credentials (e.g. `api_key`) plus an optional `timeout_seconds`. The
shared base is `BaseMemoryTool(api_key, base_url, timeout_seconds=30.0)`; most
provider tools wrap it with a provider-specific default `base_url`, for example:

```python
add = Mem0AddMemoryTool(api_key="...", timeout_seconds=30.0)
```

Read each tool's constructor in `vidbyte/tools/builtins/memory/<provider>.py` for the
exact arguments. Never hardcode credentials in skill examples or commit secrets.

## Attaching to an Agent

```python
from vidbyte import Agent
from vidbyte.tools.builtins.memory import Mem0AddMemoryTool, Mem0SearchMemoryTool

agent = Agent(
    name="memory-agent",
    system_prompt="Use memory to remember user preferences across sessions.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[
        Mem0AddMemoryTool(api_key="..."),
        Mem0SearchMemoryTool(api_key="..."),
    ],
)
```

Because memory tools perform network I/O, set their permission level appropriately and run
them under a permission policy that allows the required level (these are not `SAFE`).

## Adding a New Memory Provider

1. Add `vidbyte/tools/builtins/memory/<provider>.py` with one tool class per operation
   (add / search / get / delete), each subclassing `BaseMemoryTool`.
2. Give each a clear `ToolSpec` (name, parameters, permission) and return
   `ToolResult.success()` / `ToolResult.error()` — never raise raw HTTP errors through the tool
   boundary.
3. Export the new classes from `vidbyte/tools/builtins/memory/__init__.py` and
   `vidbyte/tools/builtins/__init__.py`.
4. Add the provider to the table in `skills/usage/available_tools.md` and this file.
5. Add tests to `tests/test_memory_tools.py` using a fake/mocked transport — no live network.

## Verification

```powershell
python -m compileall vidbyte
python -m unittest tests.test_memory_tools
```
