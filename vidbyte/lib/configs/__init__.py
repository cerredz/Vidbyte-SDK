"""Structured configuration data that must not initialize runtime configuration loaders."""

from vidbyte.lib.configs.reasoning_effort import (
    GEMINI_THINKING_BUDGET_OFF,
    REASONING_EFFORT_AS_OF,
    REASONING_EFFORT_FORMS,
    REASONING_EFFORT_SUPPORT,
)
from vidbyte.lib.configs.structured_output import (
    MODEL_SUPPORT,
    NATIVE_SCHEMA_WITHOUT_TOOLS,
    PROVIDER_SUPPORT,
    STRUCTURED_OUTPUT_AS_OF,
    STRUCTURED_OUTPUT_DESCRIPTIONS,
    StructuredOutputDescription,
)

__all__ = [
    "GEMINI_THINKING_BUDGET_OFF",
    "MODEL_SUPPORT",
    "NATIVE_SCHEMA_WITHOUT_TOOLS",
    "PROVIDER_SUPPORT",
    "REASONING_EFFORT_AS_OF",
    "REASONING_EFFORT_FORMS",
    "REASONING_EFFORT_SUPPORT",
    "STRUCTURED_OUTPUT_AS_OF",
    "STRUCTURED_OUTPUT_DESCRIPTIONS",
    "StructuredOutputDescription",
]
