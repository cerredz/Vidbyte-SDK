"""FILE: tests/features/sdk_provider_keys/test_provider_keys_matching.py

PURPOSE: Proves the matching rules of ProviderKeyMatcher one rule at a time: the list's shape, each entry's characters, which prefixes prove a provider (table F), which providers take an unproven key (table A and the reserved prefixes), unique assignment with the lone-key rule, the configured-primary rule (INV-24), the Vidbyte entry, a record passed back in, and that every refusal names indexes and providers but never key characters.
ROLE IN CODEBASE: Unit layer of tests/features/sdk_provider_keys/ (spec AC-8 to AC-10, AC-29, AC-35, AC-39, AC-42; INV-10, INV-13, INV-24 to INV-26; D-2 to D-4, D-25, D-28, D-29, D-31; EC-1 to EC-10, EC-45, EC-46, EC-51, EC-55, EC-58; table M rows M-1 to M-7, M-10, M-11, M-18 to M-20). Exercises vidbyte/lib/registries/provider_keys.py and vidbyte/lib/dataclasses/agents.py directly, and through the roots that call them (TextModelConfig, Agent, JevAgentSettings, JevRunBriefSettings, AgentRoleSettings).
ARCHITECTURE NOTE: The matcher is pure (no environment, no network), so these tests call it directly with primary/others and check the returned ProviderKeys through key_for and key_view. The expected provider of every table F sample is spelled from the spec's table, never read from KEY_FORMATS.
COMMON MODIFICATION PATTERNS: When a vendor documents a new key prefix (a table F row), add a sample to the provider_of table and a reserved-prefix case. Keep message checks to the facts table M binds; the wording is the implementer's.
WHAT NOT TO DO IN THIS FILE: 1. Do not import ProviderKeyMatcher, ProviderKeys or the new constants at module level. 2. Do not write AIza + 35, sk-ant-api03- + 93 + AA, or a T3BlbkFJ-signed key as one literal; build them by concatenation inside the AC-29 test. 3. Do not mock any part of the matcher.
KNOWN EDGE CASES: A key that starts with a table F prefix but does not fully match its rule (an xai- key with a dot) is unproven and reserved to that provider, which takes no unproven key, so nothing can take it. An sk-svcacct- key is reserved to openai, which takes it as an unproven sk- key.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md section 9.2 ("Matching", tables F, A, M) and D-28, D-29, D-31.
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_matching.py
"""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import OTHER_VIDBYTE_KEY, VIDBYTE_KEY
from tests.features.sdk_provider_keys.provider_keys_fixtures import (
    K_ANTHROPIC,
    K_GEMINI_AQ,
    K_OPENAI,
    K_OPENAI_2,
    K_OPENAI_ADMIN,
    K_OPENROUTER,
    K_SK_UNPROVEN,
    K_UNPROVEN,
    K_UNPROVEN_2,
    K_XAI,
    RecordingEnviron,
    key_view,
)
from vidbyte import Agent
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError

CREDENTIAL_ERROR_KIND = "vidbyte_managed_credentials"
ALL_PROVIDERS = tuple(ModelProvider)
FORMAT_BOUND = {ModelProvider.ANTHROPIC, ModelProvider.XAI, ModelProvider.GEMINI, ModelProvider.OPENROUTER}


def matcher() -> Any:
    # The class under test, imported late so this module collects while the feature is missing.
    from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

    return ProviderKeyMatcher


class KeySafeAssertions(unittest.TestCase):
    """Shared check that a refusal carries no key characters (D-17); holds no tests of its own."""

    def refused(self, call: Any, *keys: str) -> tuple[str, dict[str, Any]]:
        # Runs the call, requires a ConfigurationError, and returns its message and details after the no-key-text check.
        with self.assertRaises(ConfigurationError) as caught:
            call()
        message = str(caught.exception)
        details = dict(caught.exception.details)
        for key in keys:
            self.assertNotIn(key, message + repr(details))
        return message, details


class ListShapeTests(KeySafeAssertions):
    """AC-8, EC-1, EC-2, EC-4, M-1 to M-4: api_keys must be a list of strings, on every root."""

    def _roots(self) -> dict[str, Any]:
        # Every root that takes a raw list, each as a function of the bad value.
        from vidbyte.agents.jev import JevAgentSettings
        from vidbyte.agents.jev.settings import JevRunBriefSettings
        from vidbyte.paradigms.context_minimal_fanout import AgentRoleSettings

        return {
            "matcher": lambda value: matcher().match(value, primary="xai"),
            "TextModelConfig": lambda value: TextModelConfig(provider="xai", model="grok-4.5", api_keys=value),
            "Agent": lambda value: Agent(name="a", system_prompt="s", provider="xai", model_name="grok-4.5", api_keys=value),
            "JevAgentSettings": lambda value: JevAgentSettings(name="a", system_prompt="s", provider="xai", model_name="grok-4.5", api_keys=value),
            "JevRunBriefSettings": lambda value: JevRunBriefSettings(api_keys=value),
            "AgentRoleSettings": lambda value: AgentRoleSettings(name="role", provider="xai", model_name="grok-4.5", api_keys=value),
        }

    def test_a_string_bytes_mapping_or_number_is_refused_naming_the_field_and_never_its_characters(self) -> None:
        # AC-8, EC-1, EC-2, EC-58, INV-10: a bare string would otherwise become one-character keys; a dict would match its own keys.
        cases = (
            ("str", K_XAI, "list", K_XAI),
            ("bytes", K_XAI.encode(), "list", K_XAI),
            ("mapping", {"openai": K_OPENAI}, "mapping", K_OPENAI),
            ("int", 42, "int", "42"),
        )
        with patch.dict(os.environ, {}, clear=True):
            for root, build in self._roots().items():
                for kind, value, fact, secret in cases:
                    with self.subTest(root=root, kind=kind):
                        message, details = self.refused(lambda: build(value), secret)
                        self.assertIn("api_keys", message)
                        self.assertIn(fact, message)
                        self.assertIn("api_keys", str(details.get("field")))

    def test_none_and_blank_entries_are_skipped_entries_are_stripped_and_identical_repeats_collapse(self) -> None:
        # EC-3, EC-6, EC-9, D-4: the os.environ.get list pattern works; a pasted trailing newline does not break a key.
        record = matcher().match([None, "", "   ", f"  {K_XAI}\n", K_XAI], primary="xai")
        self.assertEqual(key_view(record)[0], {"xai": K_XAI})
        self.assertEqual(matcher().normalize([None, f" {K_XAI} ", "", K_UNPROVEN]), (K_XAI, K_UNPROVEN))
        self.assertEqual(matcher().normalize(None), ())

    def test_a_non_string_entry_is_refused_naming_its_index_and_type(self) -> None:
        # EC-4, M-4: the entry's index and type, never its value.
        for value, type_name in ((12345, "int"), (K_XAI.encode(), "bytes"), (object(), "object")):
            with self.subTest(type=type_name):
                message, details = self.refused(lambda: matcher().match([K_XAI, value], primary="xai"), K_XAI, "12345")
                self.assertIn("api_keys[1]", message)
                self.assertIn(type_name, message)
                self.assertEqual(details.get("index"), 1)

    def test_an_entry_with_a_space_line_break_or_non_ascii_character_is_refused_by_normalize(self) -> None:
        # AC-29 (last sentence), EC-10, T-5, M-6b: the value never reaches a header.
        for entry in ("xai-abc def", "xai-abc\r\nX-Other: y", "xai-abc\tdef", "d-mocké", "d-mock​"):
            with self.subTest(entry=repr(entry)):
                message, details = self.refused(lambda: matcher().normalize([K_XAI, entry]), entry)
                self.assertIn("api_keys[1]", message)
                self.assertIn(str(len(entry)), message)
                self.assertEqual((details.get("index"), details.get("length")), (1, len(entry)))


class TableFAndATests(unittest.TestCase):
    """AC-29, D-19, D-28, NG-18: which prefixes prove a provider and which providers take an unproven key."""

    def test_each_table_f_sample_proves_its_provider_and_every_unsourced_shape_is_unproven(self) -> None:
        # AC-29: provider_of is the first full-matching rule; the legacy, hex, 48-character, service-account and dotted xai shapes prove nothing.
        alnum = "Ab1" * 20
        proven = (
            ("sk-ant-", "sk-ant-" + "api" + "Z" * 30, ModelProvider.ANTHROPIC),
            ("sk-or-", K_OPENROUTER, ModelProvider.OPENROUTER),
            ("sk-proj-", K_OPENAI, ModelProvider.OPENAI),
            ("sk-admin-", K_OPENAI_ADMIN, ModelProvider.OPENAI),
            ("xai-", K_XAI, ModelProvider.XAI),
            ("AIza+35", "AIza" + "g" * 35, ModelProvider.GEMINI),
            ("AQ.", K_GEMINI_AQ, ModelProvider.GEMINI),
        )
        for name, key, provider in proven:
            with self.subTest(sample=name):
                self.assertIs(matcher().provider_of(key), provider)
        unproven = (
            ("legacy openai", "sk-" + alnum[:20] + "T3Blbk" + "FJ" + alnum[:20]),
            ("sk- + 32 hex", "sk-" + "0123456789abcdef" * 2),
            ("sk- + 48 alnum", "sk-" + alnum[:48]),
            ("sk-svcacct-", "sk-svcacct-" + "w" * 24),
            ("dotted xai-", "xai-client-secret." + "c" * 16),
            ("plain", K_UNPROVEN),
            ("AIza too short", "AIza" + "g" * 10),
        )
        for name, key in unproven:
            with self.subTest(sample=name):
                self.assertIsNone(matcher().provider_of(key))

    def test_accepts_unproven_follows_table_a_and_the_reserved_prefixes(self) -> None:
        # AC-29, D-28: format-bound providers take nothing; openai takes only sk-; a reserved prefix is taken only by its own provider.
        plain = K_UNPROVEN
        sk_key = K_SK_UNPROVEN
        svcacct = "sk-svcacct-" + "w" * 24
        dotted_xai = "xai-client-secret." + "c" * 16
        bad_anthropic = "sk-ant-" + "a.b"
        bad_openai = "sk-proj-" + "a.b"
        for provider in ALL_PROVIDERS:
            with self.subTest(provider=provider.value):
                open_provider = provider not in FORMAT_BOUND and provider is not ModelProvider.OPENAI
                self.assertEqual(matcher().accepts_unproven(provider, plain), open_provider)
                self.assertEqual(matcher().accepts_unproven(provider, sk_key), open_provider or provider is ModelProvider.OPENAI)
                self.assertEqual(matcher().accepts_unproven(provider, svcacct), provider is ModelProvider.OPENAI)
                self.assertFalse(matcher().accepts_unproven(provider, dotted_xai))
                self.assertFalse(matcher().accepts_unproven(provider, bad_anthropic))
                self.assertEqual(matcher().accepts_unproven(provider, bad_openai), provider is ModelProvider.OPENAI)
                # A provider name works as well as the enum member.
                self.assertEqual(matcher().accepts_unproven(provider.value, plain), open_provider)


class UniqueAssignmentTests(KeySafeAssertions):
    """INV-25, D-2, D-4, D-29: how unproven keys are bound, and the refusals M-6, M-7, M-19."""

    def test_two_different_proven_keys_for_one_provider_are_refused_and_the_same_key_twice_is_one_key(self) -> None:
        # AC-10 (first case), M-7: indexes 0 and 2 and the provider, with no key text.
        message, details = self.refused(lambda: TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI, VIDBYTE_KEY, K_OPENAI_2]), K_OPENAI, K_OPENAI_2, VIDBYTE_KEY)
        self.assertIn("api_keys[0]", message)
        self.assertIn("api_keys[2]", message)
        self.assertIn("openai", message)
        self.assertEqual(sorted(details.get("indexes", ())), [0, 2])
        self.assertEqual(details.get("provider"), "openai")
        record = matcher().match([K_OPENAI, K_OPENAI], primary="openai")
        self.assertEqual(key_view(record)[0], {"openai": K_OPENAI})

    def test_two_unproven_keys_with_one_possible_owner_are_refused(self) -> None:
        # AC-10 (second case), EC-7, M-7: the first binds to deepseek, and the second then has no owner left.
        message, details = self.refused(lambda: matcher().match([K_UNPROVEN, K_UNPROVEN_2], primary="deepseek"), K_UNPROVEN, K_UNPROVEN_2)
        self.assertIn("api_keys[0]", message)
        self.assertIn("api_keys[1]", message)
        self.assertIn("deepseek", message)
        self.assertEqual(sorted(details.get("indexes", ())), [0, 1])

    def test_an_unproven_sk_key_beside_a_proven_openai_key_is_refused_in_both_orders(self) -> None:
        # AC-42 (first case), M-7: openai already holds the sk-proj- key, and nothing else can take the sk- key.
        for api_keys in ([K_OPENAI, K_SK_UNPROVEN], [K_SK_UNPROVEN, K_OPENAI]):
            with self.subTest(first=api_keys[0][:8]):
                message, details = self.refused(lambda: TextModelConfig(provider="openai", model="gpt-5.5", api_keys=api_keys), K_OPENAI, K_SK_UNPROVEN)
                self.assertIn("api_keys[0]", message)
                self.assertIn("api_keys[1]", message)
                self.assertIn("openai", message)
                self.assertEqual(sorted(details.get("indexes", ())), [0, 1])

    def test_a_key_no_configured_provider_can_take_names_the_configured_providers(self) -> None:
        # AC-42 (second case), EC-46, M-6: anthropic takes only sk-ant- keys; with no provider configured the message says none.
        message, details = self.refused(lambda: TextModelConfig(provider="anthropic", model="claude-sonnet-5", api_keys=["k"]))
        self.assertIn("api_keys[0]", message)
        self.assertIn("1 character", message)
        self.assertIn("anthropic", message)
        self.assertIn("environment variable", message)
        self.assertEqual((details.get("index"), details.get("length")), (0, 1))
        message, _ = self.refused(lambda: matcher().match([K_UNPROVEN], primary=None), K_UNPROVEN)
        self.assertIn("none", message.lower())

    def test_unique_assignment_binds_each_unproven_key_to_its_one_possible_owner(self) -> None:
        # D-2, INV-25: the non-sk key can only be deepseek's, which leaves openai as the sk- key's one owner.
        record = matcher().match([K_SK_UNPROVEN, K_UNPROVEN, K_ANTHROPIC], primary="anthropic", others=("deepseek", "openai"))
        self.assertEqual(key_view(record)[0], {"anthropic": K_ANTHROPIC, "deepseek": K_UNPROVEN, "openai": K_SK_UNPROVEN})

    def test_a_lone_unproven_key_binds_to_the_one_keyless_primary_that_takes_it(self) -> None:
        # D-29: [k] for a deepseek agent with an openai backup is deepseek's key, not an M-19.
        record = matcher().match([K_SK_UNPROVEN], primary="deepseek", others=("openai",))
        self.assertEqual(key_view(record)[0], {"deepseek": K_SK_UNPROVEN})
        # With the primary holding a key already, the lone rule does not apply and unique assignment decides.
        record = matcher().match([K_ANTHROPIC, K_UNPROVEN], primary="anthropic", others=("deepseek",))
        self.assertEqual(key_view(record)[0], {"anthropic": K_ANTHROPIC, "deepseek": K_UNPROVEN})

    def test_two_unproven_keys_two_providers_could_take_are_refused_naming_every_candidate_and_variable(self) -> None:
        # EC-35, M-19: the lowest failing index, its length, the candidates and their environment variables.
        message, details = self.refused(lambda: matcher().match([K_UNPROVEN, K_UNPROVEN_2], primary="deepseek", others=("kimi",)), K_UNPROVEN, K_UNPROVEN_2)
        for fact in ("api_keys[0]", str(len(K_UNPROVEN)), "deepseek", "kimi", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY"):
            self.assertIn(fact, message)
        self.assertEqual(details.get("index"), 0)


class ConfiguredPrimaryTests(KeySafeAssertions):
    """INV-24, D-5, D-27, M-18: a list that holds provider keys must hold one for every primary."""

    def test_a_list_without_the_primarys_key_is_refused_unless_it_holds_no_provider_key(self) -> None:
        # INV-24: names the primary, every provider the list holds, and the primary's variable.
        message, details = self.refused(lambda: matcher().match([K_XAI, K_ANTHROPIC], primary="openai"), K_XAI, K_ANTHROPIC)
        for fact in ("openai", "xai", "anthropic", "OPENAI_API_KEY"):
            self.assertIn(fact, message)
        self.assertEqual(details.get("provider"), "openai")
        for api_keys in ([], [VIDBYTE_KEY], [None, " "]):
            with self.subTest(api_keys=len(api_keys)):
                self.assertEqual(key_view(matcher().match(api_keys, primary="openai"))[0], {})

    def test_several_primaries_each_need_a_key_and_the_first_without_one_is_named(self) -> None:
        # D-27, AC-37: an aggregate passes its proposers and aggregator as a tuple of primaries.
        message, details = self.refused(lambda: matcher().match([K_ANTHROPIC], primary=("openai", "deepseek", "anthropic")), K_ANTHROPIC)
        self.assertEqual(details.get("provider"), "openai")
        self.assertIn("anthropic", message)
        record = matcher().match([K_ANTHROPIC, K_OPENAI, K_UNPROVEN], primary=("openai", "deepseek", "anthropic"))
        self.assertEqual(key_view(record)[0], {"anthropic": K_ANTHROPIC, "openai": K_OPENAI, "deepseek": K_UNPROVEN})
        self.assertEqual(key_view(record)[2], ("openai", "deepseek", "anthropic"))

    def test_a_key_bound_to_a_backup_still_leaves_a_keyless_primary_refused(self) -> None:
        # INV-24 after unique assignment: K_u can only be deepseek's, so xai (the primary) has none.
        message, _ = self.refused(lambda: matcher().match([K_UNPROVEN], primary="xai", others=("deepseek",)), K_UNPROVEN)
        self.assertIn("xai", message)
        self.assertIn("deepseek", message)

    def test_m18_offers_vidbytes_own_account_only_for_a_provider_the_gateway_serves(self) -> None:
        # M-18 (review R-13, re-review R-C2): the gateway cannot serve mistral, so "Vidbyte's own mistral account" is a remedy that cannot work.
        # An unserved primary reaches M-18 only in DIRECT; a gateway-mode TextModelConfig refuses it first with M-12 (R-6).
        from vidbyte.lib.config import TextModelMode

        unserved = {
            "TextModelConfig DIRECT": lambda: TextModelConfig(provider="mistral", model="mistral-large-latest", api_keys=[K_XAI], mode=TextModelMode.DIRECT),
            "Agent DIRECT": lambda: Agent(name="a", system_prompt="s", provider="mistral", model_name="mistral-large-latest", api_keys=[K_XAI], model_mode=TextModelMode.DIRECT),
        }
        for root, build in unserved.items():
            with self.subTest(root=root, primary="mistral"), patch.dict(os.environ, {}, clear=True):
                message, details = self.refused(build, K_XAI)
                self.assertEqual(details.get("provider"), "mistral")
                for fact in ("mistral", "xai", "MISTRAL_API_KEY"):
                    self.assertIn(fact, message)
                self.assertNotRegex(message, r"(?i)Vidbyte\W?s own")
        # A served primary keeps the clause. The default mode is used, where the clause is true; DIRECT also keeps it (an accepted limitation), so DIRECT is not asserted either way.
        served = {
            "TextModelConfig": lambda: TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_XAI]),
            "Agent": lambda: Agent(name="a", system_prompt="s", provider="openai", model_name="gpt-5.5", api_keys=[K_XAI], vidbyte_api_key=VIDBYTE_KEY),
        }
        for root, build in served.items():
            with self.subTest(root=root, primary="openai"), patch.dict(os.environ, {}, clear=True):
                message, details = self.refused(build, K_XAI, VIDBYTE_KEY)
                self.assertEqual(details.get("provider"), "openai")
                self.assertIn("Vidbyte's own openai account", message)

    def test_require_primary_key_off_accepts_a_list_without_the_primarys_key(self) -> None:
        # D-30: only BaseAgent.restore turns the check off, for a fork child resumed with its own key.
        record = matcher().match([K_OPENAI], primary="deepseek", others=("openai",), require_primary_key=False)
        self.assertEqual(key_view(record)[0], {"openai": K_OPENAI})

    def test_the_record_keeps_the_matched_names_deduplicated_in_order(self) -> None:
        # D-30, section 9.2 step 5: names only, normalized and without repeats, so a restore re-matches the same way.
        record = matcher().match([], primary=(ModelProvider.DEEPSEEK, "openai", "deepseek"), others=["kimi", "kimi"])
        self.assertEqual(key_view(record)[2], ("deepseek", "openai"))
        self.assertEqual(key_view(record)[3], ("kimi",))


class VidbyteEntryTests(KeySafeAssertions):
    """INV-13, INV-26, D-25, EC-8, EC-19, EC-20, EC-51, AC-35: the Vidbyte key in the list and beside it."""

    def test_a_vidbyte_entry_is_the_vidbyte_key_and_never_a_provider_key(self) -> None:
        # EC-8, D-25: the README habit "pass a Vidbyte key as api_key" stays a pure rename.
        record = matcher().match([VIDBYTE_KEY, K_XAI], primary="xai")
        self.assertEqual(record.vidbyte_api_key, VIDBYTE_KEY)
        self.assertEqual(key_view(record)[0], {"xai": K_XAI})
        self.assertNotIn(VIDBYTE_KEY, record.keys)
        self.assertEqual(matcher().match([VIDBYTE_KEY], primary="xai", vidbyte_api_key=VIDBYTE_KEY).vidbyte_api_key, VIDBYTE_KEY)
        config = TextModelConfig(provider="xai", model="grok-4.5", api_keys=[VIDBYTE_KEY, K_XAI])
        self.assertEqual(config.vidbyte_api_key, VIDBYTE_KEY)

    def test_two_different_vidbyte_keys_are_refused_naming_their_indexes(self) -> None:
        # EC-51, M-5: an entry against the explicit key, or two entries against each other.
        message, details = self.refused(lambda: matcher().match([K_XAI, OTHER_VIDBYTE_KEY], primary="xai", vidbyte_api_key=VIDBYTE_KEY), VIDBYTE_KEY, OTHER_VIDBYTE_KEY, K_XAI)
        self.assertIn("api_keys[1]", message)
        self.assertIn("vidbyte_api_key", message)
        self.assertEqual(details.get("error_kind"), CREDENTIAL_ERROR_KIND)
        message, _ = self.refused(lambda: matcher().match([VIDBYTE_KEY, K_XAI, OTHER_VIDBYTE_KEY], primary="xai"), VIDBYTE_KEY, OTHER_VIDBYTE_KEY)
        self.assertIn("api_keys[0]", message)
        self.assertIn("api_keys[2]", message)

    def test_a_malformed_explicit_vidbyte_key_is_refused_at_construction_without_reading_the_environment(self) -> None:
        # AC-35, INV-26, EC-19, M-10: the format check needs no environment, so it fails where the value enters.
        from vidbyte.lib.config import TextModelMode
        from vidbyte.lib.constants.jev import VIDBYTE_API_KEY_PREFIX

        malformed = "sk-" + "n" * 32
        short_vidbyte = VIDBYTE_API_KEY_PREFIX + "short"
        builds = {
            "Agent": lambda: Agent(name="a", system_prompt="s", provider="openai", model_name="gpt-5.5", vidbyte_api_key=malformed),
            "TextModelConfig DIRECT": lambda: TextModelConfig(provider="openai", model="gpt-5.5", vidbyte_api_key=malformed, mode=TextModelMode.DIRECT),
            "list entry": lambda: TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[short_vidbyte]),
            "ProviderKeys": lambda: __import__("vidbyte.lib.dataclasses.agents", fromlist=["ProviderKeys"]).ProviderKeys(vidbyte_api_key=malformed),
        }
        for name, build in builds.items():
            with self.subTest(root=name):
                environment = RecordingEnviron({"VIDBYTE_API_KEY": VIDBYTE_KEY})
                with patch.object(os, "environ", environment):
                    message, details = self.refused(build, malformed, short_vidbyte, VIDBYTE_KEY)
                self.assertIn("must be a live key", message)
                self.assertEqual(details.get("error_kind"), CREDENTIAL_ERROR_KIND)
                self.assertNotIn("VIDBYTE_API_KEY", environment.reads)

    def test_a_vidbyte_key_that_is_not_a_string_is_refused(self) -> None:
        # EC-20, M-11.
        for root, build in {
            "matcher": lambda: matcher().match([], primary="openai", vidbyte_api_key=123),
            "TextModelConfig": lambda: TextModelConfig(provider="openai", model="gpt-5.5", vidbyte_api_key=123),  # type: ignore[arg-type]
            "Agent": lambda: Agent(name="a", system_prompt="s", provider="openai", model_name="gpt-5.5", vidbyte_api_key=123),  # type: ignore[arg-type]
        }.items():
            with self.subTest(root=root):
                message, details = self.refused(build, "123")
                self.assertIn("vidbyte_api_key must be a string or None", message)
                self.assertEqual(details.get("error_kind"), CREDENTIAL_ERROR_KIND)


class RecordPassThroughTests(KeySafeAssertions):
    """D-13, D-31, AC-39, EC-55, M-20: a ProviderKeys passed in is checked key by key, never re-bound."""

    def test_a_matched_record_passes_through_unchanged_with_no_primary_check(self) -> None:
        # D-13: this is what makes a child's construction a pass-through.
        record = matcher().match([K_UNPROVEN, K_XAI], primary="deepseek", others=("xai",))
        self.assertEqual(matcher().match(record, primary="kimi", others=("mistral",)), record)
        self.assertEqual(matcher().match(record, primary=None), record)
        config = TextModelConfig(provider="openai", model="gpt-5.5", api_keys=record)
        self.assertEqual(config.api_keys, record)
        agent = Agent(name="a", system_prompt="s", provider="openai", model_name="gpt-5.5", api_keys=record)
        self.assertEqual(agent.runner_config.api_keys, record)

    def test_an_explicit_vidbyte_key_is_added_to_a_record_that_lacks_one_and_a_different_one_is_refused(self) -> None:
        # Section 9.2 step 1: reconcile the explicit key with the record.
        record = matcher().match([K_XAI], primary="xai")
        added = matcher().match(record, primary="xai", vidbyte_api_key=VIDBYTE_KEY)
        self.assertEqual(added.vidbyte_api_key, VIDBYTE_KEY)
        self.assertEqual(key_view(added)[0], {"xai": K_XAI})
        same = matcher().match(added, primary="xai", vidbyte_api_key=VIDBYTE_KEY)
        self.assertEqual(same, added)
        self.refused(lambda: matcher().match(added, primary="xai", vidbyte_api_key=OTHER_VIDBYTE_KEY), VIDBYTE_KEY, OTHER_VIDBYTE_KEY)

    def test_a_hand_built_record_whose_key_does_not_fit_its_provider_is_refused_at_construction(self) -> None:
        # AC-39, EC-55, T-5: a proven key at another provider, a line break, an unproven key at a format-bound provider, a non-sk key at openai.
        # INV-13 (review R-2): a Vidbyte key filed as deepseek's key would otherwise be sent to DeepSeek in DIRECT.
        from vidbyte.lib.dataclasses.agents import ProviderKeys

        records = (
            ("anthropic key at openai", ProviderKeys(providers=(ModelProvider.OPENAI,), keys=(K_ANTHROPIC,)), "openai", K_ANTHROPIC),
            ("line break", ProviderKeys(providers=(ModelProvider.DEEPSEEK,), keys=("d-a\nb",)), "deepseek", "d-a\nb"),
            ("unproven at anthropic", ProviderKeys(providers=(ModelProvider.ANTHROPIC,), keys=(K_UNPROVEN,)), "anthropic", K_UNPROVEN),
            ("non-sk at openai", ProviderKeys(providers=(ModelProvider.OPENAI,), keys=(K_UNPROVEN,)), "openai", K_UNPROVEN),
            ("vidbyte key at deepseek", ProviderKeys(providers=(ModelProvider.DEEPSEEK,), keys=(VIDBYTE_KEY,)), "deepseek", VIDBYTE_KEY),
        )
        for name, record, provider, key in records:
            for root, build in (
                ("Agent", lambda: Agent(name="a", system_prompt="s", provider="openai", model_name="gpt-5.5", api_keys=record)),
                ("TextModelConfig", lambda: TextModelConfig(provider="openai", model="gpt-5.5", api_keys=record)),
            ):
                with self.subTest(record=name, root=root):
                    message, details = self.refused(build, key)
                    self.assertIn(provider, message)
                    self.assertEqual((details.get("index"), details.get("provider")), (0, provider))
        # A valid record without the agent's own provider is accepted: no INV-24 check on a record (D-31).
        valid = ProviderKeys(providers=(ModelProvider.XAI,), keys=(K_XAI,))
        agent = Agent(name="a", system_prompt="s", provider="openai", model_name="gpt-5.5", api_keys=valid)
        self.assertEqual(agent.runner_config.api_keys, valid)

    def test_key_for_returns_the_providers_key_by_member_or_name(self) -> None:
        # Section 9.1: key_for(provider) reads by ModelProvider(provider), or returns None.
        record = matcher().match([K_XAI, K_ANTHROPIC], primary="xai", others=("anthropic",))
        self.assertEqual(record.key_for(ModelProvider.XAI), K_XAI)
        self.assertEqual(record.key_for("anthropic"), K_ANTHROPIC)
        self.assertIsNone(record.key_for("openai"))


class SettingsRootTests(KeySafeAssertions):
    """EC-45, EC-58, D-24, D-27: the settings records that hold a list."""

    def test_text_config_stores_its_list_as_a_record(self) -> None:
        # EC-45: a list becomes a ProviderKeys, so the frozen config stays immutable.
        from vidbyte.lib.dataclasses.agents import ProviderKeys

        config = TextModelConfig(provider="xai", model="grok-4.5", api_keys=[K_XAI])
        self.assertIsInstance(config.api_keys, ProviderKeys)
        self.assertEqual(config.api_keys.key_for("xai"), K_XAI)
        self.assertEqual(key_view(config.api_keys)[2], ("xai",))

    def test_run_brief_and_role_settings_normalize_their_lists_and_check_the_vidbyte_key(self) -> None:
        # EC-34, EC-58, INV-26: these records only normalize; their agent matches the list as a root later.
        from vidbyte.agents.jev.settings import JevRunBriefSettings
        from vidbyte.paradigms.context_minimal_fanout import AgentRoleSettings

        self.assertEqual(tuple(JevRunBriefSettings(api_keys=[None, f" {K_UNPROVEN} "]).api_keys), (K_UNPROVEN,))
        role = AgentRoleSettings(name="role", provider="deepseek", model_name="deepseek-chat", api_keys=[f"{K_UNPROVEN}\n", None], vidbyte_api_key=VIDBYTE_KEY)
        self.assertEqual(tuple(role.api_keys), (K_UNPROVEN,))
        self.assertEqual(role.vidbyte_api_key, VIDBYTE_KEY)
        message, _ = self.refused(lambda: AgentRoleSettings(name="role", provider="deepseek", model_name="deepseek-chat", api_keys=["d-a\nb"]), "d-a\nb")
        self.assertIn("api_keys[0]", message)
        message, details = self.refused(lambda: AgentRoleSettings(name="role", provider="deepseek", model_name="deepseek-chat", vidbyte_api_key="sk-" + "n" * 32), "sk-" + "n" * 32)
        self.assertIn("must be a live key", message)
        self.assertEqual(details.get("error_kind"), CREDENTIAL_ERROR_KIND)

    def test_role_settings_accept_a_padded_vidbyte_key_and_store_what_agent_stores(self) -> None:
        # INV-26, D-18 (review R-14): a pasted key with surrounding spaces is the same key, so a role must not call it malformed when Agent accepts it.
        from vidbyte.paradigms.context_minimal_fanout import AgentRoleSettings

        padded = " " + VIDBYTE_KEY + " "
        with patch.dict(os.environ, {}, clear=True):
            agent = Agent(name="a", system_prompt="s", provider="deepseek", model_name="deepseek-chat", vidbyte_api_key=padded)
            role = AgentRoleSettings(name="role", provider="deepseek", model_name="deepseek-chat", vidbyte_api_key=padded)
        # Agent strips the key before it stores it; the role must store the same value.
        self.assertEqual(agent.runner_config.api_keys.vidbyte_api_key, VIDBYTE_KEY)
        self.assertEqual(role.vidbyte_api_key, agent.runner_config.api_keys.vidbyte_api_key)


if __name__ == "__main__":
    unittest.main()
