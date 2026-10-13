"""FILE: tests/features/sdk_provider_keys/test_provider_keys_modes.py

PURPOSE: Proves how TextModelConfig.credentials() resolves the three modes (table R) and what each runner does with the result: DIRECT reads only the provider key, VIDBYTE_MANAGED reads only the Vidbyte key, AUTO needs a Vidbyte key and relays when the provider has a key; a gateway runner pins its credentials; streaming refuses every gateway mode; and an unsendable provider key is refused before any request.
ROLE IN CODEBASE: Mode layer of tests/features/sdk_provider_keys/ (spec AC-6, AC-40; INV-5 to INV-8, INV-11, INV-12, INV-26; D-7, D-8, D-10, D-14, D-32; EC-12, EC-21 to EC-23, EC-56; table M rows M-8, M-9, M-12, M-13, M-15, M-21). Exercises vidbyte/lib/dataclasses/model_configs.py (TextModelConfig, TextCredentials), vidbyte/lib/registries/models.py (find_provider_api_key, resolve_vidbyte_api_key), vidbyte/lib/runners/text.py and vidbyte/lib/runners/streaming_text.py.
ARCHITECTURE NOTE: credentials() is the only code that reads the environment for a text call, so RecordingEnviron (a recording stand-in for os.environ) proves which variables each mode reads. Runner behavior is observed at the inner transport, which is the only fake.
COMMON MODIFICATION PATTERNS: When a mode is added, add its row to the table R test and its refusals to the streaming test. Keep message checks to the facts table M binds.
WHAT NOT TO DO IN THIS FILE: 1. Do not import TextModelMode.DIRECT, TextCredentials or the new constants at module level. 2. Do not mock credentials() or ProviderModelRegistry; patch only the environment and the inner transport.
KNOWN EDGE CASES: TextCredentials raises ConfigurationError for an impossible combination, the repo's convention for a record's own validation (spec section 9.1 names the rules, not the error type). A NaN timeout must still become the 630 s floor on a relay call.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 6.1, 9.1 (TextCredentials) and 9.2 (table R, table M).
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_modes.py
"""

from __future__ import annotations

import json
import os
import unittest
from collections.abc import Iterator, Mapping
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    GATEWAY_URL,
    OTHER_VIDBYTE_KEY,
    VIDBYTE_KEY,
    ScriptedGateway,
    header,
    provider_answer,
)
from tests.features.sdk_provider_keys.provider_keys_fixtures import (
    K_ANTHROPIC,
    K_OPENAI,
    K_UNPROVEN,
    K_XAI,
    RecordingEnviron,
    flat,
    provider_key_header,
)
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.runners import StreamingTextModelRunner, TextModelRunner

CREDENTIAL_ERROR_KIND = "vidbyte_managed_credentials"
PLACEHOLDER = "vidbyte-managed"
SERVED = ("openai", "anthropic", "gemini", "xai", "deepseek", "kimi")


class FakeStreamingTransport:
    """Records each stream request and yields scripted SSE lines, as tests/test_streaming_text_runner.py does."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = list(lines)
        self.requests: list[dict[str, Any]] = []

    def stream_request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 120.0) -> Iterator[str]:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {})})
        yield from self.lines


class TextCredentialsRecordTests(unittest.TestCase):
    """FR-3, section 9.1: the record credentials() returns, and the combinations it refuses."""

    def test_the_record_says_whether_a_call_uses_the_gateway_and_whether_it_relays(self) -> None:
        # FR-3: uses_gateway is "mode is not DIRECT"; relays is "uses the gateway and holds a provider key".
        from vidbyte.lib.config import TextModelMode
        from vidbyte.lib.dataclasses.model_configs import TextCredentials

        cases = (
            (TextCredentials(mode=TextModelMode.DIRECT, provider_api_key=K_OPENAI), False, False),
            (TextCredentials(mode=TextModelMode.AUTO, provider_api_key=K_OPENAI, vidbyte_api_key=VIDBYTE_KEY), True, True),
            (TextCredentials(mode=TextModelMode.AUTO, vidbyte_api_key=VIDBYTE_KEY), True, False),
            (TextCredentials(mode=TextModelMode.VIDBYTE_MANAGED, vidbyte_api_key=VIDBYTE_KEY), True, False),
        )
        for credentials, uses_gateway, relays in cases:
            with self.subTest(mode=credentials.mode.value, relays=relays):
                self.assertIs(credentials.uses_gateway, uses_gateway)
                self.assertIs(credentials.relays, relays)
                self.assertNotIn(K_OPENAI, repr(credentials))
                self.assertNotIn(VIDBYTE_KEY, repr(credentials))

    def test_an_impossible_combination_is_refused(self) -> None:
        # Section 9.1: DIRECT has a provider key and no Vidbyte key; VIDBYTE_MANAGED the reverse; AUTO always a Vidbyte key.
        from vidbyte.lib.config import TextModelMode
        from vidbyte.lib.dataclasses.model_configs import TextCredentials

        impossible = (
            {"mode": TextModelMode.DIRECT},
            {"mode": TextModelMode.DIRECT, "provider_api_key": "  "},
            {"mode": TextModelMode.DIRECT, "provider_api_key": K_OPENAI, "vidbyte_api_key": VIDBYTE_KEY},
            {"mode": TextModelMode.VIDBYTE_MANAGED},
            {"mode": TextModelMode.VIDBYTE_MANAGED, "provider_api_key": K_OPENAI, "vidbyte_api_key": VIDBYTE_KEY},
            {"mode": TextModelMode.AUTO, "provider_api_key": K_OPENAI},
        )
        for values in impossible:
            with self.subTest(values=sorted(values)), self.assertRaises(ConfigurationError) as caught:
                TextCredentials(**values)
            self.assertNotIn(K_OPENAI, str(caught.exception))


class ProviderKeysFactory:
    """Builds the records the M-8 test needs through the real matcher (no hand-built shortcuts)."""

    @staticmethod
    def held() -> Any:
        # A record holding keys for xai and anthropic but none for openai, as a child of an xai agent would carry.
        from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

        return ProviderKeyMatcher.match([K_XAI, K_ANTHROPIC], primary="xai", others=("anthropic",))


class CredentialResolutionTests(unittest.TestCase):
    """Table R, D-7, D-8: credentials() per mode, and what it reads."""

    def test_credentials_follow_table_r_and_read_only_what_each_mode_needs(self) -> None:
        # INV-5, INV-6, D-7: the matched key beats the variable; DIRECT never reads VIDBYTE_API_KEY; VIDBYTE_MANAGED never reads the provider's variable.
        from vidbyte.lib.config import TextModelMode

        environment_values = {"OPENAI_API_KEY": K_UNPROVEN, "VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}
        rows = (
            ("DIRECT, list key", TextModelMode.DIRECT, [K_OPENAI], None, (K_OPENAI, None), {"VIDBYTE_API_KEY"}),
            ("DIRECT, variable", TextModelMode.DIRECT, [], None, (K_UNPROVEN, None), {"VIDBYTE_API_KEY"}),
            ("DIRECT, explicit Vidbyte key ignored", TextModelMode.DIRECT, [K_OPENAI], VIDBYTE_KEY, (K_OPENAI, None), {"VIDBYTE_API_KEY"}),
            ("AUTO, list keys", TextModelMode.AUTO, [VIDBYTE_KEY, K_OPENAI], None, (K_OPENAI, VIDBYTE_KEY), set()),
            ("AUTO, variables", TextModelMode.AUTO, [], None, (K_UNPROVEN, OTHER_VIDBYTE_KEY), set()),
            ("VIDBYTE_MANAGED", TextModelMode.VIDBYTE_MANAGED, [K_OPENAI], VIDBYTE_KEY, (None, VIDBYTE_KEY), {"OPENAI_API_KEY"}),
        )
        for name, mode, api_keys, vidbyte_api_key, expected, never_read in rows:
            with self.subTest(row=name):
                environment = RecordingEnviron(environment_values)
                with patch.object(os, "environ", environment):
                    config = TextModelConfig(provider="openai", model="gpt-5.5", api_keys=api_keys, vidbyte_api_key=vidbyte_api_key, mode=mode)
                    credentials = config.credentials()
                self.assertIs(credentials.mode, mode)
                self.assertEqual((credentials.provider_api_key, credentials.vidbyte_api_key), expected)
                self.assertEqual(never_read & set(environment.reads), set())

    def test_resolved_api_key_is_the_provider_key_only_in_direct(self) -> None:
        # FR-2, INV-4: a gateway-mode adapter builds its headers from the non-secret placeholder.
        from vidbyte.lib.config import TextModelMode

        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            self.assertEqual(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI], mode=TextModelMode.DIRECT).resolved_api_key(), K_OPENAI)
            for mode in (TextModelMode.AUTO, TextModelMode.VIDBYTE_MANAGED):
                with self.subTest(mode=mode.value):
                    self.assertEqual(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI], mode=mode).resolved_api_key(), PLACEHOLDER)

    def test_direct_without_a_provider_key_names_the_variable_and_the_providers_the_list_holds(self) -> None:
        # EC-12, M-8: the variable to set, and which providers the list did hold.
        from vidbyte.lib.config import TextModelMode

        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            config = TextModelConfig(provider="openai", model="gpt-5.5", api_keys=ProviderKeysFactory.held(), mode=TextModelMode.DIRECT)
            with self.assertRaises(ConfigurationError) as caught:
                config.validate()
            bare = TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.DIRECT)
            with self.assertRaises(ConfigurationError) as bare_caught:
                TextModelRunner(bare, transport=ScriptedGateway(provider_answer(ModelProvider.OPENAI)))
        message = str(caught.exception)
        for fact in ("Missing API key for provider openai", "api_keys", "OPENAI_API_KEY", "xai", "anthropic"):
            self.assertIn(fact, message)
        for secret in (K_XAI, K_ANTHROPIC, VIDBYTE_KEY):
            self.assertNotIn(secret, message)
        self.assertIn("OPENAI_API_KEY", str(bare_caught.exception))
        self.assertNotIn("holds keys for", str(bare_caught.exception))

    def test_gateway_modes_without_a_vidbyte_key_raise_the_tagged_error_from_validate_credentials_and_the_runner(self) -> None:
        # INV-7, M-9: before any request, from all three entry points, naming both ways out.
        from vidbyte.lib.config import TextModelMode

        for mode in (TextModelMode.AUTO, TextModelMode.VIDBYTE_MANAGED):
            transport = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
            with patch.dict(os.environ, {"OPENAI_API_KEY": K_OPENAI}, clear=True):
                config = TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI], mode=mode)
                for entry, call in (("validate", config.validate), ("credentials", config.credentials), ("runner", lambda: TextModelRunner(config, transport=transport))):
                    with self.subTest(mode=mode.value, entry=entry), self.assertRaises(ConfigurationError) as caught:
                        call()
                    message = str(caught.exception)
                    self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
                    for fact in ("vidbyte_api_key", "VIDBYTE_API_KEY", "TextModelMode.DIRECT"):
                        self.assertIn(fact, message)
                    self.assertNotIn(K_OPENAI, message)
            self.assertEqual(transport.requests, [])

    def test_decision_keeps_its_own_missing_key_message_while_text_names_the_new_ways_out(self) -> None:
        # INV-18, D-14: resolve_vidbyte_api_key keeps Decision's message by default and takes text's remedy.
        from vidbyte.lib.registries.models import ProviderModelRegistry

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError) as default:
                ProviderModelRegistry.resolve_vidbyte_api_key(None)
            with self.assertRaises(ConfigurationError) as remedied:
                ProviderModelRegistry.resolve_vidbyte_api_key(None, remedy="Use the remedy.")
        self.assertEqual(str(default.exception), "Missing Vidbyte API key. Pass api_key or set VIDBYTE_API_KEY.")
        self.assertEqual(str(remedied.exception), "Missing Vidbyte API key. Use the remedy.")

    def test_find_provider_api_key_reads_the_record_then_the_variable_and_refuses_a_vidbyte_value(self) -> None:
        # FR-5, D-6, D-7, M-14: the record's key wins; a stripped variable is the fallback; a Vidbyte value in a provider variable raises.
        from vidbyte.lib.registries.models import ProviderModelRegistry
        from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

        record = ProviderKeyMatcher.match([K_OPENAI], primary="openai")
        empty = ProviderKeyMatcher.match([], primary="openai")
        with patch.dict(os.environ, {"OPENAI_API_KEY": f"  {K_UNPROVEN}\n", "XAI_API_KEY": OTHER_VIDBYTE_KEY}, clear=True):
            self.assertEqual(ProviderModelRegistry.find_provider_api_key("openai", record), K_OPENAI)
            self.assertEqual(ProviderModelRegistry.find_provider_api_key(ModelProvider.OPENAI, empty), K_UNPROVEN)
            self.assertIsNone(ProviderModelRegistry.find_provider_api_key("deepseek", empty))
            with self.assertRaises(ConfigurationError) as caught:
                ProviderModelRegistry.find_provider_api_key("xai", empty)
        self.assertIn("XAI_API_KEY", str(caught.exception))
        self.assertNotIn(OTHER_VIDBYTE_KEY, str(caught.exception) + repr(caught.exception.details))


class GatewayShapeTests(unittest.TestCase):
    """INV-8, D-11, D-23, M-12, M-13: a gateway-mode config is refused at construction before anything is read."""

    def test_every_unserved_provider_and_any_endpoint_is_refused_at_construction_in_both_gateway_modes(self) -> None:
        # INV-8: the refusal reads no key and no environment, and both messages name TextModelMode.DIRECT.
        from vidbyte.lib.config import TextModelMode

        for mode in (TextModelMode.AUTO, TextModelMode.VIDBYTE_MANAGED):
            for provider, model in (("openrouter", "openai/gpt-5.5"), ("glm", "glm-4.6"), ("minimax", "MiniMax-M2"), ("meta", "llama-4"), ("mistral", "mistral-large-latest")):
                environment = RecordingEnviron({"VIDBYTE_API_KEY": VIDBYTE_KEY})
                with self.subTest(mode=mode.value, provider=provider), patch.object(os, "environ", environment), self.assertRaises(UnsupportedProviderError) as caught:
                    TextModelConfig(provider=provider, model=model, mode=mode)
                message = str(caught.exception)
                self.assertIn("TextModelMode.DIRECT", message)
                for served in SERVED:
                    self.assertIn(served, message)
                self.assertEqual([name for name in environment.reads if name.endswith("_API_KEY")], [])
            environment = RecordingEnviron({"VIDBYTE_API_KEY": VIDBYTE_KEY})
            with self.subTest(mode=mode.value, endpoint=True), patch.object(os, "environ", environment), self.assertRaises(ConfigurationError) as refused:
                TextModelConfig(provider="openai", model="gpt-5.5", endpoint="https://proxy.example/v1", mode=mode)
            self.assertIn("endpoint", str(refused.exception))
            self.assertIn("TextModelMode.DIRECT", str(refused.exception))
            self.assertEqual([name for name in environment.reads if name.endswith("_API_KEY")], [])


class StreamingModeTests(unittest.TestCase):
    """AC-6, INV-11, D-10, EC-23, M-15: streaming happens only in DIRECT."""

    def test_streaming_refuses_every_gateway_mode_before_reading_any_key(self) -> None:
        # AC-6: with no keys at all and with every key set, the refusal is the same and names DIRECT and TextModelRunner.
        from vidbyte.lib.config import TextModelMode

        environments = ({}, {"OPENAI_API_KEY": K_OPENAI, "VIDBYTE_API_KEY": VIDBYTE_KEY})
        for mode in (TextModelMode.AUTO, TextModelMode.VIDBYTE_MANAGED):
            for values in environments:
                environment = RecordingEnviron(values)
                transport = FakeStreamingTransport([])
                with self.subTest(mode=mode.value, keys=bool(values)), patch.object(os, "environ", environment), self.assertRaises(UnsupportedProviderError) as caught:
                    StreamingTextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=mode), transport=transport)
                message = str(caught.exception)
                self.assertIn("TextModelMode.DIRECT", message)
                self.assertIn("TextModelRunner", message)
                self.assertEqual(caught.exception.details.get("mode"), mode.value)
                self.assertEqual([name for name in environment.reads if name.endswith("_API_KEY")], [])
                self.assertEqual(transport.requests, [])

    def test_direct_streams_straight_from_the_provider_with_the_provider_key(self) -> None:
        # AC-6 (last sentence): DIRECT streams as base_commit's BYOK streaming did.
        from vidbyte.lib.config import TextModelMode

        transport = FakeStreamingTransport([json.dumps({"type": "response.text.delta", "delta": "Hel"}), json.dumps({"type": "response.text.delta", "delta": "lo"})])
        with patch.dict(os.environ, {"OPENAI_API_KEY": K_OPENAI}, clear=True):
            runner = StreamingTextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.DIRECT), transport=transport)
            list(runner.stream("Hi"))
        [sent] = transport.requests
        self.assertTrue(sent["url"].startswith("https://api.openai.com/"))
        self.assertEqual(header(sent, "authorization"), f"Bearer {K_OPENAI}")


class PinnedRunnerTests(unittest.TestCase):
    """INV-12, EC-22: a gateway runner resolves its credentials once, at construction."""

    def test_a_relay_runner_keeps_its_keys_after_the_environment_changes(self) -> None:
        # INV-12: removing or replacing the variables after construction changes nothing the runner sends.
        gateway = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"OPENAI_API_KEY": K_OPENAI, "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=gateway)
        for environment in ({}, {"OPENAI_API_KEY": K_UNPROVEN, "VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY}):
            with self.subTest(environment=sorted(environment)), patch.dict(os.environ, environment, clear=True):
                runner.run("Hi")
        self.assertEqual(len(gateway.requests), 2)
        for request in gateway.requests:
            self.assertEqual(request["url"], GATEWAY_URL)
            self.assertEqual(header(request, "authorization"), f"Bearer {VIDBYTE_KEY}")
            self.assertEqual(provider_key_header(request), K_OPENAI)
            self.assertNotIn(K_UNPROVEN, flat(request))
            self.assertNotIn(OTHER_VIDBYTE_KEY, flat(request))

    def test_direct_with_an_explicit_vidbyte_key_never_sends_it(self) -> None:
        # EC-21: the explicit Vidbyte key is checked for format at construction, then never read for a call and never sent.
        from vidbyte.lib.config import TextModelMode

        vendor = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        environment = RecordingEnviron({"VIDBYTE_API_KEY": OTHER_VIDBYTE_KEY})
        with patch.object(os, "environ", environment):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI], vidbyte_api_key=VIDBYTE_KEY, mode=TextModelMode.DIRECT), transport=vendor).run("Hi")
        [sent] = vendor.requests
        self.assertEqual(sent["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(header(sent, "authorization"), f"Bearer {K_OPENAI}")
        self.assertNotIn(VIDBYTE_KEY, flat(sent))
        self.assertNotIn(OTHER_VIDBYTE_KEY, flat(sent))
        self.assertNotIn("VIDBYTE_API_KEY", environment.reads)


class UnsendableKeyTests(unittest.TestCase):
    """AC-40, D-32, EC-56, M-21: a provider key that cannot be sent is refused when the runner is built."""

    def test_an_environment_key_with_an_inner_space_is_refused_in_auto_and_direct(self) -> None:
        # AC-40 (first case): names the variable and the character count, never the key.
        from vidbyte.lib.config import TextModelMode

        broken = "dk-left right-" + "z" * 10
        for mode in (TextModelMode.AUTO, TextModelMode.DIRECT):
            transport = ScriptedGateway(provider_answer(ModelProvider.DEEPSEEK))
            with self.subTest(mode=mode.value), patch.dict(os.environ, {"DEEPSEEK_API_KEY": broken, "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
                with self.assertRaises(ConfigurationError) as caught:
                    TextModelRunner(TextModelConfig(provider="deepseek", model="deepseek-v4-pro", mode=mode), transport=transport)
            message = str(caught.exception)
            self.assertIn("DEEPSEEK_API_KEY", message)
            self.assertIn(str(len(broken)), message)
            self.assertNotIn(broken, message + repr(caught.exception.details))
            self.assertNotIn("right", message)
            self.assertEqual(transport.requests, [])

    def test_a_relayed_key_longer_than_512_characters_needs_direct(self) -> None:
        # AC-40 (second case): the gateway relays at most 512 characters; DIRECT sends the key to the vendor unchanged.
        from vidbyte.lib.config import TextModelMode

        long_key = "d" * 513
        transport = ScriptedGateway(provider_answer(ModelProvider.DEEPSEEK))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            with self.assertRaises(ConfigurationError) as caught:
                TextModelRunner(TextModelConfig(provider="deepseek", model="deepseek-v4-pro", api_keys=[long_key]), transport=transport)
        message = str(caught.exception)
        for fact in ("513", "512", "TextModelMode.DIRECT", "deepseek"):
            self.assertIn(fact, message)
        self.assertNotIn(long_key[:64], message + repr(caught.exception.details))
        self.assertEqual(transport.requests, [])

        vendor = ScriptedGateway(provider_answer(ModelProvider.DEEPSEEK))
        with patch.dict(os.environ, {}, clear=True):
            TextModelRunner(TextModelConfig(provider="deepseek", model="deepseek-v4-pro", api_keys=[long_key], mode=TextModelMode.DIRECT), transport=vendor).run("Hi")
        [sent] = vendor.requests
        self.assertEqual(sent["url"], "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(header(sent, "authorization"), f"Bearer {long_key}")

    def test_a_key_of_exactly_512_characters_still_relays(self) -> None:
        # D-32: the limit is inclusive, so a 512-character key is sent in the header unchanged.
        key = "d" * 512
        gateway = ScriptedGateway(provider_answer(ModelProvider.DEEPSEEK))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            TextModelRunner(TextModelConfig(provider="deepseek", model="deepseek-v4-pro", api_keys=[key]), transport=gateway).run("Hi")
        self.assertEqual(provider_key_header(gateway.requests[0]), key)


if __name__ == "__main__":
    unittest.main()
