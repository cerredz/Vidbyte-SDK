# Design Doc: Resolve PR 60 Comments (OpenRouter Provider Integration)

**Status:** Approved  
**Author:** Antigravity (Advanced AI Coding Agent)  
**Created:** 2026-05-27  
**Last Updated:** 2026-05-27  

---

## 1. Overview

This feature resolves review comments on PR #60 for the `vidbyte-sdk` repository. It integrates OpenRouter as a supported Model Provider, maps all OpenRouter and other supported models (including prefixed names), and centralizes the model and provider constants, validation, and key resolution logic into the newly introduced `ProviderModelRegistry`.

---

## 2. Goals & Non-Goals

### Goals

- Register `openrouter` as a supported `ModelProvider` enum member.
- Centralize all environment key maps, endpoint maps, and validation logic into `ProviderModelRegistry` (`vidbyte/lib/models/registry.py`).
- Refactor client configuration dataclasses to use `ProviderModelRegistry` as the single source of truth for validation and key resolution.
- Map OpenRouter's supported model IDs (both prefixed and non-prefixed) to `ModelModality.TEXT` so that `TextModelRunner` is routed correctly.
- Update `ModalityDetector` to support slash-splitting to dynamically parse prefixed models (e.g. `openai/gpt-4o`, `anthropic/claude-3.5-sonnet`) and support common model prefixes.
- Implement a robust `OpenRouterProvider` adapter with custom attribution headers.
- Open a fresh PR targeting `main` and close the old PR #60.

### Non-Goals

- Dynamically querying OpenRouter API models endpoint at runtime. All supported maps remain statically registered.
- Managing user account balances or billing queries.

---

## 3. Background & Context

OpenRouter routes API requests to multiple underlying model providers. Users of the SDK want to route requests through OpenRouter using model strings that might be prefixed by their native provider (e.g., `openai/gpt-4o-mini`, `google/gemini-2.5-pro`). 
Previously, the SDK had model constants and validation scattered across different config files and dataclasses. Centralizing this logic into `ProviderModelRegistry` provides a cleaner, single authoritative source for default models, active model resolution, and key verification.

---

## 4. Requirements

### Functional Requirements

1. **Centralized Registry:** `ProviderModelRegistry` must define `API_KEY_ENV_VARS` and `DEFAULT_ENDPOINTS`.
2. **Registry API:** Provide methods `get_api_key_env_var`, `get_default_endpoint`, `resolve_api_key`, `resolve_endpoint`, `get_supported_providers`, and `get_supported_models`.
3. **No Circular Imports:** Refactor `constants.py` to import maps from `ProviderModelRegistry`.
4. **Slash-Splitting Modality Resolution:** Support resolving modalities for prefixed models (e.g., `openai/gpt-4o` -> `gpt-4o` -> `ModelModality.TEXT`).
5. **Common Model Prefixes:** Add `llama-`, `mistral-`, `qwen-`, etc. to `_PREFIX_MODALITY_MAP`.
6. **OpenRouter Adapter:** Implement `OpenRouterProvider` with Bearer auth and attribution headers.

---

## 5. High-Level Design

```text
[TextModelConfig] / [ImageModelConfig]
       |
       +--> Delegates API Key / Endpoint Resolution --> [ProviderModelRegistry]
       v
[TextModelRunner]
       |
       v
[ModalityDetector.create_runner] -> matches provider == "openrouter"
       |
       v
[OpenRouterProvider] (subclass of OpenAICompatibleProvider)
       |
       +--> injects: HTTP-Referer, X-OpenRouter-Title
       v
[HttpTransport] -> POST https://openrouter.ai/api/v1/chat/completions
```

---

## 6. Detailed Design

### 6.1 Centralized `ProviderModelRegistry`

**File:** `vidbyte/lib/models/registry.py`  
**Type:** Modified  

```python
class ProviderModelRegistry:
    DEFAULT_PROVIDER_MODELS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "gpt-5.5",
        ModelProvider.ANTHROPIC: "claude-sonnet-4-6",
        ModelProvider.GEMINI: "gemini-2.5-pro",
        ModelProvider.XAI: "grok-3",
        ModelProvider.DEEPSEEK: "deepseek-v3",
        ModelProvider.GLM: "glm-4-plus",
        ModelProvider.MINIMAX: "minimax-text-01",
        ModelProvider.OPENROUTER: "openrouter/auto",
    }

    API_KEY_ENV_VARS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "OPENAI_API_KEY",
        ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        ModelProvider.GEMINI: "GEMINI_API_KEY",
        ModelProvider.XAI: "XAI_API_KEY",
        ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
        ModelProvider.GLM: "GLM_API_KEY",
        ModelProvider.MINIMAX: "MINIMAX_API_KEY",
        ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
    }

    DEFAULT_ENDPOINTS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "https://api.openai.com/v1",
        ModelProvider.ANTHROPIC: "https://api.anthropic.com/v1",
        ModelProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
        ModelProvider.XAI: "https://api.x.ai/v1",
        ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
        ModelProvider.GLM: "https://open.bigmodel.cn/api/paas/v4",
        ModelProvider.MINIMAX: "https://api.minimax.io/v1",
        ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
    }
```

Methods to add:
- `get_api_key_env_var(provider: ModelProvider | str) -> str`
- `get_default_endpoint(provider: ModelProvider | str) -> str`
- `resolve_api_key(provider: ModelProvider | str, explicit_key: str | None) -> str`
- `resolve_endpoint(provider: ModelProvider | str, explicit_endpoint: str | None) -> str`
- `get_supported_providers() -> list[str]`
- `get_supported_models() -> list[str]`

### 6.2 Refactored Configuration Dataclasses

**File:** `vidbyte/lib/dataclasses/model_configs.py`  
**Type:** Modified  

```python
    def resolved_api_key(self) -> str:
        # Resolves explicit API key or checks the central environment variable map.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Resolves explicit endpoint or checks the central default endpoint map.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)
```

### 6.3 Dynamic Modality Detection

**File:** `vidbyte/lib/agents/modality_detector.py`  
**Type:** Modified  

```python
    @staticmethod
    def detect_modality(model_name: str) -> ModelModality:
        # Resolves modality by stripping provider prefixes and using substring/prefix rules.
        name = (model_name or "").strip().lower()
        if not name:
            return ModelModality.AUTO
        
        # Slash-splitting for OpenRouter/prefixed models (e.g. openai/gpt-4o)
        if "/" in name:
            name = name.split("/")[-1]
            
        if name in _MODEL_NAME_MODALITY_MAP:
            return _MODEL_NAME_MODALITY_MAP[name]
        for pattern, modality in _SUBSTRING_MODALITY_MAP:
            if pattern in name:
                return modality
        for prefix, modality in _PREFIX_MODALITY_MAP:
            if name.startswith(prefix):
                return modality
        return ModelModality.AUTO
```

Add missing common model prefixes to `_PREFIX_MODALITY_MAP`:
- `"llama-"` -> `ModelModality.TEXT`
- `"mistral-"` -> `ModelModality.TEXT`
- `"ministral-"` -> `ModelModality.TEXT`
- `"qwen-"` -> `ModelModality.TEXT`
- `"qwen"` -> `ModelModality.TEXT`
- `"command-"` -> `ModelModality.TEXT`
- `"sonar-"` -> `ModelModality.TEXT`
- `"nova-"` -> `ModelModality.TEXT`
- `"phi-"` -> `ModelModality.TEXT`
- `"hermes-"` -> `ModelModality.TEXT`

---

## 7. Data Model Changes

N/A - This change only affects runtime provider interfaces and does not persist data to a database.

---

## 8. API Changes

N/A - Integrates external OpenRouter APIs.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/enums/model_provider.py` | Add `OPENROUTER` to `ModelProvider` |
| MODIFY | `vidbyte/lib/config/constants.py` | Import and re-export maps from `ProviderModelRegistry` |
| MODIFY | `vidbyte/lib/enums/model_modality.py` | Register modality maps for prefixed OpenRouter/supported models |
| MODIFY | `vidbyte/lib/agents/modality_detector.py` | Implement slash-splitting and new prefixes |
| MODIFY | `vidbyte/lib/models/registry.py` | Centralize variables, validation, and key resolution |
| MODIFY | `vidbyte/lib/dataclasses/model_configs.py` | Refactor configurations to delegate to registry |
| CREATE | `vidbyte/providers/openrouter.py` | Implement OpenRouterProvider class with custom headers |
| MODIFY | `vidbyte/providers/__init__.py` | Register OpenRouterProvider in factory |
| CREATE | `tests/test_openrouter_provider.py` | Unit tests for OpenRouter provider |
| CREATE | `tests/test_model_registry.py` | Unit tests for centralized ProviderModelRegistry |
| CREATE | `scripts/test-openrouter-provider-integration.py` | Verification script for Phase 5 |

---

## 10. Testing Plan

### Unit Tests

#### `tests/test_openrouter_provider.py`
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

#### `tests/test_model_registry.py`
1. **[Edge Case] Unknown Model Provider Lookup:**
   - Verify lookup behavior when an invalid provider string is passed.
2. **[Hidden Assumption] API Key Resolution and Validation:**
   - Verify `resolve_api_key` raises the correct exception when the environment variable is missing vs when it is configured properly.

### Integration Tests
Create verification script `scripts/test-openrouter-provider-integration.py` to run end-to-end configuration tests using standard and mock execution paths.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| OpenRouter API | `https://openrouter.ai/api/v1` | External AI model router | API downtime. Mitigated by using standard OpenAI-compatible format. |

---

## 12. Rollout & Deployment

All changes are strictly additive and backward compatible. Standard package version bump.

---

## 13. Open Questions

- None.

---

## 14. Alternatives Considered

N/A.

---
