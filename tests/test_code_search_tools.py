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

    async def test_grep_refuses_string_regex_flag(self) -> None:
        """Grep refuses a stringly boolean instead of reading "false" as True."""
        result = await GrepTool(self.root).execute(
            ToolCall("grep", {"pattern": "expiration", "regex": "false"})
        )
        self.assertEqual(result.status.value, "error")
        self.assertIn("'regex' must be a boolean (true/false)", result.output)
        self.assertEqual(result.metadata["error"], "invalid_argument")

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

    async def test_truncation_notice_only_when_a_hit_was_cut(self) -> None:
        """Exactly max_results hits are not truncated; one more hit is."""
        root = self.root / "exact"
        root.mkdir()
        for name in ("a", "b", "c"):
            (root / f"{name}.py").write_text("# TODO\n", encoding="utf-8")
        grep_call = ToolCall("grep", {"pattern": "TODO", "max_results": 3})
        glob_call = ToolCall("glob", {"pattern": "*.py", "max_results": 3})
        for result in (await GrepTool(root).execute(grep_call), await GlobTool(root).execute(glob_call)):
            self.assertNotIn("Results truncated", result.output)
            self.assertFalse(result.metadata["truncated"])
            self.assertEqual(result.metadata["count"], 3)
        (root / "d.py").write_text("# TODO\n", encoding="utf-8")
        for result in (await GrepTool(root).execute(grep_call), await GlobTool(root).execute(glob_call)):
            self.assertIn("Results truncated; narrow the pattern.", result.output)
            self.assertTrue(result.metadata["truncated"])
            self.assertEqual(result.metadata["count"], 3)

    async def test_null_subdir_searches_from_root(self) -> None:
        """A null subdir means the root, not a folder named "None"."""
        cases = (
            (GlobTool(self.root), ToolCall("glob", {"pattern": "**/*.py", "subdir": None})),
            (GrepTool(self.root), ToolCall("grep", {"pattern": "expiration", "subdir": None})),
            (SemanticSearchTool(str(self.root)), ToolCall("semantic_search", {"query": "jwt expiration", "subdir": None})),
        )
        for tool, call in cases:
            with self.subTest(tool=type(tool).__name__):
                result = await tool.execute(call)
                self.assertEqual(result.status.value, "success", result.output)
                self.assertIn("pkg/auth.py", result.output)

    async def test_null_numeric_limits_behave_like_omitted(self) -> None:
        """Null max_results, max_chars, context_lines, and max_chars_per_result use the documented defaults."""
        cases = (
            (GlobTool(self.root), "glob", {"pattern": "**/*.py"}, ("max_results", "max_chars")),
            (GrepTool(self.root), "grep", {"pattern": "expiration"}, ("context_lines", "max_results", "max_chars")),
            (
                SemanticSearchTool(str(self.root)),
                "semantic_search",
                {"query": "jwt expiration"},
                ("max_results", "max_chars_per_result", "max_chars"),
            ),
        )
        for tool, name, base, nullable in cases:
            with self.subTest(tool=name):
                omitted = await tool.execute(ToolCall(name, dict(base)))
                nulled = await tool.execute(ToolCall(name, {**base, **dict.fromkeys(nullable)}))
                self.assertEqual(nulled.status.value, "success", nulled.output)
                self.assertEqual(nulled.output, omitted.output)
                self.assertEqual(nulled.metadata, omitted.metadata)
