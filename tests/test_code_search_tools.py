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

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
from vidbyte.tools.types import ToolCall


class _LoopRecordingEmbeddings:
    """Embedding provider that records whether each embed() call ran on the event loop thread."""

    def __init__(self) -> None:
        self.on_loop: list[bool] = []

    def embed(self, texts):
        try:
            asyncio.get_running_loop()
            self.on_loop.append(True)
        except RuntimeError:
            self.on_loop.append(False)
        return [[1.0, float("jwt" in text)] for text in texts]


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

    async def test_grep_numbers_lines_at_newline_only(self) -> None:
        """A form feed line or a U+2028 inside a string does not shift later line numbers."""
        (self.root / "pkg" / "f.c").write_text("int a;\n\f\nint b;\nint c;\n", encoding="utf-8")
        (self.root / "pkg" / "s.js").write_text('const s = "x y";\nlet n = 1;\n', encoding="utf-8")
        tool = GrepTool(self.root)
        c_result = await tool.execute(ToolCall("grep", {"pattern": "int c", "context_lines": 0}))
        self.assertIn("pkg/f.c:4\n4: int c;", c_result.output)
        js_result = await tool.execute(ToolCall("grep", {"pattern": "let n", "context_lines": 0}))
        self.assertIn("pkg/s.js:2\n2: let n = 1;", js_result.output)

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

    async def test_semantic_search_embeds_off_the_event_loop(self) -> None:
        """Semantic search calls its synchronous embedding provider from a worker thread."""
        # @intent semantic-search-runs-off-the-event-loop: a blocking embed() must not stall the loop or defeat tool timeouts.
        embeddings = _LoopRecordingEmbeddings()
        result = await SemanticSearchTool(str(self.root), embedding_provider=embeddings).execute(
            ToolCall("semantic_search", {"query": "jwt expiration", "max_results": 1})
        )
        self.assertIn("pkg/auth.py", result.output)
        self.assertEqual(embeddings.on_loop, [False, False])
        self.assertEqual(result.metadata["indexed_chunks"], 2)

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

    async def test_bare_string_ignore_patterns_is_refused(self) -> None:
        """A bare-string ignore_patterns is refused instead of ignoring its characters."""
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "vendored.py").write_text("expiration\n", encoding="utf-8")
        with self.assertRaisesRegex(ConfigurationError, r"ignore_patterns must be a list .*not a single string"):
            GrepTool(self.root, ignore_patterns="node_modules")
        result = await GrepTool(self.root, ignore_patterns=["node_modules"]).execute(
            ToolCall("grep", {"pattern": "expiration"})
        )
        self.assertIn("pkg/auth.py", result.output)
        self.assertNotIn("node_modules", result.output)

    async def test_empty_ignore_patterns_ignores_nothing(self) -> None:
        """An explicit empty ignore_patterns searches every directory; only None uses the defaults."""
        (self.root / "node_modules" / "leftpad").mkdir(parents=True)
        (self.root / "node_modules" / "leftpad" / "index.js").write_text("eval(s)\n", encoding="utf-8")
        call = ToolCall("grep", {"pattern": "eval"})
        default = await GrepTool(self.root).execute(call)
        self.assertNotIn("node_modules", default.output)
        result = await GrepTool(self.root, ignore_patterns=[]).execute(call)
        self.assertIn("node_modules/leftpad/index.js:1", result.output)

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

    async def test_file_reached_through_links_is_reported_once(self) -> None:
        """A file reached through a file symlink or a directory alias is listed once, not once per spelling."""
        root = self.root / "linked"
        (root / "docs" / "v2").mkdir(parents=True)
        (root / "README.md").write_text("needle in the readme\n", encoding="utf-8")
        (root / "docs" / "v2" / "a.md").write_text("# a\n", encoding="utf-8")
        try:
            os.symlink(os.path.join("..", "README.md"), root / "docs" / "README.md")
            os.symlink("v2", root / "docs" / "latest", target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        self.assertTrue((root / "docs" / "README.md").is_file())
        grep = await GrepTool(root).execute(ToolCall("grep", {"pattern": "needle", "context_lines": 0}))
        self.assertEqual(grep.output.count("README.md:1"), 1, grep.output)
        readme = await GlobTool(root).execute(ToolCall("glob", {"pattern": "**/README.md"}))
        self.assertEqual(readme.output.splitlines(), ["README.md"])
        alias = await GlobTool(root).execute(ToolCall("glob", {"pattern": "docs/*/*.md"}))
        self.assertEqual(alias.output.splitlines(), ["docs/v2/a.md"])

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
