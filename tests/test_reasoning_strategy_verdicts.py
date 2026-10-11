from __future__ import annotations

import unittest

from vidbyte.context.primitives import InstantiateContextItem, TransitivityContextItem


class ReasoningStrategyFalseVerdictTests(unittest.TestCase):
    def test_false_verdicts_render_and_blank_values_are_skipped(self) -> None:
        instantiate = InstantiateContextItem(
            primitive_id="instantiate-1",
            general_rule="Licensed and insured vendors may be paid.",
            case="Vendor X",
            applicability_conditions=("licensed", "insured"),
            conditions_met=(
                {"condition": "licensed", "satisfied": True},
                {"condition": "insured", "satisfied": False},
                {"condition": "bonded", "satisfied": "   "},
            ),
            derived_conclusion="Vendor X may not be paid.",
            scope_check="Only one condition failed.",
        )
        transitivity = TransitivityContextItem(
            primitive_id="transitivity-1",
            entities=("A", "B", "C"),
            relation="precedes",
            pairwise_links=({"from": "B", "to": "C", "holds": False},),
            derived_chain=(),
            cycle_detected="no",
            consistency="unverified",
        )

        instantiate_text = instantiate.to_context_text()
        transitivity_text = transitivity.to_context_text()

        self.assertIn("condition: insured; satisfied: False", instantiate_text)
        self.assertIn("condition: licensed; satisfied: True", instantiate_text)
        self.assertIn("condition: bonded", instantiate_text)
        self.assertNotIn("condition: bonded;", instantiate_text)
        self.assertIn("from: B; to: C; holds: False", transitivity_text)


if __name__ == "__main__":
    unittest.main()
