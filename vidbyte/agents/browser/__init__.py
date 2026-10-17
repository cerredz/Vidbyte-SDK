"""FILE: vidbyte/agents/browser/__init__.py

PURPOSE: Exposes BrowserAgent, its two settings objects (BrowserAgentSettings and BrowserServerSettings), and BrowserAgentRuntime, the runtime that AgentRuntimeType.BROWSER resolves to.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents, by the runtime registry's lazy import, and by application code.
ARCHITECTURE NOTE: The role map, the episode tool, the goal card, the checks, the events, the usage ledger, and the response writer stay internal to the package; their records and enums are public from vidbyte.lib.dataclasses.browser and vidbyte.lib.enums.
FUNCTION INVENTORY: None; this module only re-exports the four public names.
COMMON MODIFICATION PATTERNS: Export a new name here only when it becomes part of the supported BrowserAgent API, and mirror it in vidbyte/agents/__init__.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not export the internal collaborators; they are built by BrowserAgent and its runtime. 2. Do not add logic here.
KNOWN EDGE CASES: Importing this package starts no server and reads no key; the servers start on an agent's first run.
RELATED DOCS: docs/spec/browser-agent/spec.md (section 8.5); vidbyte/agents/browser/README.md
TESTS: tests/features/browser_agent/test_browser_agent_contract.py
"""

from vidbyte.agents.browser.agent import BrowserAgent
from vidbyte.agents.browser.runtime import BrowserAgentRuntime
from vidbyte.agents.browser.settings import (
    BrowserAgentSettings,
    BrowserServerSettings,
)

__all__ = [
    "BrowserAgent",
    "BrowserAgentRuntime",
    "BrowserAgentSettings",
    "BrowserServerSettings",
]
