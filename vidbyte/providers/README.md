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

### Expanded provider reading maps

The short matrix above is the contract index. These larger, provider-specific
maps are the practical lookup surface for agents and maintainers. They are
intentionally grouped by provider so a stale endpoint, SDK assumption, or model
capability can be checked against the vendor's current quickstart, reference,
and operations pages without searching the entire web. **Retrieved:** 2026-08-29.

#### OpenAI

- [API documentation](https://developers.openai.com/api/docs)
- [Key concepts](https://developers.openai.com/api/docs/concepts)
- [SDKs and CLI](https://developers.openai.com/api/docs/libraries)
- [API reference overview](https://developers.openai.com/api/reference/overview)
- [Python API reference](https://developers.openai.com/api/reference/python)
- [Responses text generation](https://developers.openai.com/api/docs/guides/text?api-mode=responses)
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Streaming responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [Embeddings](https://developers.openai.com/api/docs/guides/embeddings)
- [File inputs](https://developers.openai.com/api/docs/guides/file-inputs)
- [Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use)
- [Deep research](https://developers.openai.com/api/docs/guides/deep-research)
- [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations)
- [Realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription)
- [Text to speech](https://developers.openai.com/api/docs/guides/text-to-speech)
- [Reasoning models](https://developers.openai.com/api/docs/guides/reasoning)
- [Reasoning best practices](https://developers.openai.com/api/docs/guides/reasoning-best-practices)
- [Model optimization](https://developers.openai.com/api/docs/guides/model-optimization)
- [Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
- [Rate limits](https://developers.openai.com/api/docs/guides/rate-limits)
- [Production best practices](https://developers.openai.com/api/docs/guides/production-best-practices)
- [Pricing](https://developers.openai.com/api/docs/pricing)
- [Data controls](https://developers.openai.com/api/docs/guides/your-data)
- [Supervised fine-tuning](https://developers.openai.com/api/docs/guides/supervised-fine-tuning)

#### Anthropic

- [Claude platform home](https://platform.claude.com/docs/en/home)
- [Get started](https://platform.claude.com/docs/en/get-started)
- [API overview](https://platform.claude.com/docs/en/api/overview)
- [Client SDKs](https://platform.claude.com/docs/en/api/client-sdks)
- [Messages API](https://platform.claude.com/docs/en/api/messages)
- [Create a message](https://platform.claude.com/docs/en/api/messages/create)
- [Message batches](https://platform.claude.com/docs/en/api/messages/batches)
- [Models API](https://platform.claude.com/docs/en/api/models)
- [List models](https://platform.claude.com/docs/en/api/models/list)
- [API errors](https://platform.claude.com/docs/en/api/errors)
- [Rate limits](https://platform.claude.com/docs/en/api/rate-limits)
- [Build with Claude overview](https://platform.claude.com/docs/en/build-with-claude/overview)
- [Prompt engineering overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview)
- [Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [Tool use overview](https://platform.claude.com/docs/en/build-with-claude/tool-use)
- [Implement tool use](https://platform.claude.com/docs/en/build-with-claude/tool-use/implement-tool-use)
- [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- [PDF support](https://platform.claude.com/docs/en/build-with-claude/pdf-support)
- [Citations](https://platform.claude.com/docs/en/build-with-claude/citations)
- [Computer use](https://platform.claude.com/docs/en/build-with-claude/computer-use)
- [Extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)
- [Streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Test and evaluate overview](https://platform.claude.com/docs/en/test-and-evaluate/overview)

#### Gemini

- [Gemini API documentation](https://ai.google.dev/gemini-api/docs)
- [Quickstart](https://ai.google.dev/gemini-api/docs/quickstart)
- [API keys](https://ai.google.dev/gemini-api/docs/api-key)
- [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- [Generate content API](https://ai.google.dev/api/generate-content)
- [Function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [Thinking](https://ai.google.dev/gemini-api/docs/thinking)
- [Embeddings](https://ai.google.dev/gemini-api/docs/embeddings)
- [Files](https://ai.google.dev/gemini-api/docs/files)
- [File search](https://ai.google.dev/gemini-api/docs/file-search)
- [Document processing](https://ai.google.dev/gemini-api/docs/document-processing)
- [Image generation](https://ai.google.dev/gemini-api/docs/image-generation)
- [Imagen](https://ai.google.dev/gemini-api/docs/imagen)
- [Veo](https://ai.google.dev/gemini-api/docs/veo)
- [Speech generation](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Transcription](https://ai.google.dev/gemini-api/docs/transcribe)
- [Live API](https://ai.google.dev/gemini-api/docs/live-api)
- [Live API quickstart](https://ai.google.dev/gemini-api/docs/live-api/get-started)
- [Live API WebSocket quickstart](https://ai.google.dev/gemini-api/docs/live-api/get-started-websocket)
- [Live API tools](https://ai.google.dev/gemini-api/docs/live-api/tools)
- [Live API ephemeral tokens](https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens)
- [Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search)
- [Computer use](https://ai.google.dev/gemini-api/docs/computer-use)
- [Batch API](https://ai.google.dev/gemini-api/docs/batch-api)
- [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Models](https://ai.google.dev/gemini-api/docs/models)
- [Migration guidance](https://ai.google.dev/gemini-api/docs/migrate)

#### xAI

- [Developer documentation](https://docs.x.ai)
- [Developer quickstart](https://docs.x.ai/developers/quickstart)
- [Models](https://docs.x.ai/developers/models)
- [Inference API](https://docs.x.ai/developers/rest-api-reference/inference)
- [Chat inference](https://docs.x.ai/developers/rest-api-reference/inference/chat)
- [Batch inference](https://docs.x.ai/developers/rest-api-reference/inference/batches)
- [Voice inference](https://docs.x.ai/developers/rest-api-reference/inference/voice)
- [Video inference](https://docs.x.ai/developers/rest-api-reference/inference/videos)
- [Function calling](https://docs.x.ai/developers/tools/function-calling)
- [Tools overview](https://docs.x.ai/developers/tools/overview)
- [Remote MCP](https://docs.x.ai/developers/tools/remote-mcp)
- [Web search](https://docs.x.ai/developers/tools/web-search)
- [X search](https://docs.x.ai/developers/tools/x-search)
- [Tool usage details](https://docs.x.ai/developers/tools/tool-usage-details)
- [Streaming](https://docs.x.ai/developers/model-capabilities/text/streaming)
- [Asynchronous requests](https://docs.x.ai/developers/advanced-api-usage/async)
- [WebSocket mode](https://docs.x.ai/developers/advanced-api-usage/websocket-mode)
- [Prompt caching](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/best-practices)
- [Files overview](https://docs.x.ai/developers/files)
- [Upload files](https://docs.x.ai/developers/rest-api-reference/files/upload)
- [Download files](https://docs.x.ai/developers/rest-api-reference/files/download)
- [Public file URLs](https://docs.x.ai/developers/files/public-urls)
- [Collections search](https://docs.x.ai/developers/rest-api-reference/collections/search)
- [Management API](https://docs.x.ai/developers/rest-api-reference/management)
- [Audit API](https://docs.x.ai/developers/rest-api-reference/management/audit)
- [Rate limits](https://docs.x.ai/developers/rate-limits)
- [Cost tracking](https://docs.x.ai/developers/cost-tracking)
- [Debugging](https://docs.x.ai/developers/debugging)

#### DeepSeek

- [API documentation](https://api-docs.deepseek.com)
- [First API call](https://api-docs.deepseek.com/quick_start/first_api_call)
- [API overview](https://api-docs.deepseek.com/api/deepseek-api)
- [Chat completion](https://api-docs.deepseek.com/api/create-chat-completion)
- [Responses API](https://api-docs.deepseek.com/api/create-response)
- [Function calling](https://api-docs.deepseek.com/guides/function_calling)
- [Tool calling](https://api-docs.deepseek.com/guides/tool_calling)
- [JSON output](https://api-docs.deepseek.com/guides/json_mode)
- [Thinking mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [Thinking mode streaming example](https://api-docs.deepseek.com/guides/thinking_mode_api_example_streaming)
- [Vision](https://api-docs.deepseek.com/guides/vision)
- [Multi-turn conversation](https://api-docs.deepseek.com/guides/multi_turn_conversation)
- [Prompt caching](https://api-docs.deepseek.com/guides/prompt_caching)
- [Context caching](https://api-docs.deepseek.com/guides/context_caching_on_deepseek)
- [KV cache](https://api-docs.deepseek.com/guides/kv_cache)
- [Prefix caching](https://api-docs.deepseek.com/guides/prefix_caching)
- [Batch API](https://api-docs.deepseek.com/guides/batch_api)
- [Files API](https://api-docs.deepseek.com/guides/files_api)
- [Anthropic compatibility](https://api-docs.deepseek.com/guides/anthropic_api)
- [Usage](https://api-docs.deepseek.com/guides/usage)
- [Token usage](https://api-docs.deepseek.com/quick_start/token_usage)
- [Parameter settings](https://api-docs.deepseek.com/quick_start/parameter_settings)
- [Rate limits](https://api-docs.deepseek.com/quick_start/rate_limit)
- [Pricing](https://api-docs.deepseek.com/quick_start/pricing)
- [Pricing details](https://api-docs.deepseek.com/quick_start/pricing-details)
- [Error codes](https://api-docs.deepseek.com/quick_start/error_codes)
- [Models](https://api-docs.deepseek.com/quick_start/models)
- [OpenAPI JSON](https://api-docs.deepseek.com/openapi.json)

#### GLM / Z.AI

- [API introduction](https://docs.z.ai/api-reference/introduction)
- [API code](https://docs.z.ai/api-reference/api-code)
- [Chat completion](https://docs.z.ai/api-reference/llm/chat-completion)
- [HTTP development](https://docs.z.ai/guides/develop/http/introduction)
- [OpenAI Python guide](https://docs.z.ai/guides/develop/openai/python)
- [Overview quickstart](https://docs.z.ai/guides/overview/quick-start)
- [Concepts and parameters](https://docs.z.ai/guides/overview/concept-param)
- [Streaming](https://docs.z.ai/guides/capabilities/streaming)
- [Structured output](https://docs.z.ai/guides/capabilities/struct-output)
- [Thinking](https://docs.z.ai/guides/capabilities/thinking)
- [Thinking mode](https://docs.z.ai/guides/capabilities/thinking-mode)
- [Vision](https://docs.z.ai/guides/capabilities/vision)
- [Cache](https://docs.z.ai/guides/capabilities/cache)
- [Web search](https://docs.z.ai/guides/tools/web-search)
- [Web search API](https://docs.z.ai/api-reference/tools/web-search)
- [Layout parsing](https://docs.z.ai/api-reference/tools/layout-parsing)
- [Video generation](https://docs.z.ai/api-reference/video/generate-video)
- [GLM-4.5](https://docs.z.ai/guides/llm/glm-4.5)
- [GLM-4.6](https://docs.z.ai/guides/llm/glm-4.6)
- [GLM-5](https://docs.z.ai/guides/llm/glm-5)
- [GLM-5.1](https://docs.z.ai/guides/llm/glm-5.1)
- [GLM-5.2](https://docs.z.ai/guides/llm/glm-5.2)
- [GLM-5.3](https://docs.z.ai/guides/llm/glm-5.3)
- [GLM-5.3 Flash VLM](https://docs.z.ai/guides/vlm/glm-5.3-flash)
- [Development best practices](https://docs.z.ai/devpack/resources/best-practice)
- [DevPack overview](https://docs.z.ai/devpack/overview)
- [DevPack quickstart](https://docs.z.ai/devpack/quick-start)
- [MCP reader server](https://docs.z.ai/devpack/mcp/reader-mcp-server)
- [MCP search server](https://docs.z.ai/devpack/mcp/search-mcp-server)
- [Usage policy](https://docs.z.ai/devpack/usage-policy)

#### MiniMax

- [API overview](https://platform.minimaxi.com/docs/api-reference/api-overview)
- [Text generation](https://platform.minimaxi.com/docs/guides/text-generation)
- [Text API](https://platform.minimaxi.com/docs/api-reference/text-post)
- [OpenAI-compatible text API](https://platform.minimaxi.com/docs/api-reference/text-openai-api)
- [OpenAI-compatible chat](https://platform.minimaxi.com/docs/api-reference/text-chat-openai)
- [Anthropic-compatible text API](https://platform.minimaxi.com/docs/api-reference/text-anthropic-api)
- [Anthropic-compatible chat](https://platform.minimaxi.com/docs/api-reference/text-chat-anthropic)
- [Responses API](https://platform.minimaxi.com/docs/api-reference/responses-create)
- [Input token counting](https://platform.minimaxi.com/docs/api-reference/responses-input-tokens)
- [Prompt caching](https://platform.minimaxi.com/docs/api-reference/text-prompt-caching)
- [List OpenAI models](https://platform.minimaxi.com/docs/api-reference/models/openai/list-models)
- [Retrieve OpenAI model](https://platform.minimaxi.com/docs/api-reference/models/openai/retrieve-model)
- [List Anthropic models](https://platform.minimaxi.com/docs/api-reference/models/anthropic/list-models)
- [Retrieve Anthropic model](https://platform.minimaxi.com/docs/api-reference/models/anthropic/retrieve-model)
- [Image generation text-to-image](https://platform.minimaxi.com/docs/api-reference/image-generation-t2i)
- [Image generation image-to-image](https://platform.minimaxi.com/docs/api-reference/image-generation-i2i)
- [Video generation text-to-video](https://platform.minimaxi.com/docs/api-reference/video-generation-t2v)
- [Video generation image-to-video](https://platform.minimaxi.com/docs/api-reference/video-generation-i2v)
- [Video generation query](https://platform.minimaxi.com/docs/api-reference/video-generation-query)
- [Speech HTTP](https://platform.minimaxi.com/docs/api-reference/speech-t2a-http)
- [Speech WebSocket](https://platform.minimaxi.com/docs/api-reference/speech-t2a-websocket)
- [Async speech create](https://platform.minimaxi.com/docs/api-reference/speech-t2a-async-create)
- [Async speech query](https://platform.minimaxi.com/docs/api-reference/speech-t2a-async-query)
- [Voice cloning](https://platform.minimaxi.com/docs/api-reference/voice-cloning-clone)
- [Voice management](https://platform.minimaxi.com/docs/api-reference/voice-management-get)
- [File upload](https://platform.minimaxi.com/docs/api-reference/file-management-upload)
- [File list](https://platform.minimaxi.com/docs/api-reference/file-management-list)
- [File retrieve](https://platform.minimaxi.com/docs/api-reference/file-management-retrieve)
- [Error codes](https://platform.minimaxi.com/docs/api-reference/errorcode)
- [MCP guide](https://platform.minimaxi.com/docs/guides/mcp-guide)

#### Kimi / Moonshot

- [API overview](https://platform.kimi.ai/docs/api/overview)
- [Models overview](https://platform.kimi.ai/docs/api/models-overview)
- [List models](https://platform.kimi.ai/docs/api/list-models)
- [Chat API](https://platform.kimi.ai/docs/api/chat)
- [API errors](https://platform.kimi.ai/docs/api/errors)
- [Balance](https://platform.kimi.ai/docs/api/balance)
- [Token estimate](https://platform.kimi.ai/docs/api/estimate)
- [Batch create](https://platform.kimi.ai/docs/api/batch-create)
- [Batch retrieve](https://platform.kimi.ai/docs/api/batch-retrieve)
- [Batch list](https://platform.kimi.ai/docs/api/batch-list)
- [Batch cancel](https://platform.kimi.ai/docs/api/batch-cancel)
- [Files API](https://platform.kimi.ai/docs/api/files)
- [Upload files](https://platform.kimi.ai/docs/api/files-upload)
- [List files](https://platform.kimi.ai/docs/api/files-list)
- [Retrieve file](https://platform.kimi.ai/docs/api/files-retrieve)
- [File content](https://platform.kimi.ai/docs/api/files-content)
- [Delete file](https://platform.kimi.ai/docs/api/files-delete)
- [Response format](https://platform.kimi.ai/docs/guide/response_format)
- [Prompt best practices](https://platform.kimi.ai/docs/guide/prompt-best-practice)
- [Tool calling](https://platform.kimi.ai/docs/guide/use-kimi-api-to-complete-tool-calls)
- [Official tools](https://platform.kimi.ai/docs/guide/use-official-tools)
- [Multi-turn conversations](https://platform.kimi.ai/docs/guide/engage-in-multi-turn-conversations-using-kimi-api)
- [Context caching](https://platform.kimi.ai/docs/guide/use-context-caching-feature-of-kimi-api)
- [JSON mode](https://platform.kimi.ai/docs/guide/use-json-mode-feature-of-kimi-api)
- [Batch API guide](https://platform.kimi.ai/docs/guide/use-batch-api)
- [Auto reconnect](https://platform.kimi.ai/docs/guide/auto-reconnect)
- [Account and payments](https://platform.kimi.ai/docs/guide/account-and-payments)
- [Troubleshooting](https://platform.kimi.ai/docs/guide/troubleshooting)
- [Kimi code quickstart](https://platform.kimi.ai/docs/guide/kimi-code-cli)

#### Meta Llama

Meta distributes Llama through several official surfaces rather than one
single hosted API reference. These links cover the model cards, prompt formats,
reference implementations, and official cookbook paths used when a compatible
provider is configured.

- [Llama developer resources](https://ai.meta.com/llama/get-started/)
- [Llama responsible-use guide](https://ai.meta.com/llama/responsible-use-guide/)
- [Meta Llama GitHub organization](https://github.com/meta-llama)
- [Llama models repository](https://github.com/meta-llama/llama-models)
- [Llama models README](https://github.com/meta-llama/llama-models/blob/main/README.md)
- [Llama 4 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama4/MODEL_CARD.md)
- [Llama 4 prompt format](https://github.com/meta-llama/llama-models/blob/main/models/llama4/prompt_format.md)
- [Llama 3.3 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/MODEL_CARD.md)
- [Llama 3.3 prompt format](https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/prompt_format.md)
- [Llama 3.2 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD.md)
- [Llama 3.2 prompt format](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/prompt_format.md)
- [Llama 3.1 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md)
- [Llama 3.1 prompt format](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/prompt_format.md)
- [Llama 3 model card](https://github.com/meta-llama/llama3/blob/main/MODEL_CARD.md)
- [Llama 2 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama2/MODEL_CARD.md)
- [Llama cookbook](https://github.com/meta-llama/llama-cookbook)
- [Cookbook getting started](https://github.com/meta-llama/llama-cookbook/tree/main/getting-started)
- [Cookbook inference recipes](https://github.com/meta-llama/llama-cookbook/tree/main/getting-started/inference)
- [Cookbook fine-tuning recipes](https://github.com/meta-llama/llama-cookbook/tree/main/fine-tuning)
- [Cookbook RAG recipes](https://github.com/meta-llama/llama-cookbook/tree/main/getting-started/RAG)
- [Local inference guide](https://github.com/meta-llama/llama-cookbook/tree/main/getting-started/inference/local_inference)
- [Prompt Ops](https://github.com/meta-llama/prompt-ops)
- [Llama reference implementation](https://github.com/meta-llama/llama)
- [Llama 3 reference examples](https://github.com/meta-llama/llama3)
- [Llama Guard](https://github.com/meta-llama/Llama-Guard)
- [Llama Stack](https://github.com/meta-llama/llama-stack)

#### Mistral

- [Mistral documentation](https://docs.mistral.ai)
- [API overview](https://docs.mistral.ai/api)
- [First API request](https://docs.mistral.ai/getting-started/quickstarts/developer/first-api-request)
- [Activate an API key](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key)
- [Python and other SDKs](https://docs.mistral.ai/resources/sdks)
- [Model catalog](https://docs.mistral.ai/models)
- [Model selection guide](https://docs.mistral.ai/inference/model-selection-guide)
- [Inference deployment](https://docs.mistral.ai/inference/deployment)
- [Prompting](https://docs.mistral.ai/inference/prompting)
- [Priority tier](https://docs.mistral.ai/inference/priority-tier)
- [Regional inference](https://docs.mistral.ai/inference/regional-inference)
- [Chat endpoint](https://docs.mistral.ai/api/endpoint/chat)
- [Batch endpoint](https://docs.mistral.ai/api/endpoint/batch)
- [OCR endpoint](https://docs.mistral.ai/api/endpoint/ocr)
- [Audio voices](https://docs.mistral.ai/api/endpoint/audio/voices)
- [Studio](https://docs.mistral.ai/studio)
- [Studio batch processing](https://docs.mistral.ai/studio/batch-processing)
- [Studio agent tools](https://docs.mistral.ai/studio/agents/agent-tools/websearch)
- [Studio connectors](https://docs.mistral.ai/studio/connectors/conversations)
- [Studio tool calling](https://docs.mistral.ai/studio/connectors/tool_calling)
- [Studio audio overview](https://docs.mistral.ai/studio/audio/overview)
- [Speech to text](https://docs.mistral.ai/studio/audio/speech_to_text)
- [Realtime transcription](https://docs.mistral.ai/studio/audio/speech_to_text/realtime_transcription)
- [Text to speech](https://docs.mistral.ai/studio/audio/text_to_speech)
- [Admin authentication](https://docs.mistral.ai/admin/admin-api/authentication)
- [API keys](https://docs.mistral.ai/admin/identity-access/api-keys)
- [Usage limits](https://docs.mistral.ai/admin/billing-usage/usage-limits)
- [Privacy and data controls](https://docs.mistral.ai/admin/monitor-comply/privacy-data-controls)
- [Zero data retention](https://docs.mistral.ai/admin/monitor-comply/zero-data-retention)

#### OpenRouter

- [Quickstart](https://openrouter.ai/docs/quickstart)
- [API reference overview](https://openrouter.ai/docs/api_reference/overview)
- [Basic Responses API usage](https://openrouter.ai/docs/api_reference/responses/basic-usage)
- [Create a response](https://openrouter.ai/docs/api/api-reference/responses/create-a-response)
- [Create a chat completion](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion)
- [Get a model](https://openrouter.ai/docs/api/api-reference/models/get-a-model-by-its-slug)
- [List providers](https://openrouter.ai/docs/api/api-reference/providers/list-all-providers)
- [Generation usage metadata](https://openrouter.ai/docs/api/api-reference/generations/get-request-%26-usage-metadata-for-a-generation)
- [Upload a file](https://openrouter.ai/docs/api/api-reference/files/upload-a-file)
- [Submit a rerank request](https://openrouter.ai/docs/api/api-reference/rerank/submit-a-rerank-request)
- [Batch quickstart](https://openrouter.ai/docs/batch-quickstart)
- [API limits](https://openrouter.ai/docs/api_reference/limits)
- [Latency and performance](https://openrouter.ai/docs/guides/best-practices/latency-and-performance)
- [Prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
- [Reasoning tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
- [Files API guide](https://openrouter.ai/docs/guides/features/files-api)
- [Usage for agents](https://openrouter.ai/docs/client-sdks/usage-for-agents)
- [Python SDK examples](https://openrouter.ai/docs/client-sdks/python)
- [API key rotation cookbook](https://openrouter.ai/docs/cookbook/administration/api-key-rotation)
- [Usage accounting cookbook](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [Sentry broadcast integration](https://openrouter.ai/docs/guides/features/broadcast/sentry)
- [Model migrations](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/model-migrations/gpt-5-6)
- [Video generation cookbook](https://openrouter.ai/docs/cookbook/video-generation/image-to-video)
- [Anthropic agent SDK guide](https://openrouter.ai/docs/guides/community/anthropic-agent-sdk)
- [Provider guide](https://openrouter.ai/docs/guides/community/for-providers)
- [Models API key management](https://openrouter.ai/docs/api/api-reference/api-keys/list-api-keys)
- [OAuth exchange](https://openrouter.ai/docs/api/api-reference/oauth/exchange-authorization-code-for-api-key)
- [Analytics query](https://openrouter.ai/docs/api/api-reference/analytics/query-analytics-data)
- [Presets](https://openrouter.ai/docs/api/api-reference/presets/list-presets)
- [Observability destinations](https://openrouter.ai/docs/api/api-reference/observability/create-an-observability-destination)

#### ElevenLabs

- [API introduction](https://elevenlabs.io/docs/api-reference/introduction/)
- [API authentication](https://elevenlabs.io/docs/api-reference/authentication)
- [Text to speech overview](https://elevenlabs.io/docs/overview/capabilities/text-to-speech)
- [Create speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
- [Speech generation flow](https://elevenlabs.io/docs/api-reference/flows/text-to-speech/create)
- [Text to speech quickstart](https://elevenlabs.io/docs/eleven-api/guides/cookbooks/text-to-speech/)
- [Text to speech audio streaming](https://elevenlabs.io/docs/eleven-api/concepts/audio-streaming)
- [Models](https://elevenlabs.io/docs/api-reference/models/get-all)
- [Voices](https://elevenlabs.io/docs/api-reference/voices/get-all)
- [Voice settings](https://elevenlabs.io/docs/api-reference/voices/settings/get)
- [Update voice settings](https://elevenlabs.io/docs/api-reference/voices/settings/update)
- [Voice cloning](https://elevenlabs.io/docs/api-reference/voices/add)
- [Pronunciation dictionaries](https://elevenlabs.io/docs/api-reference/pronunciation-dictionaries/create-from-file)
- [History](https://elevenlabs.io/docs/api-reference/history/get)
- [Delete history](https://elevenlabs.io/docs/api-reference/history/delete)
- [Sound effects](https://elevenlabs.io/docs/api-reference/sound-generation)
- [Music composition](https://elevenlabs.io/docs/api-reference/music/compose)
- [Speech to text](https://elevenlabs.io/docs/capabilities/speech-to-text)
- [Dubbing](https://elevenlabs.io/docs/capabilities/dubbing)
- [Conversational AI](https://elevenlabs.io/docs/conversational-ai/overview)
- [Conversational AI WebSocket](https://elevenlabs.io/docs/conversational-ai/api-reference/conversational-ai/websocket)
- [Knowledge base RAG](https://elevenlabs.io/docs/conversational-ai/customization/knowledge-base/rag)
- [Custom tools](https://elevenlabs.io/docs/conversational-ai/customization/tools)
- [MCP tools](https://elevenlabs.io/docs/eleven-agents/customization/tools/mcp)
- [Agents quickstart](https://elevenlabs.io/docs/eleven-agents/guides/quickstarts/next-js)
- [Agents authentication](https://elevenlabs.io/docs/eleven-agents/customization/authentication)
- [Agent events](https://elevenlabs.io/docs/eleven-agents/customization/events/client-events)
- [Agent workspace](https://elevenlabs.io/docs/eleven-agents/api-reference/workspace/get)
- [API errors](https://elevenlabs.io/docs/eleven-api/resources/errors)

#### PlayAI / PlayHT

- [API reference](https://docs.play.ht/reference/)
- [Quickstart](https://docs.play.ht/reference/api-getting-started)
- [Authentication](https://docs.play.ht/reference/authentication)
- [Models](https://docs.play.ht/reference/models)
- [Prebuilt voices](https://docs.play.ht/reference/list-of-prebuilt-voices)
- [Generate streaming TTS](https://docs.play.ht/reference/api-generate-tts-audio-stream)
- [TTS WebSocket API](https://docs.play.ht/reference/playht-tts-websocket-api)
- [Create batch TTS](https://docs.play.ht/reference/api-create-batch-tts)
- [Get batch TTS job](https://docs.play.ht/reference/api-get-batch-tts-job)
- [Get batch child job by ID](https://docs.play.ht/reference/api-get-batch-tts-child-job-by-id)
- [Get batch child job by custom ID](https://docs.play.ht/reference/api-get-batch-tts-child-job-by-custom-id)
- [List ultra-realistic voices](https://docs.play.ht/reference/api-list-ultra-realistic-voices)
- [Python SDK](https://docs.play.ht/reference/python-sdk)
- [Node.js SDK](https://docs.play.ht/reference/nodejs-sdk)
- [Rate limits](https://docs.play.ht/reference/api-rate-limits)
- [Lowest-latency techniques](https://docs.play.ht/reference/techniques-to-guarantee-the-lowest-latency-1)
- [Groq voice engine](https://docs.play.ht/reference/groq)
- [PlayHT API reference on GitHub](https://github.com/playht/pyht)
- [PlayHT JavaScript SDK](https://github.com/playht/playsdk-nodejs)
- [PlayHT Python examples](https://github.com/playht/pyht/tree/main/examples)
- [PlayHT API base](https://api.play.ht/api/v2/tts/stream)
- [Voice cloning overview](https://play.ht/voice-cloning/)
- [PlayAI platform](https://play.ai/)
- [PlayAI developer resources](https://play.ai/developers)
- [PlayAI terms](https://play.ai/terms)
- [PlayHT status](https://status.play.ht/)

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
