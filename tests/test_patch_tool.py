"""Context Protocol Header

Description:
    Tests the exact-match patch tool.
Purpose:
    Verifies safe, auditable file edits and rejection of ambiguous or unsafe edits.
Architecture:
    - PatchToolTests: Temp-file patch scenarios.
Relations:
    Related to vidbyte.tools.builtins.editing.patch.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.types import ToolCall


class PatchToolTests(unittest.IsolatedAsyncioTestCase):
    """Verifies patch tool behavior."""

    def setUp(self) -> None:
        """Create a temporary file for patching."""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / "demo.py"
        self.file.write_text("a = 1\nb = 2\n", encoding="utf-8")

    def tearDown(self) -> None:
        """Clean up the temporary file tree."""
        self.temp.cleanup()

    async def test_exact_patch_returns_diff(self) -> None:
        """A unique exact match is replaced and diffed."""
        result = await PatchTool(self.root).execute(
            ToolCall(
                "patch_file",
                {
                    "file_path": "demo.py",
                    "search_block": "b = 2\n",
                    "replace_block": "b = 3\n",
                },
            )
        )
        self.assertEqual(result.status.value, "success")
        self.assertIn("-b = 2", result.output)
        self.assertIn("+b = 3", result.output)
        self.assertIn("b = 3", self.file.read_text(encoding="utf-8"))

    async def test_missing_block_returns_error(self) -> None:
        """Missing search blocks do not modify the file."""
        result = await PatchTool(self.root).execute(
            ToolCall(
                "patch_file",
                {
                    "file_path": "demo.py",
                    "search_block": "z = 9\n",
                    "replace_block": "z = 10\n",
                },
            )
        )
        self.assertEqual(result.status.value, "error")
        self.assertIn("not found", result.output.lower())

    async def test_ambiguous_block_returns_error(self) -> None:
        """Search blocks matching multiple places are rejected."""
        self.file.write_text("x\nx\n", encoding="utf-8")
        result = await PatchTool(self.root).execute(
            ToolCall(
                "patch_file",
                {"file_path": "demo.py", "search_block": "x\n", "replace_block": "y\n"},
            )
        )
        self.assertEqual(result.status.value, "error")
        self.assertIn("Ambiguous", result.output)
