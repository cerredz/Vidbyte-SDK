# Providers

Providers in the Vidbyte SDK adapt model vendor APIs into SDK runner behavior.
They keep model-specific request, response, modality, and tool-schema handling
behind a common provider selection layer.

## Role In The SDK

`vidbyte.providers` exposes provider adapter classes and the `ModelProviders`
factory. It can resolve adapters for text, image, video, audio, embeddings, and
streaming text. The layer also translates Vidbyte tool specs into provider-facing
schema shapes.

## Design Philosophy

Provider support should be selected by capability and model provider, not by
scattering vendor conditionals throughout agents and tools. Unsupported
capability/provider pairs should fail early through provider-selection errors.
Credentials should come from caller configuration or environment variables, not
from hardcoded examples.

## Usage

```python
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.providers import ModelProviders

config = TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4.1")
provider = ModelProviders.text(config)
```

Translate a tool spec for a provider:

```python
from vidbyte.providers import tool_spec_to_provider_schema

schema = tool_spec_to_provider_schema(lookup_metric.spec(), "openai")
```

## Key Modules

- `__init__.py`: provider factory and public adapter exports.
- `base.py`: provider schema translation helpers.
- `openai.py`, `anthropic.py`, `gemini.py`, `xai.py`, `openrouter.py`, `compatible.py` (DeepSeek, GLM, MiniMax, Kimi, Mistral): provider adapters.
- `tracing/`: provider-backed trace adapters.

## Related Layers

Providers are selected by [`agents`](../agents/README.md), use tool schemas from
[`tools`](../tools/README.md), and can emit traces through [`trace`](../trace/README.md).
