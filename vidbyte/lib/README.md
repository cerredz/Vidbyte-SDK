# Lib

`vidbyte.lib` is the shared contract layer behind the Vidbyte SDK. It holds the
dataclasses, enums, registries, errors, config objects, runner helpers, tool
formatters, and tracing base classes that public packages build on.

## Role In The SDK

Application code normally starts with root imports from `vidbyte`, but `lib`
contains the common types that make those imports consistent. It centralizes
model provider enums, context and agent dataclasses, registry implementations,
provider config, transport helpers, and base tracing contracts.

## Design Philosophy

Shared contracts should have one home. Keeping these types in `lib` prevents
agents, tools, middleware, providers, and evals from redefining the same payload
shapes or error types. Public README examples should still prefer root imports
when a type is re-exported there.

## Vidbyte Website

This contract layer supports the SDK architecture used to power agents on the
[Vidbyte website](https://vidbyte.pro). Website agents rely on consistent
dataclasses, enums, registries, and error types so feature layers can evolve
without each layer inventing incompatible payload shapes.

## Usage

```python
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries import ProviderModelRegistry

default_model = ProviderModelRegistry.default_model(ModelProvider.OPENAI)
api_key_env = ProviderModelRegistry.get_api_key_env_var("openai")

print(default_model, api_key_env)
```

Resolve runtime and tool registry contracts:

```python
from vidbyte import tool
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.registries import RuntimeRegistry, ToolRegistry

@tool
def score_answer(answer: str) -> dict[str, int]:
    return {"score": len(answer)}

runtime_cls = RuntimeRegistry.resolve(AgentRuntimeType.LINEAR)
registry = ToolRegistry([score_answer])
```

## Feature Coverage

- Shared dataclasses for agents, context, middleware, tools, MCP, runners, traces, and strategy results.
- Enums for providers, modalities, prompts, platforms, permissions, and runtime types.
- Registry classes for agents, tools, prompts, providers, runtimes, and actor roles.
- SDK error classes with structured details for configuration, execution, provider, pipeline, MCP, and tool failures.
- Model config dataclasses for text, image, video, audio, and embedding providers.
- Runner handles and shared invocation contracts.
- Tool schema formatting and provider-specific tool translation.
- Tracing base classes and the null tracer.

## Key Modules

- `dataclasses/`: shared payloads for agents, context, tools, middleware, runners, traces, and strategies.
- `enums/`: model providers, modalities, permissions, prompts, platforms, and runtime choices.
- `registries/`: agent, provider, runtime, prompt, tool, and actor registries.
- `errors/`: SDK-specific exception types.
- `runners/`: runner handles and model runner helpers.
- `tools/`: provider-specific tool schema formatting.
- `tracing/`: tracer base classes and null tracer.

## Related Layers

`lib` supports every public layer, especially [`agents`](../agents/README.md),
[`tools`](../tools/README.md), [`providers`](../providers/README.md), and
[`middleware`](../middleware/README.md).
