# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Unit tests for the unified Vidbyte CLI public interface.
# Purpose: Ensures vidbyte skills commands dispatch in-process with stable output.
# Architecture & Functions:
#   - VidbyteCliInterfaceTests: verifies list/show/install, key parsing, and errors.
# Codebase Relation:
#   - Covers vidbyte.cli as a thin adapter over the Skills catalog.
# ==============================================================================

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vidbyte.cli import main
from vidbyte.lib.enums.skills import Skill
from vidbyte.lib.errors import ConfigurationError


class VidbyteCliInterfaceTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        # Runs the CLI in-process and captures stdout plus stderr for assertions.
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_version_returns_zero(self) -> None:
        # Verifies --version is handled by argparse but returned as an integer status.
        code, stdout, stderr = self.run_cli(["--version"])

        self.assertEqual(code, 0)
        self.assertIn("vidbyte ", stdout)
        self.assertEqual(stderr, "")

    def test_help_does_not_instantiate_skills_catalog(self) -> None:
        # Ensures help paths stay lazy even if the Skills catalog would fail at runtime.
        with patch("vidbyte.skills.catalog.Skills.__init__", side_effect=AssertionError("catalog loaded")):
            root_code, root_stdout, root_stderr = self.run_cli(["--help"])
            skills_code, skills_stdout, skills_stderr = self.run_cli(["skills", "--help"])

        self.assertEqual(root_code, 0)
        self.assertEqual(skills_code, 0)
        self.assertIn("skills", root_stdout)
        self.assertIn("install", skills_stdout)
        self.assertEqual(root_stderr, "")
        self.assertEqual(skills_stderr, "")

    def test_list_prints_keys_and_descriptions(self) -> None:
        # Confirms list output is sourced from the registry and uses stable enum values.
        code, stdout, stderr = self.run_cli(["skills", "list"])

        self.assertEqual(code, 0)
        self.assertIn(Skill.DECOMPOSE_FANOUT.value, stdout)
        self.assertIn("Decompose one large task", stdout)
        self.assertEqual(stderr, "")

    def test_show_accepts_short_kebab_key(self) -> None:
        # Verifies show accepts the user-friendly bare kebab skill name.
        code, stdout, stderr = self.run_cli(["skills", "show", "decompose-fanout"])

        self.assertEqual(code, 0)
        self.assertIn("name: decompose-fanout", stdout)
        self.assertIn("## Algorithm", stdout)
        self.assertEqual(stderr, "")

    def test_show_accepts_full_enum_value(self) -> None:
        # Verifies show also accepts the canonical full enum value.
        code, stdout, stderr = self.run_cli(["skills", "show", Skill.DECOMPOSE_FANOUT.value])

        self.assertEqual(code, 0)
        self.assertIn("name: decompose-fanout", stdout)
        self.assertEqual(stderr, "")

    def test_install_writes_skill_and_refuses_non_empty_without_force(self) -> None:
        # Checks install materializes files and enforces the --force overwrite guard.
        with tempfile.TemporaryDirectory() as tmp_dir:
            first_code, first_stdout, first_stderr = self.run_cli(["skills", "install", "decompose-fanout", "--dest", tmp_dir])
            second_code, second_stdout, second_stderr = self.run_cli(["skills", "install", "decompose-fanout", "--dest", tmp_dir])
            force_code, force_stdout, force_stderr = self.run_cli(["skills", "install", "decompose-fanout", "--dest", tmp_dir, "--force"])
            root = Path(tmp_dir)

            self.assertEqual(first_code, 0)
            self.assertTrue(root.joinpath("decompose-fanout", "SKILL.md").is_file())
            self.assertTrue(root.joinpath("references", "harness-commands.md").is_file())
            self.assertIn(str(root.joinpath("decompose-fanout")), first_stdout)
            self.assertEqual(first_stderr, "")
            self.assertEqual(second_code, 1)
            self.assertEqual(second_stdout, "")
            self.assertIn("already exists", second_stderr)
            self.assertEqual(force_code, 0)
            self.assertIn(str(root.joinpath("decompose-fanout")), force_stdout)
            self.assertEqual(force_stderr, "")

    def test_unknown_key_returns_usage_error_with_valid_keys(self) -> None:
        # Ensures unknown keys are expected usage errors with valid choices on stderr.
        code, stdout, stderr = self.run_cli(["skills", "show", "missing-skill"])

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("error: unknown skill key: missing-skill", stderr)
        self.assertEqual(stderr.count("\n"), 1)
        self.assertIn(Skill.DECOMPOSE_FANOUT.value, stderr)

    def test_configuration_error_returns_one_line_expected_failure(self) -> None:
        # Confirms expected catalog failures are printed without traceback and return exit 1.
        with patch("vidbyte.skills.Skills", side_effect=ConfigurationError("broken catalog")):
            code, stdout, stderr = self.run_cli(["skills", "list"])

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "error: broken catalog\n")


if __name__ == "__main__":
    unittest.main()
