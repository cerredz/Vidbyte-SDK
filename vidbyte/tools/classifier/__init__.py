"""FILE: vidbyte/tools/classifier/__init__.py

PURPOSE: Re-exports the classifier tool family: model-callable tools that hand a small, structured judgment to a fast calibrated decision model.
ROLE IN CODEBASE: Imported by `vidbyte/tools/__init__.py` so applications can write `from vidbyte.tools import JevDecideTool`.
ARCHITECTURE NOTE: Tools here are ModelBackedTool subclasses; their provider calls go through vidbyte/lib/runners and vidbyte/providers, and their usage is metered by AgentRuntime.
COMMON MODIFICATION PATTERNS: Add a new classifier tool as its own module, export it here and from vidbyte/tools/__init__.py, and list it in this folder's README File Index.
KNOWN EDGE CASES: None at the package level; each tool documents its own fail-open behavior.
RELATED DOCS: vidbyte/tools/classifier/README.md and docs/design/jev-decide-tool.md.
TESTS: tests/test_jev_decide_tool.py and scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

from vidbyte.tools.classifier.jev_decide import JevDecideTool

__all__ = ["JevDecideTool"]
