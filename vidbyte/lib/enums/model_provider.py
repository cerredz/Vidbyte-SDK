"""Context Protocol Header

Description:
    Supported SDK model providers enumeration.
Purpose:
    Exposes supported provider string literals as a strongly-typed Enum at the SDK boundary.
Architecture:
    - ModelProvider: Enum mapping provider keys.
Key Functions:
    None.
Relations:
    Extensively used by ProviderModelRegistry, client configuration classes, and provider factories.
Similar Files:
    - vidbyte/lib/enums/model_modality.py
"""

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
    OPENROUTER = "openrouter"
    ELEVENLABS = "elevenlabs"
    PLAYAI = "playai"


__all__ = [
    "ModelProvider",
]

