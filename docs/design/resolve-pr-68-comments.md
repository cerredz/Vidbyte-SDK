# Context Protocol Header
# Description:
#     Design document outlining the resolution of PR #68 comments regarding model provider naming updates in vidbyte-sdk.
# Purpose:
#     Forces detailed design of the default provider models updates prior to implementation to ensure correctness and alignment with 2026 provider API states.
# Architecture:
#     - Section 1-4: Overview, Goals, Background, Requirements.
#     - Section 5-8: High-Level Design, Detailed Design, Data/API changes.
#     - Section 9-14: File Manifest, Testing Plan, Rollout, and Alternatives.
# Key Functions:
#     N/A (Documentation file)
# Relations:
#     Complements design docs for multi-provider agentic grader, aligns with vidbyte-pr-comment-resolver skill.

# Design Doc: Resolve PR #68 Comments

**Status:** Draft  
**Author:** Antigravity  
**Created:** 2026-05-27  
**Last Updated:** 2026-05-27  

---

## 1. Overview

This design doc outlines the plan to address the code review comments on pull request #68 of the `vidbyte-sdk` repository. Specifically, we will update the `DEFAULT_PROVIDER_MODELS` mapping in `vidbyte/lib/models/registry.py` to use valid and more recent model names for all supported providers (OpenAI, Anthropic, Gemini, xAI, DeepSeek, GLM, and MiniMax), ensuring alignment with current (2026) vendor API specs.

---

## 2. Goals & Non-Goals

### Goals

- Update the static `DEFAULT_PROVIDER_MODELS` dictionary mapping in `ProviderModelRegistry` with accurate, valid, and recent model IDs for 2026.
- Ensure all updated model identifiers map correctly to the `ModelModality.TEXT` execution modality in `vidbyte/lib/enums/model_modality.py`.
- Run validation checks and ensure the existing SDK test suites pass cleanly.

### Non-Goals

- Adding new model providers.
- Changing the internal architecture of `ProviderModelRegistry`.
- Modifying non-default model behaviors or agent loops.

---

## 3. Background & Context

During the review of pull request #68 (which introduced the multi-provider agentic grader), a review comment was made on `vidbyte/lib/models/registry.py:43`:
> "need to make sure that these are actual valid names of the providers (also make them more recent), use web search for each platform for this"

The original mapping contains legacy model IDs or placeholders (e.g. `grok-beta`, `abab6.5-chat`, `glm-4`). A comprehensive web search confirms that these providers have newer flagship text models available in 2026 that are already supported by our `ModelNameModality` enum.

---

## 4. Requirements

### Functional Requirements

1. Modify `DEFAULT_PROVIDER_MODELS` in `ProviderModelRegistry` to use:
   - OpenAI -> `gpt-5.5`
   - Anthropic -> `claude-sonnet-4-6`
   - Gemini -> `gemini-2.5-pro`
   - xAI -> `grok-3`
   - DeepSeek -> `deepseek-v3`
   - GLM -> `glm-4-plus`
   - MiniMax -> `minimax-text-01`
2. Validate that these model IDs match the expected string representations in `_MODEL_NAME_MODALITY_MAP` in `vidbyte/lib/enums/model_modality.py` to ensure correct modality routing.

### Non-Functional Requirements

- Zero performance overhead.
- Total backward compatibility with external APIs.
- 100% test pass rate.

---

## 5. High-Level Design

The design is extremely localized. We are updating static string values inside the existing `ProviderModelRegistry` configuration. No class signatures or public interfaces will be altered.

```text
[MultiProviderAgenticGrader] 
       │
       ▼
[ProviderModelRegistry] ──► Reads DEFAULT_PROVIDER_MODELS (Updated to 2026 modern IDs)
```

---

## 6. Detailed Design

### 6.1 ProviderModelRegistry

**File(s):** `vidbyte/lib/models/registry.py`  
**Type:** Modified  

#### What it does

Defines the class-level `DEFAULT_PROVIDER_MODELS` mapping, which is used to resolve active models when none are explicitly provided by the user.

#### Interface / API

```python
class ProviderModelRegistry:
    DEFAULT_PROVIDER_MODELS: ClassVar[dict[ModelProvider, str]]
```

The values in this mapping will be changed to the new modern IDs.

#### Logic / Algorithm

N/A - Direct configuration dictionary update.

#### Edge Cases & Error Handling

- Handled by existing registry validators:
  - If an invalid model provider enum is used, `ConfigurationError` is raised at import/validation time.
  - If a resolved model resolves to empty, `ConfigurationError` is raised.

---

## 7. Data Model Changes

N/A - No database schemas or types are modified.

---

## 8. API Changes

N/A - No public network APIs are modified.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/models/registry.py` | Update `DEFAULT_PROVIDER_MODELS` to use recent, valid model names for all platforms. |

---

## 10. Testing Plan

We will write and execute verification tests in the test suite to validate all scenarios.

### Unit Tests

We will add/update tests in `tests/test_multi_provider_agentic_grader.py` or `tests/test_registry.py` (if it exists) to verify:

- **[Edge Case]**: Test that `default_model` raises `ConfigurationError` when queried for a non-existent provider.
- **[Hidden Failure]**: Test that calling `resolve_active` raises `ConfigurationError` if no credentials (API keys) are configured in the environment and no explicit models are specified.
- **[Silent Failure]**: Test that all default model IDs configured in `DEFAULT_PROVIDER_MODELS` are valid text models that successfully map to `ModelModality.TEXT` when queried via the modality detector. This ensures that no model names are typoed and all are recognized by the SDK's routing layer.
- **[Hidden Assumption]**: Test that `resolve_active` works correctly and returns the exact user-specified models when `provider_models` is explicitly provided, bypassing the environment checks.

---

## 11. Dependencies & External Services

N/A - No new dependencies.

---

## 12. Rollout & Deployment

This is a non-breaking, fully backward-compatible internal update. It will roll out as part of the normal release cycle.

---

## 13. Open Questions

N/A - No open questions.

---

## 14. Alternatives Considered

### Alternative 1: Keep using legacy names
- Rejected: Keeping names like `grok-beta` or `abab6.5-chat` goes against the explicit review comment request to make the model names valid and recent based on web searches.

### Alternative 2: Auto-detect latest models via API calls at runtime
- Rejected: Doing live HTTP requests to retrieve models on startup adds undesirable latency, potential rate-limiting, and network dependency failures. Static defaults are standard.
