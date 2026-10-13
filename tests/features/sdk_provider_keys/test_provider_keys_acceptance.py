"""FILE: tests/features/sdk_provider_keys/test_provider_keys_acceptance.py

PURPOSE: Proves the developer-visible promises of the two-key setup end to end: the spec section 4 snippet run as written relays the grok call with the xAI key, a default-mode call relays exactly when the provider has a key, AUTO refuses to run without a Vidbyte key, DIRECT stays byte-identical to base_commit's BYOK request, a Vidbyte entry in api_keys is only ever the bearer, unserved providers and custom endpoints need DIRECT, VIDBYTE_MANAGED ignores provider keys, and the README documents all of it.
ROLE IN CODEBASE: Acceptance layer of tests/features/sdk_provider_keys/ (spec AC-1 to AC-5, AC-11 to AC-13, AC-27, AC-36). Exercises vidbyte/agents/base.py, vidbyte/lib/dataclasses/model_configs.py, vidbyte/lib/registries/provider_keys.py, vidbyte/lib/runners/text.py and vidbyte/lib/http/vidbyte_gateway.py with only the inner transport faked.
ARCHITECTURE NOTE: Expected requests are literals: base_commit's BYOK goldens were recorded from the unchanged adapters, and the relay header name comes from the wire contract, never from production constants. Every test clears the environment, so a developer's real keys never change an outcome.
COMMON MODIFICATION PATTERNS: When the README section is reworded, keep every fact the README test checks. When a provider's adapter changes its BYOK request, re-record its golden from base_commit's adapter, not from the new code.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols (TextModelMode.DIRECT, ProviderKeys, the header constant) at module level; import them inside each test. 2. Do not read the developer's environment; every test uses patch.dict(os.environ, ..., clear=True) or RecordingEnviron.
KNOWN EDGE CASES: The section 4 snippet reads os.environ itself, so it runs inside the patched environment. Building the offline agent must read no VIDBYTE_API_KEY, which RecordingEnviron proves by recording every read.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 4, 6.2 and 9.2.
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_acceptance.py
"""

from __future__ import annotations

import io
import os
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    GATEWAY_URL,
    OTHER_VIDBYTE_KEY,
    RUNNER_TRANSPORT_TARGET,
    VIDBYTE_KEY,
    ScriptedGateway,
    header,
    idempotency_key,
    provider_answer,
)
from tests.features.sdk_provider_keys.provider_keys_fixtures import (
    K_ANTHROPIC,
    K_OPENAI,
    K_XAI,
    RecordingEnviron,
    chat_done,
    flat,
    provider_key_header,
)
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.runners import TextModelRunner

PROMPT = "Hi"
KEY_PATTERN = re.compile(r"[0-9a-f]{32}")
README = Path(__file__).resolve().parents[3] / "README.md"
# The same section the managed-text pack's README test reads: a level-2 to level-4 heading naming Vidbyte-managed mode.
README_SECTION_HEADING = re.compile(r"^(#{2,4}) [^\n]*\bvidbyte[- ]managed\b[^\n]*$", re.IGNORECASE | re.MULTILINE)
CREDENTIAL_ERROR_KIND = "vidbyte_managed_credentials"
# A Mistral key has no prefix that proves its provider (table F has no Mistral rule), and no reserved prefix.
MISTRAL_KEY = "mistral-" + "m" * 24


def openai_golden(key: str, url: str = "https://api.openai.com/v1/responses") -> dict[str, object]:
    # base_commit's BYOK request for TextModelConfig(provider="openai", model="gpt-5.5", api_key=key).run("Hi"), recorded from the unchanged adapter.
    return {"method": "POST", "url": url, "headers": {"authorization": f"Bearer {key}", "content-type": "application/json"}, "json_body": {"model": "gpt-5.5", "input": PROMPT}, "timeout_seconds": 60.0}


class SnippetAcceptanceTests(unittest.TestCase):
    """AC-1: the section 4 snippet, run as written against a scripted gateway."""

    def test_section_4_snippet_relays_grok_with_only_the_xai_key_and_builds_the_offline_agent_without_reading_the_vidbyte_key(self) -> None:
        # AC-1, G-1, INV-2, INV-3, INV-6, INV-23: one relay POST for grok; the Anthropic key stays out of it; the DIRECT agent reads no Vidbyte key.
        gateway = ScriptedGateway(chat_done("Hi"))
        environment = RecordingEnviron({"VIDBYTE_API_KEY": VIDBYTE_KEY, "ANTHROPIC_API_KEY": K_ANTHROPIC, "XAI_API_KEY": K_XAI})
        printed = io.StringIO()
        with patch.object(os, "environ", environment), patch(RUNNER_TRANSPORT_TARGET, new=gateway), redirect_stdout(printed):
            # The snippet's own imports, inside the test so the module collects before the feature exists.
            from vidbyte import Agent
            from vidbyte.lib.config import TextModelMode

            agent = Agent(
                name="researcher",
                system_prompt="Answer in one word.",
                provider="xai",
                model_name="grok-4.5",
                vidbyte_api_key=os.environ["VIDBYTE_API_KEY"],
                api_keys=[os.environ["ANTHROPIC_API_KEY"], os.environ["XAI_API_KEY"]],
                fallback=["anthropic/claude-sonnet-5"],
            )
            reply = agent.run("Say hi.")
            print(reply.content)

            sent_before_offline = len(gateway.requests)
            reads_before_offline = len(environment.reads)
            offline = Agent(
                name="offline",
                system_prompt="Answer in one word.",
                provider="xai",
                model_name="grok-4.5",
                api_keys=[os.environ["XAI_API_KEY"]],
                model_mode=TextModelMode.DIRECT,
            )
            offline_reads = environment.reads[reads_before_offline:]

        self.assertEqual(printed.getvalue().splitlines(), ["Hi"])
        self.assertEqual(sent_before_offline, 1, "exactly one POST: the grok call, which succeeded")
        [sent] = gateway.requests
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["url"], GATEWAY_URL)
        self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
        self.assertEqual(provider_key_header(sent), K_XAI)
        self.assertEqual((sent["json_body"]["provider"], sent["json_body"]["model"]), ("xai", "grok-4.5"))
        self.assertNotIn(K_ANTHROPIC, flat(sent))
        # Building the offline agent sends nothing, and the only variable it reads is the one the snippet itself reads.
        self.assertEqual(len(gateway.requests), 1)
        self.assertNotIn("VIDBYTE_API_KEY", offline_reads)
        self.assertIs(offline.runner_config.model_mode, TextModelMode.DIRECT)
        self.assertIsNone(offline.runner_config.api_keys.vidbyte_api_key)


class TextCallAcceptanceTests(unittest.TestCase):
    """AC-2 to AC-5, AC-11 to AC-13, AC-36: what one text call sends in each mode."""

    def test_auto_relays_exactly_when_the_provider_has_a_key_and_otherwise_sends_base_commits_three_headers(self) -> None:
        # AC-2, AC-3, INV-1, INV-2, INV-16, NFR-9: the relay adds only the header; the envelope body is the DIRECT body plus the 32,768 cap.
        from vidbyte.lib.config import TextModelMode

        vendor = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"OPENAI_API_KEY": K_OPENAI}, clear=True):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.DIRECT), transport=vendor).run(PROMPT)
        direct_body = vendor.requests[0]["json_body"]
        expected_envelope = {"provider": "openai", "model": "gpt-5.5", "body": {**direct_body, "max_output_tokens": 32768}}

        cases = (
            ("relay", {"OPENAI_API_KEY": K_OPENAI, "VIDBYTE_API_KEY": VIDBYTE_KEY}, {"authorization", "content-type", "idempotency-key", "x-vidbyte-provider-key"}),
            ("vidbyte-paid", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"authorization", "content-type", "idempotency-key"}),
        )
        for name, environment, header_names in cases:
            with self.subTest(case=name):
                gateway = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
                with patch.dict(os.environ, environment, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
                    response = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5")).run(PROMPT)
                self.assertEqual(response.text, "Hi")
                self.assertEqual(len(gateway.requests), 1)
                [sent] = gateway.requests
                self.assertEqual((sent["method"], sent["url"]), ("POST", GATEWAY_URL))
                self.assertEqual({name.lower() for name in sent["headers"]}, header_names)
                self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
                self.assertRegex(idempotency_key(sent) or "", KEY_PATTERN)
                self.assertEqual(sent["json_body"], expected_envelope)
                self.assertEqual(provider_key_header(sent), K_OPENAI if name == "relay" else None)
                if name == "vidbyte-paid":
                    self.assertNotIn(K_OPENAI, flat(sent))

    def test_auto_without_a_vidbyte_key_refuses_the_runner_before_any_request_and_names_both_ways_out(self) -> None:
        # AC-4, INV-7: a provider key alone is no longer enough in the default mode.
        transport = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"OPENAI_API_KEY": K_OPENAI}, clear=True):
            with self.assertRaises(ConfigurationError) as caught:
                TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport)
        message = str(caught.exception)
        self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
        for fact in ("VIDBYTE_API_KEY", "vidbyte_api_key", "TextModelMode.DIRECT"):
            self.assertIn(fact, message)
        self.assertNotIn(K_OPENAI, message + repr(caught.exception.details))
        self.assertEqual(transport.requests, [])

    def test_direct_sends_base_commits_byok_request_and_ignores_a_malformed_vidbyte_key_in_the_environment(self) -> None:
        # AC-5, INV-6: DIRECT never reads VIDBYTE_API_KEY, so a broken value there cannot stop the call.
        from vidbyte.lib.config import TextModelMode

        transport = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        environment = RecordingEnviron({"VIDBYTE_API_KEY": "not-a-vidbyte-key"})
        with patch.object(os, "environ", environment):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI], mode=TextModelMode.DIRECT), transport=transport)
            response = runner.run(PROMPT)
        self.assertEqual(response.text, "Hi")
        self.assertEqual(transport.requests, [openai_golden(K_OPENAI)])
        self.assertNotIn("VIDBYTE_API_KEY", environment.reads)

    def test_a_vidbyte_entry_in_api_keys_is_only_the_bearer_and_a_second_vidbyte_key_is_refused(self) -> None:
        # AC-11, D-25, INV-13, M-5: the Vidbyte entry rides only in Authorization; a different explicit Vidbyte key is a conflict.
        gateway = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[VIDBYTE_KEY, K_OPENAI])).run(PROMPT)
        [sent] = gateway.requests
        self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
        self.assertEqual(provider_key_header(sent), K_OPENAI)
        self.assertNotIn(VIDBYTE_KEY, flat({name: value for name, value in sent["headers"].items() if name.lower() != "authorization"}))
        self.assertNotIn(VIDBYTE_KEY, flat(sent["json_body"]))

        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            with self.assertRaises(ConfigurationError) as caught:
                TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[VIDBYTE_KEY, K_OPENAI], vidbyte_api_key=OTHER_VIDBYTE_KEY)
        message = str(caught.exception)
        self.assertIn("api_keys[0]", message)
        self.assertIn("vidbyte_api_key", message)
        self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
        for secret in (VIDBYTE_KEY, OTHER_VIDBYTE_KEY, K_OPENAI):
            self.assertNotIn(secret, message + repr(caught.exception.details))
        self.assertEqual(len(gateway.requests), 1, "the refused config sent nothing")

    def test_a_vidbyte_key_in_a_provider_variable_is_refused_in_auto_and_in_direct(self) -> None:
        # AC-11, EC-13, INV-13, M-14: XAI_API_KEY holding a Vidbyte key would otherwise be relayed to xAI or sent to it.
        from vidbyte.lib.config import TextModelMode

        for mode in (TextModelMode.AUTO, TextModelMode.DIRECT):
            with self.subTest(mode=mode.value):
                transport = ScriptedGateway(provider_answer(ModelProvider.XAI))
                with patch.dict(os.environ, {"XAI_API_KEY": OTHER_VIDBYTE_KEY, "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
                    config = TextModelConfig(provider="xai", model="grok-4.5", api_keys=[], mode=mode)
                    with self.assertRaises(ConfigurationError) as caught:
                        config.validate()
                message = str(caught.exception)
                self.assertIn("XAI_API_KEY", message)
                self.assertIn("VIDBYTE_API_KEY", message)
                self.assertEqual(caught.exception.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
                for secret in (VIDBYTE_KEY, OTHER_VIDBYTE_KEY):
                    self.assertNotIn(secret, message + repr(caught.exception.details))
                self.assertEqual(transport.requests, [])

    def test_unserved_providers_and_custom_endpoints_need_direct_and_then_reach_the_vendor_or_proxy_as_at_base_commit(self) -> None:
        # AC-12, AC-36, INV-8, D-23, EC-15, EC-16, EC-17: refused at construction outside DIRECT; byte-identical BYOK inside it.
        from vidbyte.lib.config import TextModelMode

        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            for provider, model in (("mistral", "mistral-large-latest"), ("openrouter", "openai/gpt-5.5")):
                with self.subTest(refused=provider), self.assertRaises(UnsupportedProviderError) as caught:
                    TextModelConfig(provider=provider, model=model)
                self.assertIn("TextModelMode.DIRECT", str(caught.exception))
            with self.subTest(refused="endpoint"), self.assertRaises(ConfigurationError) as refused:
                TextModelConfig(provider="openai", model="gpt-5.5", endpoint="https://proxy.example/v1")
            self.assertIn("TextModelMode.DIRECT", str(refused.exception))

        goldens = (
            (
                TextModelConfig(provider="mistral", model="mistral-large-latest", api_keys=[MISTRAL_KEY], mode=TextModelMode.DIRECT),
                ModelProvider.MISTRAL,
                {"method": "POST", "url": "https://api.mistral.ai/v1/chat/completions", "headers": {"authorization": f"Bearer {MISTRAL_KEY}", "content-type": "application/json"}, "json_body": {"model": "mistral-large-latest", "messages": [{"role": "user", "content": PROMPT}]}, "timeout_seconds": 60.0},
            ),
            (
                TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI], endpoint="https://proxy.example/v1", mode=TextModelMode.DIRECT),
                ModelProvider.OPENAI,
                openai_golden(K_OPENAI, url="https://proxy.example/v1/responses"),
            ),
        )
        for config, provider, golden in goldens:
            with self.subTest(direct=provider.value), patch.dict(os.environ, {}, clear=True):
                vendor = ScriptedGateway(provider_answer(provider))
                TextModelRunner(config, transport=vendor).run(PROMPT)
                self.assertEqual(vendor.requests, [golden])

    def test_unserved_provider_in_direct_uses_its_environment_key_as_at_base_commit(self) -> None:
        # AC-12 (second half): the same mistral config in DIRECT with the provider's environment key calls the vendor.
        from vidbyte.lib.config import TextModelMode

        vendor = ScriptedGateway(provider_answer(ModelProvider.MISTRAL))
        with patch.dict(os.environ, {"MISTRAL_API_KEY": MISTRAL_KEY}, clear=True):
            TextModelRunner(TextModelConfig(provider="mistral", model="mistral-large-latest", mode=TextModelMode.DIRECT), transport=vendor).run(PROMPT)
        self.assertEqual([request["url"] for request in vendor.requests], ["https://api.mistral.ai/v1/chat/completions"])
        self.assertEqual(header(vendor.requests[0], "authorization"), f"Bearer {MISTRAL_KEY}")

    def test_vidbyte_managed_never_sends_or_reads_a_provider_key(self) -> None:
        # AC-13, INV-5, EC-18: the list is matched, then ignored; the provider's variable is never read.
        from vidbyte.lib.config import TextModelMode

        gateway = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        environment = RecordingEnviron({"OPENAI_API_KEY": K_OPENAI, "VIDBYTE_API_KEY": VIDBYTE_KEY})
        with patch.object(os, "environ", environment), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI], mode=TextModelMode.VIDBYTE_MANAGED)).run(PROMPT)
        [sent] = gateway.requests
        self.assertEqual(sent["url"], GATEWAY_URL)
        self.assertIsNone(provider_key_header(sent))
        self.assertEqual({name.lower() for name in sent["headers"]}, {"authorization", "content-type", "idempotency-key"})
        self.assertNotIn(K_OPENAI, flat(sent))
        self.assertNotIn("OPENAI_API_KEY", environment.reads)

    def test_vidbyte_managed_with_no_list_never_reads_the_provider_variable_even_when_it_holds_a_vidbyte_key(self) -> None:
        # AC-13, INV-5, EC-13 (review R-4): with no list, a provider-key lookup would read OPENAI_API_KEY and raise M-14 on the old habit of a Vidbyte key there.
        from vidbyte.lib.config import TextModelMode

        gateway = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        environment = RecordingEnviron({"OPENAI_API_KEY": OTHER_VIDBYTE_KEY, "VIDBYTE_API_KEY": VIDBYTE_KEY})
        with patch.object(os, "environ", environment), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", mode=TextModelMode.VIDBYTE_MANAGED)).run(PROMPT)
        self.assertEqual(len(gateway.requests), 1)
        [sent] = gateway.requests
        self.assertIsNone(provider_key_header(sent))
        self.assertNotIn("OPENAI_API_KEY", environment.reads)


class ReadmeAcceptanceTests(unittest.TestCase):
    """AC-27: the root README documents the two keys."""

    def test_readme_managed_section_documents_api_keys_vidbyte_api_key_relay_matching_and_direct(self) -> None:
        # AC-27, FR-14: the managed-text pack checks the old facts; this checks the facts this feature adds to the same section.
        text = README.read_text(encoding="utf-8")
        heading = README_SECTION_HEADING.search(text)
        if heading is None:
            self.fail("README has no level-2 to level-4 heading naming Vidbyte-managed mode")
        rest = text[heading.end():]
        next_heading = re.search(rf"^#{{1,{len(heading.group(1))}}} ", rest, re.MULTILINE)
        section = rest[: next_heading.start()] if next_heading else rest
        for fact in ("api_keys", "vidbyte_api_key", "TextModelMode.DIRECT"):
            with self.subTest(fact=fact):
                self.assertIn(fact, section)
        for pattern in (r"\brelay", r"\bmatch"):
            with self.subTest(pattern=pattern):
                self.assertRegex(section, re.compile(pattern, re.IGNORECASE))
        # NG-19, D-31, section 12.3 row 33: the section shows only the list form of api_keys and never ProviderKeys.
        self.assertNotIn("ProviderKeys", section)


if __name__ == "__main__":
    unittest.main()
