"""FILE: tests/features/decision_model_providers/test_decision_contract.py

PURPOSE: Pins the catalog half of the decision-model-providers spec: the thirteen new ModelProvider members, the sixteen-provider DECISION_DEFAULT_MODELS map, registry rows, runner catalogs, usage-class bindings, the SystemOneProvider.HOSTS table, DecisionAuthScheme, the wire records, the wire constants, factory routing, the pricebook rows, the price-proof comments in pricing.py, and the Inception/Baseten keying of Mercury Decide.
ROLE IN CODEBASE: Covers spec INV-1, INV-2 (defaults), INV-18, INV-20, INV-29, INV-30, AC-9, AC-21, AC-22, EC-36, FR-1, FR-2, FR-4, FR-10, FR-12, FR-13 and section 9.1 of docs/spec/decision-model-providers/spec.md (r8); every expectation is a literal from the spec.
ARCHITECTURE NOTE: Pure, offline, synchronous; new symbols are imported inside each test so a missing module fails one test instead of the whole collection.
COMMON MODIFICATION PATTERNS: When a provider row changes in spec section 9.1, change HOST_ROWS or R8_HOST_ROWS in decision_fixtures.py, PRICED_ROWS, and PRICE_PROOF_URLS here together.
KNOWN EDGE CASES: Cloudflare and Foundry register an empty DEFAULT_ENDPOINTS string on purpose; OpenAI's gpt-6-luna and OpenRouter's typesafe/jev-1.13 are deliberately absent from the runner catalogs and are not asserted there; the price-proof test reads pricing.py as text, so a URL wrapped across two comment lines fails it.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 6.1, 7, 8.5, 9.1; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_contract.py
"""

from __future__ import annotations

import dataclasses
import re
import unittest
from pathlib import Path

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
from vidbyte.lib.registries.pricing import PROVIDER_PRICING, ModelPricing, ModelPricingRegistry
from vidbyte.providers import ModelProviders

SIXTEEN = ("baseten", "celeris", "cloudflare", "foundry", "hanzo", "inception", "liquid", "meragpt", "nace", "openai", "openrouter", "perplexity", "typesafe", "upstage", "vansa", "zoodata")
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
R8_QUALIFIED_KEYS = (
    "celeris/celeris-1-decision",
    "nace/drex-v1.5",
    "nace/drex-v1.0",
    "upstage/solar-decide",
    "inception/mercury-decide",
    "hanzo/kai",
    "vansa/vansa-3.4",
    "zoodata/instinct",
    "zoodata/instinct-dual-4b",
    "zoodata/instinct-tuned-4b",
)
R8_BARE_KEYS = ("celeris-1-decision", "drex-v1.5", "drex-v1.0", "solar-decide", "mercury-decide", "kai", "vansa-3.4", "instinct", "instinct-dual-4b", "instinct-tuned-4b")
R8_PREFIX_KEYS = ("drex-", "vansa-")
PRICED_ROWS = (
    ("PERPLEXITY", "pplx-decider-v1.1-27b", 0.02),
    ("PERPLEXITY", "pplx-decider-v1-27b", 0.02),
    ("CLOUDFLARE", "clef", 0.24),
    ("CLOUDFLARE", "clef-flash", 0.038),
    ("FOUNDRY", "microsoft-decision-1", 0.042),
    ("OPENAI", "gpt-6-luna", 0.10),
    ("TYPESAFE", "jev-latest", 0.042),
    ("LIQUID", "d1", 0.04),
    ("MERAGPT", "sd-1", 0.04),
    ("BASETEN", "inception/mercury-decide", 0.02),
    ("CELERIS", "celeris-1-decision", 0.04),
    ("NACE", "drex-v1.5", 0.05),
    ("NACE", "drex-v1.0", 0.04),
    ("UPSTAGE", "solar-decide", 0.10),
    ("INCEPTION", "mercury-decide", 0.02),
    ("HANZO", "kai", 0.021),
    ("VANSA", "vansa-3.4", 0.034),
    ("ZOODATA", "instinct", 0.03),
    ("ZOODATA", "instinct-dual-4b", 0.01),
    ("ZOODATA", "instinct-tuned-4b", 0.01),
)
# Spec r8 section 9.1 PROVIDER_PRICING cells: the URLs the comment above each decision block must carry verbatim (INV-29).
PRICE_PROOF_URLS = {
    "TYPESAFE": ("https://docs.typesafe.ai/models.md", "https://docs.typesafe.ai/api.md#response-body"),
    "PERPLEXITY": ("https://docs.perplexity.ai/docs/getting-started/pricing", "https://docs.perplexity.ai/api-reference/decisions-post"),
    "OPENROUTER": ("https://openrouter.ai/typesafe/jev-1.13/pricing",),
    "LIQUID": ("https://www.liquid.ai/blog/d1-decision-model", "https://docs.liquid.ai/lfm/models/d1"),
    "BASETEN": ("https://docs.inceptionlabs.ai/get-started/models", "https://docs.inceptionlabs.ai/capabilities/decisions", "https://www.baseten.co/pricing/", "https://www.baseten.co/library/mercury-decide/"),
    "MERAGPT": ("https://meragpt.com/docs/models", "https://meragpt.com/models/decider-1", "https://meragpt.com/#pricing"),
    "CLOUDFLARE": ("https://developers.cloudflare.com/workers-ai/platform/pricing/", "https://developers.cloudflare.com/workers-ai/models/clef/"),
    "FOUNDRY": (
        "https://prices.azure.com/api/retail/prices?$filter=productName%20eq%20%27Microsoft%20Decision%20Models%27",
        "https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742",
    ),
    "CELERIS": ("https://docs.celeris.ai/pricing.md",),
    "NACE": ("https://console.nace.ai/docs/drex/reference/pricing", "https://console.nace.ai/docs/drex/reference/models"),
    "UPSTAGE": ("https://console.upstage.ai/docs/models/solar-decide",),
    "INCEPTION": ("https://docs.inceptionlabs.ai/get-started/models", "https://docs.inceptionlabs.ai/capabilities/decisions"),
    "HANZO": ("https://hanzo.ai/pricing", "https://docs.hanzo.ai/docs/decisions"),
    "VANSA": ("https://vansa.org/pricing",),
    "ZOODATA": ("https://instinct.zoowork.ai/docs/",),
}
LUNA_PROOF_URLS = ("https://developers.openai.com/api/docs/guides/decisions", "https://developers.openai.com/api/docs/models/gpt-6-luna")
PRICES_RETRIEVED = "2026-10-10"
LUNA_PRICING = ModelPricing(input_per_million=0.10, output_per_million=0.0, threshold_tokens=272_000, input_over_threshold_per_million=0.20, output_over_threshold_per_million=0.0)
WIRE_CONSTANTS = {
    "PERPLEXITY_DECISIONS_PATH": "/decisions",
    "BASETEN_DECISIONS_PATH": "/decisions",
    "CLOUDFLARE_CLEF_PATH": "/run/@cf/cloudflare/clef",
    "FOUNDRY_SYSTEMONE_PATH": "/providers/microsoft/v1/systemone",
    "OPENAI_DECISIONS_PATH": "/decisions",
    "OPENAI_DECISIONS_PREDICATE_TYPE": "predicate",
    "OPENAI_DECISIONS_REFUSAL_TYPE": "refusal",
}


def _comment_block_above(lines: list[str], opening: re.Pattern[str]) -> tuple[int, str]:
    # Counts the PROVIDER_PRICING lines matching `opening` and returns the contiguous `#` lines directly above the first one.
    start = next(index for index, line in enumerate(lines) if line.startswith("PROVIDER_PRICING"))
    end = next(index for index in range(start, len(lines)) if lines[index] == "}")
    matches = [index for index in range(start, end) if opening.match(lines[index])]
    if not matches:
        return 0, ""
    above: list[str] = []
    index = matches[0] - 1
    while lines[index].lstrip().startswith("#"):
        above.insert(0, lines[index].strip())
        index -= 1
    return len(matches), "\n".join(above)


class ProviderCatalogTests(unittest.TestCase):
    """Pins the enum members, registry maps, runner catalogs, and usage bindings of spec section 9.1."""

    def test_supported_set_is_the_sixteen_keys_of_the_decision_default_map(self) -> None:
        # [Hidden Assumption] INV-1/AC-9/EC-26: the support set derives from DECISION_DEFAULT_MODELS, so the two can never drift (r8: sixteen providers).
        defaults = ProviderModelRegistry.DECISION_DEFAULT_MODELS
        self.assertEqual(DECISION_SUPPORTED_PROVIDERS, frozenset(defaults))
        self.assertEqual(tuple(sorted(provider.value for provider in DECISION_SUPPORTED_PROVIDERS)), SIXTEEN)
        self.assertEqual(len(defaults), 16)

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

    def test_r8_members_join_the_registry_with_their_section_9_1_rows(self) -> None:
        # [Silent Failure] FR-1/INV-2/INV-20/D-19: each r8 vendor is a full member: lowercase value, decision default, env var, endpoint, text default, JevUsage, AUTO modality.
        for name, row in fx.R8_HOST_ROWS.items():
            with self.subTest(provider=name):
                member = fx.provider_member(name)
                self.assertEqual(member.value, name.lower())
                self.assertIs(ModelProvider(name.lower()), member)
                self.assertIn(name.lower(), ProviderModelRegistry.get_supported_providers())
                self.assertEqual(ProviderModelRegistry.DECISION_DEFAULT_MODELS[member], row.default_model)
                self.assertEqual(ProviderModelRegistry.decision_default_model(member.value), row.default_model)
                self.assertEqual(ProviderModelRegistry.API_KEY_ENV_VARS[member], row.env_var)
                self.assertEqual(ProviderModelRegistry.DEFAULT_ENDPOINTS[member], row.base_url)
                self.assertEqual(ProviderModelRegistry.DEFAULT_PROVIDER_MODELS[member], row.default_model)
                self.assertIs(member.usage_class(), JevUsage)
                self.assertIs(ModalityDetector.detect_modality(row.default_model), ModelModality.AUTO)

    def test_runner_catalogs_mark_the_r8_decision_ids_as_decision(self) -> None:
        # [Hidden Failure] INV-20/FR-1/section 8.5: an uncatalogued r8 id would be refused by strict agent validation or run as a text model.
        for key in R8_QUALIFIED_KEYS:
            with self.subTest(qualified=key):
                self.assertEqual(MODEL_PROVIDER_RUNNER_TYPE_MAP.get(key), RUNNER_TYPE_DECISION)
        for key in R8_BARE_KEYS:
            with self.subTest(bare=key):
                self.assertEqual(MODEL_RUNNER_TYPE_MAP.get(key), RUNNER_TYPE_DECISION)
        for name in fx.R8_MEMBERS:
            with self.subTest(provider=name.lower()):
                self.assertEqual(PROVIDER_DEFAULT_RUNNER_TYPE_MAP.get(name.lower()), RUNNER_TYPE_DECISION)
        for key in R8_PREFIX_KEYS:
            with self.subTest(prefix=key):
                self.assertEqual(MODEL_PREFIX_RUNNER_TYPE_MAP.get(key), RUNNER_TYPE_DECISION)

    def test_inception_and_baseten_resolve_to_their_own_provider(self) -> None:
        # [Hidden Failure] AC-22/INV-30/D-20: one model under two ids must stay two providers, or a Baseten caller is validated and billed as Inception.
        self.assertEqual(ProviderModelRegistry.provider_for_model("inception/mercury-decide"), "baseten")
        self.assertEqual(ProviderModelRegistry.provider_for_model("mercury-decide"), "inception")
        self.assertIsNone(ProviderModelRegistry.validate_provider_model_pair(ModelProvider.BASETEN, "inception/mercury-decide"))
        self.assertIsNone(ProviderModelRegistry.validate_provider_model_pair(fx.provider_member("INCEPTION"), "mercury-decide"))
        with self.assertRaises(ConfigurationError) as caught:
            ProviderModelRegistry.validate_provider_model_pair(ModelProvider.BASETEN, "mercury-decide")
        self.assertEqual(caught.exception.message, "Model 'mercury-decide' is registered under provider 'inception', not 'baseten'.")
        # [Hidden Assumption] INV-30: provider_for_model returns the first insertion-order match, so Baseten's qualified key must come first.
        qualified = list(MODEL_PROVIDER_RUNNER_TYPE_MAP)
        self.assertLess(qualified.index("baseten/inception/mercury-decide"), qualified.index("inception/mercury-decide"))
        for name in ("BASETEN", *fx.R8_MEMBERS):
            with self.subTest(provider=name):
                self.assertIsNone(ProviderModelRegistry.validate_provider_model_pair(fx.provider_member(name), fx.ALL_HOST_ROWS[name].default_model))


class HostTableTests(unittest.TestCase):
    """Pins SystemOneProvider.HOSTS, the auth scheme enum, the wire records, and the wire constants."""

    def test_hosts_table_matches_section_9_1(self) -> None:
        # [Silent Failure] D-4/INV-27: one wrong flag sends criteria to the wrong host or prices the wrong id.
        from vidbyte.lib.dataclasses.jev import SystemOneHost
        from vidbyte.providers.systemone import SystemOneProvider

        hosts = SystemOneProvider.HOSTS
        expected_members = {fx.provider_member(name) for name in fx.ALL_HOST_ROWS if name != "OPENAI"}
        self.assertEqual(set(hosts), expected_members)
        self.assertEqual(len(hosts), 15)
        for name, row in fx.ALL_HOST_ROWS.items():
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

    def test_factory_routes_the_r8_providers_to_system_one(self) -> None:
        # [Hidden Failure] FR-10/D-19: the seven r8 vendors are rows on SystemOneProvider, each adapter carrying its own provider identity.
        for name, row in fx.R8_HOST_ROWS.items():
            with self.subTest(provider=name):
                adapter = ModelProviders.decision(fx.decision_config(name))
                self.assertEqual(type(adapter).__name__, row.adapter)
                self.assertIs(adapter.provider, fx.provider_member(name))

    def test_pricebook_rows_and_freshness_stamp(self) -> None:
        # [Silent Failure] FR-4/INV-18: every decision default resolves to its first-party rate; sibling ids get their own rows; only OpenRouter's block stays empty (usage.cost wins).
        from vidbyte.lib.registries.pricing import PRICING_AS_OF

        self.assertEqual(PRICING_AS_OF, "2026-10-10")
        registry = ModelPricingRegistry.default()
        for name, model, input_rate in PRICED_ROWS:
            with self.subTest(provider=name, model=model):
                pricing = registry.resolve(fx.provider_member(name), model)
                self.assertIsNotNone(pricing)
                self.assertEqual((pricing.input_per_million, pricing.output_per_million), (input_rate, 0.0))
        with self.subTest(provider="OPENAI", tier="gpt-6-luna"):
            luna = registry.resolve(ModelProvider.OPENAI, "gpt-6-luna")
            self.assertEqual((luna.threshold_tokens, luna.input_over_threshold_per_million, luna.output_over_threshold_per_million), (272_000, 0.20, 0.0))
        for name, row in fx.ALL_HOST_ROWS.items():
            with self.subTest(default=name):
                member = fx.provider_member(name)
                if name == "OPENROUTER":
                    self.assertEqual(PROVIDER_PRICING[member], {})
                    continue
                self.assertNotEqual(PROVIDER_PRICING[member], {})
                self.assertIsNotNone(registry.resolve(member, row.default_model))

    def test_every_decision_price_row_cites_its_first_party_urls(self) -> None:
        # [Silent Failure] AC-21/INV-29/NFR-6: a rate whose comment lacks the vendor's own URL and the retrieval date cannot be audited against the price that vendor serves.
        import vidbyte.lib.registries.pricing as pricing

        lines = Path(pricing.__file__).read_text(encoding="utf-8").splitlines()
        for name, urls in PRICE_PROOF_URLS.items():
            with self.subTest(provider=name):
                found, comment = _comment_block_above(lines, re.compile(rf"^\s*ModelProvider\.{name}:\s*\{{"))
                self.assertEqual(found, 1, f"expected one PROVIDER_PRICING block for {name}")
                self.assertNotEqual(comment, "", f"no comment directly above the {name} block")
                for url in urls:
                    self.assertIn(url, comment)
                self.assertIn(PRICES_RETRIEVED, comment)
                if name in ("INCEPTION", "BASETEN"):
                    # [Edge Case] EC-36: the 0.02 Mercury Decide rate is promotional, and both comments must say so.
                    self.assertIn("promotional", comment.lower())
        with self.subTest(provider="OPENAI", row="gpt-6-luna"):
            found, comment = _comment_block_above(lines, re.compile(r'^\s*"gpt-6-luna":'))
            self.assertEqual(found, 1)
            for url in LUNA_PROOF_URLS:
                self.assertIn(url, comment)
            self.assertIn(PRICES_RETRIEVED, comment)
        self.assertNotEqual(PROVIDER_PRICING[ModelProvider.BASETEN], {})
        self.assertEqual(PROVIDER_PRICING[ModelProvider.OPENAI]["gpt-6-luna"], LUNA_PRICING)


if __name__ == "__main__":
    unittest.main()
