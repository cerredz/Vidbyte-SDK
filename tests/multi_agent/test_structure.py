"""Context Protocol Header

Description:
    Tests structural review constraints for the multi-agent implementation.
Purpose:
    Prevents module-level helper regressions, oversized runtime modules, local type
    aliases, and nested facade lifecycle exception handling.
Architecture:
    AST and filesystem checks inspect source without executing private behavior.
Relations:
    Complements tests/multi_agent/test_behavior.py.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from vidbyte.lib.dataclasses.multi_agent import BeforeDispatch, CompletionCheck, LedgerFactory, ReportParser, RequestBuilder


class MultiAgentStructureTests(unittest.TestCase):
    """Review-driven source-structure checks."""

    package = Path(__file__).resolve().parents[2] / "vidbyte" / "agents" / "multi"

    def test_runtime_modules_define_behavior_only_inside_classes(self) -> None:
        # [Review Constraint] Module-level helper functions make the protocol harder to scan.
        for path in self.package.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            functions = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
            self.assertEqual(functions, [], path.name)

    def test_runtime_modules_remain_under_three_hundred_lines(self) -> None:
        # [Review Constraint] Focused collaborators stay small enough for one mental model.
        for path in self.package.glob("*.py"):
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            self.assertLessEqual(line_count, 300, f"{path.name}: {line_count}")

    def test_multi_agent_types_live_in_vidbyte_lib(self) -> None:
        # [Review Constraint] Shared callbacks no longer live in agents/multi/types.py.
        self.assertFalse((self.package / "types.py").exists())
        for alias in (BeforeDispatch, CompletionCheck, LedgerFactory, ReportParser, RequestBuilder):
            self.assertIsNotNone(alias)

    def test_lifecycle_execute_has_one_exception_boundary(self) -> None:
        # [Review Constraint] One top-level try/except/finally owns run cleanup and tracing.
        tree = ast.parse((self.package / "lifecycle.py").read_text(encoding="utf-8"))
        lifecycle = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MultiAgentLifecycle")
        execute = next(node for node in lifecycle.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute")
        tries = [node for node in ast.walk(execute) if isinstance(node, ast.Try)]
        self.assertEqual(len(tries), 1)


if __name__ == "__main__":
    unittest.main()
