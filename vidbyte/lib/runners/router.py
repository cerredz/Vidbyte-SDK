from __future__ import annotations

from dataclasses import fields
from typing import Any, Mapping

from vidbyte.lib.config import ImageModelConfig, TextModelConfig, VideoModelConfig
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import ConfigurationError


def coerce_modality(value: ModelModality | str | None) -> ModelModality:
    """Normalize a modality value at SDK boundaries."""
    if value is None:
        return ModelModality.AUTO
    if isinstance(value, ModelModality):
        return value
    try:
        return ModelModality(value)
    except ValueError as exc:
        raise ConfigurationError(f"Unsupported model modality: {value!r}") from exc


def resolve_modality(
    *,
    requested: ModelModality | str | None = None,
    input_modality: ModelModality | str | None = None,
    default: ModelModality | str | None = None,
) -> ModelModality:
    """Resolve call, input, and agent defaults into a concrete modality."""
    for candidate in (requested, input_modality, default):
        modality = coerce_modality(candidate)
        if modality is not ModelModality.AUTO:
            return modality
    return ModelModality.TEXT


def create_runner_for_modality(
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
    resolved = coerce_modality(modality)
    if resolved is ModelModality.AUTO:
        resolved = ModelModality.TEXT
    common_options = dict(options)
    if api_key is not None:
        common_options["api_key"] = api_key
    if resolved is ModelModality.TEXT and temperature is not None:
        common_options["temperature"] = temperature

    if resolved is ModelModality.TEXT:
        from vidbyte.lib.runners.text import TextModelRunner

        return TextModelRunner(
            _build_config(TextModelConfig, provider=provider, model=model, options=common_options),
            transport=transport,
        )
    if resolved is ModelModality.IMAGE:
        from vidbyte.lib.runners.image import ImageModelRunner

        return ImageModelRunner(
            _build_config(ImageModelConfig, provider=provider, model=model, options=common_options),
            transport=transport,
        )
    if resolved is ModelModality.VIDEO:
        from vidbyte.lib.runners.video import VideoModelRunner

        return VideoModelRunner(
            _build_config(VideoModelConfig, provider=provider, model=model, options=common_options),
            transport=transport,
        )
    raise ConfigurationError(f"Unsupported model modality: {resolved.value!r}")


def _build_config(
    config_type: type[TextModelConfig] | type[ImageModelConfig] | type[VideoModelConfig],
    *,
    provider: ModelProvider | str,
    model: str,
    options: Mapping[str, Any],
) -> TextModelConfig | ImageModelConfig | VideoModelConfig:
    field_names = {field.name for field in fields(config_type)}
    filtered_options = {key: value for key, value in dict(options).items() if key in field_names}
    return config_type(provider=provider, model=model, **filtered_options)


__all__ = [
    "coerce_modality",
    "create_runner_for_modality",
    "resolve_modality",
]
