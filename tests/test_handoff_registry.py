from __future__ import annotations

import json
import unittest

import vidbyte
from vidbyte import (
    APIDesignHandoff,
    ArchitectureDecisionHandoff,
    BugFixHandoff,
    CICDPipelineHandoff,
    CodeReviewHandoff,
    CodebaseOnboardingHandoff,
    DependencyUpgradeHandoff,
    Handoff,
    HandoffRegistry,
    IncidentResponseHandoff,
    IntegrationHandoff,
    PerformanceOptimizationHandoff,
    RefactorHandoff,
    ReleaseHandoff,
    SchemaMigrationHandoff,
    SecurityRemediationHandoff,
    TestAuthoringHandoff,
)
from vidbyte.agents import HandoffAgent
from vidbyte.context.primitives import ContextItem
from vidbyte.lib.errors import ConfigurationError

SWE_VARIANTS = [
    CodeReviewHandoff,
    BugFixHandoff,
    RefactorHandoff,
    PerformanceOptimizationHandoff,
    TestAuthoringHandoff,
    APIDesignHandoff,
    SchemaMigrationHandoff,
    DependencyUpgradeHandoff,
    IncidentResponseHandoff,
    ArchitectureDecisionHandoff,
    CodebaseOnboardingHandoff,
    CICDPipelineHandoff,
    IntegrationHandoff,
    SecurityRemediationHandoff,
    ReleaseHandoff,
]


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class SectionRunner:
    """Fake runner that finishes by emitting a markdown body of the given spec's sections."""

    def __init__(self, spec: Handoff) -> None:
        self.body = "\n\n".join(f"## {title}\n[content for {title}]" for title in spec.section_titles())

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> FakeResponse:
        arguments = json.dumps({"final_answer": self.body})
        return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": arguments}]})


class CustomHandoff(Handoff):
    DEFAULT_TITLE = "Custom Handoff"

    def default_sections(self) -> dict[str, str]:
        return {"Only": "the only section"}


class SweVariantTests(unittest.TestCase):
    def test_every_swe_variant_has_non_empty_sections(self) -> None:
        for cls in SWE_VARIANTS:
            with self.subTest(variant=cls.__name__):
                self.assertTrue(cls().sections)

    def test_all_prebuilt_section_maps_are_pairwise_distinct(self) -> None:
        registry = HandoffRegistry()
        maps = [tuple(cls().sections.items()) for cls in registry.all().values()]
        self.assertEqual(len(maps), len(registry.all()))
        self.assertEqual(len(maps), len(set(maps)))

    def test_fill_preserves_each_swe_subclass(self) -> None:
        for cls in SWE_VARIANTS:
            with self.subTest(variant=cls.__name__):
                self.assertIsInstance(cls().fill({"x": "y"}), cls)

    def test_every_swe_variant_is_context_item_with_non_default_title(self) -> None:
        for cls in SWE_VARIANTS:
            with self.subTest(variant=cls.__name__):
                self.assertIsInstance(cls(), ContextItem)
                self.assertNotEqual(cls().title, "Handoff")

    def test_default_sections_returns_fresh_dict_per_instance(self) -> None:
        first = BugFixHandoff()
        first.sections["Root Cause"] = "mutated"
        self.assertNotEqual(BugFixHandoff().sections["Root Cause"], "mutated")


class HandoffRegistryTests(unittest.TestCase):
    def test_list_matches_catalog_and_contains_known_slug(self) -> None:
        registry = HandoffRegistry()
        self.assertEqual(len(registry.list()), len(registry.all()))
        self.assertEqual(len(registry.list()), len(set(registry.list())))
        self.assertIn("code_review", registry.list())

    def test_get_returns_matching_class(self) -> None:
        registry = HandoffRegistry()
        self.assertIs(registry.get("code_review"), CodeReviewHandoff)
        self.assertIs(registry.get("release"), ReleaseHandoff)
        self.assertIs(registry.get("security_remediation"), SecurityRemediationHandoff)

    def test_get_unknown_raises_configuration_error(self) -> None:
        with self.assertRaises(ConfigurationError):
            HandoffRegistry().get("does_not_exist")

    def test_create_returns_instance_of_right_type(self) -> None:
        self.assertIsInstance(HandoffRegistry().create("bug_fix"), BugFixHandoff)

    def test_register_then_get_and_create_normalizes_case(self) -> None:
        registry = HandoffRegistry()
        registry.register("  My_Custom  ", CustomHandoff)
        self.assertIs(registry.get("my_custom"), CustomHandoff)
        self.assertIsInstance(registry.create("MY_CUSTOM"), CustomHandoff)

    def test_register_overrides_existing_slug(self) -> None:
        registry = HandoffRegistry()
        registry.register("bug_fix", CustomHandoff)
        self.assertIs(registry.get("bug_fix"), CustomHandoff)

    def test_describe_returns_class_title_and_sections_for_every_slug(self) -> None:
        registry = HandoffRegistry()
        described = registry.describe()
        self.assertEqual(len(described), len(registry.all()))
        for slug, info in described.items():
            with self.subTest(slug=slug):
                self.assertTrue(info["class"])
                self.assertTrue(info["title"])
                self.assertTrue(info["sections"])
        self.assertEqual(described["code_review"]["title"], "Code Review Handoff")
        self.assertIn("Verdict", described["code_review"]["sections"])

    def test_all_returns_copy_that_does_not_mutate_registry(self) -> None:
        registry = HandoffRegistry()
        registry.all()["bug_fix"] = CustomHandoff
        self.assertIs(registry.get("bug_fix"), BugFixHandoff)

    def test_two_instances_are_independent(self) -> None:
        a = HandoffRegistry()
        b = HandoffRegistry()
        a.register("custom", CustomHandoff)
        self.assertIn("custom", a.list())
        self.assertNotIn("custom", b.list())

    def test_describe_reflects_freshly_registered_handoff(self) -> None:
        registry = HandoffRegistry()
        registry.register("custom", CustomHandoff)
        self.assertEqual(registry.describe()["custom"]["title"], "Custom Handoff")

    def test_same_registry_object_from_root_and_registries_namespace(self) -> None:
        from vidbyte.lib.registries import HandoffRegistry as RegHandoffRegistry
        self.assertIs(vidbyte.HandoffRegistry, RegHandoffRegistry)


class HandoffRegistryAgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_agent_produces_filled_handoff_of_named_type(self) -> None:
        registry = HandoffRegistry()
        spec = registry.create("cicd_pipeline")
        agent = registry.build_agent("cicd_pipeline", runner=SectionRunner(spec))
        self.assertIsInstance(agent, HandoffAgent)
        doc = await agent.generate_handoff("the run digest")
        self.assertIsInstance(doc, CICDPipelineHandoff)
        self.assertTrue(doc.is_filled)
        # Punctuated titles must map to the right sections, not get mangled.
        self.assertEqual(doc.sections["Build/Deploy Config"], "[content for Build/Deploy Config]")


if __name__ == "__main__":
    unittest.main()
