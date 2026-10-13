"""FILE: vidbyte/harnesses/native/claude/__init__.py

PURPOSE: Exports ClaudeHost, the host that runs Claude Code turns and offers each Claude Code function as one small method.
ROLE IN CODEBASE: The public import path of the Claude Code harness: `from vidbyte.harnesses.native.claude import ClaudeHost`. The tools in vidbyte/tools/builtins/claude/ and vidbyte/tools/toolsets/claude.py take a ClaudeHost but import it only for type checking.
ARCHITECTURE NOTE: This module only re-exports. Importing it never imports claude_agent_sdk, because the host loads the SDK through ClaudeSdkLoader (sdk.py) only when one of its methods first needs it.
COMMON MODIFICATION PATTERNS: A new public name of the harness is exported here and listed in __all__.
KNOWN EDGE CASES: The package imports without the claude extra installed; only a host method then fails, with claude.sdk_unavailable.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from vidbyte.harnesses.native.claude.host import ClaudeHost

__all__ = ["ClaudeHost"]
