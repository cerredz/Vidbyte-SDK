"""Context Protocol Header

Description:
    Implements an auto-detecting LSP backend with AST-based fallback for Python.
Purpose:
    Provides language-aware code analysis using Python's ast module as a
    fallback when no full LSP server is available. Automatically detects
    language from file extension and dispatches to appropriate analyzer.
Architecture:
    - Detects language from file extension (.py, .js, .ts, etc.).
    - For Python: uses ast.parse() for definitions, symbols, and structure.
    - For other languages: returns descriptive messages.
    - diagnostics(): Returns empty list (no real LSP without server).
    - hover(): Returns None.
    - is_available(): Always returns True (static analysis fallback).
Relations:
    Related to vidbyte.lib.providers.lsp.base and vidbyte.tools.builtins.lsp.
"""

from __future__ import annotations

import ast
import logging
import os

from vidbyte.lib.providers.lsp.base import BaseLspBackend, HoverInfo, Location

logger = logging.getLogger(__name__)


class AutoLspBackend(BaseLspBackend):
    def __init__(self) -> None:
        self._root_uri: str = ""
        self._language: str = ""

    def _detect_language(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascriptreact",
            ".ts": "typescript",
            ".tsx": "typescriptreact",
            ".json": "json",
            ".md": "markdown",
            ".html": "html",
            ".css": "css",
            ".vue": "vue",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".r": "r",
            ".sh": "shell",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
        }
        return language_map.get(ext, "unknown")

    async def initialize(self, root_uri: str, language: str) -> None:
        self._root_uri = root_uri
        self._language = language

    async def definition(self, file_path: str, line: int, character: int) -> list[Location]:
        language = self._detect_language(file_path)
        if language == "python":
            return self._analyze_python_definitions(file_path, line, character)
        return []

    async def references(self, file_path: str, line: int, character: int) -> list[Location]:
        language = self._detect_language(file_path)
        if language == "python":
            return self._analyze_python_references(file_path, line, character)
        return []

    async def hover(self, file_path: str, line: int, character: int) -> HoverInfo | None:
        language = self._detect_language(file_path)
        if language == "python":
            return self._analyze_python_hover(file_path, line, character)
        return None

    async def diagnostics(self, file_path: str) -> list[str]:
        return []

    async def symbols(self, file_path: str | None) -> list[dict]:
        if file_path is None:
            return []
        language = self._detect_language(file_path)
        if language == "python":
            return self._extract_python_symbols(file_path)
        return []

    async def is_available(self) -> bool:
        return True

    def _read_file(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def _parse_ast(self, file_path: str) -> ast.AST | None:
        try:
            source = self._read_file(file_path)
            return ast.parse(source, filename=file_path)
        except Exception as exc:
            logger.exception("AST parse failed for %s", file_path)
            return None

    def _analyze_python_definitions(self, file_path: str, line: int, character: int) -> list[Location]:
        tree = self._parse_ast(file_path)
        if tree is None:
            return []

        target_name: str | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and hasattr(node, "lineno"):
                if node.lineno == line:
                    target_name = node.id
                    break
            elif isinstance(node, ast.Attribute) and hasattr(node, "lineno"):
                if node.lineno == line:
                    target_name = node.attr
                    break

        if target_name is None:
            return []

        results: list[Location] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname == target_name or (alias.asname is None and alias.name == target_name):
                        results.append(Location(uri=file_path, line=getattr(node, "lineno", 1), character=0))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.asname == target_name or (alias.asname is None and alias.name == target_name):
                        results.append(Location(uri=file_path, line=getattr(node, "lineno", 1), character=0))
            elif isinstance(node, ast.FunctionDef) and node.name == target_name:
                results.append(Location(uri=file_path, line=node.lineno, character=node.col_offset))
            elif isinstance(node, ast.AsyncFunctionDef) and node.name == target_name:
                results.append(Location(uri=file_path, line=node.lineno, character=node.col_offset))
            elif isinstance(node, ast.ClassDef) and node.name == target_name:
                results.append(Location(uri=file_path, line=node.lineno, character=node.col_offset))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == target_name:
                        results.append(Location(uri=file_path, line=node.lineno, character=node.col_offset))
        return results

    def _analyze_python_references(self, file_path: str, line: int, character: int) -> list[Location]:
        tree = self._parse_ast(file_path)
        if tree is None:
            return []

        target_name: str | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and hasattr(node, "lineno"):
                if node.lineno == line:
                    target_name = node.id
                    break
            elif isinstance(node, ast.Attribute) and hasattr(node, "lineno"):
                if node.lineno == line:
                    target_name = node.attr
                    break

        if target_name is None:
            return []

        results: list[Location] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == target_name and hasattr(node, "lineno"):
                results.append(Location(uri=file_path, line=node.lineno, character=node.col_offset))
        return results

    def _analyze_python_hover(self, file_path: str, line: int, character: int) -> HoverInfo | None:
        tree = self._parse_ast(file_path)
        if tree is None:
            return None

        target_name: str | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and hasattr(node, "lineno"):
                if node.lineno == line:
                    target_name = node.id
                    break

        if target_name is None:
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == target_name:
                args = [arg.arg for arg in node.args.args]
                return HoverInfo(contents=f"def {target_name}({', '.join(args)})")
            elif isinstance(node, ast.AsyncFunctionDef) and node.name == target_name:
                args = [arg.arg for arg in node.args.args]
                return HoverInfo(contents=f"async def {target_name}({', '.join(args)})")
            elif isinstance(node, ast.ClassDef) and node.name == target_name:
                bases = [ast.unparse(base) if hasattr(ast, "unparse") else str(base) for base in node.bases]
                bases_str = f"({', '.join(bases)})" if bases else ""
                return HoverInfo(contents=f"class {target_name}{bases_str}")
        return None

    def _extract_python_symbols(self, file_path: str) -> list[dict]:
        tree = self._parse_ast(file_path)
        if tree is None:
            return []

        symbols: list[dict] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                symbols.append({
                    "name": node.name,
                    "kind": "function",
                    "line": node.lineno,
                    "character": node.col_offset,
                    "file": file_path,
                })
            elif isinstance(node, ast.AsyncFunctionDef):
                symbols.append({
                    "name": node.name,
                    "kind": "function",
                    "line": node.lineno,
                    "character": node.col_offset,
                    "file": file_path,
                })
            elif isinstance(node, ast.ClassDef):
                symbols.append({
                    "name": node.name,
                    "kind": "class",
                    "line": node.lineno,
                    "character": node.col_offset,
                    "file": file_path,
                })
        return symbols


__all__ = ["AutoLspBackend"]
