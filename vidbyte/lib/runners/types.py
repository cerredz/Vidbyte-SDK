from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vidbyte.lib.config import ModelProvider


@dataclass(frozen=True, slots=True)
class TextModelResponse:
    provider: ModelProvider
    model: str
    text: str
    raw: Mapping[str, Any]
    usage: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    url: str | None = None
    b64_json: str | None = None
    revised_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class ImageModelResponse:
    provider: ModelProvider
    model: str
    images: tuple[GeneratedImage, ...]
    raw: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class VideoModelJob:
    provider: ModelProvider
    model: str
    job_id: str
    status: str
    raw: Mapping[str, Any]
