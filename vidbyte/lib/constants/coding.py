"""FILE: vidbyte/lib/constants/coding.py

PURPOSE: Defines the fixed file names and byte caps that CodingAgent uses when it loads a repository's AGENTS.md and MAP.md into the model's context.
ROLE IN CODEBASE: Read by AgentsMdLoader (vidbyte/agents/coding_context/agents_md.py), MapMdLoader (vidbyte/agents/coding_context/map_md.py), and the coding-agent feature tests.
ARCHITECTURE NOTE: Immutable constants only; RootFileLoader (vidbyte/agents/coding_context/root_file.py) owns the reading, decoding, and truncation behavior.
COMMON MODIFICATION PATTERNS: Change the cap here, never at the read call, so the loader, its truncation line, and the tests stay in step.
KNOWN EDGE CASES: The cap counts bytes, not characters; the loader moves the cut back to a whole UTF-8 character, so the shown text can be up to three bytes shorter.
RELATED DOCS: docs/design/coding-agent-agents-md.md; docs/design/coding-agent-map-md.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py and tests/features/coding_agent/test_coding_agent_map_md.py
"""

from __future__ import annotations

# The preferred file name; any case variant is accepted when this exact
# name is absent from the root folder.
CODING_AGENTS_MD_FILE_NAME = "AGENTS.md"

# 32 KiB, Codex's default project-doc cap, so a huge file cannot fill
# the model's context.
CODING_AGENTS_MD_MAX_BYTES = 32_768

# The preferred repository-map file name; any case variant, such as
# map.md, is accepted when this exact name is absent.
CODING_MAP_MD_FILE_NAME = "MAP.md"

# 32 KiB, the same cap as AGENTS.md; a map is meant to be short.
CODING_MAP_MD_MAX_BYTES = 32_768

__all__ = [
    "CODING_AGENTS_MD_FILE_NAME",
    "CODING_AGENTS_MD_MAX_BYTES",
    "CODING_MAP_MD_FILE_NAME",
    "CODING_MAP_MD_MAX_BYTES",
]
