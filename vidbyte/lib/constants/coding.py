"""FILE: vidbyte/lib/constants/coding.py

PURPOSE: Defines the fixed AGENTS.md file name and byte cap that CodingAgent uses when it loads a repository's AGENTS.md into the model's context, and the line and byte caps on the output tail it shows for a failed setup command.
ROLE IN CODEBASE: Read by AgentsMdLoader (vidbyte/agents/coding_context/agents_md.py), SetupCommandsLoader (vidbyte/agents/coding_context/setup_commands.py), and the coding-agent feature tests.
ARCHITECTURE NOTE: Immutable constants only; the loaders own the reading, decoding, and truncation behavior.
COMMON MODIFICATION PATTERNS: Change the cap here, never at the read call, so the loader, its truncation line, and the tests stay in step.
KNOWN EDGE CASES: The AGENTS.md cap counts bytes, not characters; the loader moves the cut back to a whole UTF-8 character, so the shown text can be up to three bytes shorter. The setup-output byte cap can cut the first shown line, or a character in it.
RELATED DOCS: docs/design/coding-agent-agents-md.md; docs/design/coding-agent-setup-commands.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py and tests/features/coding_agent/test_coding_agent_setup_commands.py
"""

from __future__ import annotations

# The preferred file name; any case variant is accepted when this exact
# name is absent from the root folder.
CODING_AGENTS_MD_FILE_NAME = "AGENTS.md"

# 32 KiB, Codex's default project-doc cap, so a huge file cannot fill
# the model's context.
CODING_AGENTS_MD_MAX_BYTES = 32_768

# A failed setup command shows at most this many of its last output
# lines, taken from at most this many of its last output bytes, so one
# huge line cannot fill the model's context either. Errors are at the
# end, so the tail is the useful part.
CODING_SETUP_OUTPUT_TAIL_LINES = 30
CODING_SETUP_OUTPUT_TAIL_BYTES = 8_192

__all__ = [
    "CODING_AGENTS_MD_FILE_NAME",
    "CODING_AGENTS_MD_MAX_BYTES",
    "CODING_SETUP_OUTPUT_TAIL_BYTES",
    "CODING_SETUP_OUTPUT_TAIL_LINES",
]
