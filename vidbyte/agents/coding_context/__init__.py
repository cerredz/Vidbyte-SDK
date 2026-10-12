"""FILE: vidbyte/agents/coding_context/__init__.py

PURPOSE: Marks the package that builds a CodingAgent's context window: one loader per context section and the CodingContextWindow that orders them after the system prompt.
ROLE IN CODEBASE: Imported through its modules by vidbyte/agents/coding.py: vidbyte.agents.coding_context.window (CodingContextWindow) and one module per section loader (vidbyte.agents.coding_context.agents_md for AgentsMdLoader).
ARCHITECTURE NOTE: The package exports nothing here on purpose, so adding a section loader never edits this file; callers import each module directly.
FUNCTION INVENTORY: No functions.
COMMON MODIFICATION PATTERNS: A new section is a new module in this package; see README.md for the three steps.
WHAT NOT TO DO IN THIS FILE: 1. Do not add per-loader imports or exports. 2. Do not add import-time side effects.
KNOWN EDGE CASES: None.
RELATED DOCS: vidbyte/agents/coding_context/README.md; docs/design/coding-agent-agents-md.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py
"""

from __future__ import annotations

__all__: list[str] = []
