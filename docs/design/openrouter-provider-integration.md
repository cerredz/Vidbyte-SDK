# Design Doc: OpenRouter Provider Integration

**Status:** Draft
**Author:** Antigravity (Advanced AI Coding Agent)
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

This feature integrates OpenRouter as a supported Model Provider in the `vidbyte-sdk`. OpenRouter serves as a single API endpoint routing requests to hundreds of models from OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek, and others. The integration enables developers to leverage OpenRouter for prototyping across multiple models with simplified authentication and custom application attribution.

---

## 2. Goals & Non-Goals

### Goals

- Introduce `openrouter` as a core `ModelProvider` enum.
- Map the top 20 OpenRouter models to `ModelModality.TEXT` to support clean modality routing.
- Create an `OpenRouterProvider` adapter that inherits from `OpenAICompatibleProvider` and provides proper Bearer auth and client attribution headers (`HTTP-Referer` and `X-OpenRouter-Title`).
- Update the central `ModelProviders` factory to register and route text generation requests to `OpenRouterProvider`.
- Maintain complete back-compatible support for all existing model providers.

### Non-Goals

- Implementing image or video modality support for OpenRouter (this is out of scope; only text/chat completions are targeted).
- Managing user account balances or billing queries via the SDK.
- Auto-detecting new models at runtime dynamically beyond the hardcoded top 20 list and standard modality fallback defaults.

---

## 3. Background & Context

OpenRouter is a popular API gateway offering developer-friendly access to diverse LLM architectures via a unified OpenAI-compatible endpoint. Teams using Vidbyte require a quick way to test diverse models (e.g., Llama-3.3, Mistral, Qwen, DeepSeek, and Gemini) via a single environment configuration. 
Currently, `vidbyte-sdk` supports native providers like OpenAI, Anthropic, Gemini, xAI, DeepSeek, GLM, and MiniMax. Integrating OpenRouter bridges the gap for hundreds of other open-source and proprietary models without necessitating a separate adapter for every model provider.

---

## 4. Requirements

### Functional Requirements

1. **Enum Extension:** `ModelProvider.OPENROUTER` must be added to the supported providers.
2. **Environment Variable Configuration:** The SDK must resolve the OpenRouter API key using `OPENROUTER_API_KEY` from the environment when not passed explicitly.
3. **Endpoint Configuration:** The default REST endpoint for OpenRouter must map to `https://openrouter.ai/api/v1`.
4. **Header Customization:** Requests to OpenRouter must include `HTTP-Referer` set to `https://github.com/vidbyte/vidbyte-sdk` and `X-OpenRouter-Title` set to `Vidbyte SDK` to ensure app attribution on OpenRouter rankings.
5. **Modality Mapping:** The top 20 models on OpenRouter must map to `ModelModality.TEXT` so that `TextModelRunner` can be instantiated without needing manual modality configuration.
6. **Class-First Provider Adapter:** Implement a robust `OpenRouterProvider` class utilizing class boundaries, sparse inline documentation, and single-line signatures.

### Non-Functional Requirements

- **Zero Added Latency:** Header injection and client routing must run synchronously with negligible overhead (<1ms).
- **Error Handling:** Gracefully parse and translate OpenRouter's specific error envelopes (e.g., rate limits, model routing errors) into standard SDK exceptions using `HttpResponseParser`.
- **Reliability:** Support retry mechanisms via the standard `HttpTransport` retry strategy.

---

## 5. High-Level Design

The design expands the existing `vidbyte.providers` and `vidbyte.lib` architecture. By leveraging the existing `OpenAICompatibleProvider` baseline, we can quickly build a secure, compliant adapter.

```text
[TextModelRunner]
       |
       v
[ModelProviders.text()] -> matches provider == "openrouter"
       |
       v
[OpenRouterProvider] (subclass of OpenAICompatibleProvider)
       |
       +--> custom headers: HTTP-Referer, X-OpenRouter-Title
       v
[HttpTransport] -> POST https://openrouter.ai/api/v1/chat/completions
```

Data flows from the `TextModelRunner` which synthesizes instructions and history, down into the `OpenRouterProvider` which constructs the payload and injects routing headers, and finally to `HttpTransport` which initiates the network call.

---

## 6. Detailed Design

### 6.1 `ModelProvider` Enum

**File(s):** `vidbyte/lib/enums/model_provider.py`  
**Type:** Modified  

#### What it does
Registers the `openrouter` string literal as a supported model provider.

#### Interface / API
```python
class ModelProvider(str, Enum):
    # Supported SDK model providers.
    OPENAI = "openai"
    ...
    OPENROUTER = "openrouter"
```

---

### 6.2 Provider Constants

**File(s):** `vidbyte/lib/config/constants.py`  
**Type:** Modified  

#### What it does
Defines `OPENROUTER_API_KEY` as the default environment variable and `https://openrouter.ai/api/v1` as the default endpoint mapping.

#### Interface / API
```python
API_KEY_ENV_VARS: dict[ModelProvider, str] = {
    ...
    ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
}

DEFAULT_ENDPOINTS: dict[ModelProvider, str] = {
    ...
    ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
}
```

---

### 6.3 Modality Detection Mapping

**File(s):** `vidbyte/lib/enums/model_modality.py`  
**Type:** Modified  

#### What it does
Maps the top 20 models supported via OpenRouter to `ModelModality.TEXT` so the SDK's automatic modality detector routes them correctly.

#### Interface / API
Adds new members to `ModelNameModality` enum and registers them in `_MODEL_NAME_MODALITY_MAP`.

List of top 20 model identifiers to map:
- `openai/gpt-4o`
- `openai/gpt-4o-mini`
- `openai/o1`
- `openai/o1-mini`
- `openai/o3-mini`
- `anthropic/claude-3.5-sonnet`
- `anthropic/claude-3-opus`
- `anthropic/claude-3.5-haiku`
- `google/gemini-2.5-pro`
- `google/gemini-2.5-flash`
- `google/gemini-2.0-flash-thinking-exp`
- `meta-llama/llama-3.3-70b-instruct`
- `meta-llama/llama-3.1-8b-instruct:free`
- `meta-llama/llama-3.1-70b-instruct`
- `meta-llama/llama-3.1-405b-instruct`
- `deepseek/deepseek-chat`
- `deepseek/deepseek-r1`
- `mistralai/mistral-large`
- `mistralai/pixtral-large-12b`
- `qwen/qwen-2.5-72b-instruct`

---

### 6.4 `OpenRouterProvider` Class

**File(s):** `vidbyte/providers/openrouter.py`  
**Type:** New file  

#### What it does
Implements the concrete adapter for OpenRouter text completion APIs.

#### Interface / API
```python
class OpenRouterProvider(OpenAICompatibleProvider):
    provider = ModelProvider.OPENROUTER

    def __init__(self, *, text_config: TextModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Initialize the OpenRouter provider adapter.
        ...

    def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute an OpenRouter chat completion request.
        ...

    def _build_request_headers(self, config: TextModelConfig) -> dict[str, str]:
        # Build OpenRouter custom HTTP headers including client attribution.
        ...

    def _execute_http_call(self, config: TextModelConfig, headers: dict[str, str], payload: dict[str, Any], transport: HttpTransport) -> HttpResponse:
        # Perform the actual network request over the standard http transport.
        ...
```

---

### 6.5 Provider Factory Registration

**File(s):** `vidbyte/providers/__init__.py`  
**Type:** Modified  

#### What it does
Imports and registers `OpenRouterProvider` inside the central factory registry for model providers.

#### Interface / API
```python
from vidbyte.providers.openrouter import OpenRouterProvider

class ModelProviders:
    @staticmethod
    def text(config: TextModelConfig) -> OpenAIProvider | AnthropicProvider | GeminiProvider | XAIProvider | DeepSeekProvider | GLMProvider | MiniMaxProvider | OpenRouterProvider:
        providers = {
            ...
            ModelProvider.OPENROUTER: OpenRouterProvider,
        }
        ...
```

---

## 7. Data Model Changes

N/A - This change only affects runtime provider interfaces and does not persist data to a database.

---

## 8. API Changes

N/A - This change integrates an external provider but does not introduce new API endpoints within the SDK's boundary.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/enums/model_provider.py` | Add `OPENROUTER` to `ModelProvider` |
| MODIFY | `vidbyte/lib/config/constants.py` | Map default endpoint and environment variables |
| MODIFY | `vidbyte/lib/enums/model_modality.py` | Register modality maps for top 20 OpenRouter models |
| CREATE | `vidbyte/providers/openrouter.py` | Implement OpenRouter provider class |
| MODIFY | `vidbyte/providers/__init__.py` | Register OpenRouter provider in central factory |
| CREATE | `tests/test_openrouter_provider.py` | Unit tests verifying request payload, headers, and response parsing |
| CREATE | `scripts/test-openrouter-provider-integration.py` | Integration test verification script for Phase 5 |

---

## 10. Testing Plan

### Unit Tests

We will create a new test suite `tests/test_openrouter_provider.py` containing the following tests:

1. **[Edge Case] Empty Model Name Validation:**
   - Verify that trying to configure an OpenRouter provider with an empty model name throws a `ConfigurationError`.
2. **[Edge Case] Non-String API Key input:**
   - Verify that resolving api keys behaves correctly when a non-string or None value is passed.
3. **[Hidden Failure] Invalid Response Status Code Handling:**
   - Verify that when the server returns a 400 or 500 error code with a JSON error envelope, `OpenRouterProvider` correctly parses it and raises a `ProviderRequestError`.
4. **[Hidden Failure] Corrupted JSON Response Payload:**
   - Verify that when the transport returns an invalid or corrupted JSON payload, the provider correctly handles it and throws a `ProviderRequestError`.
5. **[Silent Failure] Empty Response Content:**
   - Verify that when the response includes empty chat choices or missing message content, the provider parses it as an error or returns an appropriate exception instead of silently returning empty/null results.
6. **[Silent Failure] Incorrect Headers Injection:**
   - Mock a successful HTTP execution and assert that the requested headers include `HTTP-Referer` and `X-OpenRouter-Title` exactly as required.
7. **[Hidden Assumption] Default Routing Modality Fallback:**
   - Verify that models not in the top 20 text map default to `ModelModality.TEXT` when routed via `ModalityDetector`.

### Integration Tests

We will write an automated test verification script `scripts/test-openrouter-provider-integration.py` to verify end-to-end routing. It will use the `FakeTransport` class to simulate a successful OpenRouter server roundtrip, verifying:
- End-to-end model configuration initialization
- Request URL formatting
- Bearer authorization header inclusion
- Response text extraction

### Manual / QA Test Cases

1. Setup an `OPENROUTER_API_KEY` in environment.
2. Initialize `TextModelRunner(provider="openrouter", model="openai/gpt-4o-mini")`.
3. Call `runner.run("Ping")` and verify that the response text output is resolved successfully.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| OpenRouter API | `https://openrouter.ai/api/v1` | External AI model router | API downtime or schema changes. Mitigated by using standard OpenAI-compatible format. |

---

## 12. Rollout & Deployment

- **Feature Flags:** None required.
- **Breaking Change:** No. All changes are strictly additive and backward compatible.
- **Deployment:** Standard package version bump.

---

## 13. Open Questions

- None. The design mirrors the existing OpenAICompatibleProvider architecture perfectly.

---

## 14. Alternatives Considered

### Alternative 1: Direct subclassing inside `compatible.py`

- **What:** Add `OpenRouterProvider` directly to `vidbyte/providers/compatible.py`.
- **Why rejected:** Putting every OpenAI-compatible provider in a single file makes `compatible.py` hard to maintain. Creating a distinct file keeps it organized and follows the convention of `xai.py` and `anthropic.py`.

---
