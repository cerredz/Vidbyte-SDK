"""FILE: vidbyte/lib/constants/coding.py

PURPOSE: Defines the named bounds of CodingAgent's verification command: the default and the smallest allowed number of verification attempts.
ROLE IN CODEBASE: Read by vidbyte/lib/dataclasses/coding.py (CodingAgentSettings and CodingVerification checks) and by vidbyte/agents/coding.py (the max_verify_attempts default).
ARCHITECTURE NOTE: This module contains immutable constants only; the verification itself lives in vidbyte/middleware/builtins/verify_command.py.
COMMON MODIFICATION PATTERNS: Add a named constant here before introducing another CodingAgent policy literal.
KNOWN EDGE CASES: The default is a count of command runs, not of retries: 3 means the third failed run ends the run.
RELATED DOCS: docs/design/coding-agent-verify-command.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_verify_command.py
"""

from __future__ import annotations

CODING_DEFAULT_MAX_VERIFY_ATTEMPTS = 3
CODING_MIN_VERIFY_ATTEMPTS = 1

__all__ = [
    "CODING_DEFAULT_MAX_VERIFY_ATTEMPTS",
    "CODING_MIN_VERIFY_ATTEMPTS",
]
