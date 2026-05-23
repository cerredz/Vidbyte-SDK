from __future__ import annotations

from vidbyte.lib.enums import ModelProvider

API_KEY_ENV_VARS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: "OPENAI_API_KEY",
    ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    ModelProvider.GEMINI: "GEMINI_API_KEY",
    ModelProvider.XAI: "XAI_API_KEY",
    ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
    ModelProvider.GLM: "GLM_API_KEY",
    ModelProvider.MINIMAX: "MINIMAX_API_KEY",
}

DEFAULT_ENDPOINTS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: "https://api.openai.com/v1",
    ModelProvider.ANTHROPIC: "https://api.anthropic.com/v1",
    ModelProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
    ModelProvider.XAI: "https://api.x.ai/v1",
    ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
    ModelProvider.GLM: "https://open.bigmodel.cn/api/paas/v4",
    ModelProvider.MINIMAX: "https://api.minimax.io/v1",
}

__all__ = [
    "API_KEY_ENV_VARS",
    "DEFAULT_ENDPOINTS",
]
