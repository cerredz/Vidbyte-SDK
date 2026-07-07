from __future__ import annotations

from typing import Any

from vidbyte.lib.agents import ModalityDetector
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.runners.utility import Runner


def create_runner_for_model(
    *,
    provider: ModelProvider | str | None,
    model_name: str | None,
    transport: object | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    **options: Any,
) -> object:
    """Create a concrete runner from provider/model identity."""
    return Runner.from_model(
        provider=provider,
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        options=options,
    ).build(transport=transport)


def coerce_modality(value: ModelModality | str | None) -> ModelModality:
    """Compatibility wrapper around ModalityDetector.coerce()."""
    return ModalityDetector.coerce(value)


def resolve_modality(
    *,
    requested: ModelModality | str | None = None,
    input_modality: ModelModality | str | None = None,
    default: ModelModality | str | None = None,
) -> ModelModality:
    """Compatibility wrapper around ModalityDetector.resolve()."""
    return ModalityDetector.resolve(requested=requested, input_modality=input_modality, default=default)


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
    """Compatibility wrapper around ModalityDetector.create_runner()."""
    return ModalityDetector.create_runner(
        modality,
        provider=provider,
        model=model,
        transport=transport,
        api_key=api_key,
        temperature=temperature,
        **options,
    )


__all__ = [
    "coerce_modality",
    "create_runner_for_model",
    "create_runner_for_modality",
    "resolve_modality",
]
