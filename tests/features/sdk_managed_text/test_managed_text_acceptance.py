"""FILE: tests/features/sdk_managed_text/test_managed_text_acceptance.py

PURPOSE: Proves the stakeholder-visible promises of Vidbyte-managed text calls: the README snippet works with only VIDBYTE_API_KEY, all seven providers reach the one gateway route with their own BYOK body, BYOK stays byte-identical per provider, agents go managed too, and the README discloses the fee and names Meta where the gateway serves it.
ROLE IN CODEBASE: Acceptance layer of tests/features/sdk_managed_text/ (spec AC-1, AC-2, AC-3, AC-18, AC-23, AC-24; meta-muse-managed-text AC-13 and, through MANAGED_MODELS, INV-1, INV-6). Exercises vidbyte/lib/runners/text.py, vidbyte/lib/http/vidbyte_gateway.py, vidbyte/lib/dataclasses/model_configs.py and the unchanged adapters in vidbyte/providers/.
ARCHITECTURE NOTE: Only the inner HTTP transport is scripted. Expected requests are spelled as literals from spec section 4 or recorded from the real adapter in BYOK state, never recomputed from production constants.
COMMON MODIFICATION PATTERNS: When the gateway serves a new provider, add it to MANAGED_MODELS in managed_text_fixtures.py and give it an ORACLE_KEYS entry that its own key rule proves; the per-provider test picks it up, and a missing oracle key is a KeyError. When the README section is reworded, keep the facts this module checks.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level (see managed_text_fixtures.py). 2. Do not read the developer's real environment; every test clears it.
KNOWN EDGE CASES: Gemini carries the model only in its URL, so its managed body has no "model" key. Anthropic's BYOK default cap is 1,024 while managed calls default to 32,768. Since byok-api-keys, a provider key in AUTO is relayed through the gateway; byte-identical vendor-direct requests need TextModelMode.DIRECT, so the oracle and the goldens use it.
RELATED DOCS: tests/features/sdk_managed_text/FEATURE.md; docs/spec/managed-generative-models/spec.md sections 4, 6.2 and 9.2; docs/spec/byok-api-keys/spec.md section 13 (superseded rows); docs/spec/meta-muse-managed-text/spec.md sections 6.2 (AC-13) and 12.3 row 2.
TESTS: python -m pytest tests/features/sdk_managed_text/test_managed_text_acceptance.py
"""

from __future__ import annotations

import io
import json
import os
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    GATEWAY_URL,
    MANAGED_MODELS,
    RUNNER_TRANSPORT_TARGET,
    VIDBYTE_KEY,
    ScriptedGateway,
    answer,
    header,
    idempotency_key,
    provider_answer,
    provider_usage,
)
from vidbyte import Agent
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelRunner

PROMPT = "Say hi in one word."
KEY_PATTERN = re.compile(r"[0-9a-f]{32}")
RELAY_HEADER = "X-Vidbyte-Provider-Key"
# byok-api-keys FR-15: oracle keys that each match their own provider (table A), so the DIRECT oracle binds the key to the provider under test.
ORACLE_KEYS = {
    ModelProvider.OPENAI: "sk-proj-" + "oracle",
    ModelProvider.ANTHROPIC: "sk-ant-" + "oracle",
    ModelProvider.GEMINI: "AQ" + "." + "o" * 40,
    ModelProvider.XAI: "xai-" + "oracle",
    ModelProvider.DEEPSEEK: "d-oracle",
    ModelProvider.KIMI: "k-oracle",
    # META is format-bound (LLM|<digits>|<secret>), so its oracle must fully match that rule or matching refuses it (M-6).
    ModelProvider.META: "LLM" + "|" + "0" * 15 + "|" + "o" * 32,
}
README = Path(__file__).resolve().parents[3] / "README.md"
# The spec names no heading, so find the section by the spec's own term ("Vidbyte-managed mode") in any level-2 to level-4 heading.
README_SECTION_HEADING = re.compile(r"^(#{2,4}) [^\n]*\bvidbyte[- ]managed\b[^\n]*$", re.IGNORECASE | re.MULTILINE)
# The seven providers meta-muse-managed-text section 12.3 row 2(a) lists as served, in the README's spelling.
SERVED_PROVIDER_NAMES = ("OpenAI", "Anthropic", "Gemini", "xAI", "DeepSeek", "Kimi", "Meta")
# The chat-dialect providers whose cap the README says to set with max_output_tokens (row 2(b)).
CHAT_CAP_PROVIDER_NAMES = ("xAI", "DeepSeek", "Kimi", "Meta")


def readme_bullet(section: str, label: str) -> str:
    # One "- **Label:**" bullet of the section, its wrapped lines joined, so a re-wrap cannot change the outcome.
    match = re.search(rf"^- \*\*{re.escape(label)}:\*\*(.*?)(?=^- |^\*\*|^#|\Z)", section, re.MULTILINE | re.DOTALL)
    return " ".join(match.group(1).split()) if match else ""


def names_word(text: str, name: str) -> bool:
    # True when the provider name appears as a whole word, in any case (the existing README test is case-insensitive too).
    return re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE) is not None


class ManagedTextAcceptanceTests(unittest.TestCase):
    """Checks the developer-facing promises end to end through TextModelRunner."""

    def test_readme_snippet_with_only_vidbyte_key_sends_one_gateway_post_and_prints_the_provider_answer(self) -> None:
        # AC-1: the section 4 snippet, run as written (no transport argument), with only VIDBYTE_API_KEY set.
        gateway = ScriptedGateway(provider_answer(ModelProvider.OPENAI, text="Hi"))
        printed = io.StringIO()
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway), redirect_stdout(printed):
            # The snippet's own import lines, imported here so the module still collects before the feature exists.
            from vidbyte.lib.config import TextModelConfig, TextModelMode
            from vidbyte.lib.runners import TextModelRunner

            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"))
            response = runner.run("Say hi in one word.")

            print(response.provider.value, response.model)
            print(response.text)
            print(response.usage["output_tokens"])

            claude = TextModelRunner(TextModelConfig(provider="anthropic", model="claude-sonnet-5", mode=TextModelMode.VIDBYTE_MANAGED))

        self.assertIsInstance(claude, TextModelRunner)
        self.assertEqual(printed.getvalue().splitlines(), ["openai gpt-5.5", "Hi", "2"])
        self.assertEqual(len(gateway.requests), 1, "exactly one request: the openai call; building the claude runner sends nothing")
        [sent] = gateway.requests
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["url"], GATEWAY_URL)
        self.assertEqual(sent["json_body"], {"provider": "openai", "model": "gpt-5.5", "body": {"model": "gpt-5.5", "input": "Say hi in one word.", "max_output_tokens": 32768}})
        self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
        self.assertEqual(header(sent, "content-type"), "application/json")
        self.assertRegex(idempotency_key(sent) or "", KEY_PATTERN)

    def test_each_managed_provider_posts_its_byok_body_once_to_the_gateway_and_parses_the_answer(self) -> None:
        # AC-2, AC-23, INV-1..3, INV-12: one POST per call to the one route, the adapter's own body inside the envelope, the provider's answer parsed as in BYOK.
        for provider, model in MANAGED_MODELS.items():
            with self.subTest(provider=provider.value):
                gateway = ScriptedGateway(provider_answer(provider, text="Hi"))
                with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
                    response = TextModelRunner(TextModelConfig(provider=provider.value, model=model), transport=gateway).run(PROMPT, system="Be brief.")
                # The oracle: the same adapter vendor-direct (byok-api-keys FR-15: TextModelMode.DIRECT) with the config managed mode pins (cap 32,768, timeout 630 s).
                from vidbyte.lib.config import TextModelMode

                vendor = ScriptedGateway(provider_answer(provider, text="Hi"))
                with patch.dict(os.environ, {}, clear=True):
                    TextModelRunner(TextModelConfig(provider=provider, model=model, api_keys=[ORACLE_KEYS[provider]], mode=TextModelMode.DIRECT, max_output_tokens=32768, timeout_seconds=630.0), transport=vendor).run(PROMPT, system="Be brief.")
                self.assertEqual(len(vendor.requests), 1)
                self.assertNotEqual(vendor.requests[0]["url"], GATEWAY_URL)

                self.assertEqual(len(gateway.requests), 1)
                [sent] = gateway.requests
                self.assertEqual(sent["method"], "POST")
                self.assertEqual(sent["url"], GATEWAY_URL)
                self.assertEqual(sent["json_body"], {"provider": provider.value, "model": model, "body": vendor.requests[0]["json_body"]})
                self.assertEqual({name.lower() for name in sent["headers"]}, {"authorization", "content-type", "idempotency-key"})
                self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
                self.assertEqual(header(sent, "content-type"), "application/json")
                self.assertRegex(idempotency_key(sent) or "", KEY_PATTERN)
                self.assertEqual(sent.get("idempotency_key"), idempotency_key(sent))
                if provider is ModelProvider.GEMINI:
                    self.assertNotIn("model", sent["json_body"]["body"])
                    self.assertEqual(sent["json_body"]["body"]["generationConfig"]["maxOutputTokens"], 32768)
                self.assertIs(response.provider, provider)
                self.assertEqual(response.model, model)
                self.assertEqual(response.text, "Hi")
                self.assertEqual(response.usage, provider_usage(provider))

    def test_provider_key_relays_in_auto_and_keeps_its_byok_request_byte_identical_in_direct(self) -> None:
        # AC-3, EC-1, EC-30, INV-17; byok-api-keys INV-2 (AUTO relays the provider key), INV-6 (DIRECT keeps base_commit's exact vendor request).
        from vidbyte.lib.config import TextModelMode

        direct = TextModelMode.DIRECT
        gemini_key = "AQ" + "." + "g" * 40
        environment = {"OPENAI_API_KEY": "sk-openai-byok", "MOONSHOT_API_KEY": "sk-moonshot-byok", "VIDBYTE_API_KEY": VIDBYTE_KEY}
        byok_goldens = (
            (
                {"provider": "openai", "model": "gpt-5.5", "mode": direct},
                ModelProvider.OPENAI,
                {"method": "POST", "url": "https://api.openai.com/v1/responses", "headers": {"authorization": "Bearer sk-openai-byok", "content-type": "application/json"}, "json_body": {"model": "gpt-5.5", "input": PROMPT}, "timeout_seconds": 60.0},
            ),
            (
                {"provider": "gemini", "model": "gemini-3.5-flash", "api_keys": [gemini_key], "mode": direct},
                ModelProvider.GEMINI,
                {"method": "POST", "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent", "headers": {"x-goog-api-key": gemini_key, "content-type": "application/json"}, "json_body": {"contents": [{"role": "user", "parts": [{"text": PROMPT}]}]}, "timeout_seconds": 60.0},
            ),
            (
                # MOONSHOT_API_KEY, not KIMI_API_KEY, is kimi's variable; a guessed name would bill this user.
                {"provider": "kimi", "model": "kimi-k2.7-code", "mode": direct},
                ModelProvider.KIMI,
                {"method": "POST", "url": "https://api.moonshot.ai/v1/chat/completions", "headers": {"authorization": "Bearer sk-moonshot-byok", "content-type": "application/json"}, "json_body": {"model": "kimi-k2.7-code", "messages": [{"role": "user", "content": PROMPT}]}, "timeout_seconds": 60.0},
            ),
        )
        for options, provider, golden in byok_goldens:
            with self.subTest(direct=provider.value), patch.dict(os.environ, environment, clear=True):
                vendor = ScriptedGateway(provider_answer(provider))
                config = TextModelConfig(**options)
                self.assertFalse(config.credentials().uses_gateway)
                TextModelRunner(config, transport=vendor).run(PROMPT)
                self.assertEqual(vendor.requests, [golden])
        for provider, model, relayed in ((ModelProvider.OPENAI, "gpt-5.5", "sk-openai-byok"), (ModelProvider.KIMI, "kimi-k2.7-code", "sk-moonshot-byok")):
            with self.subTest(relay=provider.value), patch.dict(os.environ, environment, clear=True):
                gateway = ScriptedGateway(provider_answer(provider))
                config = TextModelConfig(provider=provider.value, model=model)
                self.assertTrue(config.credentials().uses_gateway)
                self.assertTrue(config.credentials().relays)
                TextModelRunner(config, transport=gateway).run(PROMPT)
                self.assertEqual([request["url"] for request in gateway.requests], [GATEWAY_URL])
                self.assertEqual(header(gateway.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")
                self.assertEqual(header(gateway.requests[0], RELAY_HEADER), relayed)
        with self.subTest(paid="anthropic"), patch.dict(os.environ, environment, clear=True):
            gateway = ScriptedGateway(provider_answer(ModelProvider.ANTHROPIC))
            config = TextModelConfig(provider="anthropic", model="claude-sonnet-5")
            self.assertTrue(config.credentials().uses_gateway)
            self.assertFalse(config.credentials().relays)
            TextModelRunner(config, transport=gateway).run(PROMPT)
            self.assertEqual([request["url"] for request in gateway.requests], [GATEWAY_URL])
            self.assertEqual(header(gateway.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")
            self.assertIsNone(header(gateway.requests[0], RELAY_HEADER))

    def test_readme_managed_section_states_the_fee_and_the_limits_that_match_the_constants(self) -> None:
        # AC-18: the fee disclosure ships, and its numbers cannot drift from the constants the SDK enforces.
        from vidbyte.lib.constants.jev import VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS, VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS

        text = README.read_text(encoding="utf-8")
        heading = README_SECTION_HEADING.search(text)
        if heading is None:
            self.fail("README has no level-2 to level-4 heading naming Vidbyte-managed mode")
        # The section runs to the next heading of the same or a higher level.
        rest = text[heading.end():]
        next_heading = re.search(rf"^#{{1,{len(heading.group(1))}}} ", rest, re.MULTILINE)
        section = rest[: next_heading.start()] if next_heading else rest
        facts = ("2%", "VIDBYTE_API_KEY", "Idempotency-Key", "maxOutputTokens", "max_output_tokens", "previous_response_id", "2,000,000", f"{VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS:,}", f"{VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS:g}")
        for fact in facts:
            with self.subTest(fact=fact):
                self.assertIn(fact, section)
        for provider_name in ("OpenAI", "Anthropic", "Gemini", "xAI", "DeepSeek", "Kimi"):
            with self.subTest(provider=provider_name):
                self.assertRegex(section, re.compile(re.escape(provider_name), re.IGNORECASE))
        for pattern in ("stream", "service.?tier", "snake.?case"):
            with self.subTest(pattern=pattern):
                self.assertRegex(section, re.compile(pattern, re.IGNORECASE))

    def test_readme_managed_section_names_meta_as_served_in_the_chat_cap_guidance_and_by_its_llm_prefix(self) -> None:
        # meta-muse-managed-text AC-13, FR-7, section 12.3 row 2(a)-(c): the three bullets that change when the gateway serves meta.
        text = README.read_text(encoding="utf-8")
        heading = README_SECTION_HEADING.search(text)
        if heading is None:
            self.fail("README has no level-2 to level-4 heading naming Vidbyte-managed mode")
        rest = text[heading.end():]
        next_heading = re.search(rf"^#{{1,{len(heading.group(1))}}} ", rest, re.MULTILINE)
        section = rest[: next_heading.start()] if next_heading else rest
        providers, cap, prefixes = (readme_bullet(section, label) for label in ("Providers", "Output cap", "Prefixes"))
        # Each bullet must exist, so a renamed label fails here instead of passing on an empty string.
        for label, bullet in (("Providers", providers), ("Output cap", cap), ("Prefixes", prefixes)):
            with self.subTest(bullet=label):
                self.assertTrue(bullet, f"the managed section has no '- **{label}:**' bullet")

        # (a) The bullet's first sentence is the served list: all seven names, Meta among them.
        served_list = providers.split(". ")[0]
        for name in SERVED_PROVIDER_NAMES:
            with self.subTest(served=name):
                self.assertTrue(names_word(served_list, name), f"{name!r} is not in the served list: {served_list!r}")
        # (b) The sentence that steers chat-dialect users away from max_completion_tokens names Meta with xAI, DeepSeek and Kimi.
        chat_cap_sentences = [sentence for sentence in re.split(r"(?<=\.)\s+", cap) if "max_completion_tokens" in sentence]
        self.assertTrue(chat_cap_sentences, f"the Output cap bullet no longer mentions max_completion_tokens: {cap!r}")
        self.assertTrue(
            any(all(names_word(sentence, name) for name in CHAT_CAP_PROVIDER_NAMES) for sentence in chat_cap_sentences),
            f"no max_completion_tokens sentence names all of {CHAT_CAP_PROVIDER_NAMES}: {chat_cap_sentences!r}",
        )
        # (c) The Prefixes bullet lists LLM| as the prefix that proves a Meta key, beside the prefixes it already listed.
        self.assertIn("`LLM|` (Meta)", prefixes)
        for existing in ("`sk-ant-` (Anthropic)", "`xai-` (xAI)", "(Gemini)"):
            with self.subTest(prefix=existing):
                self.assertIn(existing, prefixes)


class ManagedAgentTests(unittest.IsolatedAsyncioTestCase):
    """Checks that agents, which build their own runner, are managed too."""

    async def test_agent_model_turn_with_only_vidbyte_key_goes_through_the_gateway(self) -> None:
        # AC-24, NFR-1: Agent -> Runner.build -> TextModelRunner builds its own HttpTransport, so replace that class where text.py looks it up.
        finish = {"id": "resp_1", "output": [{"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": "Hi"}), "call_id": "call_1"}], "usage": {"input_tokens": 40, "output_tokens": 5}}
        gateway = ScriptedGateway(answer(200, finish))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            agent = Agent(name="greeter", system_prompt="Answer briefly.", provider="openai", model_name="gpt-5.5")
            message = await agent.arun("Say hi")

        self.assertEqual(message.content, "Hi")
        self.assertTrue(gateway.requests)
        self.assertEqual({request["url"] for request in gateway.requests}, {GATEWAY_URL})
        envelope = gateway.requests[0]["json_body"]
        self.assertEqual((envelope["provider"], envelope["model"]), ("openai", "gpt-5.5"))
        self.assertIn("tools", envelope["body"])
        self.assertEqual(envelope["body"]["max_output_tokens"], 32768)
        self.assertEqual(header(gateway.requests[0], "authorization"), f"Bearer {VIDBYTE_KEY}")


if __name__ == "__main__":
    unittest.main()
