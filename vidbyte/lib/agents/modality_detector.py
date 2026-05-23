from __future__ import annotations

from vidbyte.lib.enums import ModelModality
from vidbyte.lib.enums.model_modality import _MODEL_NAME_MODALITY_MAP


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
        for pattern, modality in _PATTERN_MODALITY_MAP.items():
            if pattern in name:
                return modality
        return ModelModality.AUTO

    @staticmethod
    def detect_modality_from_model(model_name: str) -> ModelModality:
        """Alias for detect_modality."""
        return ModalityDetector.detect_modality(model_name)


_PATTERN_MODALITY_MAP: dict[str, ModelModality] = {
    "dall-e": ModelModality.IMAGE,
    "imagen": ModelModality.IMAGE,
    "midjourney": ModelModality.IMAGE,
    "stable-diffusion": ModelModality.IMAGE,
    "flux": ModelModality.IMAGE,
    "sora": ModelModality.VIDEO,
    "kling": ModelModality.VIDEO,
    "runway": ModelModality.VIDEO,
    "luma": ModelModality.VIDEO,
    "pika": ModelModality.VIDEO,
    "hailuo": ModelModality.VIDEO,
    "veo": ModelModality.VIDEO,
}


__all__ = [
    "ModalityDetector",
]
