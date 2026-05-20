# Vidbyte SDK

`vidbyte-sdk` is the root-level home for Vidbyte's Python SDK surface.

This package is intentionally minimal right now. It establishes the SDK package identity and namespace layout without including private Vidbyte service logic.

## Status

This package is not published. It is marked `UNLICENSED` until Vidbyte's release, licensing, and open-source strategy are finalized.

## Usage

```python
from vidbyte import VidbyteSDK, vidbyte_tool

sdk = VidbyteSDK()
sdk.harnesses
sdk.tools
sdk.providers
```

## Custom Function Tools

Any typed Python function can become a Vidbyte tool with `@vidbyte_tool`.
The SDK reads the function signature and docstring, generates JSON Schema,
validates runtime arguments with Pydantic, and returns a normalized tool result.

```python
from vidbyte import vidbyte_tool
from vidbyte.strategies import ReActStrategy


@vidbyte_tool
async def fetch_user_metrics(user_id: int, metric_type: str = "engagement") -> str:
    """Fetches real-time performance metrics for a specific user ID."""
    return f"Metrics for {user_id}: 94%"


registry = sdk.tools.with_tools([fetch_user_metrics]).tool_registry
print(registry.specs_as_prompt_str())

harness = (
    sdk.harnesses.base()
    .with_strategy(ReActStrategy())
    .with_tools([fetch_user_metrics])
)
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
|   |-- decorators.py
|   |-- function_tool.py
|   |-- registry.py
|   `-- executor.py
|-- strategies/
|   `-- react.py
|-- shared/
`-- lib/
    `-- errors/
```

## Public Boundary

The SDK should contain reusable public namespace scaffolding and developer-facing abstractions.

Private Vidbyte service implementations, proprietary learning evaluations, prompts, scoring logic, adaptive sequencing, and database access should stay outside this package.

## Local Verification

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.harnesses).__name__)"
```
