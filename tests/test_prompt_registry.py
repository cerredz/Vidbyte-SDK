# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Unit tests for prompt catalog loading, file mapping, and strategy exports.
# Purpose: Ensures JSON-backed prompt configurations and Markdown assets parse correctly without regressions.
# Architecture & Functions:
#   - PromptCatalogTests (unittest.TestCase): Asserts strategy mapping, sentence cohesion, and markdown loaders.
# Codebase Relation:
#   - Validates correct alignment between disk assets, Prompt enums, and runtime accessors.
# Similar Files:
#   - tests/test_prompts_interface.py (tests public API surfaces)
# ==============================================================================

from __future__ import annotations

import re
import unittest

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts
from vidbyte.prompts.strategies import ChainOfThoughtPrompts, PromptTemplatesPrompts


class PromptCatalogTests(unittest.TestCase):
    def test_strategy_prompts_load_from_prompt_catalog(self) -> None:
        prompts = Prompts()

        self.assertIn(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT, prompts.keys())
        self.assertEqual(ChainOfThoughtPrompts().export(), prompts.family("chain_of_thought"))
        self.assertEqual(PromptTemplatesPrompts().export(), prompts.family("templates"))

    def test_prompt_values_are_coherent_sentence_blocks(self) -> None:
        prompts = Prompts()
        long_form_prompts = {
            Prompt.GOALS_GOAL_PROMPT,
            Prompt.MIMIC_BEHAVIOR_MIMIC_PROMPT,
            Prompt.PROMPT_ENGINEERING_MASTER_PROMPT,
            Prompt.TEMPLATES_INTENT_BASED,
            Prompt.TEMPLATES_PERSONA,
            Prompt.TEMPLATES_SPECIFICATION,
            Prompt.ACTOR_RUNTIME_EXPLORER,
            Prompt.ACTOR_RUNTIME_DECOMPOSER,
            Prompt.ACTOR_RUNTIME_EVALUATOR,
        }

        for key, prompt in prompts.all().items():
            sentence_count = len(re.findall(r"[.!?]", prompt))
            self.assertGreaterEqual(sentence_count, 4)
            if key not in long_form_prompts:
                self.assertLessEqual(sentence_count, 10)

    def test_markdown_backed_prompts_load_as_text(self) -> None:
        prompts = Prompts()

        goal_prompt = prompts.get(Prompt.GOALS_GOAL_PROMPT)
        mimic_prompt = prompts.get(Prompt.MIMIC_BEHAVIOR_MIMIC_PROMPT)
        intent_based_template = prompts.get(Prompt.TEMPLATES_INTENT_BASED)
        persona_template = prompts.get(Prompt.TEMPLATES_PERSONA)
        specification_template = prompts.get(Prompt.TEMPLATES_SPECIFICATION)

        self.assertIn("You emulate a goal-driven work loop.", goal_prompt)
        self.assertIn("You create prompts that mimic the observable behavior", mimic_prompt)
        self.assertIn("specializing in **Intent-Based Prompting**", intent_based_template)
        self.assertIn("specializing in **Persona Prompting**", persona_template)
        self.assertIn("specializing in **Specification Prompting**", specification_template)

        self.assertIn("goal_prompt", prompts.family("goals"))
        self.assertIn("mimic_prompt", prompts.family("mimic_behavior"))
        self.assertIn("intent_based", prompts.family("templates"))
        self.assertIn("persona", prompts.family("templates"))
        self.assertIn("specification", prompts.family("templates"))


if __name__ == "__main__":
    unittest.main()
