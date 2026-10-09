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

    async def test_single_block_patch_preserves_lf_line_endings(self) -> None:
        """Patching one block leaves every other LF line ending byte-for-byte unchanged."""
        self.file.write_bytes(b"def f():\n    x = 1\n    return 2\n\nprint(f())\n")
        result = await PatchTool(self.root).execute(
            ToolCall("patch_file", {"file_path": "demo.py", "search_block": "return 2", "replace_block": "return 3"})
        )
        self.assertEqual(result.status.value, "success")
        self.assertEqual(self.file.read_bytes(), b"def f():\n    x = 1\n    return 3\n\nprint(f())\n")

    async def test_single_block_patch_preserves_crlf_line_endings(self) -> None:
        """A multi-line LF search block still matches a CRLF file, and the file stays CRLF."""
        self.file.write_bytes(b"def f():\r\n    x = 1\r\n    return 2\r\n\r\nprint(f())\r\n")
        result = await PatchTool(self.root).execute(
            ToolCall(
                "patch_file",
                {"file_path": "demo.py", "search_block": "    x = 1\n    return 2\n", "replace_block": "    x = 1\n    return 3\n"},
            )
        )
        self.assertEqual(result.status.value, "success")
        self.assertEqual(self.file.read_bytes(), b"def f():\r\n    x = 1\r\n    return 3\r\n\r\nprint(f())\r\n")
