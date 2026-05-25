"""Context Protocol Header

Description:
    Tests for the Reflexion prompt family loading and access.
Purpose:
    Validates prompt JSON loading, enum sync, prompt text content,
    and strategy bundle export.
"""

from __future__ import annotations

import unittest

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts
from vidbyte.prompts.strategies import ReflexionPrompts


class ReflexionPromptFamilyTests(unittest.TestCase):
    def test_family_exists(self) -> None:
        family = Prompts().family("reflexion")
        self.assertIsInstance(family, dict)
        self.assertIn("reflect_prompt", family)
        self.assertIn("agent_prompt", family)

    def test_reflect_prompt_is_non_empty(self) -> None:
        text = Prompts().get(Prompt.REFLEXION_REFLECT_PROMPT)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text.strip()), 0)

    def test_agent_prompt_is_non_empty(self) -> None:
        text = Prompts().get(Prompt.REFLEXION_AGENT_PROMPT)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text.strip()), 0)

    def test_reflect_prompt_contains_placeholders(self) -> None:
        text = Prompts().get(Prompt.REFLEXION_REFLECT_PROMPT)
        self.assertIn("{question}", text)
        self.assertIn("{scratchpad}", text)

    def test_agent_prompt_contains_placeholders(self) -> None:
        text = Prompts().get(Prompt.REFLEXION_AGENT_PROMPT)
        self.assertIn("{reflections}", text)
        self.assertIn("{question}", text)
        self.assertIn("{scratchpad}", text)

    def test_reflect_prompt_formatting(self) -> None:
        text = Prompts().get(Prompt.REFLEXION_REFLECT_PROMPT)
        formatted = text.format(question="What is X?", scratchpad="Thought: Y")
        self.assertIn("What is X?", formatted)
        self.assertIn("Thought: Y", formatted)

    def test_agent_prompt_formatting(self) -> None:
        text = Prompts().get(Prompt.REFLEXION_AGENT_PROMPT)
        formatted = text.format(
            reflections="Prior reflections here",
            question="Solve X",
            scratchpad="",
        )
        self.assertIn("Prior reflections here", formatted)
        self.assertIn("Solve X", formatted)

    def test_bundle_export(self) -> None:
        bundle = ReflexionPrompts().export()
        self.assertIsInstance(bundle, dict)
        self.assertIn("reflect_prompt", bundle)
        self.assertIn("agent_prompt", bundle)

    def test_family_and_bundle_match(self) -> None:
        family = Prompts().family("reflexion")
        bundle = ReflexionPrompts().export()
        self.assertEqual(family, bundle)


if __name__ == "__main__":
    unittest.main()
