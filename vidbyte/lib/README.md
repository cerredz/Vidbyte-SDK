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

## Usage

```python
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries import ProviderModelRegistry

default_model = ProviderModelRegistry.default_model(ModelProvider.OPENAI)
api_key_env = ProviderModelRegistry.get_api_key_env_var("openai")

print(default_model, api_key_env)
```

## Key Modules

- `dataclasses/`: shared payloads for agents, context, tools, middleware, runners, traces, and strategies.
- `enums/`: model providers, permissions, prompts, platforms, and runtime choices.
- `constants/`: shared SDK constants, including model/provider-to-runner mappings.
- `registries/`: agent, provider, runtime, prompt, tool, actor, and declarable-component registries.
- `errors/`: SDK-specific exception types.
- `runners/`: runner handles, concrete model runners, and runner inference helpers.
- `tools/`: provider-specific tool schema formatting.
- `tracing/`: tracer base classes and null tracer.

## Related Layers

`lib` supports every public layer, especially [`agents`](../agents/README.md),
[`tools`](../tools/README.md), [`providers`](../providers/README.md), and
[`middleware`](../middleware/README.md).
