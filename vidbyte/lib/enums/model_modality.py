from __future__ import annotations

from enum import Enum


class ModelModality(str, Enum):
    """Supported model execution modalities."""

    AUTO = "auto"
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"


__all__ = [
    "ModelModality",
]
