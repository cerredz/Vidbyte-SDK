from __future__ import annotations

import json
import unittest

import vidbyte
from vidbyte import (
    ContextWindowHandoff,
    Handoff,
    HandoffRegistry,
    PatientHandoff,
    ThreatHuntHandoff,
)
from vidbyte.agents import HandoffAgent
from vidbyte.context.primitives import ContextItem

DOMAIN_SLUGS = [
    "patient", "care_transition", "diagnostic_workup",
    "contract_review", "legal_research", "due_diligence",
    "ticket_escalation", "account_health",
    "alert_triage", "threat_hunt",
    "investment_thesis", "deal", "credit_analysis",
]
AGENT_SLUGS = [
    "context_window", "tool_trajectory", "sub_agent_delegation", "orchestration",
    "human_escalation", "checkpoint_resume", "deep_research", "retrieval",
    "browser_session", "computer_use", "memory", "verification",
    "reasoning_trace", "guardrail", "evaluation",
]
NEW_SLUGS = DOMAIN_SLUGS + AGENT_SLUGS


def _registry() -> HandoffRegistry:
    # Construct a fresh registry instance for a test.
    return HandoffRegistry()


def _new_classes() -> list[type[Handoff]]:
    # Resolve every new pack class through the registry.
    registry = _registry()
    return [registry.get(slug) for slug in NEW_SLUGS]


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


class NewPackStructureTests(unittest.TestCase):
    def test_every_new_variant_has_non_empty_sections(self) -> None:
        for cls in _new_classes():
            with self.subTest(variant=cls.__name__):
                self.assertTrue(cls().sections)

    def test_full_catalog_section_maps_are_pairwise_distinct(self) -> None:
        registry = _registry()
        maps = [tuple(cls().sections.items()) for cls in registry.all().values()]
        self.assertEqual(len(maps), len(set(maps)))

    def test_fill_preserves_each_new_subclass(self) -> None:
        for cls in _new_classes():
            with self.subTest(variant=cls.__name__):
                self.assertIsInstance(cls().fill({"x": "y"}), cls)

    def test_every_new_variant_is_context_item_with_non_default_title(self) -> None:
        for cls in _new_classes():
            with self.subTest(variant=cls.__name__):
                self.assertIsInstance(cls(), ContextItem)
                self.assertNotEqual(cls().title, "Handoff")

    def test_default_sections_returns_fresh_dict_per_instance(self) -> None:
        for cls in (PatientHandoff, ContextWindowHandoff):
            with self.subTest(variant=cls.__name__):
                first = cls()
                key = next(iter(first.sections))
                first.sections[key] = "mutated"
                self.assertNotEqual(cls().sections[key], "mutated")


class NewPackRegistryTests(unittest.TestCase):
    def test_registry_contains_every_new_slug(self) -> None:
        slugs = set(_registry().list())
        for slug in NEW_SLUGS:
            with self.subTest(slug=slug):
                self.assertIn(slug, slugs)

    def test_registry_totals_56(self) -> None:
        self.assertEqual(len(_registry().list()), 56)

    def test_create_returns_right_type_for_domain_and_agent(self) -> None:
        self.assertIsInstance(_registry().create("patient"), PatientHandoff)
        self.assertIsInstance(_registry().create("context_window"), ContextWindowHandoff)

    def test_describe_includes_every_new_slug_with_sections(self) -> None:
        described = _registry().describe()
        for slug in NEW_SLUGS:
            with self.subTest(slug=slug):
                self.assertTrue(described[slug]["title"])
                self.assertTrue(described[slug]["sections"])

    def test_deep_research_does_not_collide_with_research(self) -> None:
        registry = _registry()
        self.assertIsNot(registry.get("deep_research"), registry.get("research"))

    def test_new_slugs_same_object_from_both_namespaces(self) -> None:
        import vidbyte.context as ctx
        for cls in _new_classes():
            with self.subTest(variant=cls.__name__):
                self.assertIs(getattr(vidbyte, cls.__name__), getattr(ctx, cls.__name__))


class NewPackAgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_domain_variant_flows_through_agent(self) -> None:
        registry = _registry()
        spec = registry.create("patient")
        agent = registry.build_agent("patient", runner=SectionRunner(spec))
        doc = await agent.generate_handoff("the run digest")
        self.assertIsInstance(doc, PatientHandoff)
        self.assertEqual(doc.sections["Recommendation"], "[content for Recommendation]")

    async def test_agent_native_variant_with_punctuated_titles_parses(self) -> None:
        registry = _registry()
        spec = registry.create("context_window")
        agent = registry.build_agent("context_window", runner=SectionRunner(spec))
        doc = await agent.generate_handoff("digest")
        self.assertIsInstance(doc, ContextWindowHandoff)
        self.assertEqual(doc.sections["Compacted/Dropped Context"], "[content for Compacted/Dropped Context]")
        self.assertEqual(doc.sections["Resume Instructions"], "[content for Resume Instructions]")

    async def test_tool_trajectory_ampersand_titles_round_trip(self) -> None:
        registry = _registry()
        spec = registry.create("tool_trajectory")
        agent = registry.build_agent("tool_trajectory", runner=SectionRunner(spec))
        doc = await agent.generate_handoff("digest")
        self.assertEqual(doc.sections["Calls Made & Results"], "[content for Calls Made & Results]")
        self.assertEqual(doc.sections["Failed Calls & Errors"], "[content for Failed Calls & Errors]")


if __name__ == "__main__":
    unittest.main()
