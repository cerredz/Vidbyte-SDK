"""Context Protocol Header

Description:
    Tests built-in glob, grep, and semantic-style search tools.
Purpose:
    Verifies root safety, bounded output, and dependency-free search behavior.
Architecture:
    - CodeSearchToolTests: Temp-directory tests for each search tool.
Relations:
    Related to vidbyte.tools.builtins.code_search.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
from vidbyte.tools.types import ToolCall


class CodeSearchToolTests(unittest.IsolatedAsyncioTestCase):
    """Verifies code search built-ins."""

    def setUp(self) -> None:
        """Create a temporary source tree."""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "auth.py").write_text(
            "def check_jwt(token):\n    return token.expiration\n",
            encoding="utf-8",
        )
        (self.root / "pkg" / "other.txt").write_text("no match\n", encoding="utf-8")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "hidden.py").write_text("check_jwt\n", encoding="utf-8")

    def tearDown(self) -> None:
        """Clean up the temporary source tree."""
        self.temp.cleanup()

    async def test_glob_returns_relative_paths(self) -> None:
        """Glob returns relative paths and skips ignored directories."""
        result = await GlobTool(self.root).execute(
            ToolCall("glob", {"pattern": "**/*.py", "max_results": 10})
        )
        self.assertIn("pkg/auth.py", result.output)
        self.assertNotIn(".git", result.output)

    async def test_grep_returns_line_context(self) -> None:
        """Grep returns line-numbered snippets."""
        result = await GrepTool(self.root).execute(
            ToolCall("grep", {"pattern": "expiration", "extensions": [".py"]})
        )
        self.assertIn("pkg/auth.py:2", result.output)
        self.assertIn("return token.expiration", result.output)

    async def test_grep_rejects_traversal(self) -> None:
        """Grep rejects subdirectories outside the configured root."""
        result = await GrepTool(self.root).execute(
            ToolCall("grep", {"pattern": "x", "subdir": ".."})
        )
        self.assertEqual(result.status.value, "error")
        self.assertIn("escapes root", result.output)

    async def test_semantic_fallback_ranks_token_overlap(self) -> None:
        """Semantic search works without an embedding provider."""
        result = await SemanticSearchTool(str(self.root)).execute(
            ToolCall("semantic_search", {"query": "jwt expiration", "max_results": 1})
        )
        self.assertIn("pkg/auth.py", result.output)
        self.assertIn("check_jwt", result.output)

    async def test_root_under_ignored_ancestor_still_searches_its_files(self) -> None:
        """Ignore patterns apply below the root, not to the root's own ancestors."""
        for ancestor in ("node_modules", "venv"):
            root = self.root / "project" / ancestor / "left-pad"
            (root / "src").mkdir(parents=True)
            (root / "src" / "index.js").write_text("// TODO pad\n", encoding="utf-8")
            (root / "node_modules" / "inner").mkdir(parents=True)
            (root / "node_modules" / "inner" / "x.js").write_text(
                "// TODO inner\n", encoding="utf-8"
            )
            grep = await GrepTool(root).execute(ToolCall("grep", {"pattern": "TODO"}))
            glob = await GlobTool(root).execute(ToolCall("glob", {"pattern": "**/*.js"}))
            for result in (grep, glob):
                self.assertIn("src/index.js", result.output)
                self.assertNotIn("inner", result.output)
