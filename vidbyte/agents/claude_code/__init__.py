"""FILE: vidbyte/agents/claude_code/__init__.py

PURPOSE: Exposes the public surface of the Claude Code harness agent: ClaudeCodeHarnessAgent, ClaudeCodeHarnessAgentSettings, the ClaudeCodeRunInput, ClaudeCodeImage, ClaudeCodeRunResult and ClaudeCodeUsage records, the ClaudeCodeEffort and ClaudeCodeFailureKind enums and ClaudeCodeAgentError.
ROLE IN CODEBASE: The import path the cross-repo suggest-BYOK contract names (`from vidbyte.agents.claude_code import ...`). vidbyte/agents/__init__.py and the root vidbyte package re-export the same names, which is the path vidbyte-cli uses, because its lint rule C028 accepts only root imports.
ARCHITECTURE NOTE: Re-exports only. The records, enums and error are defined in vidbyte/lib (dataclasses/claude_code.py, enums/claude_code.py, errors/base.py) and the settings in this package's settings.py, per the AGENTS.md placement rules.
COMMON MODIFICATION PATTERNS: A new public name joins this __all__, vidbyte/agents/__init__.py, vidbyte/__init__.py, and then contracts/sdk-public-api.json is regenerated (scripts/generate-sdk-public-api.py).
KNOWN EDGE CASES: Importing this package starts nothing: no process runs and no folder is made until the first arun.
RELATED DOCS: vidbyte/agents/claude_code/README.md; docs/design/claude-code-harness-agent.md
TESTS: tests/features/claude_code_agent/test_claude_code_surface.py
"""

from vidbyte.agents.claude_code.agent import ClaudeCodeHarnessAgent
from vidbyte.agents.claude_code.settings import ClaudeCodeHarnessAgentSettings
from vidbyte.lib.dataclasses.claude_code import (
    ClaudeCodeImage,
    ClaudeCodeRunInput,
    ClaudeCodeRunResult,
    ClaudeCodeUsage,
)
from vidbyte.lib.enums.claude_code import ClaudeCodeEffort, ClaudeCodeFailureKind
from vidbyte.lib.errors import ClaudeCodeAgentError

__all__ = [
    "ClaudeCodeAgentError",
    "ClaudeCodeEffort",
    "ClaudeCodeFailureKind",
    "ClaudeCodeHarnessAgent",
    "ClaudeCodeHarnessAgentSettings",
    "ClaudeCodeImage",
    "ClaudeCodeRunInput",
    "ClaudeCodeRunResult",
    "ClaudeCodeUsage",
]
