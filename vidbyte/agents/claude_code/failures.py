"""FILE: vidbyte/agents/claude_code/failures.py

PURPOSE: Defines ClaudeCodeFailures, which builds every ClaudeCodeAgentError the Claude Code harness agent raises: it looks up the likely cause and next step written for the failure kind, quotes Claude Code's own text only after scrubbing it, and composes one message that says what happened, what Claude Code said, why it likely happened and what to do next.
ROLE IN CODEBASE: One instance per run, built by ClaudeCodeHarnessAgent.arun (agent.py) and handed to ClaudeCodeLauncher (launcher.py) and ClaudeCodeWire (wire.py), which decide the kind; this class only builds the error. The texts live in vidbyte/lib/constants/claude_code.py (CLAUDE_CODE_FAILURE_TEXTS); the error class in vidbyte/lib/errors/base.py.
ARCHITECTURE NOTE: Scrubbing runs in a fixed order on the full text before it is cut: the values of the credential variables present in this process's environment (CLAUDE_CODE_CREDENTIAL_VARIABLES) are replaced first, longest first, so a cut can never leave half a key; then the shared HarnessRedactor masks credential assignments; then any sk-ant- token is masked; then the last CLAUDE_CODE_VENDOR_TEXT_MAX_CHARS characters are kept, because Claude Code prints its final error last.
COMMON MODIFICATION PATTERNS: A new failure kind needs only its CLAUDE_CODE_FAILURE_TEXTS entry; the caller passes the kind and the sentence saying what happened.
WHAT NOT TO DO IN THIS FILE: 1. Do not quote a prompt, the instructions, image data or an environment value in a message. 2. Do not cut the text before scrubbing it. 3. Do not raise from failure(); it returns the error for the caller to raise, so a builder fault can never hide the original problem.
KNOWN EDGE CASES: Empty vendor text adds no quote. The credential values are read when the instance is built (once per run), so a key exported after the run started is not known; the sk-ant- mask still catches an Anthropic key.
RELATED DOCS: docs/design/claude-code-harness-agent.md section 6.6; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/test_claude_code_failures.py
"""

from __future__ import annotations

import os
import re

from vidbyte.harnesses.serialization import HarnessRedactor
from vidbyte.lib.constants.claude_code import (
    CLAUDE_CODE_ANTHROPIC_CREDENTIAL_SHAPE,
    CLAUDE_CODE_CREDENTIAL_VARIABLES,
    CLAUDE_CODE_FAILURE_TEXTS,
    CLAUDE_CODE_REDACTED,
    CLAUDE_CODE_VENDOR_TEXT_MAX_CHARS,
)
from vidbyte.lib.enums.claude_code import ClaudeCodeFailureKind
from vidbyte.lib.errors import ClaudeCodeAgentError


class ClaudeCodeFailures:
    """Builds the scrubbed, self-explaining ClaudeCodeAgentError values of one run."""

    def __init__(self) -> None:
        # @intent remember-every-credential-value-before-claude-runs
        # Claude Code inherits this environment, so any key it holds could be
        # echoed back in an API error; its values are known before the run
        # and replaced in every quote, longest first.
        values = {os.environ.get(name, "") for name in CLAUDE_CODE_CREDENTIAL_VARIABLES}
        self._secrets = tuple(sorted((value for value in values if value), key=len, reverse=True))
        self._redactor = HarnessRedactor()
        self._token = re.compile(CLAUDE_CODE_ANTHROPIC_CREDENTIAL_SHAPE)

    def failure(self, kind: ClaudeCodeFailureKind, what: str, *, session_id: str | None = None, exit_code: int | None = None, vendor_text: str = "", error_type: str = "") -> ClaudeCodeAgentError:
        # @intent every-claude-code-error-says-what-and-what-next
        # A caller (vidbyte-cli prints str(error)) must learn from the message
        # alone what happened and what to do, so the message is the sentence
        # the caller wrote, Claude Code's own scrubbed words, the likely cause
        # and the next step, in that order.
        likely_cause, next_step = CLAUDE_CODE_FAILURE_TEXTS[kind]
        quoted = self.scrub(vendor_text)
        parts = [what]
        if quoted:
            parts.append(f'Claude Code said: "{quoted}".')
        parts.append(f"Likely cause: {likely_cause}")
        parts.append(f"Next step: {next_step}")
        return ClaudeCodeAgentError(" ".join(parts), kind=kind, likely_cause=likely_cause, next_step=next_step, session_id=session_id, exit_code=exit_code, error_type=error_type)

    def scrub(self, text: str) -> str:
        # @intent redact-secrets-before-the-cut
        # Known secret values go first, on the whole text, so the cut cannot
        # split one; then credential assignments and sk-ant- tokens; then the
        # tail is kept, where Claude Code prints its final error.
        for secret in self._secrets:
            text = text.replace(secret, CLAUDE_CODE_REDACTED)
        text = str(self._redactor.redact(text))
        text = self._token.sub(CLAUDE_CODE_REDACTED, text)
        return text.strip()[-CLAUDE_CODE_VENDOR_TEXT_MAX_CHARS:]


__all__ = ["ClaudeCodeFailures"]
