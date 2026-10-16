"""FILE: tests/features/sdk_managed_text/test_managed_text_selection.py

PURPOSE: Proves how a text call resolves its keys (a provider key relays through the gateway in AUTO, goes to the vendor only in DIRECT; a Vidbyte key is only ever the gateway bearer), what the gateway modes refuse before any request, and that the Vidbyte key never reaches a vendor, a repr or an adapter-built header. Updated for docs/spec/byok-api-keys (section 13 superseded rows).
ROLE IN CODEBASE: Selection and key-hygiene layer of tests/features/sdk_managed_text/ (spec INV-4, INV-5, INV-7, INV-8, INV-13, INV-14, INV-18..INV-22; AC-4..AC-7, AC-13..AC-16, AC-21, AC-22; EC-1..EC-7, EC-16..EC-19, EC-21, EC-28). Exercises vidbyte/lib/dataclasses/model_configs.py, vidbyte/lib/registries/models.py, vidbyte/lib/runners/text.py and vidbyte/lib/runners/streaming_text.py.
ARCHITECTURE NOTE: Every test clears the environment with patch.dict(..., clear=True) and observes the decision through what the scripted transport receives (gateway or vendor URL, and the credential header), or through the error raised at construction.
COMMON MODIFICATION PATTERNS: Add a row to the fall-through table when the key order changes; add a provider to UNMANAGED_TEXT_PROVIDERS when the SDK gains a text provider the gateway does not serve.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level (see managed_text_fixtures.py). 2. Do not leave the environment uncleared, as tests/test_model_registry.py:57-61 does; a real VIDBYTE_API_KEY would change outcomes here.
KNOWN EDGE CASES: kimi reads MOONSHOT_API_KEY. A gateway runner is pinned at construction, provider key included. Blank keys are skipped, not selected. Text missing-key messages are bound by the facts byok-api-keys table M names; Decision keeps its exact wording (INV-18).
RELATED DOCS: tests/features/sdk_managed_text/FEATURE.md; docs/spec/managed-generative-models/spec.md sections 6.1, 6.3, 8.5 and 9.2; docs/spec/byok-api-keys/spec.md sections 6.1, 9.2 (tables R and M) and 13.
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
# Decision keeps its exact missing-key message (byok-api-keys INV-18, D-14).
DECISION_MISSING_VIDBYTE_KEY = "Missing Vidbyte API key. Pass api_key or set VIDBYTE_API_KEY."
# Text names its own ways out (byok-api-keys M-9); the wording is the implementer's, so only these facts are bound.
MISSING_VIDBYTE_KEY_FACTS = ("Missing Vidbyte API key", "vidbyte_api_key", "VIDBYTE_API_KEY", "TextModelMode.DIRECT")
MALFORMED_VIDBYTE_KEY = "The managed Vidbyte API key must be a live key in the vb_live_ format."
# byok-api-keys M-11: the explicit Vidbyte key that is not a string names its field.
NON_STRING_VIDBYTE_KEY_FACTS = ("vidbyte_api_key",)
RELAY_HEADER = "X-Vidbyte-Provider-Key"
# An Anthropic-shaped fake built at run time; its sk-ant- prefix binds it to anthropic (byok-api-keys table F).
ANTHROPIC_RELAY_KEY = "sk-ant-" + "relay" + "A" * 20
# A valid live key that exercises every allowed character class at exactly the 32-character minimum.
BOUNDARY_VIDBYTE_KEY = "vb_live_" + "Ab9_-" * 6 + "Zz"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MOONSHOT_CHAT_URL = "https://api.moonshot.ai/v1/chat/completions"
EXPECTED_TEXT_CONFIG_FIELDS = [
    "provider", "model", "api_keys", "system", "messages", "temperature", "top_p", "max_output_tokens", "stop_sequences", "response_format",
    "tools", "tool_choice", "tool_config", "safety_settings", "cached_content", "thinking_config", "metadata", "extra_body", "endpoint", "timeout_seconds",
    "mode", "prompt_index", "vidbyte_api_key",
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


def run_text(provider: ModelProvider, environment: dict[str, str], *, api_keys: list[str] | None = None, endpoint: str | None = None, direct: bool = False) -> ScriptedGateway:
    # Sends one text call under a cleared environment and returns what the transport received; direct=True sends it vendor-direct (DIRECT).
    from vidbyte.lib.config import TextModelMode

    transport = ScriptedGateway(provider_answer(provider))
    model = MANAGED_MODELS.get(provider, "openrouter/auto")
    mode = TextModelMode.DIRECT if direct else TextModelMode.AUTO
    with patch.dict(os.environ, environment, clear=True):
        TextModelRunner(TextModelConfig(provider=provider.value, model=model, api_keys=api_keys, endpoint=endpoint, mode=mode), transport=transport).run("Hi")
    return transport


def assert_message(case: unittest.TestCase, message: str, expected: str | tuple[str, ...]) -> None:
    # An unchanged message is compared exactly; a byok-api-keys table M message is checked for the facts the spec binds.
    if isinstance(expected, str):
        case.assertEqual(message, expected)
        return
    for fact in expected:
        case.assertIn(fact, message)


class KeySelectionTests(unittest.TestCase):
    """Checks the INV-4 fall-through, explicit managed mode, and the refusals managed state owes before any request."""

    def test_key_resolution_relays_provider_keys_through_the_gateway_and_sends_only_direct_calls_to_the_vendor(self) -> None:
        # byok-api-keys INV-1, INV-2, D-7, D-25 (was INV-4's fall-through): each row is (env, api_keys, mode) -> destination, bearer and relayed key.
        # A wrong row sends a provider key to the wrong place, bills the wrong account, or leaks the Vidbyte key to a vendor.
        rows = (
            ("explicit provider key beside VIDBYTE_API_KEY is relayed", ModelProvider.OPENAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, ["sk-explicit"], False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", "sk-explicit"),
            ("explicit provider key in DIRECT goes to the vendor", ModelProvider.OPENAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, ["sk-explicit"], True, OPENAI_RESPONSES_URL, "Bearer sk-explicit", None),
            ("a Vidbyte entry in api_keys is the bearer and wins over VIDBYTE_API_KEY", ModelProvider.OPENAI, {"VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}, [VIDBYTE_KEY], False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", None),
            ("provider env key beside VIDBYTE_API_KEY is relayed", ModelProvider.OPENAI, {"OPENAI_API_KEY": "sk-env", "VIDBYTE_API_KEY": VIDBYTE_KEY}, None, False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", "sk-env"),
            ("VIDBYTE_API_KEY alone is Vidbyte-paid", ModelProvider.ANTHROPIC, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, None, False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", None),
            ("blank provider env var leaves the call Vidbyte-paid", ModelProvider.GEMINI, {"GEMINI_API_KEY": "   ", "VIDBYTE_API_KEY": VIDBYTE_KEY}, None, False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", None),
            ("blank list entry is skipped", ModelProvider.XAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, ["   "], False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", None),
            ("VIDBYTE_API_KEY padded with whitespace and a newline is stripped", ModelProvider.DEEPSEEK, {"VIDBYTE_API_KEY": f"  {VIDBYTE_KEY}\n"}, None, False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", None),
            ("kimi's own MOONSHOT_API_KEY is relayed", ModelProvider.KIMI, {"MOONSHOT_API_KEY": "sk-moonshot", "VIDBYTE_API_KEY": VIDBYTE_KEY}, None, False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", "sk-moonshot"),
            ("kimi in DIRECT reads MOONSHOT_API_KEY", ModelProvider.KIMI, {"MOONSHOT_API_KEY": "sk-moonshot", "VIDBYTE_API_KEY": VIDBYTE_KEY}, None, True, MOONSHOT_CHAT_URL, "Bearer sk-moonshot", None),
            ("explicit key without a prefix is stripped and relayed", ModelProvider.KIMI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, [" sk-padded "], False, GATEWAY_URL, f"Bearer {VIDBYTE_KEY}", "sk-padded"),
        )
        for label, provider, environment, api_keys, direct, url, credential, relayed in rows:
            with self.subTest(label):
                transport = run_text(provider, environment, api_keys=api_keys, direct=direct)
                self.assertEqual([request["url"] for request in transport.requests], [url])
                self.assertEqual(header(transport.requests[0], "authorization"), credential)
                self.assertEqual(header(transport.requests[0], RELAY_HEADER), relayed)
                sent = json.dumps(transport.requests)
                if url != GATEWAY_URL:
                    self.assertNotIn(VIDBYTE_KEY, sent)
                    self.assertNotIn(OTHER_VIDBYTE_KEY, sent)
                if relayed is not None:
                    self.assertEqual(sent.count(relayed), 1, "the relayed key travels only in its header")
        # EC-13, M-14: a Vidbyte key in a provider variable is refused before any request, never relayed or sent to a vendor.
        for label, environment in (("beside VIDBYTE_API_KEY", {"OPENAI_API_KEY": VIDBYTE_KEY, "VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}), ("alone", {"OPENAI_API_KEY": VIDBYTE_KEY})):
            with self.subTest(f"live key in the provider env var {label} is refused"), patch.dict(os.environ, environment, clear=True):
                transport = ScriptedGateway()
                with self.assertRaises(ConfigurationError) as caught:
                    TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport)
                self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
                self.assertNotIn(VIDBYTE_KEY, str(caught.exception) + repr(caught.exception.details))
                if "VIDBYTE_API_KEY" in environment:
                    self.assertIn("OPENAI_API_KEY", str(caught.exception))
                self.assertEqual(transport.requests, [])

    def test_without_a_usable_key_each_mode_refuses_before_any_request(self) -> None:
        # EC-2; byok-api-keys INV-7, INV-8, M-8, M-9, M-12: VIDBYTE_API_KEY never serves an unserved provider; DIRECT keeps the vendor missing-key text.
        from vidbyte.lib.config import TextModelMode

        for provider, env_var in ((ModelProvider.OPENROUTER, "OPENROUTER_API_KEY"), (ModelProvider.MISTRAL, "MISTRAL_API_KEY")):
            with self.subTest(provider=provider.value, mode="auto"), patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
                with self.assertRaises(UnsupportedProviderError) as refused:
                    TextModelConfig(provider=provider.value, model="some-model")
                self.assertIn("TextModelMode.DIRECT", str(refused.exception))
            with self.subTest(provider=provider.value, mode="direct"), patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
                transport = ScriptedGateway()
                config = TextModelConfig(provider=provider.value, model="some-model", mode=TextModelMode.DIRECT)
                with self.assertRaises(ConfigurationError) as caught:
                    TextModelRunner(config, transport=transport)
                assert_message(self, str(caught.exception), (f"Missing API key for provider {provider.value}", "api_keys", env_var))
                self.assertNotIn("holds keys for", str(caught.exception))
                self.assertEqual(transport.requests, [])
        with self.subTest(provider="openai", mode="auto"), patch.dict(os.environ, {}, clear=True):
            transport = ScriptedGateway()
            with self.assertRaises(ConfigurationError) as caught:
                TextModelRunner(TextModelConfig(provider="openai", model="some-model"), transport=transport)
            assert_message(self, str(caught.exception), MISSING_VIDBYTE_KEY_FACTS)
            self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
            self.assertEqual(transport.requests, [])

    def test_explicit_managed_mode_uses_the_vidbyte_key_and_never_reads_the_provider_env_var(self) -> None:
        # AC-4, INV-5: explicit mode ignores a BYOK key in the provider env var, and never takes a live key from it either.
        from vidbyte.lib.config import TextModelMode

        transport = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai-byok", "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED), transport=transport).run("Hi")
        self.assertEqual([request["url"] for request in transport.requests], [GATEWAY_URL])
        self.assertEqual(header(transport.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")
        # byok-api-keys INV-5: VIDBYTE_MANAGED never relays a provider key.
        self.assertIsNone(header(transport.requests[0], RELAY_HEADER))
        self.assertNotIn("sk-openai-byok", json.dumps(transport.requests))

        # byok-api-keys D-25: the Vidbyte key arrives as vidbyte_api_key or as a Vidbyte entry in api_keys, never as a provider key.
        for label, options in (("vidbyte_api_key", {"vidbyte_api_key": VIDBYTE_KEY}), ("Vidbyte entry in api_keys", {"api_keys": [VIDBYTE_KEY]})):
            with self.subTest(label):
                explicit = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
                with patch.dict(os.environ, {"VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}, clear=True):
                    TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED, **options), transport=explicit).run("Hi")
                self.assertEqual(header(explicit.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")
                self.assertIsNone(header(explicit.requests[0], RELAY_HEADER))

        with patch.dict(os.environ, {"OPENAI_API_KEY": VIDBYTE_KEY}, clear=True), self.assertRaises(ConfigurationError) as caught:
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED), transport=ScriptedGateway())
        assert_message(self, str(caught.exception), MISSING_VIDBYTE_KEY_FACTS)
        self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)

    def test_managed_credential_failures_raise_tagged_configuration_errors_before_any_request(self) -> None:
        # AC-5, EC-4: missing, malformed (including one character short and a header-injection attempt) and non-string keys fail before any request.
        # byok-api-keys INV-26, M-9, M-10, M-11: an explicit Vidbyte key is checked when the config is built; the environment is read by the runner.
        from vidbyte.lib.config import TextModelMode

        managed = TextModelMode.VIDBYTE_MANAGED
        rows = (
            ("explicit mode, no key anywhere", {}, {"mode": managed}, MISSING_VIDBYTE_KEY_FACTS, "runner"),
            ("explicit mode, test-environment key", {}, {"mode": managed, "vidbyte_api_key": "vb_test_" + "a" * 32}, MALFORMED_VIDBYTE_KEY, "config"),
            ("auto, malformed VIDBYTE_API_KEY is still selected", {"VIDBYTE_API_KEY": "vb_test_" + "a" * 32}, {}, MALFORMED_VIDBYTE_KEY, "runner"),
            ("auto, live prefix one character short", {"VIDBYTE_API_KEY": "vb_live_" + "a" * 31}, {}, MALFORMED_VIDBYTE_KEY, "runner"),
            ("auto, explicit short live key", {}, {"vidbyte_api_key": "vb_live_short"}, MALFORMED_VIDBYTE_KEY, "config"),
            ("auto, explicit live key carrying an injected header", {}, {"vidbyte_api_key": f"{VIDBYTE_KEY}\r\nX-Injected: 1"}, MALFORMED_VIDBYTE_KEY, "config"),
            ("explicit mode, non-string key", {}, {"mode": managed, "vidbyte_api_key": 12345}, NON_STRING_VIDBYTE_KEY_FACTS, "config"),
        )
        for label, environment, options, message, raised_by in rows:
            with self.subTest(label), patch.dict(os.environ, environment, clear=True):
                transport = ScriptedGateway()
                if raised_by == "config":
                    with self.assertRaises(ConfigurationError) as caught:
                        TextModelConfig(provider="openai", model="gpt-5.5", **options)
                else:
                    config = TextModelConfig(provider="openai", model="gpt-5.5", **options)
                    with self.assertRaises(ConfigurationError) as caught:
                        TextModelRunner(config, transport=transport)
                assert_message(self, str(caught.exception), message)
                self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
                self.assertNotIn("X-Injected", str(caught.exception) + repr(caught.exception.details))
                self.assertEqual(transport.requests, [])
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": BOUNDARY_VIDBYTE_KEY}, clear=True):
            transport = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport).run("Hi")
        self.assertEqual(header(transport.requests[0], "authorization"), f"Bearer {BOUNDARY_VIDBYTE_KEY}")

    def test_managed_state_refuses_a_custom_endpoint_while_a_byok_proxy_still_works(self) -> None:
        # AC-6, EC-6, EC-7; byok-api-keys INV-8, D-23, M-13, EC-17: the Vidbyte bearer never follows a caller URL; every gateway mode refuses at construction.
        from vidbyte.lib.config import TextModelMode

        proxy = "https://proxy.example/v1"
        with self.assertRaisesRegex(ConfigurationError, "(?i)endpoint"):
            TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED, endpoint=proxy)
        for label, environment, options in (("VIDBYTE_API_KEY alone", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {}), ("explicit Vidbyte key", {}, {"vidbyte_api_key": VIDBYTE_KEY})):
            with self.subTest(label), patch.dict(os.environ, environment, clear=True):
                # AUTO always means the gateway now, so the config itself refuses the endpoint before any key or variable is read.
                with self.assertRaises(ConfigurationError) as caught:
                    TextModelConfig(provider="openai", model="gpt-5.5", endpoint=proxy, **options)
                self.assertRegex(str(caught.exception), "(?i)endpoint")
                self.assertIn("TextModelMode.DIRECT", str(caught.exception))
                self.assertNotIn(VIDBYTE_KEY, str(caught.exception))
        byok = run_text(ModelProvider.OPENAI, {"OPENAI_API_KEY": "sk-proxy", "VIDBYTE_API_KEY": VIDBYTE_KEY}, endpoint=proxy, direct=True)
        self.assertEqual([request["url"] for request in byok.requests], ["https://proxy.example/v1/responses"])
        self.assertEqual(header(byok.requests[0], "authorization"), "Bearer sk-proxy")
        self.assertNotIn(VIDBYTE_KEY, json.dumps(byok.requests))

    def test_managed_state_refuses_every_provider_the_gateway_does_not_serve(self) -> None:
        # AC-7, EC-3, INV-8; byok-api-keys M-12, D-11, D-23: without this guard an explicit vb_live_ key would be sent to OpenRouter and other vendors.
        from vidbyte.lib.config import TextModelMode

        for provider in UNMANAGED_TEXT_PROVIDERS:
            with self.subTest(provider=provider.value), patch.dict(os.environ, {}, clear=True):
                transport = ScriptedGateway()
                with self.assertRaises(UnsupportedProviderError) as caught:
                    TextModelRunner(TextModelConfig(provider=provider.value, model="some-model", vidbyte_api_key=VIDBYTE_KEY), transport=transport)
                for managed_provider in MANAGED_MODELS:
                    self.assertIn(managed_provider.value, str(caught.exception))
                self.assertIn("TextModelMode.DIRECT", str(caught.exception))
                self.assertEqual(caught.exception.details.get("provider"), provider.value)
                self.assertNotIn(VIDBYTE_KEY, str(caught.exception))
                self.assertEqual(transport.requests, [])
        with self.assertRaises(UnsupportedProviderError):
            TextModelConfig(provider="openrouter", model="openrouter/auto", mode=TextModelMode.VIDBYTE_MANAGED)

    def test_streaming_refuses_managed_state_but_still_streams_byok_beside_a_vidbyte_key(self) -> None:
        # AC-13, EC-16, EC-17; byok-api-keys INV-11, D-10, M-15: every gateway mode refuses to stream, and BYOK streaming now means DIRECT.
        from vidbyte.lib.config import TextModelMode

        refusals = (
            ("VIDBYTE_API_KEY alone", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "openai", "model": "gpt-5.5"}, "auto"),
            # D-10: a provider key beside VIDBYTE_API_KEY no longer streams in the default mode.
            ("provider key beside VIDBYTE_API_KEY in AUTO", {"OPENAI_API_KEY": "sk-stream", "VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "openai", "model": "gpt-5.5"}, "auto"),
            ("explicit managed mode", {}, {"provider": "anthropic", "model": "claude-sonnet-5", "vidbyte_api_key": VIDBYTE_KEY, "mode": TextModelMode.VIDBYTE_MANAGED}, "vidbyte_managed"),
            # Gemini cannot stream at all; the mode refusal still comes first and names DIRECT and TextModelRunner.
            ("non-streaming provider", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "gemini", "model": "gemini-3.5-flash"}, "auto"),
        )
        for label, environment, options, mode in refusals:
            with self.subTest(label), patch.dict(os.environ, environment, clear=True):
                transport = FakeStreamingTransport([])
                with self.assertRaises(UnsupportedProviderError) as caught:
                    StreamingTextModelRunner(TextModelConfig(**options), transport=transport)
                message = str(caught.exception)
                self.assertIn("TextModelMode.DIRECT", message)
                self.assertIn("TextModelRunner", message)
                self.assertEqual(caught.exception.details.get("provider"), options["provider"])
                self.assertEqual(caught.exception.details.get("mode"), mode)
                self.assertEqual(transport.requests, [])
        transport = FakeStreamingTransport([json.dumps({"type": "response.text.delta", "delta": "Hel"}), json.dumps({"type": "response.text.delta", "delta": "lo"})])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-stream", "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            chunks = list(StreamingTextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.DIRECT), transport=transport).stream("Hi"))
        self.assertEqual(chunks, ["Hel", "lo"])
        self.assertEqual(transport.requests[0]["url"], OPENAI_RESPONSES_URL)
        self.assertEqual(header(transport.requests[0], "authorization"), "Bearer sk-stream")
        self.assertNotIn(VIDBYTE_KEY, json.dumps(transport.requests))

    def test_gateway_runners_keep_their_pinned_credentials_after_env_changes(self) -> None:
        # AC-21, INV-14, EC-19; byok-api-keys INV-12, INV-2, EC-22: a gateway runner fixes its Vidbyte key and its relayed provider key at construction.
        managed = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=managed)
            os.environ["OPENAI_API_KEY"] = "sk-set-after-construction"
            runner.run("Hi")
        self.assertEqual([request["url"] for request in managed.requests], [GATEWAY_URL])
        self.assertEqual(header(managed.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")
        self.assertIsNone(header(managed.requests[0], RELAY_HEADER))
        self.assertNotIn("sk-set-after-construction", json.dumps(managed.requests))

        relay = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-removed-later", "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=relay)
            del os.environ["OPENAI_API_KEY"]
            os.environ["VIDBYTE_API_KEY"] = OTHER_VIDBYTE_KEY
            runner.run("Hi")
        self.assertEqual([request["url"] for request in relay.requests], [GATEWAY_URL])
        self.assertEqual(header(relay.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")
        self.assertEqual(header(relay.requests[0], RELAY_HEADER), "sk-removed-later")
        self.assertNotIn(OTHER_VIDBYTE_KEY, json.dumps(relay.requests))

    def test_vidbyte_key_alone_manages_text_but_not_image_video_audio_or_embedding(self) -> None:
        # AC-22, INV-18: the fall-through lives outside resolve_api_key, so other modalities never send a vb_live_ key to a vendor.
        missing = "Missing API key for provider openai. Pass api_key or set OPENAI_API_KEY."
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            # byok-api-keys FR-2: is_vidbyte_managed() is gone; credentials() says whether the call uses the gateway.
            self.assertTrue(TextModelConfig(provider="openai", model="gpt-5.5").credentials().uses_gateway)
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

    def test_text_config_keeps_its_field_order_and_rejects_a_mode_that_is_not_the_enum(self) -> None:
        # INV-20, EC-18, FR-1; byok-api-keys D-24, D-20: api_keys takes api_key's place, vidbyte_api_key is appended, and a YAML string mode is refused.
        from vidbyte.lib.config import TextModelMode
        from vidbyte.lib.enums import TextModelMode as EnumsTextModelMode

        self.assertIs(TextModelMode, EnumsTextModelMode)
        self.assertEqual({member.name: member.value for member in TextModelMode}, {"AUTO": "auto", "VIDBYTE_MANAGED": "vidbyte_managed", "DIRECT": "direct"})
        self.assertEqual([field.name for field in fields(TextModelConfig)], EXPECTED_TEXT_CONFIG_FIELDS)
        self.assertIs(TextModelConfig(provider="openai", model="gpt-5.5").mode, TextModelMode.AUTO)
        self.assertEqual(TextModelConfig("openai", "gpt-5.5", ["sk-positional"]).api_keys.key_for("openai"), "sk-positional")
        # D-20: an old positional key string fails loudly (M-1) instead of being split into one-character keys.
        with self.assertRaises(ConfigurationError) as positional:
            TextModelConfig("openai", "gpt-5.5", "sk-positional")
        self.assertNotIn("sk-positional", str(positional.exception))
        with self.assertRaises(ConfigurationError) as caught:
            TextModelConfig(provider="openai", model="gpt-5.5", mode="vidbyte_managed")  # type: ignore[arg-type]
        self.assertEqual(str(caught.exception), "mode must be a TextModelMode value.")


class KeyHygieneTests(unittest.TestCase):
    """Checks that the Vidbyte key stays out of reprs and adapter-built headers, and that Decision shares the resolver."""

    def test_text_config_repr_hides_the_api_key(self) -> None:
        # AC-15, FR-10; byok-api-keys INV-4: a repr in a log or traceback must not carry any key, Vidbyte or provider, from api_keys or vidbyte_api_key.
        cases = (
            (VIDBYTE_KEY, {"api_keys": [VIDBYTE_KEY]}),
            (VIDBYTE_KEY, {"vidbyte_api_key": VIDBYTE_KEY}),
            ("sk-live-secret-123", {"api_keys": ["sk-live-secret-123"]}),
        )
        for key, options in cases:
            with self.subTest(key=key[:8], field=next(iter(options))):
                rendered = repr(TextModelConfig(provider="openai", model="gpt-5.5", **options))
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
            ("explicit Vidbyte key", {}, {"provider": "anthropic", "model": "claude-sonnet-5", "vidbyte_api_key": VIDBYTE_KEY}, "https://api.anthropic.com/v1/messages", "x-api-key", VIDBYTE_MANAGED_KEY_PLACEHOLDER),
            ("explicit managed mode", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "gemini", "model": "gemini-3.5-flash", "mode": TextModelMode.VIDBYTE_MANAGED}, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent", "x-goog-api-key", VIDBYTE_MANAGED_KEY_PLACEHOLDER),
            # byok-api-keys EC-37: a provider key meant for the relay never reaches an adapter called directly in AUTO.
            ("relay key in AUTO", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"provider": "anthropic", "model": "claude-sonnet-5", "api_keys": [ANTHROPIC_RELAY_KEY]}, "https://api.anthropic.com/v1/messages", "x-api-key", VIDBYTE_MANAGED_KEY_PLACEHOLDER),
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
                self.assertNotIn(ANTHROPIC_RELAY_KEY, json.dumps(plain.requests))

    def test_decision_and_text_share_one_managed_key_resolver_with_unchanged_messages(self) -> None:
        # AC-14, INV-19, FR-3, D-14: two inline copies of the live-key rule drift; Decision must give exactly what the shared resolver gives.
        # byok-api-keys D-14, INV-18: Decision keeps its exact message; text shares the resolver but names its own ways out (M-9).
        rows = (
            ({}, None, ("error", DECISION_MISSING_VIDBYTE_KEY, CREDENTIAL_ERROR_KIND)),
            ({"VIDBYTE_API_KEY": "   "}, "", ("error", DECISION_MISSING_VIDBYTE_KEY, CREDENTIAL_ERROR_KIND)),
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
        from vidbyte.lib.config import TextModelMode

        for environment, expected in (({}, MISSING_VIDBYTE_KEY_FACTS), ({"VIDBYTE_API_KEY": VIDBYTE_KEY}, VIDBYTE_KEY), ({"VIDBYTE_API_KEY": "vb_test_" + "a" * 32}, MALFORMED_VIDBYTE_KEY)):
            with self.subTest(text_env=sorted(environment)), patch.dict(os.environ, environment, clear=True):
                config = TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED)
                if expected == VIDBYTE_KEY:
                    self.assertEqual(config.credentials().vidbyte_api_key, VIDBYTE_KEY)
                    continue
                with self.assertRaises(ConfigurationError) as text_caught:
                    config.credentials()
                assert_message(self, str(text_caught.exception), expected)
                self.assertEqual(text_caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)

    @staticmethod
    def _resolution(resolve: object) -> tuple[str, ...]:
        # Reduces one resolution to a comparable value: the key, or the message and error_kind it raised.
        try:
            return ("key", resolve())  # type: ignore[operator]
        except ConfigurationError as error:
            return ("error", str(error), str(error.details.get("error_kind")))


if __name__ == "__main__":
    unittest.main()
