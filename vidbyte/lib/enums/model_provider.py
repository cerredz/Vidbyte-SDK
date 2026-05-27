# Context Protocol Header
# Description: Defines the supported SDK model providers.
# Purpose: Used as the core ModelProvider enum to select and configure different LLM providers (OpenAI, Anthropic, Gemini, OpenRouter, etc.).
# Architecture: Str-based Enum mapping keys to their canonical provider names.
# Key Functions: ModelProvider enum class.
# Codebase Relation: Extends provider selection in configuration and dataclasses.
# Similar Files: vidbyte/lib/enums/model_modality.py

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


__all__ = [
    "ModelProvider",
]

