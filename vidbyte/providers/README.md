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

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website agents may need different model
vendors or modalities behind the same agent surface; provider adapters keep that
selection explicit and testable.

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

Select another capability when the model output is not plain text:

```python
from vidbyte.lib.config import ImageModelConfig
from vidbyte.providers import ModelProviders

image_provider = ModelProviders.image(
    ImageModelConfig(provider=ModelProvider.OPENAI, model="gpt-image-1")
)
```

## Feature Coverage

- Text, image, video, audio, embedding, and streaming text provider factories.
- OpenAI, Anthropic, Gemini, xAI, OpenRouter, DeepSeek, GLM, MiniMax, ElevenLabs, and PlayAI adapter exports where supported.
- Provider capability validation through `ProviderSelectionError`.
- Provider schema conversion for OpenAI-style, Anthropic, and Gemini tool declarations.
- Model configuration dataclasses from `vidbyte.lib.config`.
- Provider-backed tracing adapters under `vidbyte.providers.tracing`.
- Compatibility providers for OpenAI-compatible APIs.

## Key Modules

- `__init__.py`: provider factory and public adapter exports.
- `base.py`: provider schema translation helpers.
- `openai.py`, `anthropic.py`, `gemini.py`, `xai.py`, `openrouter.py`, `compatible.py`: provider adapters.
- `tracing/`: provider-backed trace adapters.

## Related Layers

Providers are selected by [`agents`](../agents/README.md), use tool schemas from
[`tools`](../tools/README.md), and can emit traces through [`trace`](../trace/README.md).
