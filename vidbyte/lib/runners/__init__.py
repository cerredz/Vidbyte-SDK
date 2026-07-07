from __future__ import annotations

from vidbyte.lib.runners.types import (
    AudioModelResponse,
    EmbeddingResponse,
    GeneratedImage,
    ImageModelResponse,
    TextModelResponse,
    VideoModelJob,
)
from vidbyte.lib.runners.router import coerce_modality, create_runner_for_modality, resolve_modality
from vidbyte.lib.runners.router import create_runner_for_model
from vidbyte.lib.runners.utility import Runner
from vidbyte.lib.agents import ModalityDetector

__all__ = [
    "AudioModelResponse",
    "AudioModelRunner",
    "EmbeddingModelRunner",
    "EmbeddingModelRunnerProvider",
    "EmbeddingResponse",
    "GeneratedImage",
    "ImageModelResponse",
    "ImageModelRunner",
    "ModalityDetector",
    "Runner",
    "StreamingTextModelRunner",
    "TextModelResponse",
    "TextModelRunner",
    "VideoModelJob",
    "VideoModelRunner",
    "coerce_modality",
    "create_runner_for_model",
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
    if name == "AudioModelRunner":
        from vidbyte.lib.runners.audio import AudioModelRunner
        return AudioModelRunner
    if name == "EmbeddingModelRunner":
        from vidbyte.lib.runners.embedding import EmbeddingModelRunner
        return EmbeddingModelRunner
    if name == "StreamingTextModelRunner":
        from vidbyte.lib.runners.streaming_text import StreamingTextModelRunner
        return StreamingTextModelRunner
    if name == "EmbeddingModelRunnerProvider":
        from vidbyte.tools.builtins.code_search.semantic import EmbeddingModelRunnerProvider
        return EmbeddingModelRunnerProvider
    raise AttributeError(name)
