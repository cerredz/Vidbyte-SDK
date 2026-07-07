# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Unit tests for the Skill catalog public interfaces.
# Purpose: Ensures packaged skill assets are enum-synced, readable, and materializable.
# Architecture & Functions:
#   - SkillsInterfaceTests: validates registry accessors, frontmatter, files, and CLI.
# Codebase Relation:
#   - Mirrors tests/test_prompts_interface.py for multi-file skill assets.
# ==============================================================================

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.lib.enums.skills import Skill
from vidbyte.lib.errors import ConfigurationError
from vidbyte.skills import SkillRecord, Skills
from vidbyte.skills.__main__ import main as skills_main


class SkillsInterfaceTests(unittest.TestCase):
    def test_get_accepts_skill_enum_and_returns_record(self) -> None:
        # Verifies typed lookup returns a complete skill record and SKILL.md text.
        skills = Skills()
        record = skills.get(Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT)

        self.assertIsInstance(record, SkillRecord)
        self.assertEqual(record.key, Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT)
        self.assertEqual(record.paradigm, "context_minimal_fanout")
        self.assertIn("Decompose Fanout", record.text)
        self.assertEqual(skills.text(record.key), record.text)

    def test_get_rejects_string_keys(self) -> None:
        # Ensures callers use enum keys instead of raw strings.
        with self.assertRaises(TypeError):
            Skills().get("context_minimal_fanout.decompose_fanout")  # type: ignore[arg-type]

    def test_keys_and_descriptions_are_enum_keyed(self) -> None:
        # Confirms manifest entries and enum members are synchronized.
        skills = Skills()

        self.assertEqual(set(skills.keys()), set(Skill))
        self.assertEqual(set(skills.descriptions()), set(Skill))
        self.assertTrue(all(description for description in skills.descriptions().values()))

    def test_paradigm_returns_family_records(self) -> None:
        # Verifies family lookup returns every context-minimal fanout skill.
        family = Skills().paradigm("context_minimal_fanout")

        self.assertEqual(set(family), set(Skill))
        self.assertTrue(all(record.paradigm == "context_minimal_fanout" for record in family.values()))

    def test_files_include_frontmatter_for_every_skill(self) -> None:
        # Checks every shipped skill has load-bearing frontmatter and sections.
        skills = Skills()

        for key in skills.keys():
            record = skills.get(key)
            self.assertTrue(record.text.startswith("---\n"))
            self.assertIn(f"name: {record.folder}", record.text)
            self.assertIn("description:", record.text)
            self.assertIn("## Goal", record.text)
            self.assertIn("## Description", record.text)
            self.assertIn("## Use Cases", record.text)
            self.assertIn("## Algorithm", record.text)
            self.assertIn("## Rules", record.text)

    def test_fanout_files_include_shared_references(self) -> None:
        # Ensures both fanout skills expose the shared command reference file.
        skills = Skills()

        for key in (
            Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_DESIGN_FANOUT,
            Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT,
        ):
            files = skills.files(key)
            self.assertIn("references/harness-commands.md", files)
            self.assertIn("codex exec", files["references/harness-commands.md"])
            self.assertIn("claude -p", files["references/harness-commands.md"])

    def test_materialize_writes_skill_folder_and_references(self) -> None:
        # Verifies materialize writes all declared files under the destination.
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Skills().materialize(Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT, tmp_dir)
            root = Path(tmp_dir)

            self.assertEqual(target, root.resolve().joinpath("decompose-fanout"))
            self.assertTrue(root.joinpath("decompose-fanout", "SKILL.md").is_file())
            self.assertTrue(root.joinpath("references", "harness-commands.md").is_file())
            self.assertIn("Decompose Fanout", root.joinpath("decompose-fanout", "SKILL.md").read_text(encoding="utf-8"))

    def test_materialize_refuses_paths_outside_destination(self) -> None:
        # Verifies the materializer rejects unsafe relative paths before writing.
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ConfigurationError):
                Skills._safe_materialize_target(Path(tmp_dir).resolve(), "../escape.md")

    def test_module_cli_list_and_install(self) -> None:
        # Exercises the lightweight python -m vidbyte.skills command handlers.
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertEqual(skills_main(["list"]), 0)
            self.assertEqual(
                skills_main(["install", "context_minimal_fanout.decompose_fanout", "--dest", tmp_dir]),
                0,
            )
            self.assertTrue(Path(tmp_dir).joinpath("decompose-fanout", "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
