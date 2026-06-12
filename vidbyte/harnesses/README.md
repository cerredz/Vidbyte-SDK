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

## Usage

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
harnesses = sdk.harnesses
print(type(harnesses).__name__)
```

## Key Modules

- `client.py`: `HarnessClient`, currently a namespace marker.
- `__init__.py`: public export for the harness namespace.

## Related Layers

Harness integrations will usually compose [`agents`](../agents/README.md),
[`tools`](../tools/README.md), and [`mcp_server`](../mcp_server/README.md).
