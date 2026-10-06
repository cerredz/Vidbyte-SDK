# Design Doc: Models & Providers Catalog Refresh

**Status:** Approved  
**Author:** Grok  
**Created:** 2026-07-20  
**Last Updated:** 2026-07-20  

## 1. Overview

The Vidbyte SDK keeps a static catalog of known model IDs (for modality routing) and a registry of supported providers (enum, defaults, API-key env vars, base endpoints, factory adapters). Vendor catalogs have moved well past what the SDK currently lists: OpenAI has shipped GPT-5.6 Sol/Terra/Luna, Anthropic has Claude Sonnet 5 / Opus 4.8 / Fable 5, Google has Gemini 3.x stable models, xAI has Grok 4.5, DeepSeek has V4 Flash/Pro (with `deepseek-chat` / `deepseek-reasoner` deprecating on 2026-07-24), and popular OpenAI-compatible vendors such as Mistral and Moonshot (Kimi) are not first-class providers yet.

This change refreshes the model name → modality catalog, updates default model IDs per existing provider, and adds two OpenAI-compatible text providers (`mistral`, `moonshot`) through the established `OpenAICompatibleProvider` path. It does **not** introduce new runner modalities, live remote model discovery, or non-OpenAI-compatible native adapters.

## 2. Goals & Non-Goals

### Goals

- Expand `_MODEL_NAME_MODALITY_MAP` (and `ModelNameModality` where useful) with current flagship / stable / commonly used API model IDs across OpenAI, Anthropic, Gemini, xAI, DeepSeek, GLM, MiniMax, OpenRouter-prefixed routes, image/video/audio/embedding specialists, Mistral, and Moonshot/Kimi.
- Update `ProviderModelRegistry.DEFAULT_PROVIDER_MODELS` so each existing text-capable provider defaults to a current vendor-recommended model ID.
- Add `ModelProvider.MISTRAL` and `ModelProvider.MOONSHOT` end-to-end: enum, registry env/endpoint/default, thin `OpenAICompatibleProvider` subclasses, factory registration, modality prefixes, and skill/doc provider strings.
- Keep modality detection correct so new model IDs route to `TEXT` / `IMAGE` / `VIDEO` / `AUDIO` / `EMBEDDING` as appropriate (prefix maps first, exact map for special cases).
- Preserve existing tests and CI; this work does not require new feature test files, but must not break `tests/test_model_registry.py` or modality routing tests.

### Non-Goals

- Dynamic remote listing of vendor `/models` endpoints at runtime.
- Native non-OpenAI-compatible providers (Cohere Messages API, Amazon Bedrock multi-model routing, Azure OpenAI deployment names, Vertex AI auth).
- New runner capabilities (realtime WebSocket audio, Gemini Live A2A, Grok Voice API, music generation, OCR specialists).
- Changing request/response payload shapes for existing adapters beyond what the OpenAI-compatible base already supports.
- Deprecating or removing legacy model IDs already in the map (keep them for continuity).
- Adding Groq / Together / Fireworks / DashScope-native in this PR (listed as follow-ups).
- Writing new dedicated unit/integration test files (skill is design-doc-no-tests); existing CI still must pass.

## 3. Background & Context

### Current architecture (audit)

| Layer | Path | Role |
|-------|------|------|
| Provider enum | `vidbyte/lib/enums/model_provider.py` | 10 providers: openai, anthropic, gemini, xai, deepseek, glm, minimax, openrouter, elevenlabs, playai |
| Modality enum + exact map | `vidbyte/lib/enums/model_modality.py` | `ModelModality`, `ModelNameModality`, `_MODEL_NAME_MODALITY_MAP` |
| Prefix / substring detection | `vidbyte/lib/agents/modality_detector.py` | `_PREFIX_MODALITY_MAP`, `_SUBSTRING_MODALITY_MAP`, slash-split for OpenRouter-style IDs |
| Defaults / keys / endpoints | `vidbyte/lib/registries/models.py` | `ProviderModelRegistry` |
| Constants re-export | `vidbyte/lib/config/constants.py` | Delegates to registry maps |
| Factory | `vidbyte/providers/__init__.py` | `ModelProviders.text/image/video/audio/embedding/streaming_text` |
| Compatible adapters | `vidbyte/providers/compatible.py` | `OpenAICompatibleProvider` + DeepSeek / GLM / MiniMax |
| Usage skill | `skills/usage/create_agent.md` | Documents accepted provider strings |

`validate_model` only checks non-empty strings. Exact map membership is **not** a hard allowlist for execution — it primarily drives modality detection and documentation of known IDs. Prefix fallbacks already cover many unlisted IDs (`gpt-`, `claude-`, `gemini-`, `grok-`, `deepseek-`, `mistral-`, `qwen-`, etc.).

### Why this is urgent

1. **DeepSeek deprecation:** vendor docs state `deepseek-chat` and `deepseek-reasoner` deprecate on **2026-07-24 15:59 UTC**. Defaults and catalog must include `deepseek-v4-flash` and `deepseek-v4-pro`.
2. **Stale defaults:** registry still defaults xAI → `grok-3` (retired/redirected), Anthropic → `claude-sonnet-4-6` (Sonnet 5 is current), Gemini → `gemini-2.5-pro` while 3.5 Flash is the stable agentic default.
3. **Missing first-class providers:** Mistral and Moonshot (Kimi) are OpenAI-compatible and widely used; users currently must fake them via OpenRouter or custom endpoints.

### Evidence snapshot (vendor docs, 2026-07-20)

| Vendor | Notable missing / outdated items in SDK today |
|--------|-----------------------------------------------|
| OpenAI | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5-pro`, `gpt-5.4-pro`, `gpt-5.3-codex`, newer realtime/audio IDs |
| Anthropic | `claude-sonnet-5`, `claude-opus-4-8`, `claude-fable-5`, `claude-mythos-5`, `claude-mythos-preview` |
| Gemini | `gemini-3.1-pro-preview`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview`, `gemini-embedding-2`, Nano Banana 2 image IDs |
| xAI | `grok-4.5` (current flagship); default still `grok-3` |
| DeepSeek | `deepseek-v4-flash`, `deepseek-v4-pro`; chat/reasoner deprecating |
| Mistral | No provider; models only partially via OpenRouter prefixes |
| Moonshot | No provider; Kimi K2.x / K3 not catalogued |

## 4. Requirements

### Functional Requirements

1. **Catalog expansion:** Add exact entries to `_MODEL_NAME_MODALITY_MAP` for every ID listed in §6.2 (text / image / video / audio / embedding as marked). Keys are lowercase-normalized the same way `ModalityDetector.detect_modality` already lowercases lookups — store lowercase IDs except where the vendor’s public ID is mixed-case and already handled (today only Play.ai uses mixed-case; new entries should be lowercase).
2. **`ModelNameModality` enum:** Add members for the new **default-tier / flagship** IDs so the symbolic enum stays roughly aligned with the map (not every dated snapshot needs an enum member).
3. **Default model refresh** in `ProviderModelRegistry.DEFAULT_PROVIDER_MODELS`:

   | Provider | New default |
   |----------|-------------|
   | openai | `gpt-5.6-sol` |
   | anthropic | `claude-sonnet-5` |
   | gemini | `gemini-3.5-flash` |
   | xai | `grok-4.5` |
   | deepseek | `deepseek-v4-pro` |
   | glm | keep `glm-4-plus` unless a newer public default is confirmed during implementation |
   | minimax | keep `minimax-text-01` unless a newer public default is confirmed during implementation |
   | openrouter | keep `openrouter/auto` |
   | elevenlabs | keep `eleven_multilingual_v2` |
   | playai | keep `PlayDialog` |
   | mistral (new) | `mistral-medium-latest` if documented as evergreen alias; otherwise the dated Medium 3.5 ID discovered from Mistral docs at implement time (fallback candidate: `mistral-large-2512`) |
   | moonshot (new) | `kimi-k2.6` (stable generally available); add `kimi-k3` to the map if the public API ID is confirmed |

4. **New providers `mistral` and `moonshot`:**
   - `ModelProvider` enum members.
   - `API_KEY_ENV_VARS`: `MISTRAL_API_KEY`, `MOONSHOT_API_KEY`.
   - `DEFAULT_ENDPOINTS`: `https://api.mistral.ai/v1`, `https://api.moonshot.ai/v1`.
   - Thin subclasses in `compatible.py`: `MistralProvider`, `MoonshotProvider`.
   - Register both in `ModelProviders.text`.
   - Export from `vidbyte/providers/__init__.py` `__all__`.
5. **Prefix maps:** Ensure `_PREFIX_MODALITY_MAP` covers `kimi-` and `ministral-` / `devstral-` / `voxtral-` as TEXT (or AUDIO for clearly audio-only voxtral TTS/transcribe IDs via exact map + substring). Exact map wins before prefixes.
6. **OpenRouter-prefixed companions:** For high-traffic new models, add a few `provider/model` map entries (e.g. `anthropic/claude-sonnet-5`, `x-ai/grok-4.5`, `deepseek/deepseek-v4-pro`, `mistralai/mistral-large-2411` style) where the OpenRouter slug is known; slash-split already handles many cases without an exact entry.
7. **Docs/skills:** Update `skills/usage/create_agent.md` provider comment list to include `mistral` and `moonshot`. Update `vidbyte/providers/README.md` key-modules line if it enumerates adapters.
8. **No silent behavior change for explicit models:** Users who hard-code `model_name="gpt-5.5"` continue to work; only the **default** when a provider is selected without an override changes.

### Non-Functional Requirements

- **Compatibility:** Additive enum members and map entries only; no renames of existing provider string values.
- **Security:** No hardcoded API keys; continue env-var resolution through `ProviderModelRegistry`.
- **Observability:** No new logging required.
- **CI:** Canonical full local CI from the implementation worktree:

  ```bash
  python -m pip install -e ".[dev]"
  python scripts/run_ci.py
  ```

  Diagnostic stages: `python scripts/run_ci.py --stage source` and `--stage package`.
- **Remote:** Draft PR against `main`; all required GitHub checks must be green before handoff.
- **No new test files** required by this skill; if an existing test asserts a specific default model string, update that assertion to the new default (in-scope baseline maintenance, not a new feature pack).

## 5. High-Level Design

```text
                    ┌──────────────────────────────────────┐
                    │  Agent / Runner / Grader config       │
                    │  provider + model_name                │
                    └───────────────┬──────────────────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │ ModalityDetector.detect_modality(model)   │
              │  1) exact _MODEL_NAME_MODALITY_MAP        │
              │  2) slash-split last segment              │
              │  3) substring / prefix maps               │
              └─────────────────────┬─────────────────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │ ProviderModelRegistry                     │
              │  defaults · env keys · endpoints          │
              └─────────────────────┬─────────────────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │ ModelProviders.text(config)               │
              │  openai · anthropic · gemini · xai · …    │
              │  + mistral · moonshot (new)               │
              └─────────────────────┬─────────────────────┘
                                    │
         OpenAI-compatible path     │     Native adapters
   (compatible.py + openrouter)     │  (openai/anthropic/…)
                                    ▼
                              HttpTransport
```

**Design decisions**

1. **Catalog-first, adapters only where cheap:** Expanding the map fixes routing for already-supported providers immediately. New providers reuse `OpenAICompatibleProvider` (same pattern as DeepSeek/GLM/MiniMax).
2. **Defaults track current flagships, not previews when a stable alternative exists:** e.g. Gemini → `gemini-3.5-flash` (stable) rather than `gemini-3.1-pro-preview`.
3. **Keep legacy IDs:** Do not delete older map entries; deprecation is a vendor concern, not an SDK allowlist purge.
4. **Moonshot env var `MOONSHOT_API_KEY`:** Matches Moonshot’s own docs (`MOONSHOT_API_KEY` + `https://api.moonshot.ai/v1`).

## 6. Detailed Design

### 6.1 ModelProvider enum

**Files:** `vidbyte/lib/enums/model_provider.py`  
**Type:** Modified  

#### Responsibility

Strongly typed provider identifiers at the SDK boundary.

#### Interface / API

```python
class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    MINIMAX = "minimax"
    OPENROUTER = "openrouter"
    ELEVENLABS = "elevenlabs"
    PLAYAI = "playai"
    MISTRAL = "mistral"      # NEW
    MOONSHOT = "moonshot"    # NEW
```

#### Logic / Algorithm

1. Append new members; do not reorder existing members if any code depends on declaration order (none currently does, but keep additive style).

#### Edge Cases & Error Handling

- `ModelProvider("mistral")` / `ModelProvider("moonshot")` must succeed.
- Unknown strings still raise `ValueError` → wrapped as `ConfigurationError` by the registry.

---

### 6.2 Model modality catalog

**Files:** `vidbyte/lib/enums/model_modality.py`  
**Type:** Modified  

#### Responsibility

Exact model-ID → modality mapping and symbolic `ModelNameModality` aliases.

#### Interface / API

Add to `_MODEL_NAME_MODALITY_MAP` (non-exhaustive implementation checklist — implementers must include at least these; may add closely related dated snapshots found on the same vendor docs page):

**OpenAI text**

- `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`
- `gpt-5.5-pro`, `gpt-5.4-pro`, `gpt-5-pro`
- `gpt-5.3-codex`, `gpt-5.3-chat` (if still listed), `o3-pro`

**OpenAI audio / realtime (AUDIO)**

- `gpt-realtime`, `gpt-realtime-mini`, `gpt-realtime-1.5`, `gpt-realtime-2`, `gpt-realtime-2.1`, `gpt-realtime-2.1-mini`
- `gpt-audio`, `gpt-audio-1.5`, `gpt-audio-mini`
- `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe-diarize`

**Anthropic text**

- `claude-sonnet-5`
- `claude-opus-4-8`
- `claude-fable-5`
- `claude-mythos-5`
- `claude-mythos-preview`
- keep existing 4.x / 3.x entries

**Gemini text / embedding / image / video**

- `gemini-3.1-pro-preview`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview`
- keep `gemini-3.5-flash`, live/tts previews already present
- `gemini-embedding-001`, `gemini-embedding-2` (EMBEDDING)
- image: `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`, `gemini-3-pro-image` (IMAGE) — Nano Banana 2 family
- video: `veo-3.1-generate-preview`, `veo-3.1-lite-generate-preview` if not already covered by `veo-3.1` / `veo-3.1-lite-preview`

**xAI text**

- `grok-4.5`, `grok-4.5-latest`, `grok-build-latest`
- keep `grok-4.3`, `grok-3`, `grok-3-mini`, image/video imagine IDs

**DeepSeek text**

- `deepseek-v4-flash`, `deepseek-v4-pro`
- keep `deepseek-chat`, `deepseek-reasoner`, `deepseek-v3` for continuity until vendor hard-cut

**Mistral text (and selective audio)**

- `mistral-large-2512`, `mistral-medium-latest`, `mistral-medium-2604` (if confirmed), `mistral-small-2603` / `mistral-small-latest`
- `ministral-3b-latest`, `ministral-8b-latest`, `ministral-14b-latest` (or dated equivalents from docs)
- `devstral-2512` (TEXT; coding)
- audio exacts: `voxtral-mini-transcribe-…` → AUDIO when using known TTS/transcribe IDs

**Moonshot / Kimi text**

- `kimi-k2.5`, `kimi-k2.6`, `kimi-k3` (if public API ID confirmed at implement time)
- optional OpenRouter forms: `moonshotai/kimi-k2.5`, `moonshotai/kimi-k2.6`

**OpenRouter companions (TEXT)**

- `anthropic/claude-sonnet-5`, `anthropic/claude-opus-4.8` (or slug form documented on OpenRouter)
- `x-ai/grok-4.5`, `deepseek/deepseek-v4-pro`, `deepseek/deepseek-v4-flash`
- `openai/gpt-5.6-sol`, `openai/gpt-5.5`, `google/gemini-3.5-flash`

#### Logic / Algorithm

1. Insert new keys in the existing vendor-grouped sections of the dict for readability.
2. Extend `ModelNameModality` with flagship symbols only (e.g. `GPT_5_6_SOL = "text"`, `CLAUDE_SONNET_5 = "text"`, `GROK_4_5 = "text"`, `DEEPSEEK_V4_PRO = "text"`, `MISTRAL_MEDIUM = "text"`, `KIMI_K2_6 = "text"`).

#### Edge Cases & Error Handling

- Duplicate keys: forbidden; last-write-wins is a bug — keep one entry per ID.
- Image models whose names start with `gpt-` must appear in the **exact** map or be covered by `_SUBSTRING_MODALITY_MAP` (`gpt-image`) **before** the `gpt-` text prefix wins. Existing substring map already handles `gpt-image`; do not break that ordering.
- `grok-imagine-*` remains IMAGE/VIDEO via substring map; `grok-4.5` is TEXT via exact + `grok-` prefix.

---

### 6.3 ModalityDetector prefix/substring maps

**Files:** `vidbyte/lib/agents/modality_detector.py`  
**Type:** Modified  

#### Responsibility

Fallback modality inference for unlisted but patterned IDs.

#### Logic / Algorithm

1. Add prefixes (TEXT): `kimi-`, `ministral-`, `devstral-`, `codestral-`, `magistral-`.
2. Add substring AUDIO guards before generic text prefixes if needed: `voxtral` TTS/transcribe IDs → AUDIO (prefer exact map entries).
3. Do not reorder existing image/video substrings ahead of text prefixes incorrectly — current structure already checks substrings before prefixes.

#### Edge Cases & Error Handling

- `kimi-k3` without exact map still becomes TEXT via `kimi-` prefix.

---

### 6.4 ProviderModelRegistry

**Files:** `vidbyte/lib/registries/models.py`  
**Type:** Modified  

#### Responsibility

Defaults, API key env vars, endpoints, support listings, validation.

#### Interface / API

```python
DEFAULT_PROVIDER_MODELS = {
    ModelProvider.OPENAI: "gpt-5.6-sol",
    ModelProvider.ANTHROPIC: "claude-sonnet-5",
    ModelProvider.GEMINI: "gemini-3.5-flash",
    ModelProvider.XAI: "grok-4.5",
    ModelProvider.DEEPSEEK: "deepseek-v4-pro",
    ModelProvider.GLM: "glm-4-plus",
    ModelProvider.MINIMAX: "minimax-text-01",
    ModelProvider.OPENROUTER: "openrouter/auto",
    ModelProvider.ELEVENLABS: "eleven_multilingual_v2",
    ModelProvider.PLAYAI: "PlayDialog",
    ModelProvider.MISTRAL: "<mistral default from §4>",
    ModelProvider.MOONSHOT: "kimi-k2.6",
}

API_KEY_ENV_VARS = {
    ...
    ModelProvider.MISTRAL: "MISTRAL_API_KEY",
    ModelProvider.MOONSHOT: "MOONSHOT_API_KEY",
}

DEFAULT_ENDPOINTS = {
    ...
    ModelProvider.MISTRAL: "https://api.mistral.ai/v1",
    ModelProvider.MOONSHOT: "https://api.moonshot.ai/v1",
}
```

#### Logic / Algorithm

1. Update defaults for existing providers.
2. Add maps for new providers (all three ClassVars must stay complete for every `ModelProvider` member — missing entry raises `ConfigurationError` from `default_model` / `get_api_key_env_var` / `get_default_endpoint`).
3. `get_supported_providers()` / `get_supported_models()` pick up new values automatically via enum + defaults dict.

#### Edge Cases & Error Handling

- Existing tests assert `openrouter/auto` remains in supported models — preserve that default.
- If any test hard-codes old defaults (`gpt-5.5`, `claude-sonnet-4-6`, `grok-3`, `deepseek-v3`), update those assertions in the same PR.

---

### 6.5 OpenAI-compatible adapters

**Files:** `vidbyte/providers/compatible.py`, `vidbyte/providers/__init__.py`  
**Type:** Modified  

#### Responsibility

Thin provider adapters and factory registration for Mistral and Moonshot.

#### Interface / API

```python
class MistralProvider(OpenAICompatibleProvider):
    provider = ModelProvider.MISTRAL

class MoonshotProvider(OpenAICompatibleProvider):
    provider = ModelProvider.MOONSHOT
```

Register in `ModelProviders.text` providers dict; export in `__all__`.

#### Logic / Algorithm

1. No custom payload logic unless a vendor is discovered (during implementation smoke) to reject standard `tools` / `response_format` the same way DeepSeek does — only then specialize.
2. Default chat completions path: `POST {endpoint}/chat/completions` via existing base class.

#### Edge Cases & Error Handling

- Missing API key → `ConfigurationError` from registry (unchanged).
- Unsupported capability (image/video for these providers) → `ProviderSelectionError` from factory (unchanged — not registered under image/video).

---

### 6.6 Skills / README touch-ups

**Files:** `skills/usage/create_agent.md`, `vidbyte/providers/README.md`  
**Type:** Modified  

#### Responsibility

Keep human-facing provider lists aligned with the enum.

#### Logic / Algorithm

1. Extend the `provider:` comment string in `create_agent.md` with `mistral`, `moonshot`.
2. Mention the new adapters in providers README key-modules list.

## 7. Data Model Changes

| Symbol | Change |
|--------|--------|
| `ModelProvider` | +`MISTRAL`, +`MOONSHOT` |
| `ModelNameModality` | +flagship members for new defaults |
| `_MODEL_NAME_MODALITY_MAP` | +dozens of exact model IDs |
| `ProviderModelRegistry` ClassVars | defaults updated; new env/endpoint rows |
| Runtime DB / migrations | N/A — pure in-process catalog |

**Forward compatibility:** New enum members are additive.  
**Rollback:** Revert the PR; no persisted schema.

## 8. API Changes

| Surface | Change |
|---------|--------|
| `ModelProvider` values | Additive: `"mistral"`, `"moonshot"` |
| `ProviderModelRegistry.default_model(...)` | New return values for refreshed defaults |
| `ProviderModelRegistry.get_supported_providers()` | Includes new providers |
| `ModelProviders.text(...)` | Accepts mistral/moonshot configs |
| Public HTTP API | N/A |
| Breaking changes | None intended. Default model IDs change for env-driven auto-selection (`_resolve_from_environment`) — document in PR body. |

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/models-providers-catalog-refresh.md` | This design doc (committed first on the feature branch) |
| MODIFY | `vidbyte/lib/enums/model_provider.py` | Add MISTRAL, MOONSHOT |
| MODIFY | `vidbyte/lib/enums/model_modality.py` | Expand map + ModelNameModality flagships |
| MODIFY | `vidbyte/lib/agents/modality_detector.py` | New prefixes for kimi/mistral family |
| MODIFY | `vidbyte/lib/registries/models.py` | Defaults, env vars, endpoints |
| MODIFY | `vidbyte/providers/compatible.py` | MistralProvider, MoonshotProvider |
| MODIFY | `vidbyte/providers/__init__.py` | Factory registration + exports |
| MODIFY | `vidbyte/providers/README.md` | Document new adapters |
| MODIFY | `skills/usage/create_agent.md` | Provider string list |
| MODIFY | `tests/test_model_registry.py` (only if assertions pin old defaults/providers) | Keep existing CI green |

**Manifest counts:** 1 CREATE, 8–9 MODIFY, 0 DELETE.

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| OpenAI API catalog | `https://api.openai.com/v1` | Existing text/image/video/audio | Low — additive IDs only |
| Anthropic API | `https://api.anthropic.com/v1` | Existing text | Low |
| Gemini API | `https://generativelanguage.googleapis.com/v1beta` | Existing text/embed | Low |
| xAI API | `https://api.x.ai/v1` | Existing text/image | Low — default moves to `grok-4.5` |
| DeepSeek API | `https://api.deepseek.com/v1` | Existing text | Medium — default moves before chat/reasoner deprecation |
| Mistral API | `https://api.mistral.ai/v1` | New OpenAI-compatible text | Low — standard chat completions |
| Moonshot API | `https://api.moonshot.ai/v1` | New OpenAI-compatible text | Low — standard chat completions |
| New Python packages | None | — | None |

## 11. Rollout & Deployment

1. Land design doc commit on `feat/models-providers-catalog-refresh`.
2. Implement catalog + registry + adapters in logical commits.
3. Run full local CI (`python scripts/run_ci.py`).
4. Open **draft** PR to `main`; watch required checks until green.
5. Merge when approved — pure library catalog change; no feature flag needed.
6. **Rollback:** revert the merge commit / close PR; no data migration.

**Compatibility note:** Environment-based multi-provider graders that omit explicit models will start calling newer defaults. Callers with explicit `model_name` / `provider_models` are unaffected.

## 12. Open Questions

- [x] **OpenAI default:** Implemented as `gpt-5.6-sol` (approved recommendation).
- [x] **Mistral default ID:** Implemented as `mistral-medium-latest` evergreen alias.
- [x] **Kimi K3:** Catalog includes `kimi-k3`; default remains existing `kimi-k2.7-code` (main already had Kimi).
- [x] **Scope of new providers:** Mistral added. Moonshot endpoint already exists as `ModelProvider.KIMI` on main — do not add a duplicate `moonshot` enum member. Groq/Together/Fireworks deferred.

### Implementation deviations (evidence from origin/main at start)

1. **Kimi already first-class on main** as `ModelProvider.KIMI` with `MOONSHOT_API_KEY` + `https://api.moonshot.ai/v1` + `KimiProvider`. Design originally proposed `moonshot`; implementation keeps `kimi` to avoid a breaking rename.
2. **Many catalog IDs already present on main** (Claude Sonnet 5 / Opus 4.8 / Fable, DeepSeek V4, Gemini 3.x, GLM 5.x, MiniMax M3, Kimi K2.x). This PR focuses on residual gaps: GPT-5.6 family, Grok 4.5, Mistral provider + models, OpenRouter companions, prefix/runner maps, skill docs, and default refreshes for OpenAI/xAI.

## 13. Alternatives Considered

### Live vendor `/models` discovery

- What: Query each provider’s models list at runtime and cache.
- Why rejected: Adds network dependency, auth complexity, and non-determinism to agent construction; conflicts with the SDK’s static registry pattern.

### OpenRouter-only expansion (no new native providers)

- What: Only add model IDs + OpenRouter-prefixed routes; tell users to set `provider=openrouter`.
- Why rejected: Users with direct Mistral/Moonshot keys want first-class `provider=` values and correct env var names; cost and latency differ from OpenRouter.

### Full native adapters (Cohere, Bedrock, Azure)

- What: First-class non-OpenAI-compatible providers in this PR.
- Why rejected: Each needs distinct auth/payload work and is out of scope for a catalog refresh. Follow-up design docs can cover them.

### Aggressive default freeze (never change defaults)

- What: Only expand the map; leave defaults on older IDs.
- Why rejected: DeepSeek deprecation and retired Grok-3 defaults create production footguns; updating defaults is the highest-leverage part of “refresh.”
