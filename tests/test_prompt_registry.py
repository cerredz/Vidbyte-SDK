from __future__ import annotations

import re
import unittest

from vidbyte.lib.prompts import PromptRegistry
from vidbyte.prompts.strategies import ChainOfThoughtPrompts


class PromptRegistryTests(unittest.TestCase):
    def test_strategy_prompts_load_from_json_registry(self) -> None:
        registry = PromptRegistry.default()

        self.assertIn("chain_of_thought", registry.keys())
        self.assertEqual(ChainOfThoughtPrompts().export(), registry.get("chain_of_thought"))

    def test_prompt_values_are_coherent_sentence_blocks(self) -> None:
        registry = PromptRegistry.default()

        for prompt_group in registry.all().values():
            for prompt in prompt_group.values():
                sentence_count = len(re.findall(r"[.!?]", prompt))
                self.assertGreaterEqual(sentence_count, 6)
                self.assertLessEqual(sentence_count, 8)


if __name__ == "__main__":
    unittest.main()
