"""FILE: tests/features/system_prompt_presets/test_system_prompt_presets_units.py

PURPOSE: Unit tests for the system-prompt preset building blocks: the Working Principles asset, the SystemPromptPreset enum, SystemPromptPresetSelection, SystemPromptPresetScope, and SystemPromptPresetComposer.
ROLE IN CODEBASE: Covers the unit section of the design doc's testing plan; test_system_prompt_presets_propagation.py covers agents, children, persistence, Jev, and the paradigm.
ARCHITECTURE NOTE: The verbatim checks compare the catalog text with the pack's own copy in fakes.py, so an "improved" asset cannot pass by being compared with itself. Nothing here builds an agent or a runner.
COMMON MODIFICATION PATTERNS: A new preset adds its member to the enum checks and its own verbatim test.
KNOWN EDGE CASES: A bare string is iterable, a generator is consumed once, and ContextVar scopes must survive exceptions and concurrent tasks.
RELATED DOCS: docs/design/working-principles-preset.md; tests/features/system_prompt_presets/FEATURE.md.
TESTS: python scripts/test-working-principles-preset.py, or python -m pytest tests/features/system_prompt_presets.
"""

from __future__ import annotations

import asyncio
import re
import unittest

import vidbyte
from tests.features.system_prompt_presets.fakes import WORKING_PRINCIPLES
from vidbyte.lib.dataclasses.prompts import SystemPromptPresetSelection
from vidbyte.lib.enums import Prompt, SystemPromptPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.system_prompt_presets import SystemPromptPresetScope
from vidbyte.prompts import Prompts, SystemPromptPresetComposer, working_principles_system_prompt

WP = SystemPromptPreset.WORKING_PRINCIPLES


class WorkingPrinciplesAssetTests(unittest.TestCase):
    def test_the_key_and_the_direct_import_resolve_to_the_verbatim_paragraph(self) -> None:
        self.assertEqual(Prompts().get(Prompt.WORKING_PRINCIPLES_SYSTEM_PROMPT).strip(), WORKING_PRINCIPLES)
        self.assertEqual(working_principles_system_prompt.strip(), WORKING_PRINCIPLES)
        self.assertEqual(SystemPromptPresetComposer.text(WP), WORKING_PRINCIPLES)

    def test_the_paragraph_has_eight_sentences_and_no_examples(self) -> None:
        text = SystemPromptPresetComposer.text(WP)
        self.assertEqual(len(re.findall(r"[.!?](?:\s|$)", text)), 8)
        self.assertNotIn("\n", text)
        for marker in ("for example", "e.g.", "such as", "for instance", "i.e."):
            self.assertNotIn(marker, text.lower())

    def test_the_family_is_described_and_credits_the_essay(self) -> None:
        description = Prompts().descriptions()[Prompt.WORKING_PRINCIPLES_SYSTEM_PROMPT]
        self.assertIn("Felix Rieseberg", description)
        self.assertIn("system_prompt_presets", description)


class SystemPromptPresetEnumTests(unittest.TestCase):
    def test_every_member_resolves_to_a_family_system_prompt_leaf(self) -> None:
        for preset in SystemPromptPreset:
            self.assertIn(Prompt(f"{preset.value}.system_prompt"), Prompts().keys())
            self.assertTrue(SystemPromptPresetComposer.text(preset))

    def test_the_enum_is_exported_where_developers_look(self) -> None:
        self.assertIs(vidbyte.SystemPromptPreset, SystemPromptPreset)
        self.assertIn("SystemPromptPreset", vidbyte.__all__)
        self.assertEqual(SystemPromptPreset("working_principles"), WP)


class SystemPromptPresetSelectionTests(unittest.TestCase):
    def test_none_stays_none_so_the_agent_inherits(self) -> None:
        self.assertIsNone(SystemPromptPresetSelection.parse(None, "owner"))

    def test_an_empty_list_is_an_explicit_empty_tuple(self) -> None:
        self.assertEqual(SystemPromptPresetSelection.parse([], "owner"), ())
        self.assertEqual(SystemPromptPresetSelection.parse((), "owner"), ())

    def test_members_strings_and_generators_become_a_tuple_of_members(self) -> None:
        self.assertEqual(SystemPromptPresetSelection.parse([WP], "owner"), (WP,))
        self.assertEqual(SystemPromptPresetSelection.parse(["working_principles"], "owner"), (WP,))
        self.assertEqual(SystemPromptPresetSelection.parse((preset for preset in [WP]), "owner"), (WP,))

    def test_a_bare_string_is_rejected_instead_of_read_per_character(self) -> None:
        for value in ("working_principles", b"working_principles"):
            with self.assertRaises(ConfigurationError) as caught:
                SystemPromptPresetSelection.parse(value, "BaseAgent.system_prompt_presets")
            self.assertIn("BaseAgent.system_prompt_presets", str(caught.exception))

    def test_a_non_iterable_is_rejected(self) -> None:
        for value in (1, True, 3.5, object()):
            with self.assertRaises(ConfigurationError):
                SystemPromptPresetSelection.parse(value, "owner")

    def test_an_unknown_value_names_the_allowed_values(self) -> None:
        with self.assertRaises(ConfigurationError) as caught:
            SystemPromptPresetSelection.parse(["be_ambitious"], "owner")
        self.assertIn("be_ambitious", str(caught.exception))
        self.assertEqual(caught.exception.details["allowed"], ["working_principles"])

    def test_a_repeated_preset_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            SystemPromptPresetSelection.parse([WP, "working_principles"], "owner")

    def test_the_record_rejects_a_non_member_and_is_frozen(self) -> None:
        with self.assertRaises(ConfigurationError):
            SystemPromptPresetSelection(presets=("working_principles",))  # type: ignore[arg-type]
        record = SystemPromptPresetSelection(presets=(WP,))
        with self.assertRaises(AttributeError):
            record.presets = ()  # type: ignore[misc]


class SystemPromptPresetScopeTests(unittest.IsolatedAsyncioTestCase):
    def test_outside_any_run_nothing_is_active(self) -> None:
        self.assertEqual(SystemPromptPresetScope.active(), ())
        self.assertEqual(SystemPromptPresetScope.resolve(None), ())

    def test_an_agents_own_value_wins_even_when_empty(self) -> None:
        with SystemPromptPresetScope.scope((WP,)):
            self.assertEqual(SystemPromptPresetScope.resolve(None), (WP,))
            self.assertEqual(SystemPromptPresetScope.resolve(()), ())
            self.assertEqual(SystemPromptPresetScope.resolve((WP,)), (WP,))

    def test_nested_scopes_restore_in_order_and_survive_an_exception(self) -> None:
        with self.assertRaises(RuntimeError):
            with SystemPromptPresetScope.scope((WP,)):
                with SystemPromptPresetScope.scope(()):
                    self.assertEqual(SystemPromptPresetScope.active(), ())
                self.assertEqual(SystemPromptPresetScope.active(), (WP,))
                raise RuntimeError("boom")
        self.assertEqual(SystemPromptPresetScope.active(), ())

    def test_enter_and_exit_restore_the_previous_presets(self) -> None:
        outer = SystemPromptPresetScope.enter((WP,))
        inner = SystemPromptPresetScope.enter(())
        self.assertEqual(SystemPromptPresetScope.active(), ())
        SystemPromptPresetScope.exit(inner)
        self.assertEqual(SystemPromptPresetScope.active(), (WP,))
        SystemPromptPresetScope.exit(outer)
        self.assertEqual(SystemPromptPresetScope.active(), ())

    async def test_a_task_started_inside_a_scope_inherits_it(self) -> None:
        async def read_active() -> tuple[SystemPromptPreset, ...]:
            await asyncio.sleep(0)
            return SystemPromptPresetScope.active()

        with SystemPromptPresetScope.scope((WP,)):
            task = asyncio.create_task(read_active())
            gathered = await asyncio.gather(read_active(), read_active())
            threaded = await asyncio.to_thread(SystemPromptPresetScope.active)
        self.assertEqual(await task, (WP,))
        self.assertEqual(gathered, [(WP,), (WP,)])
        self.assertEqual(threaded, (WP,))

    async def test_concurrent_scopes_stay_isolated(self) -> None:
        release = asyncio.Event()

        async def scoped(presets: tuple[SystemPromptPreset, ...]) -> tuple[SystemPromptPreset, ...]:
            with SystemPromptPresetScope.scope(presets):
                await release.wait()
                return SystemPromptPresetScope.active()

        first = asyncio.create_task(scoped((WP,)))
        second = asyncio.create_task(scoped(()))
        await asyncio.sleep(0)
        release.set()
        self.assertEqual(await first, (WP,))
        self.assertEqual(await second, ())
        self.assertEqual(SystemPromptPresetScope.active(), ())


class SystemPromptPresetComposerTests(unittest.TestCase):
    def test_no_presets_returns_the_prompt_unchanged_byte_for_byte(self) -> None:
        for prompt in ("  Be brief.\n", "", "Line one.\r\nLine two."):
            self.assertEqual(SystemPromptPresetComposer.compose(prompt, ()), prompt)
        self.assertEqual(SystemPromptPresetComposer.compose(None, ()), "")
        self.assertEqual(SystemPromptPresetComposer.compose("  Be brief.\n", None), "  Be brief.\n")

    def test_the_preset_follows_the_prompt_after_one_blank_line(self) -> None:
        self.assertEqual(SystemPromptPresetComposer.compose("Be brief.\n\n", [WP]), f"Be brief.\n\n{WORKING_PRINCIPLES}")

    def test_an_empty_or_missing_prompt_yields_just_the_preset(self) -> None:
        self.assertEqual(SystemPromptPresetComposer.compose("", [WP]), WORKING_PRINCIPLES)
        self.assertEqual(SystemPromptPresetComposer.compose("   ", [WP]), WORKING_PRINCIPLES)
        self.assertEqual(SystemPromptPresetComposer.compose(None, [WP]), WORKING_PRINCIPLES)

    def test_a_prompt_that_already_holds_the_paragraph_gets_no_second_copy(self) -> None:
        rewrapped = "Lead.\n\n" + WORKING_PRINCIPLES.replace(". ", ".\n")
        self.assertEqual(SystemPromptPresetComposer.compose(rewrapped, [WP]), rewrapped.strip())
        once = SystemPromptPresetComposer.compose("Lead.", [WP])
        self.assertEqual(SystemPromptPresetComposer.compose(once, [WP]), once)
        self.assertEqual(once.count(WORKING_PRINCIPLES), 1)

    def test_a_repeated_or_reordered_input_composes_the_same_prompt(self) -> None:
        self.assertEqual(SystemPromptPresetComposer.compose("Lead.", [WP, WP]), SystemPromptPresetComposer.compose("Lead.", (WP,)))


if __name__ == "__main__":
    unittest.main()
