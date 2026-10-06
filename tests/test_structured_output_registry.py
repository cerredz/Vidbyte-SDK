"""Context Protocol Header

Description:
    Regression tests for provider/model structured-output capability resolution.
Purpose:
    Keep xAI Grok models on the native JSON Schema request path required by the
    current xAI API when an agent combines tool calls with a final typed reply.
Architecture:
    - StructuredOutputRegistryTests: Verifies the xAI Grok capability tier and
      preserves prompt-only fallback behavior for unknown providers.
Relations:
    Protects vidbyte.lib.configs.structured_output as consumed by
    vidbyte.providers.compatible.OpenAICompatibleProvider.
Similar Files:
    - tests/test_model_registry.py
"""

from __future__ import annotations

import unittest

from vidbyte.lib.enums import StructuredOutputSupport
from vidbyte.lib.registries.structured_output import StructuredOutputRegistry


class StructuredOutputRegistryTests(unittest.TestCase):
    """Verify provider/model structured-output capability decisions."""

    def test_grok_4_3_uses_native_schema_support(self) -> None:
        """xAI Grok final outputs use native JSON Schema enforcement after tools."""
        self.assertEqual(
            StructuredOutputRegistry.resolve("xai", "grok-4.3"),
            StructuredOutputSupport.NATIVE_SCHEMA,
        )

    def test_unknown_provider_remains_prompt_only(self) -> None:
        """Unknown providers do not inherit xAI's structured-output capability."""
        self.assertEqual(
            StructuredOutputRegistry.resolve("unknown-provider", "model"),
            StructuredOutputSupport.PROMPT_ONLY,
        )
