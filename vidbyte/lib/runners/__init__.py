from __future__ import annotations

from vidbyte.lib.runners.types import (
    GeneratedImage,
    ImageModelResponse,
    TextModelResponse,
    VideoModelJob,
)
from vidbyte.lib.runners.router import coerce_modality, create_runner_for_modality, resolve_modality

__all__ = [
    "GeneratedImage",
    "ImageModelResponse",
    "ImageModelRunner",
    "TextModelResponse",
    "TextModelRunner",
    "VideoModelJob",
    "VideoModelRunner",
    "coerce_modality",
    "create_runner_for_modality",
    "resolve_modality",
]


def __getattr__(name: str) -> object:
    if name == "TextModelRunner":
        from vidbyte.lib.runners.text import TextModelRunner

        return TextModelRunner
    if name == "ImageModelRunner":
        from vidbyte.lib.runners.image import ImageModelRunner

        return ImageModelRunner
    if name == "VideoModelRunner":
        from vidbyte.lib.runners.video import VideoModelRunner

        return VideoModelRunner
    raise AttributeError(name)
