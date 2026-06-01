"""Context Protocol Header

Description:
    Unit tests for the centralized ProviderModelRegistry.
Purpose:
    Verifies API key and endpoint validation/resolution, supported provider and model listings, and exception mapping.
Architecture:
    - ModelRegistryTests: unittest.TestCase suite.
Key Functions:
    - test_get_api_key_env_var: Verifies env var mappings.
    - test_get_default_endpoint: Verifies default URLs.
    - test_resolve_api_key: Verifies key resolution logic under various env setups.
    - test_resolve_endpoint: Verifies custom and fallback endpoint handling.
    - test_supported_lists: Verifies retrieval of supported models/providers.
    - test_validations: Verifies validation logic raises ConfigurationError correctly.
Relations:
    Validates the central ProviderModelRegistry code.
Similar Files:
    - tests/test_openrouter_provider.py
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry


class ModelRegistryTests(unittest.TestCase):
    def test_get_api_key_env_var(self) -> None:
        # Verifies that get_api_key_env_var returns the correct environment variable.
        self.assertEqual(ProviderModelRegistry.get_api_key_env_var(ModelProvider.OPENAI), "OPENAI_API_KEY")
        self.assertEqual(ProviderModelRegistry.get_api_key_env_var(ModelProvider.OPENROUTER), "OPENROUTER_API_KEY")
        self.assertEqual(ProviderModelRegistry.get_api_key_env_var("openai"), "OPENAI_API_KEY")
        with self.assertRaises(ConfigurationError):
            ProviderModelRegistry.get_api_key_env_var("invalid-provider")

    def test_get_default_endpoint(self) -> None:
        # Verifies that get_default_endpoint returns the correct REST URL.
        self.assertEqual(ProviderModelRegistry.get_default_endpoint(ModelProvider.OPENAI), "https://api.openai.com/v1")
        self.assertEqual(ProviderModelRegistry.get_default_endpoint(ModelProvider.OPENROUTER), "https://openrouter.ai/api/v1")
        self.assertEqual(ProviderModelRegistry.get_default_endpoint("openai"), "https://api.openai.com/v1")

    def test_resolve_api_key(self) -> None:
        # Verifies that resolve_api_key correctly resolves explicit keys and falls back to env vars.
        self.assertEqual(ProviderModelRegistry.resolve_api_key(ModelProvider.OPENAI, "explicit-key"), "explicit-key")
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            self.assertEqual(ProviderModelRegistry.resolve_api_key(ModelProvider.OPENAI, None), "env-key")
            self.assertEqual(ProviderModelRegistry.resolve_api_key(ModelProvider.OPENAI, "   "), "env-key")

        with patch.dict(os.environ, {}):
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
            with self.assertRaises(ConfigurationError):
                ProviderModelRegistry.resolve_api_key(ModelProvider.OPENAI, None)

    def test_resolve_endpoint(self) -> None:
        # Verifies that resolve_endpoint resolves explicit values or falls back to defaults.
        self.assertEqual(ProviderModelRegistry.resolve_endpoint(ModelProvider.OPENAI, "https://myproxy.com/"), "https://myproxy.com")
        self.assertEqual(ProviderModelRegistry.resolve_endpoint(ModelProvider.OPENAI, None), "https://api.openai.com/v1")
        self.assertEqual(ProviderModelRegistry.resolve_endpoint(ModelProvider.OPENAI, "   "), "https://api.openai.com/v1")

    def test_supported_lists(self) -> None:
        # Verifies that support listings match enums and registry mappings.
        self.assertIn("openai", ProviderModelRegistry.get_supported_providers())
        self.assertIn("openrouter", ProviderModelRegistry.get_supported_providers())
        self.assertIn("openrouter/auto", ProviderModelRegistry.get_supported_models())

    def test_validations(self) -> None:
        # Verifies validation exceptions map correctly.
        ProviderModelRegistry.validate_provider("openai")
        with self.assertRaises(ConfigurationError):
            ProviderModelRegistry.validate_provider("invalid-provider")

        ProviderModelRegistry.validate_model("gpt-4o")
        with self.assertRaises(ConfigurationError):
            ProviderModelRegistry.validate_model(" ")


if __name__ == "__main__":
    unittest.main()
