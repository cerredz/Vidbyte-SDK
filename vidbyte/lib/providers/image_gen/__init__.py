"""Context Protocol Header

Description:
    Re-exports image generation backend implementations.
Purpose:
    Provides a stable import surface for image generation provider backends
    without exposing internal implementation details.
Architecture:
    - BaseImageGenBackend: Abstract contract.
    - OpenAIDalleBackend: OpenAI DALL-E 3 implementation.
    - ImageGenResult: Data transfer object for generated images.
Relations:
    Related to vidbyte.tools.builtins.image_gen.
"""

from __future__ import annotations

from vidbyte.lib.providers.image_gen.base import BaseImageGenBackend, ImageGenResult
from vidbyte.lib.providers.image_gen.openai_dalle_backend import OpenAIDalleBackend

__all__ = [
    "BaseImageGenBackend",
    "ImageGenResult",
    "OpenAIDalleBackend",
]
