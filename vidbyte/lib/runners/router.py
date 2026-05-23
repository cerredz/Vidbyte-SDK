from __future__ import annotations

from typing import Any

from vidbyte.lib.agents import ModalityDetector
from vidbyte.lib.enums import ModelModality, ModelProvider


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
    "create_runner_for_modality",
    "resolve_modality",
]
