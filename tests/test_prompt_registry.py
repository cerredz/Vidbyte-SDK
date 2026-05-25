from __future__ import annotations

import re
import unittest

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts
from vidbyte.prompts.strategies import ChainOfThoughtPrompts


class PromptCatalogTests(unittest.TestCase):
    def test_strategy_prompts_load_from_prompt_catalog(self) -> None:
        prompts = Prompts()

        self.assertIn(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT, prompts.keys())
        self.assertEqual(ChainOfThoughtPrompts().export(), prompts.family("chain_of_thought"))

    def test_prompt_values_are_coherent_sentence_blocks(self) -> None:
        prompts = Prompts()
        long_form_prompts = {
            Prompt.GOALS_GOAL_PROMPT,
            Prompt.MIMIC_BEHAVIOR_MIMIC_PROMPT,
            Prompt.PROMPT_ENGINEERING_MASTER_PROMPT,
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

        self.assertIn("You emulate a goal-driven work loop.", goal_prompt)
        self.assertIn("You create prompts that mimic the observable behavior", mimic_prompt)
        self.assertIn("goal_prompt", prompts.family("goals"))
        self.assertIn("mimic_prompt", prompts.family("mimic_behavior"))


if __name__ == "__main__":
    unittest.main()
