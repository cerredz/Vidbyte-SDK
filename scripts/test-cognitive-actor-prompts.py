"""Context Protocol Header

Description:
    Verification script for Cognitive Actor Prompts.
Purpose:
    Executes and validates the dynamic loading of Explorer, Decomposer, and Evaluator
    prompts, ensuring perfect registration in enums and successful catalog retrieval.
Architecture:
    Independent Python test script utilizing unittest assertions to verify components.
Relations:
    Located in scripts/. Used to certify PR readiness in Phase 5.
Similar Files:
    - tests/test_prompts_interface.py: Standard prompt registry tests.
"""

from __future__ import annotations
import sys
import unittest

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts


class TestCognitiveActorPrompts(unittest.TestCase):
    """Exhaustive test suite verifying the dynamic loading and validation of cognitive actor prompts."""

    def test_prompt_enum_resolves(self) -> None:
        # [Edge Case] Verify that the three new enum keys resolve perfectly in the Prompt class.
        self.assertEqual(Prompt.ACTOR_RUNTIME_EXPLORER.value, "actor_runtime.explorer")
        self.assertEqual(Prompt.ACTOR_RUNTIME_DECOMPOSER.value, "actor_runtime.decomposer")
        self.assertEqual(Prompt.ACTOR_RUNTIME_EVALUATOR.value, "actor_runtime.evaluator")

    def test_prompt_text_loads_correctly(self) -> None:
        # [Hidden Assumption] Verify Prompts().get(...) correctly loads the complete Markdown text.
        prompts = Prompts()
        
        explorer_text = prompts.get(Prompt.ACTOR_RUNTIME_EXPLORER)
        self.assertIn("You are an Explorer actor", explorer_text)
        self.assertIn("divergent hypotheses", explorer_text)

        decomposer_text = prompts.get(Prompt.ACTOR_RUNTIME_DECOMPOSER)
        self.assertIn("You are a Decomposer actor", decomposer_text)
        self.assertIn("manageable sub-problems", decomposer_text)

        evaluator_text = prompts.get(Prompt.ACTOR_RUNTIME_EVALUATOR)
        self.assertIn("You are an Evaluator actor", evaluator_text)
        self.assertIn("objective confidence", evaluator_text)

    def test_prompt_keys_present_in_catalog(self) -> None:
        # [Silent Failure] Verify that the keys exist in Prompts().keys() and descriptions are valid.
        prompts = Prompts()
        keys = prompts.keys()
        
        self.assertIn(Prompt.ACTOR_RUNTIME_EXPLORER, keys)
        self.assertIn(Prompt.ACTOR_RUNTIME_DECOMPOSER, keys)
        self.assertIn(Prompt.ACTOR_RUNTIME_EVALUATOR, keys)

        descriptions = prompts.descriptions()
        self.assertIn("abstract cognitive problem-solving actors", descriptions[Prompt.ACTOR_RUNTIME_EXPLORER])
        self.assertIn("explorer", descriptions[Prompt.ACTOR_RUNTIME_EXPLORER].lower())


def main() -> None:
    # Run the test suite synchronously
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCognitiveActorPrompts)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
