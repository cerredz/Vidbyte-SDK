"""FILE: vidbyte/agents/jev/documentation/__init__.py

PURPOSE: Exposes JevAgent's documentation lookup: the JevDocumentation search agent and the records it returns.
ROLE IN CODEBASE: vidbyte/agents/jev/agent.py and runtime.py import from here; vidbyte.agents.jev re-exports the public names.
ARCHITECTURE NOTE: Questions, the provider table, and the hit recorder stay internal to this package; the only public switch is JevAgentSettings.documentation.
COMMON MODIFICATION PATTERNS: Export a new name here only when callers need to read it from a result.
KNOWN EDGE CASES: Importing this package reads no API key and builds no client; keys are read when JevDocumentation is constructed.
RELATED DOCS: docs/design/jev-documentation.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_documentation.py.
"""

from vidbyte.agents.jev.documentation.agent import JevDocumentation
from vidbyte.agents.jev.documentation.result import (
    JevDocumentationLink,
    JevDocumentationResult,
    JevDocumentationStatus,
)

__all__ = ["JevDocumentation", "JevDocumentationLink", "JevDocumentationResult", "JevDocumentationStatus"]
