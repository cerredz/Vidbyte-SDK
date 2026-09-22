from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vidbyte.lib.config import ModelProvider
from vidbyte.lib.dataclasses.jev import JevAnswer
from vidbyte.lib.errors import ConfigurationError


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


@dataclass(frozen=True, slots=True)
class AudioModelResponse:
    provider: ModelProvider
    model: str
    audio_bytes: bytes | None
    transcript: str | None
    raw: Mapping[str, Any]
    usage: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingResponse:
    provider: ModelProvider
    model: str
    embeddings: tuple[tuple[float, ...], ...]
    raw: Mapping[str, Any]
    usage: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DecisionModelResponse:
    provider: ModelProvider
    model: str
    answers: Mapping[str, JevAnswer]
    raw: Mapping[str, Any]
    usage: Mapping[str, Any] | None = None

    def answer(self, name: str) -> JevAnswer:
        # Returns the normalized answer for one question name, raising when it is absent.
        found = self.answers.get(name)
        if found is None:
            raise ConfigurationError(f"No Jev answer for question {name!r}.", details={"known_questions": sorted(self.answers)})
        return found
