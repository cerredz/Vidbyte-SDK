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

---

# External Contract

Each module here speaks one vendor's HTTP API directly: it builds the request body, sets the auth
headers, and walks the response to extract text, embeddings, or bytes. There is no vendor SDK in
between, so **the correctness of every adapter is defined entirely off-repo**. This section records
that contract so an adapter can be reviewed without leaving the repository.

> **Note on this section.** `vidbyte-sdk` is MIT-licensed and published to PyPI. Vendor
> documentation is not MIT-licensed, so the contract below is written in our own words with
> attribution rather than quoted verbatim.

> **sources:** the first-party links in the provider reference table below
> **retrieved:** 2026-08-29
> **verified_by:** every module in `vidbyte/providers/`
> **scope:** Endpoint paths, auth headers, and response usage/text extraction paths. Excludes
> per-model parameter semantics and rate limits.

## Endpoint And Auth Matrix

| Provider | Module | Auth header | Endpoints used |
| --- | --- | --- | --- |
| OpenAI | `openai.py` | `Authorization: Bearer` | `/responses` (text + SSE stream), `/images/generations`, `/videos`, `/videos/{id}`, `/audio/speech`, `/audio/transcriptions` (multipart), `/embeddings` |
| Anthropic | `anthropic.py` | `x-api-key` + `anthropic-version` | `/messages` |
| Gemini | `gemini.py` | `x-goog-api-key` | `/models/{model}:generateContent`, `/models/{model}:batchEmbedContents` |
| ElevenLabs | `elevenlabs.py` | vendor key header | `/text-to-speech/{voice_id}` |
| xAI | `xai.py` | `Authorization: Bearer` | OpenAI-compatible surface |
| OpenRouter | `openrouter.py` | `Authorization: Bearer` | OpenAI-compatible surface |
| PlayAI | `playai.py` | vendor key header | text-to-speech |
| Generic | `compatible.py` | `Authorization: Bearer` | any OpenAI-compatible endpoint |

## Official Provider Documentation

These are the current first-party references for the registered model providers.
The links provide the external contract behind the matrix above; they do not
freeze model catalogs, pricing, or rate limits in this repository.

| Provider | API overview | Contract reference |
| --- | --- | --- |
| OpenAI | [API docs](https://developers.openai.com/api/docs/) | [Responses](https://developers.openai.com/api/docs/guides/text?api-mode=responses), [embeddings](https://developers.openai.com/api/docs/guides/embeddings) |
| Anthropic | [API overview](https://docs.anthropic.com/en/api/overview) | [Messages API](https://docs.anthropic.com/en/api/messages) |
| Gemini | [Gemini API docs](https://ai.google.dev/gemini-api/docs) | [Generate content](https://ai.google.dev/api/generate-content), [embeddings](https://ai.google.dev/api/embeddings) |
| xAI | [Developer docs](https://docs.x.ai/) | [Inference API](https://docs.x.ai/developers/rest-api-reference/inference) |
| DeepSeek | [API docs](https://api-docs.deepseek.com/) | [Chat completion](https://api-docs.deepseek.com/api/create-chat-completion) |
| GLM / Z.AI | [API introduction](https://docs.z.ai/api-reference/introduction) | [Chat completion](https://docs.z.ai/api-reference/llm/chat-completion) |
| MiniMax | [Developer docs](https://platform.minimaxi.com/docs/guides/text-generation) | [Image generation](https://platform.minimaxi.com/docs/api-reference/image-generation-t2i) |
| Kimi / Moonshot | [API overview](https://platform.kimi.ai/docs/api/overview) | [Official tools](https://platform.kimi.ai/docs/guide/use-official-tools) |
| Meta Llama | [Developer resources](https://ai.meta.com/llama/get-started/) | [Llama API docs](https://llama.developer.meta.com/docs) |
| Mistral | [Documentation](https://docs.mistral.ai/) | [SDKs](https://docs.mistral.ai/resources/sdks) |
| OpenRouter | [Quickstart](https://openrouter.ai/docs/quickstart) | [API reference](https://openrouter.ai/docs/api_reference/overview) |
| ElevenLabs | [API reference](https://elevenlabs.io/docs/api-reference/introduction/) | [Text to speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert) |
| PlayAI / Play | [API reference](https://docs.play.ht/reference/) | [API quickstart](https://docs.play.ht/reference/api-getting-started) |

Two auth details are vendor-specific and neither is guessable from the code alone:

- **Anthropic requires a dated API-version header on every request.** `anthropic.py` sends
  `anthropic-version: 2023-06-01` alongside `x-api-key`. This is a pinned contract version, not a
  release date to keep current — changing it changes response shapes and must be a deliberate
  migration.
- **Gemini accepts the key as a header or a URL query parameter.** `gemini.py` uses the
  `x-goog-api-key` header specifically so the key never lands in a URL, where proxy logs, browser
  history, and error reporters would capture it. The intent comment in the file says so; preserve it.

## Google's Colon-Method REST Convention

Gemini endpoints are `/models/{model}:generateContent`, not `/models/{model}/generateContent`. The
colon is part of Google's AIP resource-method convention and is correct as written. It reads like a
typo, so it is worth knowing before "fixing" it.

## Usage Key Divergence

Every vendor reports token usage under a different key, at a different nesting level, with different
names. This is the most consequential fact in this package, because it is why `vidbyte/agents/pricing`
needs per-provider cost classes rather than one shared formula.

| Provider | Top-level key | Input field | Output field | Total field |
| --- | --- | --- | --- | --- |
| OpenAI (Responses) | `usage` | `input_tokens` | `output_tokens` | `total_tokens` |
| OpenAI (Chat Completions) | `usage` | `prompt_tokens` | `completion_tokens` | `total_tokens` |
| Anthropic | `usage` | `input_tokens` | `output_tokens` | — (not returned) |
| Gemini | **`usageMetadata`** | `promptTokenCount` | `candidatesTokenCount` | `totalTokenCount` |

Three consequences worth stating explicitly:

1. **Gemini's usage is not under `usage`.** `gemini.py` reads `parsed.get("usageMetadata")` while
   every other adapter reads `parsed.get("usage")`. A refactor that unifies the extraction path must
   special-case this, or Gemini usage silently becomes `None`.
2. **Anthropic returns no total.** Code that needs a total must compute `input + output` for
   Anthropic rather than reading a field.
3. **The Responses API renamed OpenAI's fields.** Chat Completions used
   `prompt_tokens`/`completion_tokens`; the Responses API uses `input_tokens`/`output_tokens`.
   Because `compatible.py`, `xai.py`, and `openrouter.py` target OpenAI-*compatible* surfaces, a
   vendor behind those adapters may emit either naming depending on which OpenAI API it mirrors.

### Nested Usage Details

OpenAI's Responses API nests breakdowns that matter for cost accuracy:

- `usage.input_tokens_details.cached_tokens` — prompt-cache reads, billed at a reduced rate.
  `ModelPricing` in `vidbyte/lib/registries/pricing.py` carries an optional `cache_read_per_million`
  field for exactly this.
- `usage.output_tokens_details.reasoning_tokens` — reasoning tokens. They are billed as output
  tokens and consume context, and they are **already included** in `output_tokens`. Adding them to
  `output_tokens` double-counts and overstates cost.

## Defensive Extraction

Every adapter guards the usage read:

```python
usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None
```

The `isinstance` check is not defensiveness for its own sake — nothing in this repository guarantees
the vendor's response shape, and a vendor returning `usage: null` on an error path would otherwise
propagate `None` into arithmetic downstream. Resolving to `None` matches the deliberate policy in
`pricing.py`, whose header records that unverifiable rates are omitted "so cost resolves to None
instead of a guessed number."

Keep that policy consistent: **an unknown cost is `None`, never zero.** Zero is a claim that
something was free.

## Contract Invariants

1. **Adapters are stateless per call.** Config resolves through `_config(config)`, which prefers the
   per-call config over the instance default. Do not cache mutable per-request state on the adapter.
2. **Response parsing stays injectable.** Each adapter accepts a `response_parser` so tests and
   alternate transports can substitute one. Do not construct `HttpResponseParser` inline.
3. **Transport is injected, never created.** Adapters receive a `transport` argument and must not
   build their own HTTP client.
4. **Missing config raises `ProviderConfigurationError`**, not `ValueError` or `KeyError`, and it
   carries `provider=self.provider.value`.
5. **API keys never appear in a URL.** Header auth only.

## Adding A Provider

1. Read the vendor's current API reference and record, in the tables above: base endpoint, auth
   header style, request fields sent, the response path to generated text, and the exact usage key
   names.
2. Add a `ModelProvider` enum member and register default models in
   `vidbyte/lib/registries/models.py`.
3. Add rates to `PROVIDER_PRICING` in `vidbyte/lib/registries/pricing.py` **only if verified against
   the vendor's official pricing page**, and update `PRICING_AS_OF`. Omit the model rather than
   guessing.
4. Guard usage extraction with the `isinstance` pattern above.
5. If the vendor requires a dated version header, pin it explicitly and note here why that value.
