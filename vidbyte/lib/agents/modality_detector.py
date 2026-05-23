from __future__ import annotations

from dataclasses import fields
from typing import Any, Mapping

from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.enums.model_modality import _MODEL_NAME_MODALITY_MAP
from vidbyte.lib.errors import ConfigurationError


class ModalityDetector:
    """Automatic model modality detection from model name identifiers."""

    @staticmethod
    def is_text(model_name: str) -> bool:
        """Return True when the model name maps to text modality."""
        return ModalityDetector.detect_modality(model_name) is ModelModality.TEXT

    @staticmethod
    def is_image(model_name: str) -> bool:
        """Return True when the model name maps to image modality."""
        return ModalityDetector.detect_modality(model_name) is ModelModality.IMAGE

    @staticmethod
    def is_video(model_name: str) -> bool:
        """Return True when the model name maps to video modality."""
        return ModalityDetector.detect_modality(model_name) is ModelModality.VIDEO

    @staticmethod
    def detect_modality(model_name: str) -> ModelModality:
        """Resolve the execution modality for a known model name."""
        name = (model_name or "").strip().lower()
        if not name:
            return ModelModality.AUTO
        if name in _MODEL_NAME_MODALITY_MAP:
            return _MODEL_NAME_MODALITY_MAP[name]
        for pattern, modality in _SUBSTRING_MODALITY_MAP:
            if pattern in name:
                return modality
        for prefix, modality in _PREFIX_MODALITY_MAP:
            if name.startswith(prefix):
                return modality
        return ModelModality.AUTO

    @staticmethod
    def detect_modality_from_model(model_name: str) -> ModelModality:
        """Alias for detect_modality."""
        return ModalityDetector.detect_modality(model_name)

    @staticmethod
    def coerce(value: ModelModality | str | None) -> ModelModality:
        """Normalize a modality value at SDK boundaries."""
        if value is None:
            return ModelModality.AUTO
        if isinstance(value, ModelModality):
            return value
        try:
            return ModelModality(value)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model modality: {value!r}") from exc

    @staticmethod
    def transform(value: ModelModality | str | None) -> ModelModality:
        """Alias for coerce when transforming boundary values."""
        return ModalityDetector.coerce(value)

    @staticmethod
    def resolve(
        *,
        requested: ModelModality | str | None = None,
        input_modality: ModelModality | str | None = None,
        default: ModelModality | str | None = None,
    ) -> ModelModality:
        """Resolve call, input, and agent defaults into an execution modality."""
        for candidate in (requested, input_modality, default):
            modality = ModalityDetector.coerce(candidate)
            if modality is not ModelModality.AUTO:
                return modality
        return ModelModality.AUTO

    @staticmethod
    def create_runner(
        modality: ModelModality | str,
        *,
        provider: ModelProvider | str,
        model: str,
        transport: object | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        **options: Any,
    ) -> object:
        """Create the internal concrete runner for a resolved modality."""
        from vidbyte.lib.config import ImageModelConfig, TextModelConfig, VideoModelConfig

        resolved = ModalityDetector.coerce(modality)
        if resolved is ModelModality.AUTO:
            detected = ModalityDetector.detect_modality(model)
            resolved = detected if detected is not ModelModality.AUTO else ModelModality.TEXT

        common_options = dict(options)
        if api_key is not None:
            common_options["api_key"] = api_key
        if resolved is ModelModality.TEXT and temperature is not None:
            common_options["temperature"] = temperature

        if resolved is ModelModality.TEXT:
            from vidbyte.lib.runners.text import TextModelRunner

            return TextModelRunner(
                ModalityDetector.build_config(
                    TextModelConfig,
                    provider=provider,
                    model=model,
                    options=common_options,
                ),
                transport=transport,
            )
        if resolved is ModelModality.IMAGE:
            from vidbyte.lib.runners.image import ImageModelRunner

            return ImageModelRunner(
                ModalityDetector.build_config(
                    ImageModelConfig,
                    provider=provider,
                    model=model,
                    options=common_options,
                ),
                transport=transport,
            )
        if resolved is ModelModality.VIDEO:
            from vidbyte.lib.runners.video import VideoModelRunner

            return VideoModelRunner(
                ModalityDetector.build_config(
                    VideoModelConfig,
                    provider=provider,
                    model=model,
                    options=common_options,
                ),
                transport=transport,
            )
        raise ConfigurationError(f"Unsupported model modality: {resolved.value!r}")

    @staticmethod
    def build_config(
        config_type: type[Any],
        *,
        provider: ModelProvider | str,
        model: str,
        options: Mapping[str, Any],
    ) -> object:
        """Build a runner config with only fields supported by that config type."""
        field_names = {field.name for field in fields(config_type)}
        filtered_options = {key: value for key, value in dict(options).items() if key in field_names}
        return config_type(provider=provider, model=model, **filtered_options)


_SUBSTRING_MODALITY_MAP: tuple[tuple[str, ModelModality], ...] = (
    ("gpt-image", ModelModality.IMAGE),
    ("chatgpt-image", ModelModality.IMAGE),
    ("dall-e", ModelModality.IMAGE),
    ("imagen", ModelModality.IMAGE),
    ("nano-banana", ModelModality.IMAGE),
    ("grok-imagine-image", ModelModality.IMAGE),
    ("midjourney", ModelModality.IMAGE),
    ("stable-diffusion", ModelModality.IMAGE),
    ("flux", ModelModality.IMAGE),
    ("sora", ModelModality.VIDEO),
    ("veo", ModelModality.VIDEO),
    ("kling", ModelModality.VIDEO),
    ("runway", ModelModality.VIDEO),
    ("luma", ModelModality.VIDEO),
    ("pika", ModelModality.VIDEO),
    ("hailuo", ModelModality.VIDEO),
    ("grok-imagine-video", ModelModality.VIDEO),
)

_PREFIX_MODALITY_MAP: tuple[tuple[str, ModelModality], ...] = (
    ("gpt-", ModelModality.TEXT),
    ("chatgpt-", ModelModality.TEXT),
    ("o1", ModelModality.TEXT),
    ("o3", ModelModality.TEXT),
    ("o4", ModelModality.TEXT),
    ("claude-", ModelModality.TEXT),
    ("gemini-", ModelModality.TEXT),
    ("grok-", ModelModality.TEXT),
    ("deepseek-", ModelModality.TEXT),
    ("glm-", ModelModality.TEXT),
    ("minimax-", ModelModality.TEXT),
    ("abab", ModelModality.TEXT),
)


__all__ = [
    "ModalityDetector",
]
