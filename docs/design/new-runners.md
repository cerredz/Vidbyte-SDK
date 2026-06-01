# Design Doc: AudioModelRunner, EmbeddingModelRunner, StreamingTextModelRunner

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

This feature adds three new runner classes to `vidbyte/lib/runners/`: `AudioModelRunner` (text-to-speech and speech-to-text over OpenAI, ElevenLabs, and Play.ai), `EmbeddingModelRunner` (dense vector embeddings over OpenAI and Gemini), and `StreamingTextModelRunner` (SSE token streaming over OpenAI and Anthropic). Each follows the existing runner pattern — frozen config dataclass, thin runner class, frozen response type, provider method, factory entry — while introducing targeted HTTP transport upgrades (binary response bodies, multipart form-data uploads, and line-by-line SSE streaming) needed only by these new modalities.

---

## 2. Goals & Non-Goals

### Goals
- Add `AudioModelRunner` with `text_to_speech()` and `speech_to_text()` supporting OpenAI (Whisper, TTS API), ElevenLabs, and Play.ai
- Add `EmbeddingModelRunner` with a single `run()` method that accepts one or many texts, supporting OpenAI and Gemini
- Add `StreamingTextModelRunner` with a `stream()` method that yields text chunks as they arrive, supporting OpenAI and Anthropic
- Add `AUDIO` and `EMBEDDING` to the `ModelModality` enum and wire them through `ModalityDetector`
- Add `ELEVENLABS` and `PLAYAI` to the `ModelProvider` enum with full registry entries
- Extend `HttpTransport` with `stream_request()` (SSE line iterator) and `request_bytes()` (binary response) and `upload_multipart()` (form-data) — without breaking the existing `request()` contract
- Provide an `EmbeddingModelRunnerProvider` bridge so `SemanticSearchTool` can use `EmbeddingModelRunner` directly as its `embedding_provider`
- Export all new types from the existing public namespaces (`lib/runners/__init__`, `lib/config/__init__`, etc.)

### Non-Goals
- Streaming support for Gemini, XAI, DeepSeek, GLM, MiniMax, or OpenRouter providers (Phase 2)
- Embedding support for Anthropic, XAI, or DeepSeek (no public embedding API at time of writing)
- Audio support for Gemini, Anthropic, or XAI providers
- Real-time audio WebSocket streaming (Push-to-Talk / live transcription)
- Audio file storage or binary persistence utilities
- Breaking changes to any existing runner, config, or provider interface

---

## 3. Background & Context

The codebase has a well-established runner pattern: `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner` each own a frozen config dataclass, a thin runner class, a frozen response dataclass, and a provider adapter method. This pattern is consistent across all three existing runners, making Audio and Embedding the natural next modalities.

**Audio gap:** There is no way to call a TTS or STT API through the SDK. Users who need speech synthesis or transcription must reach the provider APIs directly, losing config validation, API key resolution, and transport injection.

**Embedding gap:** `SemanticSearchTool` already has an `EmbeddingProvider` protocol and cosine similarity ranking, but it ships without a real provider implementation. Without a real embedding runner, users fall back to token-overlap scoring, which is significantly worse for semantic queries. `EmbeddingModelRunner` directly bridges this gap.

**Streaming gap:** `TextModelRunner.run()` holds the HTTP connection open until the provider returns the full response. Agent loops that want to display incremental output — a critical UX pattern — have no way to stream tokens today.

**HTTP transport constraints:** The existing `HttpTransport` stores all responses as decoded UTF-8 strings. Binary TTS audio, multipart STT uploads, and SSE streaming all require distinct HTTP behavior that doesn't fit the current interface. Extending `HttpTransport` with three new methods is the minimal, backward-compatible approach.

---

## 4. Requirements

### Functional Requirements

1. `AudioModelRunner(config)` or `AudioModelRunner(provider=..., model=...)` must initialize from either form, matching existing runner ergonomics.
2. `AudioModelRunner.text_to_speech(text: str) -> AudioModelResponse` must call the provider TTS endpoint and return audio bytes plus metadata.
3. `AudioModelRunner.speech_to_text(audio: bytes, *, format: str = "mp3") -> AudioModelResponse` must call the provider STT endpoint and return a transcript string.
4. `AudioModelConfig` must validate that the provider is one of `{openai, elevenlabs, playai}` and that the model is non-empty.
5. `EmbeddingModelRunner(config)` or `EmbeddingModelRunner(provider=..., model=...)` must initialize from either form.
6. `EmbeddingModelRunner.run(texts: str | list[str]) -> EmbeddingResponse` must return one embedding vector per input text, normalized to a list even for single-string inputs.
7. `EmbeddingModelConfig` must validate that the provider is one of `{openai, gemini}`.
8. `StreamingTextModelRunner(config)` or `StreamingTextModelRunner(provider=..., model=...)` must initialize from `TextModelConfig` (no separate config class).
9. `StreamingTextModelRunner.stream(prompt: str, *, system: str | None = None, ...) -> Iterator[str]` must yield text chunk strings as they arrive from the provider SSE stream.
10. `StreamingTextModelRunner` must validate that the provider supports streaming (`openai`, `anthropic`); unsupported providers raise `UnsupportedProviderError` at init time.
11. `ELEVENLABS` and `PLAYAI` must be new `ModelProvider` enum members with API key env vars and default endpoints in `ProviderModelRegistry`.
12. `AUDIO` and `EMBEDDING` must be new `ModelModality` enum members; known model names (whisper-1, tts-1, text-embedding-3-small, etc.) must be added to `_MODEL_NAME_MODALITY_MAP`.
13. `ModalityDetector.create_runner()` must return `AudioModelRunner` for `AUDIO` modality and `EmbeddingModelRunner` for `EMBEDDING` modality.
14. `EmbeddingModelRunnerProvider` must implement the existing `EmbeddingProvider` protocol so it can be passed directly to `SemanticSearchTool(embedding_provider=...)`.
15. All new types must be exported from `vidbyte/lib/runners/__init__.py` and `vidbyte/lib/config/__init__.py`.

### Non-Functional Requirements
- No existing test must break; all new runner tests must be runnable with `python -m pytest tests/` without live API credentials (all tests use `FakeTransport`).
- `HttpTransport.request()` signature and behavior must be unchanged.
- `HttpResponse` binary extension must be backward-compatible — `body: str` remains; `raw_bytes: bytes | None = None` is added as an optional field.
- `stream_request()` must be a synchronous generator; no `async`/`asyncio` introduced in this PR.
- Provider-level changes (adding new methods to `OpenAIProvider`, `AnthropicProvider`, etc.) must not touch existing method signatures.

---

## 5. High-Level Design

Three new runners follow the identical constructor/config/response/provider/factory chain used by `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner`. Each new modality is a vertical slice through the same six-layer stack: enum → config dataclass → response type → runner → provider method → factory entry.

The only cross-cutting infrastructure work is in `HttpTransport`, which gains three narrow new methods: `request_bytes()` for TTS binary audio bodies, `upload_multipart()` for STT audio file uploads, and `stream_request()` for SSE streaming. These do not change the existing `request()` method. `HttpResponse` gains an optional `raw_bytes: bytes | None = None` field; existing code ignores it.

```
[AudioModelRunner / EmbeddingModelRunner / StreamingTextModelRunner]
       │                     │                        │
       │  AudioModelConfig   │  EmbeddingModelConfig  │  TextModelConfig (reused)
       │                     │                        │
[ModelProviders.audio()]  [ModelProviders.embedding()]  [ModelProviders.streaming_text()]
       │                     │                        │
[ElevenLabsProvider]      [OpenAIProvider]          [OpenAIProvider]
[PlayAIProvider]          [GeminiProvider]          [AnthropicProvider]
[OpenAIProvider]               │                        │
       │                 run_embedding()         stream_text()
  run_tts()                    │                        │
  run_stt()            [HttpTransport.request()]  [HttpTransport.stream_request()]
       │
[HttpTransport.request_bytes()]   ← TTS binary audio
[HttpTransport.upload_multipart()] ← STT form-data
```

`EmbeddingModelRunnerProvider` is a thin bridge class in `semantic.py` that wraps `EmbeddingModelRunner` and implements the existing `EmbeddingProvider` protocol. This requires zero changes to `SemanticSearchTool` itself.

---

## 6. Detailed Design

### 6.1 `ModelModality` — Add AUDIO and EMBEDDING

**File(s):** `vidbyte/lib/enums/model_modality.py`
**Type:** Modified

#### What it does
Extends the modality enum with two new values and adds known model names to the lookup map.

#### Interface / API
```python
class ModelModality(str, Enum):
    AUTO = "auto"
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"       # NEW
    EMBEDDING = "embedding"  # NEW
```

New entries in `_MODEL_NAME_MODALITY_MAP`:
```python
# OpenAI audio
"whisper-1": ModelModality.AUDIO,
"whisper-2": ModelModality.AUDIO,
"tts-1": ModelModality.AUDIO,
"tts-1-hd": ModelModality.AUDIO,
"gpt-4o-realtime-preview": ModelModality.AUDIO,
# ElevenLabs audio
"eleven_multilingual_v2": ModelModality.AUDIO,
"eleven_turbo_v2_5": ModelModality.AUDIO,
# Play.ai audio
"PlayDialog": ModelModality.AUDIO,
"PlayDialogMultilingual": ModelModality.AUDIO,
# OpenAI embeddings
"text-embedding-3-small": ModelModality.EMBEDDING,
"text-embedding-3-large": ModelModality.EMBEDDING,
"text-embedding-ada-002": ModelModality.EMBEDDING,
# Gemini embeddings
"text-embedding-004": ModelModality.EMBEDDING,
"embedding-001": ModelModality.EMBEDDING,
```

New substring/prefix patterns in `_SUBSTRING_MODALITY_MAP`:
```python
("whisper", ModelModality.AUDIO),
("tts-", ModelModality.AUDIO),
("eleven_", ModelModality.AUDIO),
("PlayDialog", ModelModality.AUDIO),
("text-embedding", ModelModality.EMBEDDING),
("embedding-", ModelModality.EMBEDDING),
```

#### Edge Cases & Error Handling
- Unknown audio/embedding model names still fall back to `ModelModality.AUTO` via the existing pattern; no new error paths.

---

### 6.2 `ModelProvider` — Add ELEVENLABS and PLAYAI

**File(s):** `vidbyte/lib/enums/model_provider.py`
**Type:** Modified

#### What it does
Adds two new provider identifiers for audio-only providers.

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
    ELEVENLABS = "elevenlabs"   # NEW
    PLAYAI = "playai"           # NEW
```

#### Edge Cases & Error Handling
- All existing code that switches on `ModelProvider` is exhaustive by case-by-case logic (not `match` statements), so new values are safely ignored by existing paths.

---

### 6.3 `ProviderModelRegistry` — Add ElevenLabs and Play.ai entries

**File(s):** `vidbyte/lib/models/registry.py`
**Type:** Modified

#### What it does
Registers API key env vars, default endpoints, and default models for ElevenLabs and Play.ai.

#### Interface / API
```python
# New entries in DEFAULT_PROVIDER_MODELS
ModelProvider.ELEVENLABS: "eleven_multilingual_v2",
ModelProvider.PLAYAI: "PlayDialog",

# New entries in API_KEY_ENV_VARS
ModelProvider.ELEVENLABS: "ELEVENLABS_API_KEY",
ModelProvider.PLAYAI: "PLAYAI_API_KEY",

# New entries in DEFAULT_ENDPOINTS
ModelProvider.ELEVENLABS: "https://api.elevenlabs.io/v1",
ModelProvider.PLAYAI: "https://api.play.ai/api/v1",
```

#### Edge Cases & Error Handling
- `resolve_api_key()` raises `ConfigurationError` if the env var is absent and no explicit key is provided — same behavior as existing providers.

---

### 6.4 `AudioModelConfig` and `EmbeddingModelConfig`

**File(s):** `vidbyte/lib/dataclasses/model_configs.py`
**Type:** Modified

#### What it does
Adds two new frozen dataclasses following the exact pattern of `ImageModelConfig` and `VideoModelConfig`.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class AudioModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    voice: str | None = None          # TTS voice identifier
    speed: float | None = None        # TTS playback speed (0.25–4.0)
    response_format: str | None = None  # "mp3", "opus", "aac", "flac", "wav", "pcm"
    language: str | None = None       # STT language hint (BCP-47)
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider: ...
    def validate(self) -> None: ...  # checks provider in AUDIO_SUPPORTED_PROVIDERS
    def resolved_api_key(self) -> str: ...
    def resolved_endpoint(self) -> str: ...

AUDIO_SUPPORTED_PROVIDERS = {ModelProvider.OPENAI, ModelProvider.ELEVENLABS, ModelProvider.PLAYAI}


@dataclass(frozen=True, slots=True)
class EmbeddingModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    dimensions: int | None = None     # OpenAI allows truncation to fewer dims
    input_type: str | None = None     # Gemini uses "RETRIEVAL_DOCUMENT" etc.
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 60.0

    def normalized_provider(self) -> ModelProvider: ...
    def validate(self) -> None: ...  # checks provider in EMBEDDING_SUPPORTED_PROVIDERS
    def resolved_api_key(self) -> str: ...
    def resolved_endpoint(self) -> str: ...

EMBEDDING_SUPPORTED_PROVIDERS = {ModelProvider.OPENAI, ModelProvider.GEMINI}
```

#### Logic / Algorithm
`validate()` follows the same sequence as `ImageModelConfig.validate()`:
1. Normalize provider enum
2. Assert provider in supported set, raising `UnsupportedProviderError` if not
3. Assert model is non-empty string
4. Validate optional numeric fields (speed in 0.25–4.0, dimensions > 0)
5. Call `resolved_api_key()` to confirm key is available

#### Edge Cases & Error Handling
- `speed` outside the valid range raises `ConfigurationError` with a clear message.
- Unknown provider string raises `ConfigurationError` from `normalized_provider()`.

---

### 6.5 `lib/config/__init__.py` and `lib/config/models.py`

**File(s):** `vidbyte/lib/config/__init__.py`, `vidbyte/lib/config/models.py`
**Type:** Modified

#### What it does
Re-exports `AudioModelConfig` and `EmbeddingModelConfig` into the public `vidbyte.lib.config` namespace.

#### Interface / API
```python
# lib/config/models.py — add two imports
from vidbyte.lib.dataclasses.model_configs import AudioModelConfig, EmbeddingModelConfig, ...

# lib/config/__init__.py — add two exports
from vidbyte.lib.dataclasses.model_configs import AudioModelConfig, EmbeddingModelConfig
__all__ = [..., "AudioModelConfig", "EmbeddingModelConfig"]
```

---

### 6.6 `AudioModelResponse` and `EmbeddingResponse`

**File(s):** `vidbyte/lib/runners/types.py`
**Type:** Modified

#### What it does
Adds two new frozen response dataclasses.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class AudioModelResponse:
    provider: ModelProvider
    model: str
    audio_bytes: bytes | None          # populated by TTS; None for STT
    transcript: str | None             # populated by STT; None for TTS
    raw: Mapping[str, Any]             # raw provider JSON (STT) or empty dict (TTS)
    usage: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingResponse:
    provider: ModelProvider
    model: str
    embeddings: tuple[tuple[float, ...], ...]  # one vector per input text
    raw: Mapping[str, Any]
    usage: Mapping[str, Any] | None = None
```

#### Edge Cases & Error Handling
- Exactly one of `audio_bytes`/`transcript` will be non-None; callers check which they need.
- `embeddings` is a tuple of tuples (immutable, frozen-safe); vector count equals input text count.

---

### 6.7 `HttpTransport` — Binary, Multipart, and Streaming Extensions

**File(s):** `vidbyte/lib/http/transport.py`
**Type:** Modified

#### What it does
Adds three new methods to `HttpTransport` without touching `request()`. Also adds optional `raw_bytes: bytes | None = None` field to `HttpResponse`.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str
    headers: Mapping[str, str]
    raw_bytes: bytes | None = None    # NEW — populated by request_bytes(); None otherwise


class HttpTransport:
    def request(...) -> HttpResponse: ...  # UNCHANGED

    def request_bytes(self, *, method: str, url: str, headers: Mapping[str, str],
                      json_body: Mapping[str, object] | None = None,
                      timeout_seconds: float = 120.0) -> HttpResponse:
        # Like request() but stores response as raw_bytes instead of decoded body string.
        # Used for TTS endpoints that return binary audio data.

    def upload_multipart(self, *, url: str, headers: Mapping[str, str],
                         fields: Mapping[str, str],
                         file_field: str, file_bytes: bytes,
                         file_name: str, file_content_type: str,
                         timeout_seconds: float = 120.0) -> HttpResponse:
        # Sends a multipart/form-data POST. Used for STT audio file uploads.
        # Returns a normal HttpResponse (JSON body).

    def stream_request(self, *, method: str, url: str, headers: Mapping[str, str],
                       json_body: Mapping[str, object] | None = None,
                       timeout_seconds: float = 120.0) -> Iterator[str]:
        # Opens an SSE connection and yields raw data lines one at a time.
        # Yields only lines that start with "data: " after stripping the prefix.
        # Stops when it sees "data: [DONE]" or the connection closes.
```

#### Logic / Algorithm — `request_bytes()`
1. Build `Request` the same way as `_send_once()`.
2. Open with `urlopen`. On success, read `.read()` as `bytes` and store in `raw_bytes`.
3. Set `body = ""` (empty string, safe for existing callers).
4. On `HTTPError`, read error body as bytes and decode as `utf-8` for `body`.

#### Logic / Algorithm — `upload_multipart()`
1. Build a multipart boundary string (UUID-based).
2. Encode each text field + the file field manually into bytes following RFC 2046.
3. Set `Content-Type: multipart/form-data; boundary=<boundary>`.
4. Send via `_send_once()` equivalent.
5. Return `HttpResponse` with JSON body decoded normally.

#### Logic / Algorithm — `stream_request()`
1. Build `Request` with the SSE accept header (`Accept: text/event-stream`).
2. Open with `urlopen` in a context manager (no `.read()` — leaves connection open).
3. Iterate `response` line-by-line (yields `bytes` per line from urllib).
4. Decode each line as UTF-8. Skip blank lines, `event:` lines, `comment:` lines.
5. For lines starting with `"data: "`: strip prefix, yield the remainder.
6. If the remainder is `"[DONE]"`: return (stop iteration).

#### Edge Cases & Error Handling
- `request_bytes()`: non-2xx status codes raise `ProviderRequestError` exactly like `parse_json_response()` does.
- `upload_multipart()`: malformed multipart responses raise `ProviderRequestError`.
- `stream_request()`: `URLError` mid-stream raises `ProviderRequestError`. Partial final chunks (incomplete JSON) are yielded as-is; the calling provider is responsible for parsing.

---

### 6.8 `AudioModelRunner`

**File(s):** `vidbyte/lib/runners/audio.py`
**Type:** New file

#### What it does
Thin runner for TTS and STT. Identical ergonomics to `ImageModelRunner` and `VideoModelRunner`.

#### Interface / API
```python
class AudioModelRunner:
    """Semantic runner for text-to-speech and speech-to-text models."""

    def __init__(self, config: AudioModelConfig | None = None, *,
                 provider: ModelProvider | str | None = None,
                 model: str | None = None,
                 transport: HttpTransport | None = None,
                 **config_options: Any) -> None:
        # Coerce config, validate, build provider adapter.

    def text_to_speech(self, text: str) -> AudioModelResponse:
        # Call provider TTS endpoint and return binary audio + metadata.

    def speech_to_text(self, audio: bytes, *, format: str = "mp3") -> AudioModelResponse:
        # Upload audio to provider STT endpoint and return transcript.

    def model_name(self) -> str:
        # Return the configured model string.

    def _coerce_config(self, config, *, provider, model, config_options) -> AudioModelConfig:
        # Raise ConfigurationError if neither config nor provider+model given.
```

#### Logic / Algorithm — `text_to_speech()`
1. Call `self._provider.run_tts(text=text, transport=self._transport)`.
2. Return the `AudioModelResponse` directly.

#### Logic / Algorithm — `speech_to_text()`
1. Call `self._provider.run_stt(audio=audio, format=format, transport=self._transport)`.
2. Return the `AudioModelResponse` directly.

#### Edge Cases & Error Handling
- Empty `text` string is allowed (provider will handle it or return empty audio).
- Zero-byte `audio` raises `ConfigurationError` before the HTTP call.

---

### 6.9 `EmbeddingModelRunner`

**File(s):** `vidbyte/lib/runners/embedding.py`
**Type:** New file

#### What it does
Thin runner for dense vector embeddings.

#### Interface / API
```python
class EmbeddingModelRunner:
    """Semantic runner for dense vector embedding models."""

    def __init__(self, config: EmbeddingModelConfig | None = None, *,
                 provider: ModelProvider | str | None = None,
                 model: str | None = None,
                 transport: HttpTransport | None = None,
                 **config_options: Any) -> None:

    def run(self, texts: str | list[str]) -> EmbeddingResponse:
        # Normalize texts to list, call provider, return EmbeddingResponse.

    def model_name(self) -> str: ...

    def _coerce_config(...) -> EmbeddingModelConfig: ...

    def _normalize_texts(self, texts: str | list[str]) -> list[str]:
        # Convert scalar to single-item list; validate list is non-empty.
```

#### Logic / Algorithm — `run()`
1. Normalize `texts` via `_normalize_texts()`.
2. Call `self._provider.run_embedding(texts=texts, transport=self._transport)`.
3. Return `EmbeddingResponse`.

#### Edge Cases & Error Handling
- Empty list `[]` raises `ConfigurationError` before the HTTP call.
- Single string `""` is passed through; provider returns a zero-vector or error.
- Vector count mismatch between input texts and returned embeddings raises `ProviderResponseError`.

---

### 6.10 `StreamingTextModelRunner`

**File(s):** `vidbyte/lib/runners/streaming_text.py`
**Type:** New file

#### What it does
Thin runner for SSE token streaming. Reuses `TextModelConfig` — no separate config class.

#### Interface / API
```python
from collections.abc import Iterable, Iterator

class StreamingTextModelRunner:
    """Semantic runner for streaming text generation models."""

    STREAMING_SUPPORTED_PROVIDERS = {ModelProvider.OPENAI, ModelProvider.ANTHROPIC}

    def __init__(self, config: TextModelConfig | None = None, *,
                 provider: ModelProvider | str | None = None,
                 model: str | None = None,
                 transport: HttpTransport | None = None,
                 **config_options: Any) -> None:
        # Validate provider is in STREAMING_SUPPORTED_PROVIDERS at init time.

    def stream(self, prompt: str, *, system: str | None = None,
               metadata: Mapping[str, object] | None = None,
               tools: Iterable[Mapping[str, Any]] = (),
               tool_choice: str | Mapping[str, Any] | None = None,
               messages: Iterable[Mapping[str, Any]] = ()) -> Iterator[str]:
        # Yield text chunk strings as they arrive from the provider SSE stream.

    def model_name(self) -> str: ...

    def _coerce_config(...) -> TextModelConfig: ...

    def _validate_streaming_provider(self, provider: ModelProvider) -> None:
        # Raise UnsupportedProviderError if provider not in STREAMING_SUPPORTED_PROVIDERS.
```

#### Logic / Algorithm — `stream()`
1. Build `call_config` via `dataclasses.replace()` to merge per-call overrides (same as `TextModelRunner.run()`).
2. Call `self._provider.stream_text(prompt=prompt, system=system, metadata=metadata, transport=self._transport, config=call_config)`.
3. `yield from` the returned iterator.

#### Edge Cases & Error Handling
- Unsupported provider raises `UnsupportedProviderError` at `__init__` time, not at `stream()` call time.
- If the SSE stream closes unexpectedly mid-generation, `ProviderRequestError` propagates to the caller.
- Empty `prompt` is passed through; provider behavior is provider-defined.

---

### 6.11 `OpenAIProvider` — TTS, STT, Embedding, Streaming Text

**File(s):** `vidbyte/providers/openai.py`
**Type:** Modified

#### What it does
Adds four new methods alongside the existing `run_text()`, `run_image()`, and `create_video()`.

#### Interface / API
```python
def run_tts(self, *, text: str, transport: HttpTransport,
            config: AudioModelConfig | None = None) -> AudioModelResponse:
    # POST /audio/speech → binary MP3/WAV bytes.

def run_stt(self, *, audio: bytes, format: str, transport: HttpTransport,
            config: AudioModelConfig | None = None) -> AudioModelResponse:
    # POST /audio/transcriptions (multipart) → transcript JSON.

def run_embedding(self, *, texts: list[str], transport: HttpTransport,
                  config: EmbeddingModelConfig | None = None) -> EmbeddingResponse:
    # POST /embeddings → list of float vectors.

def stream_text(self, *, prompt: str, system: str | None,
                metadata: Mapping[str, object] | None,
                transport: HttpTransport,
                config: TextModelConfig | None = None) -> Iterator[str]:
    # POST /responses with stream=True; yield text deltas from SSE events.
```

#### Logic / Algorithm — `run_tts()`
1. Build payload: `{"model": config.model, "input": text, "voice": config.voice or "alloy", "response_format": config.response_format or "mp3"}`.
2. Call `transport.request_bytes(method="POST", url=f"{endpoint}/audio/speech", ...)`.
3. Return `AudioModelResponse(audio_bytes=response.raw_bytes, transcript=None, raw={}, ...)`.

#### Logic / Algorithm — `run_stt()`
1. Call `transport.upload_multipart(url=f"{endpoint}/audio/transcriptions", fields={"model": config.model, "language": config.language or ""}, file_field="file", file_bytes=audio, file_name=f"audio.{format}", ...)`.
2. Parse JSON body via `_parser.parse_json_response()`.
3. Extract `parsed["text"]` as transcript string.
4. Return `AudioModelResponse(audio_bytes=None, transcript=transcript, raw=parsed, ...)`.

#### Logic / Algorithm — `run_embedding()`
1. Build payload: `{"model": config.model, "input": texts}`. Add `dimensions` if set.
2. Call `transport.request()`.
3. Parse JSON. Extract `parsed["data"]` list. Each item has `item["embedding"]` (list of floats) and `item["index"]`.
4. Sort by `index`, convert each embedding to `tuple[float, ...]`.
5. Return `EmbeddingResponse(embeddings=tuple(vectors), ...)`.

#### Logic / Algorithm — `stream_text()`
1. Build payload same as `_create_text_payload()` but add `"stream": True`.
2. Call `transport.stream_request(method="POST", url=f"{endpoint}/responses", ...)`.
3. For each yielded SSE line: `json.loads(line)`. If `event.type == "response.text.delta"`: `yield event["delta"]`. If type is `"response.done"` or `"done"`: return.

#### Edge Cases & Error Handling
- `run_tts()`: zero-length `raw_bytes` raises `ProviderResponseError`.
- `run_stt()`: missing `"text"` key in JSON raises `ProviderResponseError`.
- `run_embedding()`: `data` list length != `len(texts)` raises `ProviderResponseError`.
- `stream_text()`: malformed SSE JSON lines are silently skipped (partial delta vs. protocol event).

---

### 6.12 `AnthropicProvider` — Streaming Text

**File(s):** `vidbyte/providers/anthropic.py`
**Type:** Modified

#### What it does
Adds `stream_text()` alongside `run_text()`.

#### Interface / API
```python
def stream_text(self, *, prompt: str, system: str | None,
                metadata: Mapping[str, object] | None,
                transport: HttpTransport,
                config: TextModelConfig | None = None) -> Iterator[str]:
    # POST /messages with stream=True; yield text from content_block_delta events.
```

#### Logic / Algorithm — `stream_text()`
1. Build payload same as `_create_payload()` but add `"stream": True`.
2. Call `transport.stream_request(method="POST", url=f"{endpoint}/messages", headers=self._create_headers(config), ...)`.
3. For each SSE line: parse JSON. If `type == "content_block_delta"` and `delta.type == "text_delta"`: `yield delta["text"]`. If `type == "message_stop"`: return.

---

### 6.13 `GeminiProvider` — Embeddings

**File(s):** `vidbyte/providers/gemini.py`
**Type:** Modified

#### What it does
Adds `run_embedding()` using Gemini's `embedContent` endpoint.

#### Interface / API
```python
def run_embedding(self, *, texts: list[str], transport: HttpTransport,
                  config: EmbeddingModelConfig | None = None) -> EmbeddingResponse:
    # POST /models/{model}:batchEmbedContents → list of float vectors.
```

#### Logic / Algorithm — `run_embedding()`
1. Build Gemini batch embedding payload: `{"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t}]}, "taskType": config.input_type or "RETRIEVAL_DOCUMENT"} for t in texts]}`.
2. POST to `{endpoint}/models/{model}:batchEmbedContents?key={api_key}`.
3. Parse response `embeddings` list; each item has `values` (list of floats).
4. Return `EmbeddingResponse`.

---

### 6.14 `ElevenLabsProvider`

**File(s):** `vidbyte/providers/elevenlabs.py`
**Type:** New file

#### What it does
TTS-only provider for ElevenLabs.

#### Interface / API
```python
class ElevenLabsProvider:
    provider = ModelProvider.ELEVENLABS

    def __init__(self, *, audio_config: AudioModelConfig | None = None, ...) -> None: ...

    def run_tts(self, *, text: str, transport: HttpTransport,
                config: AudioModelConfig | None = None) -> AudioModelResponse:
        # POST /text-to-speech/{voice_id} → binary audio bytes.
```

#### Logic / Algorithm — `run_tts()`
1. Extract `voice_id` from `config.voice` (required; raises `ConfigurationError` if None).
2. POST to `{endpoint}/text-to-speech/{voice_id}` with JSON body `{"text": text, "model_id": config.model}`.
3. Set `Accept: audio/mpeg` header (ElevenLabs returns binary directly).
4. Call `transport.request_bytes()`.
5. Return `AudioModelResponse(audio_bytes=response.raw_bytes, ...)`.

#### Edge Cases & Error Handling
- `voice` is required for ElevenLabs (unlike OpenAI where it defaults to "alloy"). Raises `ConfigurationError` if not set.

---

### 6.15 `PlayAIProvider`

**File(s):** `vidbyte/providers/playai.py`
**Type:** New file

#### What it does
TTS-only provider for Play.ai.

#### Interface / API
```python
class PlayAIProvider:
    provider = ModelProvider.PLAYAI

    def __init__(self, *, audio_config: AudioModelConfig | None = None, ...) -> None: ...

    def run_tts(self, *, text: str, transport: HttpTransport,
                config: AudioModelConfig | None = None) -> AudioModelResponse:
        # POST /tts → binary audio or job response depending on model.
```

#### Logic / Algorithm — `run_tts()`
1. POST to `{endpoint}/tts` with JSON: `{"model": config.model, "voice": config.voice, "text": text, "outputFormat": config.response_format or "mp3"}`.
2. Play.ai returns synchronous binary audio for PlayDialog. Call `transport.request_bytes()`.
3. Return `AudioModelResponse(audio_bytes=response.raw_bytes, ...)`.

#### Edge Cases & Error Handling
- `voice` is required for Play.ai. Raises `ConfigurationError` if not set.

---

### 6.16 `ModelProviders` Factory — audio, embedding, streaming_text

**File(s):** `vidbyte/providers/__init__.py`
**Type:** Modified

#### What it does
Adds three new factory methods following the exact pattern of `text()`, `image()`, `video()`.

#### Interface / API
```python
@staticmethod
def audio(config: AudioModelConfig) -> OpenAIProvider | ElevenLabsProvider | PlayAIProvider:
    # Return an audio-capable adapter for the requested provider.
    providers = {
        ModelProvider.OPENAI: OpenAIProvider,
        ModelProvider.ELEVENLABS: ElevenLabsProvider,
        ModelProvider.PLAYAI: PlayAIProvider,
    }
    return ModelProviders._build_audio_provider(config, providers)

@staticmethod
def embedding(config: EmbeddingModelConfig) -> OpenAIProvider | GeminiProvider:
    providers = {ModelProvider.OPENAI: OpenAIProvider, ModelProvider.GEMINI: GeminiProvider}
    return ModelProviders._build_embedding_provider(config, providers)

@staticmethod
def streaming_text(config: TextModelConfig) -> OpenAIProvider | AnthropicProvider:
    providers = {ModelProvider.OPENAI: OpenAIProvider, ModelProvider.ANTHROPIC: AnthropicProvider}
    return ModelProviders._build_streaming_text_provider(config, providers)
```

---

### 6.17 `ModalityDetector` — AUDIO and EMBEDDING routing

**File(s):** `vidbyte/lib/agents/modality_detector.py`
**Type:** Modified

#### What it does
Extends `is_*` predicates, `create_runner()`, and `_SUBSTRING_MODALITY_MAP` / `_PREFIX_MODALITY_MAP` for the two new modalities.

#### Interface / API
```python
@staticmethod
def is_audio(model_name: str) -> bool:
    """Return True when the model name maps to audio modality."""

@staticmethod
def is_embedding(model_name: str) -> bool:
    """Return True when the model name maps to embedding modality."""
```

`create_runner()` gains two new branches:
```python
if resolved is ModelModality.AUDIO:
    from vidbyte.lib.runners.audio import AudioModelRunner
    return AudioModelRunner(
        ModalityDetector.build_config(AudioModelConfig, provider=provider, model=model, options=common_options),
        transport=transport,
    )
if resolved is ModelModality.EMBEDDING:
    from vidbyte.lib.runners.embedding import EmbeddingModelRunner
    return EmbeddingModelRunner(
        ModalityDetector.build_config(EmbeddingModelConfig, provider=provider, model=model, options=common_options),
        transport=transport,
    )
```

New substring patterns added to `_SUBSTRING_MODALITY_MAP`:
```python
("whisper", ModelModality.AUDIO),
("tts-", ModelModality.AUDIO),
("eleven_", ModelModality.AUDIO),
("text-embedding", ModelModality.EMBEDDING),
("embedding-", ModelModality.EMBEDDING),
```

---

### 6.18 `EmbeddingModelRunnerProvider` Bridge

**File(s):** `vidbyte/tools/builtins/code_search/semantic.py`
**Type:** Modified

#### What it does
Adds a concrete adapter class that implements the existing `EmbeddingProvider` protocol using `EmbeddingModelRunner`. This allows callers to pass a real embedding runner to `SemanticSearchTool` without any changes to `SemanticSearchTool` itself.

#### Interface / API
```python
class EmbeddingModelRunnerProvider:
    """Adapts EmbeddingModelRunner to the EmbeddingProvider protocol."""

    def __init__(self, runner: "EmbeddingModelRunner") -> None:
        # Store the runner reference.

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        # Delegate to runner.run() and return list of embedding vectors.
        response = self._runner.run(list(texts))
        return [list(vector) for vector in response.embeddings]
```

#### Logic / Algorithm
1. `embed()` calls `self._runner.run(list(texts))`.
2. Unwraps `response.embeddings` (tuple of tuples) into a list of lists.
3. Returns the list — compatible with the `Sequence[Sequence[float]]` protocol return type.

#### Edge Cases & Error Handling
- Empty `texts` sequence: `EmbeddingModelRunner.run([])` raises `ConfigurationError` before the HTTP call.
- Provider errors propagate as `ProviderRequestError` to `SemanticSearchTool.rebuild_index()`, which wraps them in a `ToolResult.error()`.

---

### 6.19 `lib/runners/__init__.py`

**File(s):** `vidbyte/lib/runners/__init__.py`
**Type:** Modified

#### What it does
Adds new runner classes, response types, and the bridge adapter to `__all__` with the same lazy-import pattern as existing runners.

#### Interface / API
```python
__all__ = [
    # existing...
    "AudioModelResponse",
    "AudioModelRunner",
    "EmbeddingModelRunner",
    "EmbeddingModelRunnerProvider",
    "EmbeddingResponse",
    "StreamingTextModelRunner",
]

def __getattr__(name: str) -> object:
    if name == "AudioModelRunner":
        from vidbyte.lib.runners.audio import AudioModelRunner
        return AudioModelRunner
    if name == "EmbeddingModelRunner":
        from vidbyte.lib.runners.embedding import EmbeddingModelRunner
        return EmbeddingModelRunner
    if name == "StreamingTextModelRunner":
        from vidbyte.lib.runners.streaming_text import StreamingTextModelRunner
        return StreamingTextModelRunner
    # ... existing cases ...
    raise AttributeError(name)
```

---

## 7. Data Model Changes

N/A — This feature adds no database tables, migrations, or persistent storage. All new types are in-memory dataclasses.

---

## 8. API Changes

N/A — This is a pure library SDK feature with no HTTP API endpoints. All interfaces are Python class/method surfaces documented in Section 6.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/new-runners.md` | This design document |
| MODIFY | `vidbyte/lib/enums/model_modality.py` | Add AUDIO, EMBEDDING to ModelModality; add model name entries to lookup map |
| MODIFY | `vidbyte/lib/enums/model_provider.py` | Add ELEVENLABS, PLAYAI enum members |
| MODIFY | `vidbyte/lib/models/registry.py` | Add env vars, endpoints, default models for ElevenLabs and Play.ai |
| MODIFY | `vidbyte/lib/dataclasses/model_configs.py` | Add AudioModelConfig, EmbeddingModelConfig frozen dataclasses |
| MODIFY | `vidbyte/lib/config/models.py` | Re-export AudioModelConfig, EmbeddingModelConfig |
| MODIFY | `vidbyte/lib/config/__init__.py` | Export AudioModelConfig, EmbeddingModelConfig |
| MODIFY | `vidbyte/lib/runners/types.py` | Add AudioModelResponse, EmbeddingResponse frozen dataclasses |
| MODIFY | `vidbyte/lib/http/transport.py` | Add raw_bytes to HttpResponse; add request_bytes(), upload_multipart(), stream_request() |
| MODIFY | `vidbyte/lib/http/__init__.py` | No change needed (HttpResponse already re-exported; raw_bytes is additive) |
| CREATE | `vidbyte/lib/runners/audio.py` | AudioModelRunner class |
| CREATE | `vidbyte/lib/runners/embedding.py` | EmbeddingModelRunner class |
| CREATE | `vidbyte/lib/runners/streaming_text.py` | StreamingTextModelRunner class |
| MODIFY | `vidbyte/lib/runners/__init__.py` | Add new runners + types to __all__ and lazy __getattr__ |
| MODIFY | `vidbyte/providers/openai.py` | Add run_tts(), run_stt(), run_embedding(), stream_text() |
| MODIFY | `vidbyte/providers/anthropic.py` | Add stream_text() |
| MODIFY | `vidbyte/providers/gemini.py` | Add run_embedding() |
| CREATE | `vidbyte/providers/elevenlabs.py` | ElevenLabsProvider (TTS-only) |
| CREATE | `vidbyte/providers/playai.py` | PlayAIProvider (TTS-only) |
| MODIFY | `vidbyte/providers/__init__.py` | Import ElevenLabsProvider, PlayAIProvider; add ModelProviders.audio(), embedding(), streaming_text() |
| MODIFY | `vidbyte/lib/agents/modality_detector.py` | Add is_audio(), is_embedding(); extend create_runner() for AUDIO/EMBEDDING; update substring/prefix maps |
| MODIFY | `vidbyte/tools/builtins/code_search/semantic.py` | Add EmbeddingModelRunnerProvider bridge class |
| CREATE | `tests/test_audio_runner.py` | Unit tests for AudioModelRunner (FakeTransport) |
| CREATE | `tests/test_embedding_runner.py` | Unit tests for EmbeddingModelRunner (FakeTransport) |
| CREATE | `tests/test_streaming_text_runner.py` | Unit tests for StreamingTextModelRunner (FakeStreamingTransport) |
| CREATE | `scripts/test-new-runners.py` | Executable verification script covering all test cases |

**Total: 26 files (9 new, 17 modified)**

---

## 10. Testing Plan

### Unit Tests

#### `tests/test_audio_runner.py`

**AudioModelConfig validation:**
- `describe('AudioModelConfig') -> it('should raise ConfigurationError when model is empty string')` — [Edge Case]
- `describe('AudioModelConfig') -> it('should raise UnsupportedProviderError for provider=gemini')` — [Hidden Assumption]
- `describe('AudioModelConfig') -> it('should raise ConfigurationError when speed is 0.0')` — [Edge Case]
- `describe('AudioModelConfig') -> it('should raise ConfigurationError when speed is 5.0')` — [Edge Case]
- `describe('AudioModelConfig') -> it('should raise ConfigurationError when api_key is missing and env var absent')` — [Hidden Assumption]

**AudioModelRunner TTS (OpenAI):**
- `describe('AudioModelRunner') -> it('should call /audio/speech and return audio_bytes from raw_bytes')` — [Silent Failure]
- `describe('AudioModelRunner') -> it('should default voice to alloy when not specified')` — [Hidden Assumption]
- `describe('AudioModelRunner') -> it('should raise ProviderResponseError when raw_bytes is empty bytes')` — [Hidden Failure]
- `describe('AudioModelRunner') -> it('should pass response_format to payload when specified')` — [Silent Failure]

**AudioModelRunner STT (OpenAI):**
- `describe('AudioModelRunner') -> it('should call /audio/transcriptions via multipart and return transcript')` — [Silent Failure]
- `describe('AudioModelRunner') -> it('should raise ConfigurationError when audio bytes is empty')` — [Edge Case]
- `describe('AudioModelRunner') -> it('should raise ProviderResponseError when response lacks text key')` — [Hidden Failure]

**AudioModelRunner TTS (ElevenLabs):**
- `describe('AudioModelRunner') -> it('should call ElevenLabs /text-to-speech/{voice_id} endpoint')` — [Silent Failure]
- `describe('AudioModelRunner') -> it('should raise ConfigurationError when voice is None for ElevenLabs')` — [Hidden Assumption]

**AudioModelRunner TTS (Play.ai):**
- `describe('AudioModelRunner') -> it('should call Play.ai /tts endpoint and return audio_bytes')` — [Silent Failure]
- `describe('AudioModelRunner') -> it('should raise ConfigurationError when voice is None for Play.ai')` — [Hidden Assumption]

**Constructor ergonomics:**
- `describe('AudioModelRunner') -> it('should raise ConfigurationError when neither config nor provider+model given')` — [Edge Case]
- `describe('AudioModelRunner') -> it('should accept provider+model kwargs without explicit config')` — [Hidden Assumption]

#### `tests/test_embedding_runner.py`

**EmbeddingModelConfig validation:**
- `describe('EmbeddingModelConfig') -> it('should raise UnsupportedProviderError for provider=anthropic')` — [Hidden Assumption]
- `describe('EmbeddingModelConfig') -> it('should raise ConfigurationError for empty model string')` — [Edge Case]

**EmbeddingModelRunner (OpenAI):**
- `describe('EmbeddingModelRunner') -> it('should call /embeddings and return one vector per input text')` — [Silent Failure]
- `describe('EmbeddingModelRunner') -> it('should accept a single string and return a one-element embeddings tuple')` — [Edge Case]
- `describe('EmbeddingModelRunner') -> it('should raise ConfigurationError when texts list is empty')` — [Edge Case]
- `describe('EmbeddingModelRunner') -> it('should raise ProviderResponseError when data length differs from input length')` — [Hidden Failure]
- `describe('EmbeddingModelRunner') -> it('should sort by index field so out-of-order response vectors align to inputs')` — [Silent Failure]
- `describe('EmbeddingModelRunner') -> it('should pass dimensions to payload when set in config')` — [Silent Failure]

**EmbeddingModelRunner (Gemini):**
- `describe('EmbeddingModelRunner') -> it('should call Gemini batchEmbedContents and return vectors')` — [Silent Failure]
- `describe('EmbeddingModelRunner') -> it('should pass taskType from input_type when set')` — [Silent Failure]

**EmbeddingModelRunnerProvider bridge:**
- `describe('EmbeddingModelRunnerProvider') -> it('should return list of lists matching SemanticSearchTool EmbeddingProvider protocol')` — [Hidden Assumption]
- `describe('EmbeddingModelRunnerProvider') -> it('should propagate ConfigurationError from runner when texts is empty sequence')` — [Hidden Failure]

#### `tests/test_streaming_text_runner.py`

**StreamingTextModelRunner:**
- `describe('StreamingTextModelRunner') -> it('should raise UnsupportedProviderError at init for provider=gemini')` — [Hidden Assumption]
- `describe('StreamingTextModelRunner') -> it('should yield text chunks from OpenAI SSE response.text.delta events')` — [Silent Failure]
- `describe('StreamingTextModelRunner') -> it('should yield text chunks from Anthropic content_block_delta events')` — [Silent Failure]
- `describe('StreamingTextModelRunner') -> it('should stop iteration on OpenAI response.done event without extra empty yields')` — [Hidden Failure]
- `describe('StreamingTextModelRunner') -> it('should stop iteration on Anthropic message_stop without extra empty yields')` — [Hidden Failure]
- `describe('StreamingTextModelRunner') -> it('should skip non-delta SSE event types silently')` — [Silent Failure]
- `describe('StreamingTextModelRunner') -> it('should propagate ProviderRequestError when stream closes mid-response')` — [Hidden Failure]
- `describe('StreamingTextModelRunner') -> it('should collect all chunks into a complete string matching run() output for simple prompts')` — [Silent Failure]

**HttpTransport.stream_request():**
- `describe('HttpTransport') -> it('should yield one string per data: line stripping the prefix')` — [Silent Failure]
- `describe('HttpTransport') -> it('should stop at data: [DONE] and not yield the DONE sentinel itself')` — [Hidden Assumption]
- `describe('HttpTransport') -> it('should skip blank lines and event: lines')` — [Edge Case]
- `describe('HttpTransport') -> it('should raise ProviderRequestError on URLError mid-stream')` — [Hidden Failure]

**HttpTransport.request_bytes():**
- `describe('HttpTransport') -> it('should return raw_bytes populated and body as empty string')` — [Silent Failure]
- `describe('HttpTransport') -> it('should raise ProviderRequestError on non-2xx status')` — [Hidden Assumption]

**HttpTransport.upload_multipart():**
- `describe('HttpTransport') -> it('should include file field with correct content-type in multipart body')` — [Silent Failure]
- `describe('HttpTransport') -> it('should include text fields before the file field in the multipart body')` — [Hidden Assumption]

### Integration Tests

**Flow: EmbeddingModelRunner → SemanticSearchTool**
- Instantiate `EmbeddingModelRunner` with a `FakeTransport` returning fixed vectors.
- Wrap with `EmbeddingModelRunnerProvider`.
- Pass to `SemanticSearchTool(root_dir=..., embedding_provider=provider)`.
- Call `rebuild_index()` and assert cosine-based ranking overrides token-overlap fallback.
- Silent failure to catch: `EmbeddingModelRunnerProvider.embed()` returning wrong vector count silently corrupts ranking — inject a mock returning fewer vectors than texts and assert `ProviderResponseError` propagates, not a silent zip truncation.

**Flow: StreamingTextModelRunner collecting full output**
- Use `FakeStreamingTransport` that yields pre-baked SSE lines.
- Assert `"".join(runner.stream(prompt))` equals the expected concatenated string.
- Hidden assumption: provider stops emitting after the `[DONE]` sentinel; assert no extra empty strings yielded after stop.

**Flow: AudioModelRunner TTS → binary bytes**
- Use a `FakeTransport` that returns `raw_bytes=b"\xff\xfb\x90\x00"` (synthetic MP3 header).
- Assert `response.audio_bytes` equals the expected bytes.
- Assert `response.transcript` is None.

**What external dependencies need to be mocked:**
- All HTTP calls mocked via `FakeTransport` / `FakeStreamingTransport`. No live API keys required.

### Manual / QA Test Cases

1. Given a valid `OPENAI_API_KEY` env var, when `AudioModelRunner(provider="openai", model="tts-1").text_to_speech("Hello")` is called, then `response.audio_bytes` is non-empty bytes and can be written to a `.mp3` file that plays correctly — [Hidden Assumption: provider returns valid audio encoding]
2. Given a valid `OPENAI_API_KEY`, when `AudioModelRunner(provider="openai", model="whisper-1").speech_to_text(audio_bytes, format="mp3")` is called with a real audio clip, then `response.transcript` contains the spoken words — [Silent Failure: empty transcript returned without error on silence]
3. Given a valid `OPENAI_API_KEY`, when `EmbeddingModelRunner(provider="openai", model="text-embedding-3-small").run(["cat", "kitten", "car"])`, then cosine similarity of embedding[0] and embedding[1] is > similarity of embedding[0] and embedding[2] — [Silent Failure: vectors returned but semantically wrong]
4. Given a valid `OPENAI_API_KEY`, when `"".join(StreamingTextModelRunner(provider="openai", model="gpt-4o").stream("Say hi"))` is called, then the result matches what `TextModelRunner(...).run("Say hi").text` would return — [Silent Failure: stream yields but assembled text differs from blocking call]
5. Given `ELEVENLABS_API_KEY` is set and `voice="Rachel"`, when `AudioModelRunner(provider="elevenlabs", model="eleven_multilingual_v2").text_to_speech("Test")` is called, then `response.audio_bytes` is non-empty and playable — [Hidden Assumption: ElevenLabs voice identifier is valid]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| OpenAI TTS API | `POST /v1/audio/speech` | Text-to-speech audio generation | API changes binary response format |
| OpenAI STT API | `POST /v1/audio/transcriptions` | Speech-to-text transcription | Multipart upload format changes |
| OpenAI Embeddings API | `POST /v1/embeddings` | Dense vector embeddings | Breaking changes to data envelope |
| OpenAI Streaming | `POST /v1/responses` with `stream=True` | SSE token streaming | SSE event type names may change |
| ElevenLabs TTS API | `POST /v1/text-to-speech/{voice_id}` | ElevenLabs text-to-speech | Response format, auth header changes |
| Play.ai TTS API | `POST /api/v1/tts` | Play.ai text-to-speech | Endpoint may differ by account tier |
| Gemini Embeddings API | `POST /v1beta/models/{model}:batchEmbedContents` | Gemini batch embeddings | taskType field semantics may shift |
| Anthropic Streaming | `POST /v1/messages` with `stream=True` | Anthropic SSE streaming | `content_block_delta` schema may evolve |
| stdlib `urllib` | Python 3.11+ | All HTTP I/O (no third-party HTTP lib) | None — same as existing transport |

---

## 12. Rollout & Deployment

- **No feature flags.** All three runners are additive; zero existing code paths are modified.
- **Not a breaking change.** All changes are new symbols or additive fields (`raw_bytes` on `HttpResponse` defaults to `None`).
- **No migration path needed.** The SDK ships as a library; consumers upgrade by changing their import at their own pace.
- **No deployment order.** This is a pure Python library — no service deploy.
- **Rollback:** Revert the PR. No persistent state is touched.
- **Dependency install note:** ElevenLabs and Play.ai require only an API key — no new Python package dependencies. All HTTP is via stdlib `urllib`. `pyproject.toml` does not need changes.

---

## 13. Open Questions

- [ ] **Play.ai endpoint shape:** Play.ai's v1 TTS endpoint may return a streaming audio response (chunked transfer) rather than a single binary blob. Does Play.ai's synchronous TTS return binary bytes or a JSON job ID? Needs verification against current Play.ai API docs before implementation.
- [ ] **ElevenLabs authentication header:** ElevenLabs uses `xi-api-key` header, not `Authorization: Bearer`. The `HttpResponseParser.bearer_headers()` helper is not reusable as-is. ElevenLabsProvider will need its own `_create_headers()` method — confirm this is acceptable.
- [ ] **Streaming for Gemini, XAI, DeepSeek:** Should `StreamingTextModelRunner.__init__` raise `UnsupportedProviderError` eagerly for unsupported providers, or should it fall back silently to blocking mode? Current proposal: raise eagerly.
- [ ] **EmbeddingModelRunner batch size limits:** OpenAI embeds up to 2048 input strings per request. Should `EmbeddingModelRunner.run()` auto-batch large inputs silently, or raise `ConfigurationError` when `len(texts) > 2048`? Current proposal: raise, let the caller batch.
- [ ] **`AudioModelResponse.raw` for TTS:** TTS endpoints return binary, not JSON — `raw` would be an empty dict `{}`. Is this acceptable, or should `raw` be typed as `Mapping[str, Any] | None` with `None` for binary-only responses?

---

## 14. Alternatives Considered

### Alternative 1: Extend TextModelRunner with optional streaming flag
- **What:** Add `stream: bool = False` parameter to `TextModelRunner.run()` and have it return `Union[TextModelResponse, Iterator[str]]`.
- **Why rejected:** Union return types force callers to type-check at runtime. A dedicated `StreamingTextModelRunner` is a clean, predictable interface. The existing runner pattern — one class per modality — is more consistent.

### Alternative 2: Add `audio()` as a method on TextModelRunner
- **What:** Route TTS/STT through TextModelRunner using special model names.
- **Why rejected:** TTS and STT are not text completion. Their request/response shapes are completely different (binary bodies, multipart uploads). A shared runner class would require deeply conditional logic and mislead callers about what `TextModelRunner` does.

### Alternative 3: Use `httpx` or `aiohttp` instead of extending stdlib urllib
- **What:** Replace `HttpTransport` with an httpx-based transport to get built-in streaming and multipart support.
- **Why rejected:** The SDK explicitly avoids third-party dependencies beyond `pydantic` (see `pyproject.toml`). Adding `httpx` is a significant dependency and API surface change. Extending `urllib` manually is more verbose but keeps the zero-dependency contract.

### Alternative 4: Separate AsyncStreamingTextModelRunner using asyncio
- **What:** Implement streaming as an `async def` generator returning `AsyncIterator[str]`.
- **Why rejected:** The entire SDK is synchronous today (no async imports anywhere). Introducing `asyncio` in one runner would require callers to manage an event loop and would look inconsistent with every other part of the SDK. Sync generators with `urllib` line-by-line reading deliver streaming behavior without `asyncio` complexity.

### Alternative 5: Cohere or OpenAI-compatible providers for embeddings
- **What:** Add Cohere as an embedding provider alongside OpenAI and Gemini.
- **Why rejected:** Cohere is not currently in the `ModelProvider` enum. Adding it here would expand scope significantly. OpenAI + Gemini covers the two most common embedding use cases and demonstrates the pattern for adding more later.
