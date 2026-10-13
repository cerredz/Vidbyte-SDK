"""Context Protocol Header

Description:
    Unit tests for the centralized ProviderModelRegistry.
Purpose:
    Verifies API key and endpoint validation/resolution, supported provider and model listings, and exception mapping.
Architecture:
    - ModelRegistryTests: unittest.TestCase suite.
    - ProviderPrefixedModelTests: Provider-prefixed ids and OpenRouter vendor slugs in normalization and validation.
Key Functions:
    - test_get_api_key_env_var: Verifies env var mappings.
    - test_get_default_endpoint: Verifies default URLs.
    - test_resolve_api_key: Verifies key resolution logic under various env setups.
    - test_resolve_endpoint: Verifies custom and fallback endpoint handling.
    - test_supported_lists: Verifies retrieval of supported models/providers.
    - test_validations: Verifies validation logic raises ConfigurationError correctly.
    - test_provider_predicate_and_coercion: Verifies is_valid_provider/resolve_provider.
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
from vidbyte.lib.registries.pricing import ModelPricingRegistry


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

    def test_provider_predicate_and_coercion(self) -> None:
        # Verifies the non-raising provider surface agrees with validate_provider.
        self.assertTrue(ProviderModelRegistry.is_valid_provider("openai"))
        self.assertTrue(ProviderModelRegistry.is_valid_provider("  OpenAI  "))
        self.assertFalse(ProviderModelRegistry.is_valid_provider("invalid-provider"))
        self.assertEqual(
            ProviderModelRegistry.resolve_provider("ANTHROPIC"),
            ModelProvider.ANTHROPIC,
        )
        self.assertIsNone(ProviderModelRegistry.resolve_provider("invalid-provider"))
        for name in ProviderModelRegistry.get_supported_providers():
            self.assertTrue(ProviderModelRegistry.is_valid_provider(name))
            ProviderModelRegistry.validate_provider(name)


class ProviderPrefixedModelTests(unittest.TestCase):
    SLUG = "openrouter/anthropic/claude-sonnet-5"

    def test_normalize_model_drops_the_providers_own_prefix_without_an_alias(self) -> None:
        # @intent normalized-model-drops-its-own-provider-prefix
        # 'openai/gpt-5.5' has no alias but must still normalize to the bare catalog name.
        self.assertEqual(ProviderModelRegistry.normalize_model("openai", "openai/gpt-5.5"), "gpt-5.5")
        self.assertEqual(ProviderModelRegistry.normalize_model("openai", "openai/gpt-5.6"), "gpt-5.6-sol")
        self.assertEqual(ProviderModelRegistry.normalize_model("openrouter", "openrouter/auto"), "auto")
        self.assertEqual(ProviderModelRegistry.normalize_model("anthropic", "openai/gpt-5.5"), "openai/gpt-5.5")

    def test_is_supported_model_agrees_for_prefixed_and_bare_names(self) -> None:
        for provider, model in (("openai", "gpt-5.5"), ("openai", "gpt-5.6")):
            with self.subTest(model=model):
                self.assertTrue(ProviderModelRegistry.is_supported_model(provider, model))
                self.assertTrue(ProviderModelRegistry.is_supported_model(provider, f"{provider}/{model}"))
        self.assertFalse(ProviderModelRegistry.is_supported_model("anthropic", "openai/gpt-5.5"))

    def test_openrouter_default_model_is_supported_by_its_own_provider(self) -> None:
        default = ProviderModelRegistry.DEFAULT_PROVIDER_MODELS[ModelProvider.OPENROUTER]
        self.assertTrue(ProviderModelRegistry.is_supported_model("openrouter", default))

    def test_prefixed_name_prices_like_its_bare_name(self) -> None:
        pricing = ModelPricingRegistry.default()
        bare = pricing.resolve(ModelProvider.OPENAI, "gpt-5.5")
        self.assertIsNotNone(bare)
        self.assertEqual(pricing.resolve(ModelProvider.OPENAI, "openai/gpt-5.5"), bare)

    def test_openrouter_vendor_slug_validates_under_openrouter(self) -> None:
        # @intent openrouter-slug-validates-as-its-vendor-model
        # The Runner strips 'openrouter/' before a vendor slug, so validation must accept the same id.
        ProviderModelRegistry.validate_model(self.SLUG)
        ProviderModelRegistry.validate_provider_model_pair("openrouter", self.SLUG)
        ProviderModelRegistry.validate_provider_models_map({"openrouter": self.SLUG})
        ProviderModelRegistry.validate_provider_model_pair("openrouter", "openrouter/auto")
        with self.assertRaisesRegex(ConfigurationError, "no registered runner"):
            ProviderModelRegistry.validate_model("openrouter/meta-llama/llama-4-maverick")

    def test_openrouter_vendor_slug_stays_rejected_under_other_providers(self) -> None:
        # @intent openrouter-routed-ids-stay-with-openrouter
        # Another vendor would receive the 'openrouter/' prefix verbatim, so the slug is OpenRouter's alone.
        for provider in ("anthropic", "openai", "deepseek"):
            with self.subTest(provider=provider):
                with self.assertRaisesRegex(ConfigurationError, "registered under provider 'openrouter'"):
                    ProviderModelRegistry.validate_provider_model_pair(provider, self.SLUG)
                with self.assertRaisesRegex(ConfigurationError, "registered under provider 'openrouter'"):
                    ProviderModelRegistry.validate_provider_models_map({provider: self.SLUG})
        with self.assertRaisesRegex(ConfigurationError, "registered under provider 'openrouter'"):
            ProviderModelRegistry.require_openrouter_for_routed_model(ModelProvider.ANTHROPIC, self.SLUG)
        ProviderModelRegistry.require_openrouter_for_routed_model("openrouter", self.SLUG)
        ProviderModelRegistry.require_openrouter_for_routed_model("anthropic", "anthropic/claude-sonnet-5")


if __name__ == "__main__":
    unittest.main()
