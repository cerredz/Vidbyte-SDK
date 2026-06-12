# Harnesses

The Vidbyte SDK reserves `vidbyte.harnesses` as the namespace for adapting SDK
abstractions into external execution harnesses.

## Role In The SDK

`vidbyte.harnesses` currently exposes `HarnessClient` through
`VidbyteSDK().harnesses`. It is intentionally minimal: it marks where future
custom harness integration helpers belong without mixing those concerns into
agents, tools, providers, or evals.

## Design Philosophy

Harness integration should stay at the boundary of the SDK. Core abstractions
should remain usable in ordinary Python code, while harness-specific launch,
configuration, or discovery behavior can live behind this namespace when those
contracts become stable.

## Vidbyte Website

This namespace supports the SDK architecture used to power agents on the
[Vidbyte website](https://vidbyte.pro). As website and external harness needs
diverge, this layer is the intended place for stable harness adapters rather
than one-off integration code inside agent or tool modules.

## Usage

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
harnesses = sdk.harnesses
print(type(harnesses).__name__)
```

Keep application code pointed at the namespace boundary even before concrete
helpers are added:

```python
def configure_harnesses(sdk: VidbyteSDK) -> None:
    harness_client = sdk.harnesses
    assert type(harness_client).__name__ == "HarnessClient"
```

## Feature Coverage

- `HarnessClient` as the current namespace client exposed by `VidbyteSDK`.
- A stable package location for future adapters that connect Vidbyte agents to external harnesses.
- Explicit separation from agent execution, tool execution, provider configuration, and MCP serving.
- A documentation boundary that tells contributors not to bury harness-specific behavior in unrelated layers.

## Key Modules

- `client.py`: `HarnessClient`, currently a namespace marker.
- `__init__.py`: public export for the harness namespace.

## Related Layers

Harness integrations will usually compose [`agents`](../agents/README.md),
[`tools`](../tools/README.md), and [`mcp_server`](../mcp_server/README.md).
