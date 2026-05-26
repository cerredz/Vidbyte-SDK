"""Context Protocol Header

Description:
    Tests for the Reflexion prompt family.
Purpose:
    Validates Markdown-backed prompt loading, enum sync, direct import names,
    and strategy bundle access.
"""

from __future__ import annotations

import unittest

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import (
    Prompts,
    reflexion_agent_system_prompt,
    reflexion_reflect_prompt,
    reflexion_reflect_system_prompt,
)
from vidbyte.prompts.strategies import ReflexionPrompts


class ReflexionPromptTests(unittest.TestCase):
    def test_reflexion_prompt_family_loads_from_markdown_assets(self) -> None:
        family = Prompts().family("reflexion")

        self.assertIn("agent_system_prompt", family)
        self.assertIn("reflect_system_prompt", family)
        self.assertIn("reflect_prompt", family)
        self.assertIn("{reflections}", family["agent_system_prompt"])
        self.assertIn("{failed_attempt}", family["reflect_prompt"])

    def test_prompt_enum_and_direct_imports_resolve(self) -> None:
        prompts = Prompts()

        self.assertEqual(prompts.get(Prompt.REFLEXION_AGENT_SYSTEM_PROMPT), reflexion_agent_system_prompt)
        self.assertEqual(prompts.get(Prompt.REFLEXION_REFLECT_SYSTEM_PROMPT), reflexion_reflect_system_prompt)
        self.assertEqual(prompts.get(Prompt.REFLEXION_REFLECT_PROMPT), reflexion_reflect_prompt)

    def test_strategy_prompt_bundle_matches_catalog(self) -> None:
        self.assertEqual(ReflexionPrompts().export(), Prompts().family("reflexion"))

    def test_reflexion_prompts_are_format_ready(self) -> None:
        family = Prompts().family("reflexion")

        agent_prompt = family["agent_system_prompt"].format(
            system_prompt="System",
            task="Task",
            reflections="Reflection memory",
            previous_attempt="Attempt trace",
        )
        reflect_prompt = family["reflect_prompt"].format(
            task="Task",
            failed_attempt="Attempt trace",
            reflections="Reflection memory",
        )

        self.assertIn("System", agent_prompt)
        self.assertIn("Reflection memory", agent_prompt)
        self.assertIn("Attempt trace", reflect_prompt)


if __name__ == "__main__":
    unittest.main()
