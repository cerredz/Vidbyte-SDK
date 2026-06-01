"""Context Protocol Header

Description:
    Model execution modality definitions and maps.
Purpose:
    Maps model names and prefixes to their supported execution modalities (auto, text, image, video).
Architecture:
    - ModelModality: Supported execution modalities.
    - ModelNameModality: Known model names.
    - _MODEL_NAME_MODALITY_MAP: Comprehensive mapping dictionary.
Key Functions:
    None.
Relations:
    Used by ModalityDetector to automatically infer modality for any given model name.
Similar Files:
    - vidbyte/lib/agents/modality_detector.py
"""

from __future__ import annotations

from enum import Enum


class ModelModality(str, Enum):
    """Supported model execution modalities."""

    AUTO = "auto"
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    EMBEDDING = "embedding"


class ModelNameModality(str, Enum):
    """Known model names mapped to their execution modality."""

    OPENROUTER_AUTO = "text"
    GPT_4 = "text"
    GPT_4O = "text"
    GPT_4O_MINI = "text"
    GPT_4_TURBO = "text"
    GPT_3_5_TURBO = "text"
    O1 = "text"
    O1_MINI = "text"
    O3 = "text"
    O3_MINI = "text"
    GPT_4_1 = "text"
    GPT_4_1_MINI = "text"
    GPT_4_1_NANO = "text"
    GPT_5 = "text"
    GPT_5_4 = "text"
    GPT_5_4_MINI = "text"
    GPT_5_4_NANO = "text"
    GPT_5_5 = "text"

    CLAUDE_3_5_SONNET = "text"
    CLAUDE_3_OPUS = "text"
    CLAUDE_3_HAIKU = "text"
    CLAUDE_3_SONNET = "text"
    CLAUDE_OPUS_4 = "text"
    CLAUDE_OPUS_4_7 = "text"
    CLAUDE_SONNET_4 = "text"
    CLAUDE_SONNET_4_6 = "text"
    CLAUDE_HAIKU_4_5 = "text"

    GEMINI_2_0_FLASH = "text"
    GEMINI_2_5_PRO = "text"
    GEMINI_2_5_FLASH = "text"
    GEMINI_3_1_FLASH = "text"
    GEMINI_3_5_FLASH = "text"
    GEMINI_1_5_PRO = "text"
    GEMINI_1_5_FLASH = "text"

    GROK_4_3 = "text"
    GROK_3 = "text"
    GROK_2 = "text"

    DEEPSEEK_CHAT = "text"
    DEEPSEEK_REASONER = "text"
    DEEPSEEK_V3 = "text"

    GLM_4 = "text"
    GLM_4_FLASH = "text"

    MINIMAX_TEXT_01 = "text"
    ABAB = "text"

    DALL_E_2 = "image"
    DALL_E_3 = "image"
    GPT_IMAGE_1 = "image"
    GPT_IMAGE_2 = "image"
    IMAGEN_3 = "image"
    IMAGEN_4 = "image"
    NANO_BANANA = "image"

    SORA = "video"
    SORA_2 = "video"
    SORA_TURBO = "video"
    VEO_3_1 = "video"


_MODEL_NAME_MODALITY_MAP: dict[str, ModelModality] = {
    "gpt-4": ModelModality.TEXT,
    "gpt-4-0125-preview": ModelModality.TEXT,
    "gpt-4-1106-preview": ModelModality.TEXT,
    "gpt-4-vision-preview": ModelModality.TEXT,
    "gpt-4o": ModelModality.TEXT,
    "gpt-4o-mini": ModelModality.TEXT,
    "gpt-4o-2024-05-13": ModelModality.TEXT,
    "gpt-4o-2024-08-06": ModelModality.TEXT,
    "gpt-4o-2024-11-20": ModelModality.TEXT,
    "gpt-4-turbo": ModelModality.TEXT,
    "gpt-4-turbo-2024-04-09": ModelModality.TEXT,
    "gpt-3.5-turbo": ModelModality.TEXT,
    "gpt-3.5-turbo-0125": ModelModality.TEXT,
    "gpt-3.5-turbo-1106": ModelModality.TEXT,
    "o1": ModelModality.TEXT,
    "o1-mini": ModelModality.TEXT,
    "o1-preview": ModelModality.TEXT,
    "o3": ModelModality.TEXT,
    "o3-mini": ModelModality.TEXT,
    "o4-mini": ModelModality.TEXT,
    "gpt-4.1": ModelModality.TEXT,
    "gpt-4.1-mini": ModelModality.TEXT,
    "gpt-4.1-nano": ModelModality.TEXT,
    "gpt-5": ModelModality.TEXT,
    "gpt-5-mini": ModelModality.TEXT,
    "gpt-5-nano": ModelModality.TEXT,
    "gpt-5.1": ModelModality.TEXT,
    "gpt-5.1-codex": ModelModality.TEXT,
    "gpt-5.1-codex-max": ModelModality.TEXT,
    "gpt-5.1-codex-mini": ModelModality.TEXT,
    "gpt-5.2": ModelModality.TEXT,
    "gpt-5.2-chat-latest": ModelModality.TEXT,
    "gpt-5.2-codex": ModelModality.TEXT,
    "gpt-5.2-pro": ModelModality.TEXT,
    "gpt-5.4": ModelModality.TEXT,
    "gpt-5.4-mini": ModelModality.TEXT,
    "gpt-5.4-nano": ModelModality.TEXT,
    "gpt-5.5": ModelModality.TEXT,
    "gpt-oss-120b": ModelModality.TEXT,
    "gpt-oss-20b": ModelModality.TEXT,

    "claude-3-5-sonnet-20240620": ModelModality.TEXT,
    "claude-3-5-sonnet-20241022": ModelModality.TEXT,
    "claude-3-5-sonnet-latest": ModelModality.TEXT,
    "claude-3-opus-20240229": ModelModality.TEXT,
    "claude-3-opus-latest": ModelModality.TEXT,
    "claude-3-haiku-20240307": ModelModality.TEXT,
    "claude-3-sonnet-20240229": ModelModality.TEXT,
    "claude-opus-4-20250514": ModelModality.TEXT,
    "claude-opus-4-1-20250805": ModelModality.TEXT,
    "claude-opus-4-6": ModelModality.TEXT,
    "claude-opus-4-7": ModelModality.TEXT,
    "claude-sonnet-4-20250514": ModelModality.TEXT,
    "claude-sonnet-4-5": ModelModality.TEXT,
    "claude-sonnet-4-6": ModelModality.TEXT,
    "claude-haiku-4-5": ModelModality.TEXT,
    "claude-haiku-4-5-20251001": ModelModality.TEXT,

    "gemini-2.0-flash": ModelModality.TEXT,
    "gemini-2.0-flash-001": ModelModality.TEXT,
    "gemini-2.5-pro": ModelModality.TEXT,
    "gemini-2.5-pro-preview-03-25": ModelModality.TEXT,
    "gemini-2.5-flash": ModelModality.TEXT,
    "gemini-2.5-flash-preview-04-17": ModelModality.TEXT,
    "gemini-2.5-flash-lite": ModelModality.TEXT,
    "gemini-3.1-flash-live-preview": ModelModality.TEXT,
    "gemini-3.1-flash-tts-preview": ModelModality.TEXT,
    "gemini-3.5-flash": ModelModality.TEXT,
    "gemini-1.5-pro": ModelModality.TEXT,
    "gemini-1.5-pro-002": ModelModality.TEXT,
    "gemini-1.5-flash": ModelModality.TEXT,
    "gemini-1.5-flash-002": ModelModality.TEXT,

    "grok-3": ModelModality.TEXT,
    "grok-3-mini": ModelModality.TEXT,
    "grok-4.3": ModelModality.TEXT,
    "grok-2": ModelModality.TEXT,
    "grok-2-vision": ModelModality.TEXT,

    "deepseek-chat": ModelModality.TEXT,
    "deepseek-reasoner": ModelModality.TEXT,
    "deepseek-v3": ModelModality.TEXT,

    "glm-4": ModelModality.TEXT,
    "glm-4-flash": ModelModality.TEXT,
    "glm-4-plus": ModelModality.TEXT,

    "minimax-text-01": ModelModality.TEXT,
    "abab6.5s-chat": ModelModality.TEXT,

    "openrouter/auto": ModelModality.TEXT,
    "openai/gpt-4o": ModelModality.TEXT,
    "openai/gpt-4o-mini": ModelModality.TEXT,
    "openai/o1": ModelModality.TEXT,
    "openai/o1-mini": ModelModality.TEXT,
    "openai/o3-mini": ModelModality.TEXT,
    "anthropic/claude-3.5-sonnet": ModelModality.TEXT,
    "anthropic/claude-3-opus": ModelModality.TEXT,
    "anthropic/claude-3.5-haiku": ModelModality.TEXT,
    "google/gemini-2.5-pro": ModelModality.TEXT,
    "google/gemini-2.5-flash": ModelModality.TEXT,
    "google/gemini-2.0-flash-thinking-exp": ModelModality.TEXT,
    "meta-llama/llama-3.3-70b-instruct": ModelModality.TEXT,
    "meta-llama/llama-3.1-8b-instruct:free": ModelModality.TEXT,
    "meta-llama/llama-3.1-70b-instruct": ModelModality.TEXT,
    "meta-llama/llama-3.1-405b-instruct": ModelModality.TEXT,
    "deepseek/deepseek-chat": ModelModality.TEXT,
    "deepseek/deepseek-r1": ModelModality.TEXT,
    "mistralai/mistral-large": ModelModality.TEXT,
    "mistralai/pixtral-large-12b": ModelModality.TEXT,
    "qwen/qwen-2.5-72b-instruct": ModelModality.TEXT,

    "dall-e-2": ModelModality.IMAGE,
    "dall-e-3": ModelModality.IMAGE,
    "gpt-image-1": ModelModality.IMAGE,
    "gpt-image-1-mini": ModelModality.IMAGE,
    "gpt-image-1.5": ModelModality.IMAGE,
    "gpt-image-2": ModelModality.IMAGE,
    "chatgpt-image-latest": ModelModality.IMAGE,

    "imagen-3.0-generate-001": ModelModality.IMAGE,
    "imagen-4": ModelModality.IMAGE,
    "nano-banana": ModelModality.IMAGE,
    "nano-banana-2-preview": ModelModality.IMAGE,
    "nano-banana-pro-preview": ModelModality.IMAGE,
    "grok-imagine-image": ModelModality.IMAGE,

    "sora": ModelModality.VIDEO,
    "sora-2": ModelModality.VIDEO,
    "sora-2-pro": ModelModality.VIDEO,
    "sora-turbo": ModelModality.VIDEO,
    "veo-3.1": ModelModality.VIDEO,
    "veo-3.1-lite-preview": ModelModality.VIDEO,
    "grok-imagine-video": ModelModality.VIDEO,

    # OpenAI audio models
    "whisper-1": ModelModality.AUDIO,
    "whisper-2": ModelModality.AUDIO,
    "tts-1": ModelModality.AUDIO,
    "tts-1-hd": ModelModality.AUDIO,
    "gpt-4o-audio-preview": ModelModality.AUDIO,
    "gpt-4o-realtime-preview": ModelModality.AUDIO,
    # ElevenLabs audio models
    "eleven_multilingual_v2": ModelModality.AUDIO,
    "eleven_turbo_v2_5": ModelModality.AUDIO,
    "eleven_monolingual_v1": ModelModality.AUDIO,
    "eleven_turbo_v2": ModelModality.AUDIO,
    # Play.ai audio models
    "PlayDialog": ModelModality.AUDIO,
    "PlayDialogMultilingual": ModelModality.AUDIO,

    # OpenAI embedding models
    "text-embedding-3-small": ModelModality.EMBEDDING,
    "text-embedding-3-large": ModelModality.EMBEDDING,
    "text-embedding-ada-002": ModelModality.EMBEDDING,
    # Gemini embedding models
    "text-embedding-004": ModelModality.EMBEDDING,
    "embedding-001": ModelModality.EMBEDDING,
    "gemini-embedding-exp-03-07": ModelModality.EMBEDDING,
}


__all__ = [
    "ModelModality",
    "ModelNameModality",
]
