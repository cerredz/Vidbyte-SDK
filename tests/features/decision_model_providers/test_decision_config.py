"""FILE: tests/features/decision_model_providers/test_decision_config.py

PURPOSE: Pins DecisionModelConfig for nine providers: the registry default fill and resolved_model(), the blank-model check, the nine-value UnsupportedProviderError message, the TypeSafe-only managed guard, tenant endpoints that must be passed explicitly, the per-provider missing-key message, explicit key and endpoint precedence, and the unchanged TypeSafe default.
ROLE IN CODEBASE: Covers spec INV-1 to INV-5, INV-21, AC-7, AC-8, AC-9, AC-14, EC-1 to EC-5, EC-24 and FR-3 of docs/spec/decision-model-providers/spec.md.
ARCHITECTURE NOTE: Synchronous and offline; DecisionModelRunner is constructed with a scripted transport that must record no request, because every failure here lands at construction.
COMMON MODIFICATION PATTERNS: A new provider adds one HOST_ROWS entry in decision_fixtures.py and is picked up by every loop here; a new validation rule gets its own test with the exact message.
KNOWN EDGE CASES: Environment variables are patched with patch.dict; tests that must prove "no env var is read" clear the environment entirely before constructing.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 6.1, 6.2, 6.3, 9.3; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_config.py
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tests.features.decision_model_providers import decision_fixtures as fx
from vidbyte.lib.config import DecisionModelConfig, DecisionModelMode
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.runners.decision import DecisionModelRunner

UNSUPPORTED_MESSAGE = "DecisionModelRunner supports: baseten, cloudflare, foundry, liquid, meragpt, openai, openrouter, perplexity, typesafe."
MANAGED_MESSAGE = "VIDBYTE_MANAGED decision mode is available only for provider typesafe."
NO_ENDPOINT_MESSAGE = "No default endpoint registered for provider '{provider}'. Pass endpoint explicitly with the provider's base URL."
MISSING_KEY_MESSAGE = "Missing API key for provider {provider}. Pass api_key or set {env_var}."


class DefaultModelTests(unittest.TestCase):
    """Pins the registry default fill and the typed resolved_model() reader."""

    def test_model_defaults_from_the_registry_for_every_provider(self) -> None:
        # [Silent Failure] INV-2/FR-3: model is never None after construction and resolved_model() is the str reader.
        for name, row in fx.HOST_ROWS.items():
            with self.subTest(provider=name):
                config = fx.decision_config(name)
                self.assertEqual(config.model, row.default_model)
                self.assertEqual(config.resolved_model(), row.default_model)
                as_string = fx.decision_config(name, provider=name.lower())
                self.assertIs(as_string.normalized_provider(), fx.provider_member(name))
                self.assertEqual(as_string.resolved_model(), row.default_model)

    def test_explicit_model_wins_over_the_default(self) -> None:
        # [Hidden Assumption] INV-2: a caller-chosen id is kept verbatim, including slashed vendor ids.
        self.assertEqual(fx.decision_config("PERPLEXITY", model="pplx-decider-v1-27b").resolved_model(), "pplx-decider-v1-27b")
        self.assertEqual(fx.decision_config("CLOUDFLARE", model="clef-flash").resolved_model(), "clef-flash")
        self.assertEqual(fx.decision_config("OPENAI", model="openai/gpt-6-luna-decisions").resolved_model(), "openai/gpt-6-luna-decisions")

    def test_blank_model_is_rejected_after_the_default_fill(self) -> None:
        # [Edge Case] EC-2: None selects the default, but an empty or whitespace model is still an error.
        self.assertEqual(DecisionModelConfig(model=None, api_key=fx.KEY).resolved_model(), "jev-latest")
        for blank in ("", "  "):
            with self.subTest(model=repr(blank)), self.assertRaises(ConfigurationError) as caught:
                fx.decision_config("PERPLEXITY", model=blank)
            self.assertEqual(caught.exception.message, "model must be non-empty.")


class ProviderGuardTests(unittest.TestCase):
    """Pins the provider membership check and the TypeSafe-only managed mode."""

    def test_unsupported_provider_lists_the_nine_supported_values_sorted(self) -> None:
        # [Hidden Failure] INV-1/AC-9/EC-1: the message names every supported value, and no env var is consulted first.
        with patch.dict(os.environ, {}, clear=True):
            for provider, rejected in (("gemini", "gemini"), (ModelProvider.ANTHROPIC, "anthropic")):
                with self.subTest(provider=rejected), self.assertRaises(UnsupportedProviderError) as caught:
                    DecisionModelConfig(provider=provider)
                self.assertEqual(caught.exception.message, UNSUPPORTED_MESSAGE)
                self.assertEqual(caught.exception.details["provider"], rejected)

    def test_managed_mode_is_typesafe_only_and_reads_no_env_var(self) -> None:
        # [Hidden Failure] INV-3/AC-8/EC-3/D-9: without the guard the Vidbyte key would be posted to another vendor's host.
        with patch.dict(os.environ, {}, clear=True):
            for provider in (ModelProvider.OPENAI, "baseten", *(fx.provider_member(name) for name in fx.NEW_MEMBERS)):
                with self.subTest(provider=str(provider)), self.assertRaises(ConfigurationError) as caught:
                    DecisionModelConfig(provider=provider, mode=DecisionModelMode.VIDBYTE_MANAGED)
                self.assertEqual(caught.exception.message, MANAGED_MESSAGE)
            managed = DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED)
            self.assertIs(managed.normalized_provider(), ModelProvider.TYPESAFE)
            self.assertEqual(managed.resolved_model(), "jev-latest")


class ResolutionTests(unittest.TestCase):
    """Pins key and endpoint resolution at runner construction, before any transport call."""

    def test_tenant_scoped_hosts_require_an_explicit_endpoint(self) -> None:
        # [Hidden Failure] INV-4/AC-7/EC-4/D-7: an empty default endpoint fails at construction, not with a 404 after the first call.
        env = {"CLOUDFLARE_API_TOKEN": fx.KEY, "FOUNDRY_API_KEY": fx.KEY}
        with patch.dict(os.environ, env, clear=False):
            for name in ("CLOUDFLARE", "FOUNDRY"):
                with self.subTest(provider=name):
                    config = DecisionModelConfig(provider=fx.provider_member(name))
                    transport = fx.ScriptedTransport()
                    with self.assertRaises(ConfigurationError) as caught:
                        DecisionModelRunner(config, transport=transport)
                    self.assertEqual(caught.exception.message, NO_ENDPOINT_MESSAGE.format(provider=name.lower()))
                    self.assertEqual(transport.requests, [])
                    with self.assertRaises(ConfigurationError):
                        config.validate()
                    with_endpoint = DecisionModelConfig(provider=fx.provider_member(name), endpoint=fx.TENANT_ENDPOINTS[name])
                    with_endpoint.validate()
                    self.assertEqual(with_endpoint.resolved_endpoint(), fx.TENANT_ENDPOINTS[name])

    def test_missing_key_names_the_provider_and_its_env_var(self) -> None:
        # [Hidden Failure] INV-4/EC-5: each provider's message names its own env var, so a Perplexity user is never told about TYPESAFE_API_KEY.
        with patch.dict(os.environ, {}, clear=False):
            for row in fx.HOST_ROWS.values():
                os.environ.pop(row.env_var, None)
            for name, row in fx.HOST_ROWS.items():
                with self.subTest(provider=name):
                    config = fx.decision_config(name, api_key=None)
                    transport = fx.ScriptedTransport()
                    with self.assertRaises(ConfigurationError) as caught:
                        DecisionModelRunner(config, transport=transport)
                    self.assertEqual(caught.exception.message, MISSING_KEY_MESSAGE.format(provider=name.lower(), env_var=row.env_var))
                    self.assertEqual(transport.requests, [])

    def test_explicit_key_and_endpoint_win_over_the_environment(self) -> None:
        # [Hidden Assumption] INV-4/EC-24: explicit values win, env vars fill gaps, and a trailing slash never reaches the URL.
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "env-perplexity-key"}, clear=False):
            explicit = DecisionModelConfig(provider=fx.provider_member("PERPLEXITY"), api_key=fx.KEY, endpoint="https://proxy.example/v1/")
            self.assertEqual(explicit.resolved_api_key(), fx.KEY)
            self.assertEqual(explicit.resolved_endpoint(), "https://proxy.example/v1")
            from_env = DecisionModelConfig(provider=fx.provider_member("PERPLEXITY"))
            self.assertEqual(from_env.resolved_api_key(), "env-perplexity-key")
            self.assertEqual(from_env.resolved_endpoint(), "https://api.perplexity.ai/v1")
            from_env.validate()

    def test_repr_hides_the_key_for_every_provider(self) -> None:
        # [Silent Failure] INV-5/T-3: a repr leak would put a vendor key into logs and exception reports.
        for name in fx.HOST_ROWS:
            with self.subTest(provider=name):
                self.assertNotIn(fx.KEY, repr(fx.decision_config(name)))


class TypeSafeDefaultTests(unittest.TestCase):
    """Pins that DecisionModelConfig() still means direct TypeSafe with the same values."""

    def test_default_config_is_direct_typesafe_with_the_same_values(self) -> None:
        # [Hidden Failure] INV-21/AC-14: the default provider, model, mode, key source, and endpoint are unchanged.
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": fx.KEY}, clear=False):
            config = DecisionModelConfig()
            self.assertIs(config.mode, DecisionModelMode.TYPESAFE)
            self.assertIs(config.normalized_provider(), ModelProvider.TYPESAFE)
            self.assertEqual(config.model, "jev-latest")
            self.assertEqual(config.resolved_model(), "jev-latest")
            self.assertEqual(config.resolved_api_key(), fx.KEY)
            self.assertEqual(config.resolved_endpoint(), "https://api.typesafe.ai/v1")
            self.assertEqual((config.timeout_seconds, config.retry_count), (60.0, 2))

    def test_positional_construction_is_unchanged(self) -> None:
        # [Hidden Failure] section 9.4: widening model to str | None must not shift the positional field order.
        config = DecisionModelConfig(ModelProvider.TYPESAFE, "jev-latest", fx.KEY, "https://proxy.example/v1", 30.0, 1)
        self.assertEqual(config.resolved_model(), "jev-latest")
        self.assertEqual(config.resolved_api_key(), fx.KEY)
        self.assertEqual(config.resolved_endpoint(), "https://proxy.example/v1")
        self.assertEqual((config.timeout_seconds, config.retry_count, config.mode), (30.0, 1, DecisionModelMode.TYPESAFE))


if __name__ == "__main__":
    unittest.main()
