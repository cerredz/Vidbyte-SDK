from __future__ import annotations

import json
import unittest

import vidbyte
from vidbyte import (
    BacktrackingHandoff,
    BudgetBoundedHandoff,
    ConstraintSatisfactionHandoff,
    CoverageHandoff,
    DecompositionHandoff,
    GoalStackHandoff,
    Handoff,
    MigrationHandoff,
    RefinementLoopHandoff,
    TradeoffHandoff,
    TreeSearchHandoff,
)
from vidbyte.agents import HandoffAgent
from vidbyte.context import EngineeringHandoff, MinimalHandoff, ResearchHandoff
from vidbyte.context.primitives import ContextItem

NEW_VARIANTS = [
    TreeSearchHandoff,
    DecompositionHandoff,
    RefinementLoopHandoff,
    ConstraintSatisfactionHandoff,
    BacktrackingHandoff,
    TradeoffHandoff,
    GoalStackHandoff,
    CoverageHandoff,
    BudgetBoundedHandoff,
    MigrationHandoff,
]

ALL_PREBUILTS = NEW_VARIANTS + [EngineeringHandoff, ResearchHandoff, MinimalHandoff]


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class SectionRunner:
    """Fake runner that finishes by emitting a markdown body of the given spec's sections."""

    def __init__(self, spec: Handoff) -> None:
        body = "\n\n".join(f"## {title}\n[content for {title}]" for title in spec.section_titles())
        self.body = body

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> FakeResponse:
        arguments = json.dumps({"final_answer": self.body})
        return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": arguments}]})


class NewVariantStructureTests(unittest.TestCase):
    def test_every_variant_has_non_empty_sections(self) -> None:
        for cls in NEW_VARIANTS:
            with self.subTest(variant=cls.__name__):
                self.assertTrue(cls().sections)

    def test_all_prebuilt_section_maps_are_pairwise_distinct(self) -> None:
        maps = [tuple(cls().sections.items()) for cls in ALL_PREBUILTS]
        self.assertEqual(len(maps), len(set(maps)))

    def test_fill_preserves_each_subclass(self) -> None:
        for cls in NEW_VARIANTS:
            with self.subTest(variant=cls.__name__):
                filled = cls().fill({"x": "y"})
                self.assertIsInstance(filled, cls)

    def test_fill_marks_each_variant_filled(self) -> None:
        for cls in NEW_VARIANTS:
            with self.subTest(variant=cls.__name__):
                self.assertTrue(cls().fill({"x": "y"}).is_filled)

    def test_every_variant_is_a_context_item(self) -> None:
        for cls in NEW_VARIANTS:
            with self.subTest(variant=cls.__name__):
                self.assertIsInstance(cls(), ContextItem)

    def test_default_sections_returns_fresh_dict_per_instance(self) -> None:
        first = TreeSearchHandoff()
        first.sections["Frontier"] = "mutated"
        second = TreeSearchHandoff()
        self.assertNotEqual(second.sections["Frontier"], "mutated")

    def test_to_context_text_renders_every_section_header(self) -> None:
        handoff = TradeoffHandoff()
        text = handoff.to_context_text()
        self.assertIn(handoff.title, text)
        for title in handoff.section_titles():
            self.assertIn(f"## {title}", text)

    def test_section_brief_lists_every_section_title(self) -> None:
        handoff = ConstraintSatisfactionHandoff()
        brief = handoff.render_section_brief()
        for title in handoff.section_titles():
            self.assertIn(title, brief)

    def test_every_variant_has_distinct_non_default_title(self) -> None:
        for cls in NEW_VARIANTS:
            with self.subTest(variant=cls.__name__):
                self.assertNotEqual(cls().title, "Handoff")

    def test_each_variant_same_object_from_both_namespaces(self) -> None:
        import vidbyte.context as ctx
        for cls in NEW_VARIANTS:
            with self.subTest(variant=cls.__name__):
                self.assertIs(getattr(vidbyte, cls.__name__), getattr(ctx, cls.__name__))

    def test_explicit_sections_override_preset(self) -> None:
        handoff = ConstraintSatisfactionHandoff(sections={"Only": "x"})
        self.assertEqual(handoff.sections, {"Only": "x"})


class NewVariantAgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_variant_flows_through_handoff_agent(self) -> None:
        spec = TreeSearchHandoff()
        agent = HandoffAgent(spec, runner=SectionRunner(spec))
        doc = await agent.generate_handoff("the run digest")
        self.assertIsInstance(doc, TreeSearchHandoff)
        self.assertTrue(doc.is_filled)
        self.assertEqual(doc.sections["Frontier"], "[content for Frontier]")

    async def test_punctuated_section_titles_parse_correctly(self) -> None:
        # Titles with slashes/hyphens must still map to the right sections, not get mangled.
        for cls in (TreeSearchHandoff, ConstraintSatisfactionHandoff):
            with self.subTest(variant=cls.__name__):
                spec = cls()
                agent = HandoffAgent(spec, runner=SectionRunner(spec))
                doc = await agent.generate_handoff("digest")
                for title in spec.section_titles():
                    self.assertEqual(doc.sections[title], f"[content for {title}]")


if __name__ == "__main__":
    unittest.main()
