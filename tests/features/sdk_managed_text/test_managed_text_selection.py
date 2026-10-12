"""FILE: tests/features/sdk_managed_text/test_managed_text_selection.py

PURPOSE: Proves how a text call decides between BYOK and Vidbyte-managed state, what managed state refuses before any request, and that the Vidbyte key never reaches a vendor, a repr or an adapter-built header.
ROLE IN CODEBASE: Selection and key-hygiene layer of tests/features/sdk_managed_text/ (spec INV-4, INV-5, INV-7, INV-8, INV-13, INV-14, INV-18..INV-22; AC-4..AC-7, AC-13..AC-16, AC-21, AC-22; EC-1..EC-7, EC-16..EC-19, EC-21, EC-28). Exercises vidbyte/lib/dataclasses/model_configs.py, vidbyte/lib/registries/models.py, vidbyte/lib/runners/text.py and vidbyte/lib/runners/streaming_text.py.
ARCHITECTURE NOTE: Every test clears the environment with patch.dict(..., clear=True) and observes the decision through what the scripted transport receives (gateway or vendor URL, and the credential header), or through the error raised at construction.
COMMON MODIFICATION PATTERNS: Add a row to the fall-through table when the key order changes; add a provider to UNMANAGED_TEXT_PROVIDERS when the SDK gains a text provider the gateway does not serve.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level (see managed_text_fixtures.py). 2. Do not leave the environment uncleared, as tests/test_model_registry.py:57-61 does; a real VIDBYTE_API_KEY would change outcomes here.
KNOWN EDGE CASES: kimi reads MOONSHOT_API_KEY. A BYOK runner is not pinned, so removing its provider key later sends the placeholder to the vendor. Blank keys are skipped, not selected.
RELATED DOCS: tests/features/sdk_managed_text/FEATURE.md; docs/spec/managed-generative-models/spec.md sections 6.1, 6.3, 8.5 and 9.2.
TESTS: python -m pytest tests/features/sdk_managed_text/test_managed_text_selection.py
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from dataclasses import fields
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    GATEWAY_URL,
    MANAGED_MODELS,
    OTHER_VIDBYTE_KEY,
    UNMANAGED_TEXT_PROVIDERS,
    VIDBYTE_KEY,
    ScriptedGateway,
    answer,
    header,
    provider_answer,
)
from vidbyte.lib.config import AudioModelConfig, DecisionModelConfig, DecisionModelMode, EmbeddingModelConfig, ImageModelConfig, TextModelConfig, VideoModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError, UnsupportedProviderError
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.runners import StreamingTextModelRunner, TextModelRunner

CREDENTIAL_ERROR_KIND = "vidbyte_managed_credentials"
MISSING_VIDBYTE_KEY = "Missing Vidbyte API key. Pass api_key or set VIDBYTE_API_KEY."
MALFORMED_VIDBYTE_KEY = "The managed Vidbyte API key must be a live key in the vb_live_ format."
NON_STRING_TEXT_KEY = "api_key must be a string in VIDBYTE_MANAGED text mode."
# A valid live key that exercises every allowed character class at exactly the 32-character minimum.
BOUNDARY_VIDBYTE_KEY = "vb_live_" + "Ab9_-" * 6 + "Zz"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MOONSHOT_CHAT_URL = "https://api.moonshot.ai/v1/chat/completions"
EXPECTED_TEXT_CONFIG_FIELDS = [
    "provider", "model", "api_key", "system", "messages", "temperature", "top_p", "max_output_tokens", "stop_sequences", "response_format",
    "tools", "tool_choice", "tool_config", "safety_settings", "cached_content", "thinking_config", "metadata", "extra_body", "endpoint", "timeout_seconds",
    "mode",
]


class FakeStreamingTransport:
    """Records streaming requests and yields scripted SSE lines."""

    def __init__(self, lines: list[str]) -> None:
        # Keeps the scripted lines and every stream request made.
        self.lines = list(lines)
        self.requests: list[dict[str, object]] = []

    def stream_request(self, **kwargs: object) -> object:
        # Records the request, then yields the scripted lines as the provider stream.
        self.requests.append(dict(kwargs))
        yield from self.lines


def run_text(provider: ModelProvider, environment: dict[str, str], *, api_key: str | None = None, endpoint: str | None = None) -> ScriptedGateway:
    # Sends one text call under a cleared environment and returns what the transport received.
    transport = ScriptedGateway(provider_answer(provider))
    model = MANAGED_MODELS.get(provider, "openrouter/auto")
    with patch.dict(os.environ, environment, clear=True):
        TextModelRunner(TextModelConfig(provider=provider.value, model=model, api_key=api_key, endpoint=endpoint), transport=transport).run("Hi")
    return transport


class KeySelectionTests(unittest.TestCase):
    """Checks the INV-4 fall-through, explicit managed mode, and the refusals managed state owes before any request."""

    def test_key_fall_through_sends_byok_to_the_vendor_or_vidbyte_keys_to_the_gateway_in_inv4_order(self) -> None:
        # INV-4, EC-1, EC-5, EC-28: each row is (env, explicit key) -> destination and credential; a wrong row bills a BYOK user or leaks the key.
        rows = (
            ("explicit provider key beats VIDBYTE_API_KEY", ModelProvider.OPENAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, "sk-explicit", OPENAI_RESPONSES_URL, "Bearer sk-explicit"),
            ("explicit live key is managed and wins over VIDBYTE_API_KEY", ModelProvider.OPENAI, {"VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}, VIDBYTE_KEY, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}"),
            ("provider env key beats VIDBYTE_API_KEY", ModelProvider.OPENAI, {"OPENAI_API_KEY": "sk-env", "VIDBYTE_API_KEY": VIDBYTE_KEY}, None, OPENAI_RESPONSES_URL, "Bearer sk-env"),
            ("live key in the provider env var is managed and is the bearer", ModelProvider.OPENAI, {"OPENAI_API_KEY": VIDBYTE_KEY, "VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}, None, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}"),
            ("live key in the provider env var alone is managed", ModelProvider.OPENAI, {"OPENAI_API_KEY": VIDBYTE_KEY}, None, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}"),
            ("VIDBYTE_API_KEY alone is managed", ModelProvider.ANTHROPIC, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, None, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}"),
            ("blank provider env var falls through to VIDBYTE_API_KEY", ModelProvider.GEMINI, {"GEMINI_API_KEY": "   ", "VIDBYTE_API_KEY": VIDBYTE_KEY}, None, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}"),
            ("blank explicit key falls through to VIDBYTE_API_KEY", ModelProvider.XAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, "   ", GATEWAY_URL, f"Bearer {VIDBYTE_KEY}"),
            ("VIDBYTE_API_KEY padded with whitespace and a newline is stripped", ModelProvider.DEEPSEEK, {"VIDBYTE_API_KEY": f"  {VIDBYTE_KEY}\n"}, None, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}"),
            ("kimi's own MOONSHOT_API_KEY keeps it BYOK", ModelProvider.KIMI, {"MOONSHOT_API_KEY": "sk-moonshot", "VIDBYTE_API_KEY": VIDBYTE_KEY}, None, MOONSHOT_CHAT_URL, "Bearer sk-moonshot"),
            ("explicit key without the prefix stays BYOK after stripping", ModelProvider.KIMI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, " sk-padded ", MOONSHOT_CHAT_URL, "Bearer sk-padded"),
        )
        for label, provider, environment, api_key, url, credential in rows:
            with self.subTest(label):
                transport = run_text(provider, environment, api_key=api_key)
                self.assertEqual([request["url"] for request in transport.requests], [url])
                self.assertEqual(header(transport.requests[0], "authorization"), credential)
                if url != GATEWAY_URL:
                    sent = json.dumps(transport.requests)
                    self.assertNotIn(VIDBYTE_KEY, sent)
                    self.assertNotIn(OTHER_VIDBYTE_KEY, sent)

    def test_without_a_selectable_key_the_existing_missing_key_message_is_unchanged(self) -> None:
        # EC-2, INV-21: VIDBYTE_API_KEY never serves an unmanaged provider, and the no-key text keeps today's wording.
        rows = (
            (ModelProvider.OPENROUTER, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, "Missing API key for provider openrouter. Pass api_key or set OPENROUTER_API_KEY."),
            (ModelProvider.MISTRAL, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, "Missing API key for provider mistral. Pass api_key or set MISTRAL_API_KEY."),
            (ModelProvider.OPENAI, {}, "Missing API key for provider openai. Pass api_key or set OPENAI_API_KEY."),
        )
        for provider, environment, message in rows:
            with self.subTest(provider=provider.value, vidbyte_key_set=bool(environment)), patch.dict(os.environ, environment, clear=True):
                config = TextModelConfig(provider=provider.value, model="some-model")
                self.assertFalse(config.is_vidbyte_managed())
                with self.assertRaises(ConfigurationError) as caught:
                    TextModelRunner(config, transport=ScriptedGateway())
                self.assertEqual(str(caught.exception), message)

    def test_explicit_managed_mode_uses_the_vidbyte_key_and_never_reads_the_provider_env_var(self) -> None:
        # AC-4, INV-5: explicit mode ignores a BYOK key in the provider env var, and never takes a live key from it either.
        from vidbyte.lib.config import TextModelMode

        transport = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai-byok", "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED), transport=transport).run("Hi")
        self.assertEqual([request["url"] for request in transport.requests], [GATEWAY_URL])
        self.assertEqual(header(transport.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")
        self.assertNotIn("sk-openai-byok", json.dumps(transport.requests))

        explicit = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}, clear=True):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_key=VIDBYTE_KEY, mode=TextModelMode.VIDBYTE_MANAGED), transport=explicit).run("Hi")
        self.assertEqual(header(explicit.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")

        with patch.dict(os.environ, {"OPENAI_API_KEY": VIDBYTE_KEY}, clear=True), self.assertRaises(ConfigurationError) as caught:
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED), transport=ScriptedGateway())
        self.assertEqual(str(caught.exception), MISSING_VIDBYTE_KEY)
        self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)

    def test_managed_credential_failures_raise_tagged_configuration_errors_before_any_request(self) -> None:
        # AC-5, EC-4: missing, malformed (including one character short and a header-injection attempt) and non-string keys fail at construction.
        from vidbyte.lib.config import TextModelMode

        managed = TextModelMode.VIDBYTE_MANAGED
        rows = (
            ("explicit mode, no key anywhere", {}, {"mode": managed}, MISSING_VIDBYTE_KEY),
            ("explicit mode, test-environment key", {}, {"mode": managed, "api_key": "vb_test_" + "a" * 32}, MALFORMED_VIDBYTE_KEY),
            ("auto, malformed VIDBYTE_API_KEY is still selected", {"VIDBYTE_API_KEY": "vb_test_" + "a" * 32}, {}, MALFORMED_VIDBYTE_KEY),
            ("auto, live prefix one character short", {"VIDBYTE_API_KEY": "vb_live_" + "a" * 31}, {}, MALFORMED_VIDBYTE_KEY),
            ("auto, explicit short live key", {}, {"api_key": "vb_live_short"}, MALFORMED_VIDBYTE_KEY),
            ("auto, explicit live key carrying an injected header", {}, {"api_key": f"{VIDBYTE_KEY}\r\nX-Injected: 1"}, MALFORMED_VIDBYTE_KEY),
            ("explicit mode, non-string key", {}, {"mode": managed, "api_key": 12345}, NON_STRING_TEXT_KEY),
        )
        for label, environment, options, message in rows:
            with self.subTest(label), patch.dict(os.environ, environment, clear=True):
                transport = ScriptedGateway()
                with self.assertRaises(ConfigurationError) as caught:
                    TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", **options), transport=transport)
                self.assertEqual(str(caught.exception), message)
                self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
                self.assertNotIn("X-Injected", repr(caught.exception.details))
                self.assertEqual(transport.requests, [])
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": BOUNDARY_VIDBYTE_KEY}, clear=True):
            transport = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport).run("Hi")
        self.assertEqual(header(transport.requests[0], "authorization"), f"Bearer {BOUNDARY_VIDBYTE_KEY}")

    def test_managed_state_refuses_a_custom_endpoint_while_a_byok_proxy_still_works(self) -> None:
        # AC-6, EC-6, EC-7, INV-7: the Vidbyte bearer never follows a caller URL; explicit mode refuses at construction, AUTO at the runner.
        from vidbyte.lib.config import TextModelMode

        proxy = "https://proxy.example/v1"
        with self.assertRaisesRegex(ConfigurationError, "(?i)endpoint"):
            TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED, endpoint=proxy)
        for label, environment, api_key in (("VIDBYTE_API_KEY alone", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, None), ("explicit live key", {}, VIDBYTE_KEY)):
            with self.subTest(label), patch.dict(os.environ, environment, clear=True):
                # Building the AUTO config reads no environment, so it must succeed; the runner then refuses.
                config = TextModelConfig(provider="openai", model="gpt-5.5", api_key=api_key, endpoint=proxy)
                transport = ScriptedGateway()
                with self.assertRaisesRegex(ConfigurationError, "(?i)endpoint"):
                    TextModelRunner(config, transport=transport)
                self.assertEqual(transport.requests, [])
        byok = run_text(ModelProvider.OPENAI, {"OPENAI_API_KEY": "sk-proxy", "VIDBYTE_API_KEY": VIDBYTE_KEY}, endpoint=proxy)
        self.assertEqual([request["url"] for request in byok.requests], ["https://proxy.example/v1/responses"])
        self.assertEqual(header(byok.requests[0], "authorization"), "Bearer sk-proxy")

    def test_managed_state_refuses_every_provider_the_gateway_does_not_serve(self) -> None:
        # AC-7, EC-3, INV-8: without this guard an explicit vb_live_ key would be sent to OpenRouter and other vendors.
        from vidbyte.lib.config import TextModelMode

        for provider in UNMANAGED_TEXT_PROVIDERS:
            with self.subTest(provider=provider.value), patch.dict(os.environ, {}, clear=True):
                transport = ScriptedGateway()
                with self.assertRaises(UnsupportedProviderError) as caught:
                    TextModelRunner(TextModelConfig(provider=provider.value, model="some-model", api_key=VIDBYTE_KEY), transport=transport)
                for managed_provider in MANAGED_MODELS:
                    self.assertIn(managed_provider.value, str(caught.exception))
                self.assertEqual(caught.exception.details.get("provider"), provider.value)
                self.assertNotIn(VIDBYTE_KEY, str(caught.exception))
                self.assertEqual(transport.requests, [])
        with self.assertRaises(UnsupportedProviderError):
            TextModelConfig(provider="openrouter", model="openrouter/auto", mode=TextModelMode.VIDBYTE_MANAGED)

    def test_streaming_refuses_managed_state_but_still_streams_byok_beside_a_vidbyte_key(self) -> None:
        # AC-13, EC-16, EC-17, INV-13, INV-22: the refusal must discriminate; refusing whenever VIDBYTE_API_KEY is set would break BYOK streaming.
        from vidbyte.lib.config import TextModelMode

        refusals = (
            ("VIDBYTE_API_KEY alone", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "openai", "model": "gpt-5.5"}, "OPENAI_API_KEY"),
            ("explicit managed mode", {}, {"provider": "anthropic", "model": "claude-sonnet-5", "api_key": VIDBYTE_KEY, "mode": TextModelMode.VIDBYTE_MANAGED}, "ANTHROPIC_API_KEY"),
            # Gemini cannot stream at all; the managed refusal still comes first and names the managed limitation.
            ("non-streaming provider", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "gemini", "model": "gemini-3.5-flash"}, "GEMINI_API_KEY"),
        )
        for label, environment, options, env_var in refusals:
            with self.subTest(label), patch.dict(os.environ, environment, clear=True):
                transport = FakeStreamingTransport([])
                with self.assertRaises(UnsupportedProviderError) as caught:
                    StreamingTextModelRunner(TextModelConfig(**options), transport=transport)
                message = str(caught.exception)
                self.assertRegex(message, "(?i)managed")
                self.assertIn("TextModelRunner", message)
                self.assertIn(env_var, message)
                self.assertEqual(caught.exception.details.get("provider"), options["provider"])
                self.assertEqual(caught.exception.details.get("mode"), "vidbyte_managed")
                self.assertEqual(transport.requests, [])
        transport = FakeStreamingTransport([json.dumps({"type": "response.text.delta", "delta": "Hel"}), json.dumps({"type": "response.text.delta", "delta": "lo"})])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-stream", "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            chunks = list(StreamingTextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport).stream("Hi"))
        self.assertEqual(chunks, ["Hel", "lo"])
        self.assertEqual(transport.requests[0]["url"], OPENAI_RESPONSES_URL)
        self.assertEqual(header(transport.requests[0], "authorization"), "Bearer sk-stream")
        self.assertNotIn(VIDBYTE_KEY, json.dumps(transport.requests))

    def test_managed_runner_stays_managed_and_byok_runner_never_sends_the_vidbyte_key_after_env_changes(self) -> None:
        # AC-21, INV-14, EC-19: managed mode is fixed at construction; an unpinned BYOK runner may fall to the placeholder but never to the gateway or the key.
        from vidbyte.lib.constants.jev import VIDBYTE_MANAGED_KEY_PLACEHOLDER

        managed = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=managed)
            os.environ["OPENAI_API_KEY"] = "sk-set-after-construction"
            runner.run("Hi")
        self.assertEqual([request["url"] for request in managed.requests], [GATEWAY_URL])
        self.assertEqual(header(managed.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")

        vendor = ScriptedGateway(answer(401, {"error": {"message": "Incorrect API key provided: vidbyte-managed.", "type": "invalid_request_error", "code": "invalid_api_key"}}))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-removed-later", "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=vendor)
            del os.environ["OPENAI_API_KEY"]
            with self.assertRaises(ProviderRequestError) as caught:
                runner.run("Hi")
        self.assertEqual((caught.exception.provider, caught.exception.status_code), ("openai", 401))
        self.assertEqual([request["url"] for request in vendor.requests], [OPENAI_RESPONSES_URL])
        self.assertEqual(header(vendor.requests[0], "authorization"), f"Bearer {VIDBYTE_MANAGED_KEY_PLACEHOLDER}")
        self.assertNotIn(VIDBYTE_KEY, json.dumps(vendor.requests))

    def test_vidbyte_key_alone_manages_text_but_not_image_video_audio_or_embedding(self) -> None:
        # AC-22, INV-18: the fall-through lives outside resolve_api_key, so other modalities never send a vb_live_ key to a vendor.
        missing = "Missing API key for provider openai. Pass api_key or set OPENAI_API_KEY."
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            self.assertTrue(TextModelConfig(provider="openai", model="gpt-5.5").is_vidbyte_managed())
            others = (
                ImageModelConfig(provider="openai", model="gpt-image-1"),
                VideoModelConfig(provider="openai", model="sora-2"),
                AudioModelConfig(provider="openai", model="gpt-4o-mini-tts"),
                EmbeddingModelConfig(provider="openai", model="text-embedding-3-small"),
            )
            for config in others:
                with self.subTest(config=type(config).__name__), self.assertRaises(ConfigurationError) as caught:
                    config.validate()
                self.assertEqual(str(caught.exception), missing)
            with self.assertRaises(ConfigurationError) as caught:
                ProviderModelRegistry.resolve_api_key("openai", None)
            self.assertEqual(str(caught.exception), missing)

    def test_text_config_appends_mode_last_and_rejects_a_mode_that_is_not_the_enum(self) -> None:
        # INV-20, EC-18, FR-1: the first 20 fields keep their order (positional callers), and a YAML string mode is refused like DecisionModelConfig does.
        from vidbyte.lib.config import TextModelMode
        from vidbyte.lib.enums import TextModelMode as EnumsTextModelMode

        self.assertIs(TextModelMode, EnumsTextModelMode)
        self.assertEqual({member.name: member.value for member in TextModelMode}, {"AUTO": "auto", "VIDBYTE_MANAGED": "vidbyte_managed"})
        self.assertEqual([field.name for field in fields(TextModelConfig)], EXPECTED_TEXT_CONFIG_FIELDS)
        self.assertIs(TextModelConfig(provider="openai", model="gpt-5.5").mode, TextModelMode.AUTO)
        self.assertEqual(TextModelConfig("openai", "gpt-5.5", "sk-positional").api_key, "sk-positional")
        with self.assertRaises(ConfigurationError) as caught:
            TextModelConfig(provider="openai", model="gpt-5.5", mode="vidbyte_managed")  # type: ignore[arg-type]
        self.assertEqual(str(caught.exception), "mode must be a TextModelMode value.")


class KeyHygieneTests(unittest.TestCase):
    """Checks that the Vidbyte key stays out of reprs and adapter-built headers, and that Decision shares the resolver."""

    def test_text_config_repr_hides_the_api_key(self) -> None:
        # AC-15, FR-10: a repr in a log or traceback must not carry any key, Vidbyte or BYOK.
        for key in (VIDBYTE_KEY, "sk-live-secret-123"):
            with self.subTest(key=key[:8]):
                rendered = repr(TextModelConfig(provider="openai", model="gpt-5.5", api_key=key))
                self.assertNotIn(key, rendered)
                self.assertIn("gpt-5.5", rendered)

    def test_adapters_see_only_the_placeholder_key_in_managed_state_even_when_called_directly(self) -> None:
        # AC-16, EC-21, INV-6, INV-7: adapters build vendor auth from resolved_api_key(); a direct call must hand the vendor only the placeholder.
        from vidbyte.lib.config import TextModelMode
        from vidbyte.lib.constants.jev import VIDBYTE_MANAGED_KEY_PLACEHOLDER
        from vidbyte.providers import ModelProviders

        self.assertFalse(VIDBYTE_MANAGED_KEY_PLACEHOLDER.startswith("vb_live_"))
        cases = (
            ("VIDBYTE_API_KEY alone", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "openai", "model": "gpt-5.5"}, OPENAI_RESPONSES_URL, "authorization", f"Bearer {VIDBYTE_MANAGED_KEY_PLACEHOLDER}"),
            ("explicit live key", {}, {"provider": "anthropic", "model": "claude-sonnet-5", "api_key": VIDBYTE_KEY}, "https://api.anthropic.com/v1/messages", "x-api-key", VIDBYTE_MANAGED_KEY_PLACEHOLDER),
            ("explicit managed mode", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "gemini", "model": "gemini-3.5-flash", "mode": TextModelMode.VIDBYTE_MANAGED}, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent", "x-goog-api-key", VIDBYTE_MANAGED_KEY_PLACEHOLDER),
        )
        for label, environment, options, url, header_name, credential in cases:
            with self.subTest(label), patch.dict(os.environ, environment, clear=True):
                config = TextModelConfig(**options)
                self.assertEqual(config.resolved_api_key(), VIDBYTE_MANAGED_KEY_PLACEHOLDER)
                plain = ScriptedGateway(answer(401, {"error": {"message": "invalid api key", "type": "authentication_error"}}))
                with self.assertRaises(ProviderRequestError) as caught:
                    asyncio.run(ModelProviders.text(config).run_text(prompt="Hi", system=None, metadata=None, transport=plain, config=config))
                self.assertEqual((caught.exception.provider, caught.exception.status_code), (options["provider"], 401))
                self.assertEqual([request["url"] for request in plain.requests], [url])
                self.assertEqual(header(plain.requests[0], header_name), credential)
                self.assertNotIn(VIDBYTE_KEY, json.dumps(plain.requests))

    def test_decision_and_text_share_one_managed_key_resolver_with_unchanged_messages(self) -> None:
        # AC-14, INV-19, FR-3, D-14: two inline copies of the live-key rule drift; Decision must give exactly what the shared resolver gives.
        rows = (
            ({}, None, ("error", MISSING_VIDBYTE_KEY, CREDENTIAL_ERROR_KIND)),
            ({"VIDBYTE_API_KEY": "   "}, "", ("error", MISSING_VIDBYTE_KEY, CREDENTIAL_ERROR_KIND)),
            ({"VIDBYTE_API_KEY": VIDBYTE_KEY}, None, ("key", VIDBYTE_KEY)),
            ({"VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}, f"  {VIDBYTE_KEY}\n", ("key", VIDBYTE_KEY)),
            ({}, "vb_test_" + "a" * 32, ("error", MALFORMED_VIDBYTE_KEY, CREDENTIAL_ERROR_KIND)),
            ({}, "vb_live_" + "a" * 31, ("error", MALFORMED_VIDBYTE_KEY, CREDENTIAL_ERROR_KIND)),
            ({}, BOUNDARY_VIDBYTE_KEY, ("key", BOUNDARY_VIDBYTE_KEY)),
        )
        for environment, explicit_key, expected in rows:
            with self.subTest(explicit=repr(explicit_key)[:12], env=sorted(environment)), patch.dict(os.environ, environment, clear=True):
                shared = self._resolution(lambda key=explicit_key: ProviderModelRegistry.resolve_vidbyte_api_key(key))
                decision = self._resolution(lambda key=explicit_key: DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, api_key=key).resolved_api_key())
                self.assertEqual(shared, expected)
                self.assertEqual(decision, expected)
        with self.assertRaises(ConfigurationError) as caught:
            DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, api_key=12345).resolved_api_key()  # type: ignore[arg-type]
        self.assertEqual(str(caught.exception), "api_key must be a string in VIDBYTE_MANAGED decision mode.")
        self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)

    @staticmethod
    def _resolution(resolve: object) -> tuple[str, ...]:
        # Reduces one resolution to a comparable value: the key, or the message and error_kind it raised.
        try:
            return ("key", resolve())  # type: ignore[operator]
        except ConfigurationError as error:
            return ("error", str(error), str(error.details.get("error_kind")))


if __name__ == "__main__":
    unittest.main()
