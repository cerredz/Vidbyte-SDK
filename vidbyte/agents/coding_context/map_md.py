"""FILE: vidbyte/agents/coding_context/map_md.py

PURPOSE: Defines MapMdLoader, which reads the root folder's MAP.md once, capped at 32 KiB, into the REPO_MAP section of a CodingAgent's context window. MAP.md is a short, human-written map of where things live in the repository, so the model can skip exploring the layout with ls and find.
ROLE IN CODEBASE: Called once by CodingAgent.__init__ (vidbyte/agents/coding.py) with the validated CodingAgentSettings; returns a CodingContextSectionText (vidbyte/lib/dataclasses/coding.py) that CodingContextWindow (vidbyte/agents/coding_context/window.py) places after the AGENTS.md section. The reading itself is RootFileLoader's (vidbyte/agents/coding_context/root_file.py); the file name and cap come from vidbyte/lib/constants/coding.py.
ARCHITECTURE NOTE: A thin RootFileLoader subclass, the same as AgentsMdLoader: it names the file, the cap, the section, the title, and the load_map switch, and inherits the lookup, capped read, decoding, and truncation note.
FUNCTION INVENTORY: MapMdLoader._enabled returns settings.load_map; load is RootFileLoader.load.
COMMON MODIFICATION PATTERNS: Change the cap or the preferred name in vidbyte/lib/constants/coding.py. A change to how root files are read belongs in root_file.py, where AgentsMdLoader shares it.
WHAT NOT TO DO IN THIS FILE: 1. Do not generate a file list from the tree; the map is the file the repository wrote. 2. Do not copy reading or decoding code here.
KNOWN EDGE CASES: The exact name MAP.md wins over a case variant such as map.md. Other names, such as REPO_MAP.md, are not read. See root_file.py for the cut, decoding, and broken-file cases.
RELATED DOCS: docs/design/coding-agent-map-md.md; vidbyte/agents/coding_context/README.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_map_md.py
"""

from __future__ import annotations

from vidbyte.agents.coding_context.root_file import RootFileLoader
from vidbyte.lib.constants.coding import (
    CODING_MAP_MD_FILE_NAME,
    CODING_MAP_MD_MAX_BYTES,
)
from vidbyte.lib.dataclasses.coding import CodingAgentSettings
from vidbyte.lib.enums.coding import CodingContextSection


class MapMdLoader(RootFileLoader):
    """Reads the root folder's MAP.md once, capped at 32 KiB, into the REPO_MAP context section."""

    FILE_NAME = CODING_MAP_MD_FILE_NAME
    MAX_BYTES = CODING_MAP_MD_MAX_BYTES
    SECTION = CodingContextSection.REPO_MAP
    TITLE = "Repository map"

    @staticmethod
    def _enabled(settings: CodingAgentSettings) -> bool:
        """Return the load_map switch."""
        return settings.load_map


__all__ = ["MapMdLoader"]
