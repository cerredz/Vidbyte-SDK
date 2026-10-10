"""FILE: tests/features/decision_model_providers/test_decision_contract.py

PURPOSE: Pins the catalog half of the decision-model-providers spec: the six new ModelProvider members, the nine-provider DECISION_DEFAULT_MODELS map, registry rows, runner catalogs, usage-class bindings, the SystemOneProvider.HOSTS table, DecisionAuthScheme, the wire records, the wire constants, factory routing, and the pricebook rows.
ROLE IN CODEBASE: Covers spec INV-1, INV-2 (defaults), INV-20, FR-1, FR-2, FR-4, FR-10, FR-12, FR-13 and section 9.1 of docs/spec/decision-model-providers/spec.md; every expectation is a literal from that table.
ARCHITECTURE NOTE: Pure, offline, synchronous; new symbols are imported inside each test so a missing module fails one test instead of the whole collection.
COMMON MODIFICATION PATTERNS: When a provider row changes in spec section 9.1, change HOST_ROWS in decision_fixtures.py and PRICED_ROWS here together.
KNOWN EDGE CASES: Cloudflare and Foundry register an empty DEFAULT_ENDPOINTS string on purpose; OpenAI's gpt-6-luna and OpenRouter's typesafe/jev-1.13 are deliberately absent from the runner catalogs and are not asserted there.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 6.1, 7, 8.5, 9.1; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_contract.py
"""

from __future__ import annotations

import dataclasses
import unittest

from tests.features.decision_model_providers import decision_fixtures as fx
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.constants.runners import (
    MODEL_PREFIX_RUNNER_TYPE_MAP,
    MODEL_PROVIDER_RUNNER_TYPE_MAP,
    MODEL_RUNNER_TYPE_MAP,
    PROVIDER_DEFAULT_RUNNER_TYPE_MAP,
    RUNNER_TYPE_DECISION,
)
from vidbyte.lib.dataclasses.model_configs import DECISION_SUPPORTED_PROVIDERS
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.pricing import PROVIDER_PRICING, ModelPricingRegistry
from vidbyte.providers import ModelProviders

NINE = ("baseten", "cloudflare", "foundry", "liquid", "meragpt", "openai", "openrouter", "perplexity", "typesafe")
QUALIFIED_KEYS = (
    "perplexity/pplx-decider-v1.1-27b",
    "perplexity/pplx-decider-v1-27b",
    "cloudflare/clef",
    "cloudflare/clef-flash",
    "foundry/microsoft-decision-1",
    "liquid/d1",
    "baseten/inception/mercury-decide",
    "meragpt/sd-1",
    "meragpt/state-decider-1",
)
BARE_KEYS = ("pplx-decider-v1.1-27b", "pplx-decider-v1-27b", "clef", "clef-flash", "microsoft-decision-1", "d1", "inception/mercury-decide", "mercury-decide", "sd-1", "state-decider-1")
PREFIX_KEYS = ("pplx-decider-", "microsoft-decision-", "mercury-decide")
PROVIDER_KEYS = ("perplexity", "cloudflare", "foundry", "liquid", "baseten", "meragpt")
PRICED_ROWS = (
    ("PERPLEXITY", "pplx-decider-v1.1-27b", 0.02),
    ("PERPLEXITY", "pplx-decider-v1-27b", 0.02),
    ("CLOUDFLARE", "clef", 0.24),
    ("CLOUDFLARE", "clef-flash", 0.038),
    ("FOUNDRY", "microsoft-decision-1", 0.042),
    ("OPENAI", "gpt-6-luna", 0.10),
    ("TYPESAFE", "jev-latest", 0.042),
)
UNPRICED = ("LIQUID", "BASETEN", "MERAGPT")
WIRE_CONSTANTS = {
    "PERPLEXITY_DECISIONS_PATH": "/decisions",
    "BASETEN_DECISIONS_PATH": "/decisions",
    "CLOUDFLARE_CLEF_PATH": "/run/@cf/cloudflare/clef",
    "FOUNDRY_SYSTEMONE_PATH": "/providers/microsoft/v1/systemone",
    "OPENAI_DECISIONS_PATH": "/decisions",
    "OPENAI_DECISIONS_PREDICATE_TYPE": "predicate",
    "OPENAI_DECISIONS_REFUSAL_TYPE": "refusal",
}


class ProviderCatalogTests(unittest.TestCase):
    """Pins the enum members, registry maps, runner catalogs, and usage bindings of spec section 9.1."""

    def test_supported_set_is_the_nine_keys_of_the_decision_default_map(self) -> None:
        # [Hidden Assumption] INV-1/EC-26: the support set derives from DECISION_DEFAULT_MODELS, so the two can never drift.
        defaults = ProviderModelRegistry.DECISION_DEFAULT_MODELS
        self.assertEqual(DECISION_SUPPORTED_PROVIDERS, frozenset(defaults))
        self.assertEqual(tuple(sorted(provider.value for provider in DECISION_SUPPORTED_PROVIDERS)), NINE)
        self.assertEqual(len(defaults), 9)

    def test_new_members_have_lowercase_values_and_join_every_provider_enumeration(self) -> None:
        # [Edge Case] FR-1: the value is the lowercase name, so string configs and env-var lookups agree.
        for name in fx.NEW_MEMBERS:
            with self.subTest(member=name):
                member = fx.provider_member(name)
                self.assertEqual(member.value, name.lower())
                self.assertIs(ModelProvider(name.lower()), member)
                self.assertIn(name.lower(), ProviderModelRegistry.get_supported_providers())

    def test_decision_default_models_match_the_catalog(self) -> None:
        # [Silent Failure] INV-2/FR-2: a wrong default would silently send the wrong model id to a real vendor.
        for name, row in fx.HOST_ROWS.items():
            with self.subTest(provider=name):
                member = fx.provider_member(name)
                self.assertEqual(ProviderModelRegistry.DECISION_DEFAULT_MODELS[member], row.default_model)
                self.assertEqual(ProviderModelRegistry.decision_default_model(member), row.default_model)
                self.assertEqual(ProviderModelRegistry.decision_default_model(member.value), row.default_model)

    def test_decision_default_model_rejects_a_provider_without_one(self) -> None:
        # [Hidden Failure] FR-2: a text-only provider has no decision default and must say so, not KeyError.
        with self.assertRaises(ConfigurationError) as caught:
            ProviderModelRegistry.decision_default_model(ModelProvider.ANTHROPIC)
        self.assertEqual(caught.exception.message, "No decision model registered for provider 'anthropic'.")

    def test_registry_rows_for_the_new_members(self) -> None:
        # [Silent Failure] FR-1/D-7: env var, base URL (empty for tenant hosts), and text-catalog default per member.
        for name in fx.NEW_MEMBERS:
            row = fx.HOST_ROWS[name]
            with self.subTest(provider=name):
                member = fx.provider_member(name)
                self.assertEqual(ProviderModelRegistry.API_KEY_ENV_VARS[member], row.env_var)
                expected_endpoint = "" if name in fx.TENANT_ENDPOINTS else row.base_url
                self.assertEqual(ProviderModelRegistry.DEFAULT_ENDPOINTS[member], expected_endpoint)
                self.assertEqual(ProviderModelRegistry.DEFAULT_PROVIDER_MODELS[member], row.default_model)
                self.assertIs(member.usage_class(), JevUsage)

    def test_runner_catalogs_mark_every_decision_default_as_decision(self) -> None:
        # [Hidden Failure] INV-20/D-16: an uncatalogued default would be refused by strict agent validation or run as text.
        for key in QUALIFIED_KEYS:
            with self.subTest(qualified=key):
                self.assertEqual(MODEL_PROVIDER_RUNNER_TYPE_MAP.get(key), RUNNER_TYPE_DECISION)
        for key in BARE_KEYS:
            with self.subTest(bare=key):
                self.assertEqual(MODEL_RUNNER_TYPE_MAP.get(key), RUNNER_TYPE_DECISION)
        for key in PROVIDER_KEYS:
            with self.subTest(provider=key):
                self.assertEqual(PROVIDER_DEFAULT_RUNNER_TYPE_MAP.get(key), RUNNER_TYPE_DECISION)
        for key in PREFIX_KEYS:
            with self.subTest(prefix=key):
                self.assertEqual(MODEL_PREFIX_RUNNER_TYPE_MAP.get(key), RUNNER_TYPE_DECISION)

    def test_decision_defaults_detect_as_auto_modality(self) -> None:
        # [Hidden Assumption] INV-20: AUTO keeps _resolve_from_environment from activating a decision-only provider as text.
        for name in fx.NEW_MEMBERS:
            with self.subTest(provider=name):
                default = ProviderModelRegistry.DECISION_DEFAULT_MODELS[fx.provider_member(name)]
                self.assertIs(ModalityDetector.detect_modality(default), ModelModality.AUTO)


class HostTableTests(unittest.TestCase):
    """Pins SystemOneProvider.HOSTS, the auth scheme enum, the wire records, and the wire constants."""

    def test_hosts_table_matches_section_9_1(self) -> None:
        # [Silent Failure] D-4/INV-27: one wrong flag sends criteria to the wrong host or prices the wrong id.
        from vidbyte.lib.dataclasses.jev import SystemOneHost
        from vidbyte.providers.systemone import SystemOneProvider

        hosts = SystemOneProvider.HOSTS
        expected_members = {fx.provider_member(name) for name in fx.HOST_ROWS if name != "OPENAI"}
        self.assertEqual(set(hosts), expected_members)
        self.assertEqual(len(hosts), 8)
        for name, row in fx.HOST_ROWS.items():
            if name == "OPENAI":
                continue
            with self.subTest(provider=name):
                host = hosts[fx.provider_member(name)]
                self.assertIsInstance(host, SystemOneHost)
                self.assertEqual(host.display_name, row.display_name)
                self.assertEqual(host.path, row.path)
                self.assertEqual(host.auth_scheme.value, row.auth_scheme)
                self.assertIs(host.noul_criteria_required, row.noul_criteria_required)
                self.assertIs(host.model_from_request, row.model_from_request)

    def test_system_one_host_record_validates_and_freezes(self) -> None:
        # [Edge Case] section 9.1: blank display name, relative path, or a bare string scheme are construction errors.
        from vidbyte.lib.dataclasses.jev import SystemOneHost
        from vidbyte.lib.enums.jev import DecisionAuthScheme

        host = SystemOneHost(display_name="Perplexity", path="/decisions")
        self.assertIs(host.auth_scheme, DecisionAuthScheme.BEARER)
        self.assertFalse(host.noul_criteria_required)
        self.assertFalse(host.model_from_request)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            host.path = "/other"  # type: ignore[misc]
        for kwargs in ({"display_name": " ", "path": "/decisions"}, {"display_name": "Perplexity", "path": "decisions"}, {"display_name": "Perplexity", "path": "/decisions", "auth_scheme": "Bearer"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigurationError):
                SystemOneHost(**kwargs)  # type: ignore[arg-type]

    def test_decision_auth_scheme_lives_in_the_jev_enums_and_is_re_exported(self) -> None:
        # [Hidden Assumption] D-18/FR-12: one enum object reachable from both import paths with the documented values.
        import vidbyte.lib.enums as enums
        import vidbyte.lib.enums.jev as jev_enums
        from vidbyte.lib.enums import DecisionAuthScheme as exported
        from vidbyte.lib.enums.jev import DecisionAuthScheme

        self.assertIs(exported, DecisionAuthScheme)
        self.assertEqual([member.value for member in DecisionAuthScheme], ["Bearer", "Api-Key"])
        self.assertEqual(DecisionAuthScheme.BEARER.value, "Bearer")
        self.assertEqual(DecisionAuthScheme.API_KEY.value, "Api-Key")
        self.assertIn("DecisionAuthScheme", enums.__all__)
        self.assertIn("DecisionAuthScheme", jev_enums.__all__)

    def test_openai_wire_records_validate_their_fields(self) -> None:
        # [Edge Case] FR-12: the records reject a System One type tag, blank identity, and an empty question tuple.
        import vidbyte.lib.dataclasses.jev as jev
        from vidbyte.lib.dataclasses.jev import JevOption, OpenAIDecisionsWireQuestion, OpenAIDecisionsWireRequest

        for name in ("SystemOneHost", "OpenAIDecisionsWireQuestion", "OpenAIDecisionsWireRequest"):
            self.assertIn(name, jev.__all__)
        question = OpenAIDecisionsWireQuestion(type="choice", name="team", instructions="Which team?", options=(JevOption("billing"), JevOption("support")))
        request = OpenAIDecisionsWireRequest(model="gpt-6-luna", input="state", questions=(question,))
        self.assertEqual(request.questions[0].options[1].name, "support")
        with self.assertRaises(ConfigurationError):
            OpenAIDecisionsWireQuestion(type="noul", name="refund", instructions="Refund?")
        with self.assertRaises(ConfigurationError):
            OpenAIDecisionsWireQuestion(type="predicate", name=" ", instructions="Refund?")
        with self.assertRaises(ConfigurationError):
            OpenAIDecisionsWireRequest(model="gpt-6-luna", input="state", questions=())
        with self.assertRaises(ConfigurationError):
            OpenAIDecisionsWireRequest(model=" ", input="state", questions=(question,))

    def test_wire_constants_are_declared_and_exported(self) -> None:
        # [Silent Failure] FR-13: the path literals the adapters append to each base URL.
        import vidbyte.lib.constants.jev as constants

        for name, value in WIRE_CONSTANTS.items():
            with self.subTest(constant=name):
                self.assertEqual(getattr(constants, name), value)
                self.assertIn(name, constants.__all__)


class FactoryAndPricebookTests(unittest.TestCase):
    """Pins ModelProviders.decision routing and the dated pricebook rows."""

    def test_factory_routes_each_provider_to_its_adapter(self) -> None:
        # [Hidden Failure] FR-10/D-5: every provider reaches the adapter class of its wire, carrying its own identity.
        import vidbyte.providers as providers

        self.assertIn("SystemOneProvider", providers.__all__)
        self.assertIn("OpenAIDecisionsProvider", providers.__all__)
        for name, row in fx.HOST_ROWS.items():
            with self.subTest(provider=name):
                adapter = ModelProviders.decision(fx.decision_config(name))
                self.assertEqual(type(adapter).__name__, row.adapter)
                self.assertIs(adapter.provider, fx.provider_member(name))

    def test_pricebook_rows_and_freshness_stamp(self) -> None:
        # [Silent Failure] FR-4/INV-18: priced rows carry the first-party rate; unverified vendors stay unpriced, never guessed.
        from vidbyte.lib.registries.pricing import PRICING_AS_OF

        self.assertEqual(PRICING_AS_OF, "2026-10-10")
        registry = ModelPricingRegistry.default()
        for name, model, input_rate in PRICED_ROWS:
            with self.subTest(provider=name, model=model):
                pricing = registry.resolve(fx.provider_member(name), model)
                self.assertIsNotNone(pricing)
                self.assertEqual((pricing.input_per_million, pricing.output_per_million), (input_rate, 0.0))
        for name in UNPRICED:
            with self.subTest(provider=name):
                member = fx.provider_member(name)
                self.assertEqual(PROVIDER_PRICING[member], {})
                self.assertIsNone(registry.resolve(member, fx.HOST_ROWS[name].default_model))


if __name__ == "__main__":
    unittest.main()
