# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Unit tests for the Prompt catalog public interfaces.
# Purpose: Ensures consistency, type safety, and export compliance for prompt retrieval APIs.
# Architecture & Functions:
#   - PromptsInterfaceTests (unittest.TestCase): Asserts key enums map to valid strings,
#     rejects invalid types, and checks dynamic module exports.
# Codebase Relation:
#   - Validates that the entire Prompts system operates cleanly and consistently.
# ==============================================================================

from __future__ import annotations

import importlib
import unittest

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import (
    Prompts,
    goals_goal_prompt,
    mimic_behavior_mimic_prompt,
    templates_intent_based,
    templates_persona,
    templates_specification,
)


class PromptsInterfaceTests(unittest.TestCase):
    def test_get_accepts_prompt_enum_and_returns_text(self) -> None:
        prompts = Prompts()

        self.assertEqual(prompts.get(Prompt.GOALS_GOAL_PROMPT), goals_goal_prompt)
        self.assertIsInstance(goals_goal_prompt, str)
        self.assertEqual(prompts.get(Prompt.MIMIC_BEHAVIOR_MIMIC_PROMPT), mimic_behavior_mimic_prompt)
        self.assertEqual(prompts.get(Prompt.TEMPLATES_INTENT_BASED), templates_intent_based)
        self.assertEqual(prompts.get(Prompt.TEMPLATES_PERSONA), templates_persona)
        self.assertEqual(prompts.get(Prompt.TEMPLATES_SPECIFICATION), templates_specification)

    def test_get_rejects_string_keys(self) -> None:
        with self.assertRaises(TypeError):
            Prompts().get("reflexion.agent_system_prompt")  # type: ignore[arg-type]

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
