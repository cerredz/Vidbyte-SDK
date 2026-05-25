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

        for prompt in prompts.all().values():
            sentence_count = len(re.findall(r"[.!?]", prompt))
            self.assertGreaterEqual(sentence_count, 4)
            self.assertLessEqual(sentence_count, 300)


if __name__ == "__main__":
    unittest.main()
