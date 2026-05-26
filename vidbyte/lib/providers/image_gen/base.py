"""Context Protocol Header

Description:
    Defines the abstract base class and data transfer object for image generation backends.
Purpose:
    Provides a typed contract that image generation provider backends must implement,
    along with the shared ImageGenResult dataclass.
Architecture:
    - ImageGenResult: Dataclass with url and optional revised_prompt.
    - BaseImageGenBackend: ABC requiring async generate() and is_available().
Relations:
    Related to vidbyte.lib.providers.image_gen and vidbyte.tools.builtins.image_gen.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class ImageGenResult:
    url: str
    revised_prompt: str | None = None


class BaseImageGenBackend(ABC):
    @abstractmethod
    async def generate(self, prompt: str, size: str, style: str) -> ImageGenResult:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


__all__ = [
    "BaseImageGenBackend",
    "ImageGenResult",
]
