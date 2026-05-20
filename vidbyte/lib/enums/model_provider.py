from __future__ import annotations

from enum import Enum


class ModelProvider(str, Enum):
    """Supported SDK model providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    MINIMAX = "minimax"


__all__ = [
    "ModelProvider",
]
