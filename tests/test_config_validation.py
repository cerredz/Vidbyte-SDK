from __future__ import annotations

import unittest
from unittest.mock import patch

from vidbyte.lib.config import ImageModelConfig, ModelProvider, TextModelConfig, VideoModelConfig
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError


class ConfigValidationTests(unittest.TestCase):
    def test_text_config_resolves_explicit_api_key(self) -> None:
        config = TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key=" key ")

        self.assertEqual(config.resolved_api_key(), "key")
        self.assertEqual(config.resolved_endpoint(), "https://api.openai.com/v1")

    def test_text_config_resolves_env_api_key(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}, clear=True):
            config = TextModelConfig(provider="anthropic", model="claude-test")

            self.assertEqual(config.resolved_api_key(), "env-key")

    def test_text_config_rejects_missing_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            config = TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-test")

            with self.assertRaises(ConfigurationError):
                config.validate()

    def test_text_config_rejects_bad_temperature(self) -> None:
        config = TextModelConfig(
            provider=ModelProvider.OPENAI,
            model="gpt-test",
            api_key="key",
            temperature=3,
        )

        with self.assertRaises(ConfigurationError):
            config.validate()

    def test_image_config_rejects_unsupported_provider(self) -> None:
        config = ImageModelConfig(provider=ModelProvider.ANTHROPIC, model="none", api_key="key")

        with self.assertRaises(UnsupportedProviderError):
            config.validate()

    def test_video_config_rejects_unsupported_provider(self) -> None:
        config = VideoModelConfig(provider=ModelProvider.XAI, model="none", api_key="key")

        with self.assertRaises(UnsupportedProviderError):
            config.validate()


if __name__ == "__main__":
    unittest.main()
