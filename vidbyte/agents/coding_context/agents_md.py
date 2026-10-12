"""FILE: vidbyte/agents/coding_context/agents_md.py

PURPOSE: Defines AgentsMdLoader, which reads the root folder's AGENTS.md once, capped at 32 KiB, into the AGENTS_MD section of a CodingAgent's context window, so the model follows the rules the repository already wrote down.
ROLE IN CODEBASE: Called once by CodingAgent.__init__ (vidbyte/agents/coding.py) with the validated CodingAgentSettings; returns a CodingContextSectionText (vidbyte/lib/dataclasses/coding.py) that CodingContextWindow (vidbyte/agents/coding_context/window.py) places after the system prompt. The reading itself is RootFileLoader's (vidbyte/agents/coding_context/root_file.py); the file name and cap come from vidbyte/lib/constants/coding.py.
ARCHITECTURE NOTE: A thin RootFileLoader subclass: it names the file, the cap, the section, the title, and the load_agents switch, and inherits the lookup, capped read, decoding, and truncation note.
FUNCTION INVENTORY: AgentsMdLoader._enabled returns settings.load_agents; load is RootFileLoader.load.
COMMON MODIFICATION PATTERNS: Change the cap or the preferred name in vidbyte/lib/constants/coding.py. A change to how root files are read belongs in root_file.py, where MapMdLoader shares it.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy reading or decoding code back here. 2. Do not walk parent folders or merge nested AGENTS.md files; the user asked for the root folder's file only.
KNOWN EDGE CASES: The exact name AGENTS.md wins over a case variant such as agents.md; see root_file.py for the cut, decoding, and broken-file cases.
RELATED DOCS: docs/design/coding-agent-agents-md.md; vidbyte/agents/coding_context/README.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py
"""

from __future__ import annotations

from vidbyte.agents.coding_context.root_file import RootFileLoader
from vidbyte.lib.constants.coding import (
    CODING_AGENTS_MD_FILE_NAME,
    CODING_AGENTS_MD_MAX_BYTES,
)
from vidbyte.lib.dataclasses.coding import CodingAgentSettings
from vidbyte.lib.enums.coding import CodingContextSection


class AgentsMdLoader(RootFileLoader):
    """Reads the root folder's AGENTS.md once, capped at 32 KiB, into the AGENTS_MD context section."""

    FILE_NAME = CODING_AGENTS_MD_FILE_NAME
    MAX_BYTES = CODING_AGENTS_MD_MAX_BYTES
    SECTION = CodingContextSection.AGENTS_MD
    TITLE = "Repository instructions"

    @staticmethod
    def _enabled(settings: CodingAgentSettings) -> bool:
        """Return the load_agents switch."""
        return settings.load_agents


__all__ = ["AgentsMdLoader"]
