from __future__ import annotations

import importlib
import unittest

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import (
    Prompts,
    chain_of_thought_reason_prompt,
    goals_goal_prompt,
    mimic_behavior_mimic_prompt,
)


class PromptsInterfaceTests(unittest.TestCase):
    def test_get_accepts_prompt_enum_and_returns_text(self) -> None:
        prompts = Prompts()

        self.assertEqual(prompts.get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT), chain_of_thought_reason_prompt)
        self.assertIsInstance(chain_of_thought_reason_prompt, str)
        self.assertEqual(prompts.get(Prompt.GOALS_GOAL_PROMPT), goals_goal_prompt)
        self.assertEqual(prompts.get(Prompt.MIMIC_BEHAVIOR_MIMIC_PROMPT), mimic_behavior_mimic_prompt)

    def test_get_rejects_string_keys(self) -> None:
        with self.assertRaises(TypeError):
            Prompts().get("chain_of_thought.reason_prompt")  # type: ignore[arg-type]

    def test_keys_and_descriptions_are_enum_keyed(self) -> None:
        prompts = Prompts()

        self.assertEqual(set(prompts.keys()), set(Prompt))
        self.assertEqual(set(prompts.descriptions()), set(Prompt))
        self.assertTrue(all(description for description in prompts.descriptions().values()))

    def test_all_direct_import_names_are_exported(self) -> None:
        prompt_module = importlib.import_module("vidbyte.prompts")
        prompts = Prompts()

        for prompt_key, import_name in prompts.import_names().items():
            self.assertIn(import_name, prompt_module.__all__)
            self.assertEqual(getattr(prompt_module, import_name), prompts.get(prompt_key))

    def test_prompts_has_no_override_or_tool_call_surface(self) -> None:
        prompts = Prompts()

        self.assertFalse(hasattr(prompts, "override"))
        self.assertFalse(hasattr(prompts, "tool_call"))
        self.assertFalse(hasattr(prompts, "tools"))


if __name__ == "__main__":
    unittest.main()
