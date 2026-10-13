"""Structured configuration data that must not initialize runtime configuration loaders."""

from vidbyte.lib.configs.harness_backends import HARNESS_BACKENDS
from vidbyte.lib.configs.structured_output import (
    MODEL_SUPPORT,
    NATIVE_SCHEMA_WITHOUT_TOOLS,
    PROVIDER_SUPPORT,
    STRUCTURED_OUTPUT_AS_OF,
    STRUCTURED_OUTPUT_DESCRIPTIONS,
    StructuredOutputDescription,
)

__all__ = [
    "HARNESS_BACKENDS",
    "MODEL_SUPPORT",
    "NATIVE_SCHEMA_WITHOUT_TOOLS",
    "PROVIDER_SUPPORT",
    "STRUCTURED_OUTPUT_AS_OF",
    "STRUCTURED_OUTPUT_DESCRIPTIONS",
    "StructuredOutputDescription",
]
