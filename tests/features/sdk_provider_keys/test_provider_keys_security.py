"""FILE: tests/features/sdk_provider_keys/test_provider_keys_security.py

PURPOSE: Proves that keys never leak: no record listed in INV-4 shows a key in its repr; no log line, error message, details mapping or traceback produced by relay, refusal, retry or agent failure paths holds a key; and every credential guard catches the new plural name api_keys (with list and tuple values, in the = and : forms) while still catching every name it caught before.
ROLE IN CODEBASE: Security layer of tests/features/sdk_provider_keys/ (spec AC-20, AC-21, AC-22; INV-4, INV-22; FR-13; EC-49; T-1). Exercises vidbyte/lib/dataclasses (model_configs, agents), vidbyte/agents (fallback, jev settings), vidbyte/paradigms/context_minimal_fanout/types.py, vidbyte/lib/util/credential_keys.py, vidbyte/lib/dataclasses/config.py, vidbyte/lib/dataclasses/agent_descriptor.py and vidbyte/harnesses/serialization.py.
ARCHITECTURE NOTE: The harness free-text cases live here rather than in tests/test_harness_redaction.py, which the spec's section 13 lists as not superseded. Log capture attaches one recording handler to the root logger at DEBUG for the duration of each scenario, so any SDK logger that propagates is seen.
COMMON MODIFICATION PATTERNS: When INV-4 gains a record, add it to the repr test. When a guard gains a name, add the name to the guard test and keep the old names in the INV-22 half.
WHAT NOT TO DO IN THIS FILE: 1. Do not import ProviderKeys, TextCredentials or TextModelMode.DIRECT at module level. 2. Do not build AIza or OpenAI-legacy key shapes here; the fixtures' fakes are enough. 3. Do not loosen a "no key" check to "no full key"; a prefix of a key is still key text.
KNOWN EDGE CASES: AgentFallback is a plain class whose default repr shows no fields; the check still guards against a future __repr__ that prints its record. AgentFallbackSettings cannot hold a key at all after D-26, so it has no repr case.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 6.1 (INV-4, INV-22), 6.2 (AC-20 to AC-22) and 12.3 rows 14 to 16.
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_security.py
"""

from __future__ import annotations

import logging
import os
import tempfile
import traceback
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    RUNNER_TRANSPORT_TARGET,
    SLEEP_TARGET,
    VIDBYTE_KEY,
    BackoffRecorder,
    ScriptedGateway,
    gateway_error,
    provider_answer,
)
from tests.features.sdk_provider_keys.provider_keys_fixtures import (
    K_ANTHROPIC,
    K_OPENAI,
    K_UNPROVEN,
    K_UNPROVEN_2,
    K_XAI,
    responses_done,
)
from vidbyte.lib.config import TextModelConfig, YamlLoader
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners import TextModelRunner

ALL_KEYS = (K_OPENAI, K_XAI, K_ANTHROPIC, K_UNPROVEN, K_UNPROVEN_2, VIDBYTE_KEY)
DESCRIPTOR_HEAD = "name: support-agent\nsystem_prompt: Help customers.\n"


class RecordingHandler(logging.Handler):
    """Keeps every formatted log record, including any traceback, for one scenario."""

    def __init__(self) -> None:
        # Accepts every level so a DEBUG line that prints a key is caught too.
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        # Formats the record the way a default handler would, traceback included.
        self.lines.append(logging.Formatter("%(name)s %(levelname)s %(message)s").format(record))


def rendered_error(error: BaseException) -> str:
    # Everything an exception can show: message, details, repr, and the formatted traceback with its chain.
    details = getattr(error, "details", {})
    return str(error) + repr(details) + repr(error) + "".join(traceback.format_exception(type(error), error, error.__traceback__))


class ReprTests(unittest.TestCase):
    """AC-20, INV-4: the repr of every record that holds keys shows none of them."""

    def test_no_record_listed_in_inv_4_shows_a_key_in_its_repr(self) -> None:
        # AC-20: each record is built holding keys; ProviderKeys still shows its provider names.
        from vidbyte.agents.fallback import AgentFallback
        from vidbyte.agents.jev.settings import JevAgentSettings, JevRunBriefSettings
        from vidbyte.lib.config import TextModelMode
        from vidbyte.lib.dataclasses.agents import AgentRunnerConfig, FallbackModel
        from vidbyte.lib.dataclasses.model_configs import TextCredentials
        from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher
        from vidbyte.paradigms.context_minimal_fanout.types import AgentRoleSettings

        with patch.dict(os.environ, {}, clear=True):
            record = ProviderKeyMatcher.match([K_OPENAI, K_XAI, VIDBYTE_KEY], primary="openai")
            records: dict[str, Any] = {
                "ProviderKeys": record,
                "TextModelConfig": TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI, K_XAI], vidbyte_api_key=VIDBYTE_KEY),
                "TextCredentials": TextCredentials(mode=TextModelMode.AUTO, provider_api_key=K_OPENAI, vidbyte_api_key=VIDBYTE_KEY),
                "AgentRunnerConfig": AgentRunnerConfig(api_keys=record, provider="openai", model_name="gpt-5.5"),
                "AgentFallback": AgentFallback([FallbackModel(provider="openai", model="gpt-5.5")], api_keys=record),
                "JevAgentSettings": JevAgentSettings(name="jev", system_prompt="Help.", provider="openai", model_name="gpt-5.5", api_keys=[K_OPENAI, K_XAI], vidbyte_api_key=VIDBYTE_KEY),
                "JevRunBriefSettings": JevRunBriefSettings(provider="anthropic", model_name="claude-sonnet-5", api_keys=[K_ANTHROPIC]),
                "AgentRoleSettings": AgentRoleSettings(name="planner", provider="openai", model_name="gpt-5.5", api_keys=[K_OPENAI, K_XAI], vidbyte_api_key=VIDBYTE_KEY),
            }
        for name, value in records.items():
            with self.subTest(record=name):
                shown = repr(value) + str(value)
                for key in ALL_KEYS:
                    self.assertNotIn(key, shown)
        self.assertIn("openai", repr(record))
        self.assertIn("xai", repr(record))


class LeakScenarioTests(unittest.TestCase):
    """AC-21, INV-4, D-17: logs, errors, details and tracebacks from key-handling paths never hold a key."""

    def run_scenario(self, scenario: Callable[[], Any]) -> tuple[list[str], BaseException | None]:
        # Runs one scenario with a cleared environment, no retry waits, and every log record captured.
        handler = RecordingHandler()
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY, "DEEPSEEK_API_KEY": K_UNPROVEN_2}, clear=True), patch(SLEEP_TARGET, new=BackoffRecorder()):
                scenario()
        except Exception as error:  # noqa: BLE001 - the scenario's own error is what the test inspects.
            return handler.lines, error
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)
        return handler.lines, None

    def test_relay_refusal_retry_and_agent_failure_paths_print_no_key(self) -> None:
        # AC-21: each scenario either succeeds or raises; whatever it logs or raises is searched for every fake key.
        from vidbyte import Agent
        from vidbyte.lib.config import TextModelMode

        def relay_success() -> None:
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI]), transport=ScriptedGateway(provider_answer(ModelProvider.OPENAI))).run("Hi")

        def relay_retry_then_failure() -> None:
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI]), transport=ScriptedGateway(gateway_error(502))).run("Hi")

        def relay_unauthorized() -> None:
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI]), transport=ScriptedGateway(gateway_error(401))).run("Hi")

        def two_keys_for_one_provider() -> None:
            TextModelConfig(provider="deepseek", model="deepseek-v4-pro", api_keys=[K_UNPROVEN, K_UNPROVEN_2, K_OPENAI])

        def missing_primary_key() -> None:
            Agent(name="writer", system_prompt="Write.", provider="openai", model_name="gpt-5.5", api_keys=[K_XAI, K_ANTHROPIC])

        def direct_missing_key() -> None:
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[VIDBYTE_KEY], mode=TextModelMode.DIRECT), transport=ScriptedGateway(provider_answer(ModelProvider.OPENAI))).run("Hi")

        def agent_run_without_vidbyte_key() -> None:
            os.environ.pop("VIDBYTE_API_KEY")
            with patch(RUNNER_TRANSPORT_TARGET, new=ScriptedGateway(responses_done("Hi"))):
                Agent(name="writer", system_prompt="Write.", provider="openai", model_name="gpt-5.5", api_keys=[K_OPENAI, K_XAI]).run("Say hi.")

        def agent_relay_failure() -> None:
            with patch(RUNNER_TRANSPORT_TARGET, new=ScriptedGateway(gateway_error(403))):
                Agent(name="writer", system_prompt="Write.", provider="openai", model_name="gpt-5.5", api_keys=[K_OPENAI, K_XAI]).run("Say hi.")

        expected_errors = {
            "relay success": False,
            "relay 502 three times": True,
            "relay 401": True,
            "two keys for one provider (M-7)": True,
            "missing primary key (M-18)": True,
            "DIRECT missing key (M-8)": True,
            "agent run without a Vidbyte key": True,
            "agent relay 403": True,
        }
        scenarios = (relay_success, relay_retry_then_failure, relay_unauthorized, two_keys_for_one_provider, missing_primary_key, direct_missing_key, agent_run_without_vidbyte_key, agent_relay_failure)
        for (label, raises), scenario in zip(expected_errors.items(), scenarios, strict=True):
            with self.subTest(scenario=label):
                lines, error = self.run_scenario(scenario)
                self.assertEqual(error is not None, raises, f"{label}: {type(error).__name__ if error else 'no error'}")
                searched = "\n".join(lines) + (rendered_error(error) if error is not None else "")
                for key in ALL_KEYS:
                    self.assertNotIn(key, searched)


class CredentialGuardTests(unittest.TestCase):
    """AC-22, INV-22, FR-13, EC-49: every guard catches api_keys and keeps catching the names it caught before."""

    def test_the_credential_key_policies_classify_the_plural_names_and_still_the_old_ones(self) -> None:
        # AC-22: api_keys, openai_api_keys, apiKeys and vidbyte_api_key are secret names; INV-22 keeps the singular ones.
        from vidbyte.lib.dataclasses.config import _YamlSecretKeyPolicy
        from vidbyte.lib.util.credential_keys import CredentialKeyPolicy

        for policy in (CredentialKeyPolicy, _YamlSecretKeyPolicy):
            for name in ("api_keys", "openai_api_keys", "apiKeys", "vidbyte_api_key", "api_key", "openai_api_key", "apiKey", "access_token"):
                with self.subTest(policy=policy.__name__, name=name):
                    self.assertTrue(policy.is_secret_key(name))
            for name in ("author", "providers", "key_providers", "model_mode"):
                with self.subTest(policy=policy.__name__, plain=name):
                    self.assertFalse(policy.is_secret_key(name))

    def test_the_agent_descriptor_guard_rejects_api_keys_in_metadata_and_tool_options(self) -> None:
        # AC-22, row 15: a top-level api_keys entry in a descriptor's metadata or a tool's options is refused at load.
        documents = (
            "metadata:\n  api_keys:\n    - k1\n    - k2\n",
            "metadata:\n  openai_api_keys: [k1]\n",
            "metadata:\n  api_key: k1\n",
            "tools:\n  - ref: web_search\n    options:\n      api_keys: [k1]\n",
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "agent.yaml"
            for document in documents:
                with self.subTest(document=document.splitlines()[1].strip()):
                    path.write_text(DESCRIPTOR_HEAD + document, encoding="utf-8")
                    with self.assertRaises(ConfigurationError):
                        YamlLoader().load_agent(path)
            path.write_text(DESCRIPTOR_HEAD + "metadata:\n  key_providers: [openai]\n", encoding="utf-8")
            self.assertIsNotNone(YamlLoader().load_agent(path))

    def test_the_harness_redactor_removes_every_key_in_a_list_or_tuple_value(self) -> None:
        # AC-22, EC-49, T-1: a list or tuple value is redacted whole, so the second key does not survive; the Vidbyte value too.
        from vidbyte.harnesses.serialization import HarnessRedactor

        texts = (
            f"api_keys=['{K_XAI}', '{K_ANTHROPIC}']",
            f"api_keys=('{K_XAI}', '{K_ANTHROPIC}')",
            f"api_keys: ['{K_XAI}', '{K_ANTHROPIC}']",
            f"api_keys: ('{K_XAI}', '{K_ANTHROPIC}')",
            f"{{'api_keys': ('{K_XAI}', '{K_ANTHROPIC}')}}",
            f"{{'api_keys': ['{K_XAI}', '{K_ANTHROPIC}']}}",
            f"run failed: openai_api_keys=['{K_XAI}', '{K_ANTHROPIC}'] after retry",
            f"vidbyte_api_key={VIDBYTE_KEY}",
            f"api_key={K_XAI}",
            f"Authorization: Bearer {K_ANTHROPIC}",
        )
        redactor = HarnessRedactor()
        for text in texts:
            with self.subTest(text=text[:16]):
                for output in (redactor.safe_error_message(text), redactor.redact(text)):
                    for key in (K_XAI, K_ANTHROPIC, VIDBYTE_KEY):
                        self.assertNotIn(key, output)
        structured = redactor.redact({"api_keys": (K_XAI, K_ANTHROPIC), "vidbyte_api_key": VIDBYTE_KEY, "provider": "xai"})
        for key in (K_XAI, K_ANTHROPIC, VIDBYTE_KEY):
            self.assertNotIn(key, repr(structured))
        self.assertIn("xai", repr(structured))


if __name__ == "__main__":
    unittest.main()
