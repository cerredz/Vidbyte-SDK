"""FILE: tests/features/sdk_provider_keys/test_provider_keys_contract.py

PURPOSE: Proves the public surface the spec commits to: the DIRECT member, the three wire constants, where ProviderKeyMatcher and ProviderKeys are exported, the field order of every renamed record, the removed methods, the table F, table A and reserved-prefix class tables, the signatures that replace api_key with api_keys, the old keyword failing loudly everywhere, the records' own refusals, and the manual scripts no longer passing api_key= to TextModelConfig.
ROLE IN CODEBASE: Interface layer of tests/features/sdk_provider_keys/ (spec AC-24, AC-30; FR-1, FR-4 to FR-7, FR-11, FR-12, FR-16, FR-17; D-20, D-26; section 8.5 and section 12.3 rows 1 to 5, 11 to 13, 17 to 21, 24, 29, 39 and 41; table M rows M-16 and M-17; EC-39).
ARCHITECTURE NOTE: Signatures are read with inspect and record layouts with dataclasses.fields, so a rename or a dropped parameter fails here before any behavior test runs. The manual scripts are parsed with ast, never executed.
COMMON MODIFICATION PATTERNS: When the spec renames a public parameter, add the surface to SIGNATURES with the new name present and the old one absent. Keep field lists literal; never read them from the code under test.
WHAT NOT TO DO IN THIS FILE: 1. Do not import a new symbol at module level; each test imports what it checks. 2. Do not run the scripts in scripts/; AC-30 only needs them to parse and to pass no api_key= to TextModelConfig.
KNOWN EDGE CASES: A TypeError raised for some other reason would satisfy assertRaises, so every AC-24 check also requires the old keyword's name in the message. BaseAgent.restore and Session.resume get placeholder arguments, because an unknown keyword fails while the call binds, before the body runs.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 8.5, 9.2 (tables F, A, M) and 12.3.
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_contract.py
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import os
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import VIDBYTE_KEY
from tests.features.sdk_provider_keys.provider_keys_fixtures import K_OPENAI
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ("scripts/test-new-runners.py", "scripts/test-async-http-transport.py", "scripts/test-openai-compatible-chat-trace-inputs.py")


class NamesAndConstantsTests(unittest.TestCase):
    """FR-1, FR-4, FR-6, FR-17, section 12.3 rows 1, 2, 4, 5 and 41."""

    def test_the_new_mode_and_the_wire_constants_have_their_contract_values(self) -> None:
        # FR-1, FR-6: DIRECT is the third member; the header name and limits mirror the backend's rule.
        from vidbyte.lib.constants.jev import VIDBYTE_PROVIDER_KEY_HEADER, VIDBYTE_PROVIDER_KEY_MAX_LENGTH, VIDBYTE_PROVIDER_KEY_PATTERN
        from vidbyte.lib.enums.text_model import TextModelMode

        self.assertEqual([member.value for member in TextModelMode], ["auto", "vidbyte_managed", "direct"])
        self.assertIs(TextModelMode("direct"), TextModelMode.DIRECT)
        self.assertEqual(VIDBYTE_PROVIDER_KEY_HEADER, "X-Vidbyte-Provider-Key")
        self.assertEqual(VIDBYTE_PROVIDER_KEY_PATTERN, r"[!-~]+")
        self.assertEqual(VIDBYTE_PROVIDER_KEY_MAX_LENGTH, 512)
        self.assertIs(type(VIDBYTE_PROVIDER_KEY_MAX_LENGTH), int)

    def test_the_matcher_and_the_record_are_exported_where_the_spec_says(self) -> None:
        # Rows 5 and 41: one class each, reachable from its module and its package.
        import vidbyte.lib.dataclasses as dataclasses_package
        import vidbyte.lib.registries as registries_package
        from vidbyte.lib.dataclasses.agents import ProviderKeys
        from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

        self.assertIs(registries_package.ProviderKeyMatcher, ProviderKeyMatcher)
        self.assertIn("ProviderKeyMatcher", registries_package.__all__)
        self.assertIs(dataclasses_package.ProviderKeys, ProviderKeys)
        self.assertIn("ProviderKeys", dataclasses_package.__all__)
        self.assertTrue(dataclasses.is_dataclass(ProviderKeys))
        self.assertEqual([field.name for field in dataclasses.fields(ProviderKeys)], ["providers", "keys", "vidbyte_api_key", "matched_primary", "matched_others"])
        self.assertEqual([field.name for field in dataclasses.fields(ProviderKeys) if not field.repr], ["keys", "vidbyte_api_key"])

    def test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes(self) -> None:
        # Section 9.2: table F's order, each rule's literal prefixes, the format-bound set, and the one refuse-only prefix.
        from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

        rows = ProviderKeyMatcher.KEY_FORMATS
        self.assertEqual([ModelProvider(provider) for provider, _, _ in rows], [ModelProvider.ANTHROPIC, ModelProvider.OPENROUTER, ModelProvider.OPENAI, ModelProvider.XAI, ModelProvider.GEMINI, ModelProvider.META])
        self.assertEqual([set(prefixes) for _, prefixes, _ in rows], [{"sk-ant-"}, {"sk-or-"}, {"sk-proj-", "sk-admin-"}, {"xai-"}, {"AIza", "AQ."}, {"LLM|"}])
        for _, _, pattern in rows:
            self.assertIsInstance(pattern, re.Pattern)
        self.assertEqual(set(ProviderKeyMatcher.FORMAT_BOUND_PROVIDERS), {ModelProvider.ANTHROPIC, ModelProvider.XAI, ModelProvider.GEMINI, ModelProvider.OPENROUTER, ModelProvider.META})
        self.assertEqual(tuple(ProviderKeyMatcher.RESERVED_PREFIXES), (("sk-svcacct-", ModelProvider.OPENAI),))

    def test_the_removed_methods_are_gone(self) -> None:
        # Section 9.2 "Removed": no alias survives (D-20).
        from vidbyte.lib.config import TextModelConfig
        from vidbyte.lib.registries.models import ProviderModelRegistry

        for owner, name in ((TextModelConfig, "is_vidbyte_managed"), (TextModelConfig, "resolved_vidbyte_api_key"), (ProviderModelRegistry, "find_vidbyte_api_key"), (ProviderModelRegistry, "vidbyte_key_follows_provider")):
            with self.subTest(name=f"{owner.__name__}.{name}"):
                self.assertFalse(hasattr(owner, name))
        self.assertTrue(callable(getattr(ProviderModelRegistry, "find_provider_api_key", None)))


class RecordLayoutTests(unittest.TestCase):
    """Section 8.5, rows 3, 24 and 29: api_keys takes api_key's place, new fields are appended, keys stay out of repr."""

    def test_each_renamed_record_keeps_its_field_order(self) -> None:
        # D-20 and section 8.5: a positional caller sees the same layout with the renamed field in place.
        from vidbyte.agents.jev.settings import JevAgentSettings, JevRunBriefSettings
        from vidbyte.lib.dataclasses.agents import AgentRunnerConfig, FallbackModel
        from vidbyte.paradigms.context_minimal_fanout.types import AgentRoleSettings

        layouts = {
            AgentRunnerConfig: (["api_keys", "provider", "model_name", "temperature", "run_id", "timeout_seconds", "model_mode"], ["api_keys"]),
            FallbackModel: (["provider", "model", "temperature"], []),
            JevAgentSettings: (["name", "system_prompt", "provider", "model_name", "api_keys", "temperature", "timeout_seconds", "tools", "permission_policy", "loop", "agents", "bulk_work", "alignment", "outputs", "vidbyte_api_key", "model_mode"], ["api_keys", "vidbyte_api_key"]),
            JevRunBriefSettings: (["provider", "model_name", "api_keys", "temperature", "every_iterations", "max_iterations", "max_tokens"], ["api_keys"]),
            AgentRoleSettings: (["name", "system_prompt", "runner", "provider", "model_name", "api_keys", "temperature", "tools", "middleware", "agent_options", "max_tokens", "vidbyte_api_key"], ["api_keys", "vidbyte_api_key"]),
        }
        for record, (names, hidden) in layouts.items():
            with self.subTest(record=record.__name__):
                fields = dataclasses.fields(record)
                self.assertEqual([field.name for field in fields], names)
                self.assertEqual([field.name for field in fields if not field.repr], hidden)

    def test_agent_runner_config_refuses_a_raw_list_and_a_string_mode(self) -> None:
        # Row 3, M-16: the config carries the matched record only, and the mode must be the enum.
        from vidbyte.lib.dataclasses.agents import AgentRunnerConfig, ProviderKeys

        self.assertEqual(AgentRunnerConfig().api_keys, ProviderKeys())
        with self.assertRaises(ConfigurationError) as raw:
            AgentRunnerConfig(api_keys=[K_OPENAI], provider="openai", model_name="gpt-5.5")
        self.assertIn("ProviderKeys", str(raw.exception))
        self.assertNotIn(K_OPENAI, str(raw.exception))
        with self.assertRaises(ConfigurationError) as mode:
            AgentRunnerConfig(provider="openai", model_name="gpt-5.5", model_mode="direct")
        self.assertIn("AgentRunnerConfig.model_mode must be a TextModelMode value", str(mode.exception))

    def test_jev_settings_check_their_mode_and_match_their_list(self) -> None:
        # Row 24, M-16: JevAgentSettings matches api_keys at construction and refuses a string mode.
        from vidbyte.agents.jev.settings import JevAgentSettings
        from vidbyte.lib.dataclasses.agents import ProviderKeys

        base = {"name": "jev", "system_prompt": "Help.", "provider": "openai", "model_name": "gpt-5.5"}
        with patch.dict(os.environ, {}, clear=True):
            settings = JevAgentSettings(**base, api_keys=[K_OPENAI, VIDBYTE_KEY])
            self.assertIsInstance(settings.api_keys, ProviderKeys)
            self.assertEqual(settings.api_keys.key_for("openai"), K_OPENAI)
            self.assertEqual(settings.vidbyte_api_key, VIDBYTE_KEY)
            with self.assertRaises(ConfigurationError) as mode:
                JevAgentSettings(**base, model_mode="direct")
        self.assertIn("JevAgentSettings.model_mode must be a TextModelMode value", str(mode.exception))

    def test_fallback_settings_name_the_providers_their_entries_switch_to(self) -> None:
        # Rows 18 and 19, D-27: the providers a chain names become the root's other configured providers; bare names add none.
        from vidbyte.agents.fallback import AgentFallback
        from vidbyte.agents.settings import AgentFallbackSettings
        from vidbyte.lib.dataclasses.agents import FallbackModel

        entries = ["anthropic/claude-sonnet-5", "gpt-5.5-mini", FallbackModel(provider="openai", model="gpt-5.5"), "anthropic/claude-haiku-5"]
        self.assertEqual(tuple(AgentFallbackSettings(models=entries).named_providers()), ("anthropic", "openai"))
        self.assertEqual(tuple(AgentFallback.providers_in(entries)), ("anthropic", "openai"))
        self.assertEqual(tuple(AgentFallback.providers_in(None)), ())
        self.assertEqual(tuple(AgentFallback.providers_in(AgentFallbackSettings(models=entries, enabled=False))), ())
        with self.assertRaises(ConfigurationError):
            AgentFallback.providers_in("anthropic/claude-sonnet-5")


class SignatureTests(unittest.TestCase):
    """Section 8.5: every surface that took api_key now takes api_keys, and the new keywords exist."""

    def test_each_surface_takes_the_new_keywords_and_not_the_old_one(self) -> None:
        # D-20: no alias; the new parameters are keyword arguments with the spec's defaults.
        from vidbyte.agents.aggregation import AggregateAgent
        from vidbyte.agents.base import BaseAgent
        from vidbyte.agents.fallback import AgentFallback
        from vidbyte.agents.settings import AgentFallbackSettings
        from vidbyte.lib.agents.modality_detector import ModalityDetector
        from vidbyte.lib.config import TextModelMode
        from vidbyte.lib.runners.router import create_runner_for_modality
        from vidbyte.lib.runners.utility import Runner
        from vidbyte.sessions.session import Session

        surfaces: dict[str, tuple[Callable[..., Any], dict[str, Any], tuple[str, ...]]] = {
            "Runner.__init__": (Runner.__init__, {"api_keys": None, "vidbyte_api_key": None, "model_mode": TextModelMode.AUTO}, ("api_key",)),
            "BaseAgent.__init__": (BaseAgent.__init__, {"api_keys": None, "vidbyte_api_key": None, "model_mode": TextModelMode.AUTO}, ("api_key",)),
            "AggregateAgent.__init__": (AggregateAgent.__init__, {"api_keys": None, "vidbyte_api_key": None, "model_mode": TextModelMode.AUTO}, ("api_key",)),
            "BaseAgent.restore": (BaseAgent.restore, {"api_keys": None, "vidbyte_api_key": None}, ("api_key",)),
            "Session.resume": (Session.resume, {"api_keys": None, "vidbyte_api_key": None}, ("api_key",)),
            "Session.fork_from": (Session.fork_from, {"api_keys": None, "vidbyte_api_key": None}, ("api_key",)),
            "AgentFallback.__init__": (AgentFallback.__init__, {"model_mode": TextModelMode.AUTO}, ("api_key",)),
            "AgentFallbackSettings.to_fallback": (AgentFallbackSettings.to_fallback, {"model_mode": TextModelMode.AUTO}, ("api_key",)),
            "ModalityDetector.create_runner": (ModalityDetector.create_runner, {"api_keys": None}, ("api_key",)),
            "create_runner_for_modality": (create_runner_for_modality, {"api_keys": None}, ("api_key",)),
        }
        for name, (function, defaults, removed) in surfaces.items():
            with self.subTest(surface=name):
                parameters = inspect.signature(function).parameters
                for parameter, default in defaults.items():
                    self.assertIn(parameter, parameters)
                    self.assertIs(parameters[parameter].kind, inspect.Parameter.KEYWORD_ONLY)
                    self.assertEqual(parameters[parameter].default, default)
                for parameter in removed:
                    self.assertNotIn(parameter, parameters)
        for name in ("AgentFallback.__init__", "AgentFallbackSettings.to_fallback"):
            with self.subTest(surface=name, parameter="api_keys"):
                self.assertIn("api_keys", inspect.signature(surfaces[name][0]).parameters)

    def test_the_gateway_transport_registry_and_matcher_signatures(self) -> None:
        # Section 8.5: the relay key is an optional keyword; resolve_vidbyte_api_key takes remedy; match takes its keyword set.
        from vidbyte.lib.http.vidbyte_gateway import VidbyteGatewayTransport
        from vidbyte.lib.registries.models import ProviderModelRegistry
        from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

        gateway = inspect.signature(VidbyteGatewayTransport.__init__).parameters
        self.assertIn("api_key", gateway)
        self.assertIs(gateway["provider_api_key"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(gateway["provider_api_key"].default)
        remedy = inspect.signature(ProviderModelRegistry.resolve_vidbyte_api_key).parameters["remedy"]
        self.assertIs(remedy.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(remedy.default)
        self.assertEqual(list(inspect.signature(ProviderModelRegistry.find_provider_api_key).parameters), ["provider", "keys"])
        match = inspect.signature(ProviderKeyMatcher.match).parameters
        self.assertEqual({name: match[name].default for name in ("others", "vidbyte_api_key", "field_name", "require_primary_key")}, {"others": (), "vidbyte_api_key": None, "field_name": "api_keys", "require_primary_key": True})
        self.assertIs(match["primary"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(match["primary"].default, inspect.Parameter.empty)
        self.assertEqual(inspect.signature(ProviderKeyMatcher.normalize).parameters["field_name"].default, "api_keys")


class OldKeywordTests(unittest.TestCase):
    """AC-24, EC-39, D-20, M-17: the old api_key= keyword fails loudly everywhere and is never ignored."""

    def test_the_old_keyword_raises_a_type_error_naming_it(self) -> None:
        # AC-24: each surface rejects api_key=; FallbackModel also rejects api_keys= (D-26).
        from vidbyte import Agent
        from vidbyte.agents.base import BaseAgent
        from vidbyte.agents.jev.settings import JevAgentSettings
        from vidbyte.lib.config import TextModelConfig
        from vidbyte.lib.dataclasses.agents import FallbackModel
        from vidbyte.lib.runners import TextModelRunner
        from vidbyte.lib.runners.utility import Runner
        from vidbyte.sessions import FileSessionStore, Session

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            store = FileSessionStore(Path(folder))
            calls: dict[str, tuple[Callable[[], Any], str]] = {
                "Agent": (lambda: Agent(name="a", system_prompt="s", provider="openai", model_name="gpt-5.5", api_key=K_OPENAI), "api_key"),
                "BaseAgent.restore": (lambda: BaseAgent.restore(object(), api_key=K_OPENAI), "api_key"),  # type: ignore[arg-type]
                "TextModelConfig": (lambda: TextModelConfig(provider="openai", model="gpt-5.5", api_key=K_OPENAI), "api_key"),
                "TextModelRunner": (lambda: TextModelRunner(provider="openai", model="gpt-5.5", api_key=K_OPENAI), "api_key"),
                "Runner": (lambda: Runner(provider="openai", model_name="gpt-5.5", api_key=K_OPENAI), "api_key"),
                "FallbackModel api_key": (lambda: FallbackModel(provider="openai", model="gpt-5.5", api_key=K_OPENAI), "api_key"),
                "FallbackModel api_keys": (lambda: FallbackModel(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI]), "api_keys"),
                "JevAgentSettings": (lambda: JevAgentSettings(name="jev", system_prompt="Help.", provider="openai", model_name="gpt-5.5", api_key=K_OPENAI), "api_key"),
                "Session.resume": (lambda: Session.resume(store, "missing-session", api_key=K_OPENAI), "api_key"),
            }
            for name, (call, keyword) in calls.items():
                with self.subTest(surface=name), self.assertRaises(TypeError) as caught:
                    call()
                self.assertIn(f"'{keyword}'", str(caught.exception))
                self.assertNotIn(K_OPENAI, str(caught.exception))

    def test_create_runner_refuses_api_key_for_a_text_model_naming_api_keys(self) -> None:
        # AC-24, M-17: create_runner takes **options, so the text path must refuse the old name instead of dropping it.
        from vidbyte.lib.agents.modality_detector import ModalityDetector
        from vidbyte.lib.runners.router import create_runner_for_modality

        for name, factory in (("ModalityDetector.create_runner", ModalityDetector.create_runner), ("create_runner_for_modality", create_runner_for_modality)):
            with self.subTest(factory=name), patch.dict(os.environ, {}, clear=True), self.assertRaises(ConfigurationError) as caught:
                factory("text", provider="openai", model="gpt-5.5", api_key=K_OPENAI)
            self.assertIn("api_keys", str(caught.exception))
            self.assertNotIn(K_OPENAI, str(caught.exception) + repr(caught.exception.details))
            self.assertEqual(caught.exception.details.get("model"), "gpt-5.5")


class ManualScriptTests(unittest.TestCase):
    """AC-30, FR-16: the three manual scripts compile and pass no api_key= to TextModelConfig."""

    def test_the_manual_scripts_compile_and_build_text_configs_with_api_keys(self) -> None:
        # AC-30: parsed with ast (the gate only compiles them); every TextModelConfig( call is inspected.
        configs = 0
        for relative in SCRIPTS:
            with self.subTest(script=relative):
                source = (REPO_ROOT / relative).read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative)
                compile(tree, relative, "exec")
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "TextModelConfig":
                        configs += 1
                        keywords = {keyword.arg for keyword in node.keywords}
                        self.assertNotIn("api_key", keywords, f"{relative}:{node.lineno}")
        self.assertGreater(configs, 0, "the scan found no TextModelConfig( call, so it proved nothing")


if __name__ == "__main__":
    unittest.main()
