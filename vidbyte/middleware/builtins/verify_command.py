"""FILE: vidbyte/middleware/builtins/verify_command.py

PURPOSE: Defines VerifyCommandMiddleware, which runs CodingAgent's verification command once at every finish attempt and lets the run end only when the command exits with code 0; otherwise it sends the failure back to the model, and after the last allowed attempt it ends the run with the model's answer marked as not verified.
ROLE IN CODEBASE: Built by vidbyte/agents/coding.py (CodingAgent.__init__) from a validated CodingAgentSettings and appended after the caller's middleware; called by vidbyte/agents/runtime.py through MiddlewarePipeline.review_finish on both finish paths, after the output contracts. Runs the command through vidbyte/tools/builtins/bash.py (BashTool). Not re-exported from vidbyte.middleware.builtins.
ARCHITECTURE NOTE: review_finish is the narrated main function. The command runs through BashTool.execute, so the Git for Windows lookup, the time limit, the output cap, and the kill on timeout or cancellation are the bash tool's own, with its BASH_* constants read at call time. Per-run state is one CodingVerification kept in the run's run_state, so attempts never leak between runs, forks, or concurrent runs that share this instance. The outcome is published as result metadata through AgentRuntimeStateKey.RESULT_METADATA.
FUNCTION INVENTORY: __init__ builds the bash tool over the root folder and fails when there is no bash; review_finish runs the command and returns the FinishReview; _record_attempt counts the run and keeps its exit code; _publish writes metadata["verify_command"]; _feedback builds the message the model reads.
COMMON MODIFICATION PATTERNS: Change what the model reads in VERIFY_COMMAND_FEEDBACK and _feedback together; change what callers read in _publish and in vidbyte/agents/README.md (Coding Agent) together.
WHAT NOT TO DO IN THIS FILE: 1. Do not sanitize, quote, or restrict the command; the developer wrote it, not the model. 2. Do not route it through the agent's tool loop or permission policy; it is not a model tool call and must not appear in tool_call_states. 3. Do not catch CancelledError or other exceptions around the command; a cancelled run must stop the command and stay cancelled. 4. Do not keep per-run counters on the instance.
KNOWN EDGE CASES: Exit code 0 is the only pass; a timeout or a spawn failure has no exit code and counts as a failure. The command runs even under a read-only PermissionPolicy, and like the bash tool it is not confined to the root folder. On Windows a timed-out command may keep running after the call returns (BashTool EC-14). BashTool resolves bash once, at construction, so a missing bash fails here instead of failing every finish attempt.
RELATED DOCS: docs/design/coding-agent-verify-command.md; vidbyte/agents/README.md (Coding Agent); vidbyte/middleware/README.md
TESTS: tests/features/coding_agent/test_coding_agent_verify_command.py
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vidbyte.lib.dataclasses.agents import FinishReview
from vidbyte.lib.dataclasses.coding import CodingVerification
from vidbyte.lib.dataclasses.middleware import MiddlewareContext
from vidbyte.lib.enums import AgentRuntimeStateKey
from vidbyte.lib.errors import ConfigurationError
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.tools.builtins.bash import BashTool
from vidbyte.tools.types import ToolCall, ToolResult

VERIFY_COMMAND_FEEDBACK = "Not done yet: the verification command `{command}` failed ({reason}). Its output is below. Fix the problem, then finish again.\n\n{output}"
VERIFY_COMMAND_METADATA_KEY = "verify_command"


class VerifyCommandMiddleware(AgentMiddleware):
    """Runs one verification command at every finish attempt and accepts the finish only when it exits with code 0."""

    def __init__(self, command: str, root_dir: Path, max_attempts: int) -> None:
        # Keep the command and the attempt limit, which
        # CodingAgentSettings has already checked, and build one bash
        # tool over the root folder.
        self._command = command
        self._max_attempts = max_attempts
        self._bash = BashTool(root_dir)

        # @intent missing-bash-fails-at-construction
        # The bash tool looks for bash once, here, so without one every
        # verification would fail and the run could only end unverified
        # after wasting max_attempts model turns. Fail now instead.
        if self._bash.executable is None:
            hint = "Install Git for Windows and put git on PATH." if sys.platform == "win32" else "Install bash and put it on PATH."
            raise ConfigurationError(f"CodingAgent verify_command needs bash, but none was found. {hint}", details={"parameter": "verify_command"})

    async def review_finish(self, ctx: MiddlewareContext) -> FinishReview:
        """Run the verification command once, and accept the finish attempt only when it exits with code 0."""
        # Run the command the way the bash tool runs a model's command:
        # the same bash, in the root folder, under the same time limit
        # and output cap. It is not a model tool call, so it skips the
        # permission policy and never shows up in tool_call_states.
        result = await self._bash.execute(ToolCall("bash", {"command": self._command}))

        # Count this attempt, keep its exit code, and publish both, so
        # the result shows the outcome even if a budget ends the run.
        verification = self._record_attempt(ctx.run_state, result)
        self._publish(ctx.run_state, verification)

        # A zero exit code lets the run finish with the model's answer.
        if verification.passed:
            return FinishReview.accept()

        # Otherwise tell the model what failed and send it back to
        # work. After the last allowed attempt the run ends instead,
        # with the model's answer and a stop reason saying it was not
        # verified.
        feedback = self._feedback(result)
        if verification.attempts >= self._max_attempts:
            return FinishReview.stop(feedback)
        return FinishReview.continue_with(feedback)

    def _record_attempt(self, run_state: dict[Any, Any], result: ToolResult) -> CodingVerification:
        """Store and return this run's verification record with one more attempt and this result's exit code."""
        previous = run_state.get(type(self))
        attempts = previous.attempts + 1 if isinstance(previous, CodingVerification) else 1
        exit_code = result.metadata.get("exit_code")
        verification = CodingVerification(attempts=attempts, last_exit_code=exit_code if isinstance(exit_code, int) else None)
        run_state[type(self)] = verification
        return verification

    @staticmethod
    def _publish(run_state: dict[Any, Any], verification: CodingVerification) -> None:
        """Merge metadata["verify_command"] into the result metadata the runtime lifts from run_state."""
        key = AgentRuntimeStateKey.RESULT_METADATA.value
        published = run_state.get(key)
        base = dict(published) if isinstance(published, Mapping) else {}
        run_state[key] = {**base, VERIFY_COMMAND_METADATA_KEY: {"passed": verification.passed, "attempts": verification.attempts, "last_exit_code": verification.last_exit_code}}

    def _feedback(self, result: ToolResult) -> str:
        """Return the message the model reads: the command, why it failed, and the bash tool's output."""
        # The bash tool's output already ends with its own exit-code,
        # truncation, or time-limit line, so it is passed on unchanged.
        exit_code = result.metadata.get("exit_code")
        if isinstance(exit_code, int):
            reason = f"exit code {exit_code}"
        elif result.metadata.get("error") == "timeout":
            reason = "it timed out"
        else:
            reason = "bash could not start it"
        return VERIFY_COMMAND_FEEDBACK.format(command=self._command, reason=reason, output=result.output or "")


__all__ = ["VerifyCommandMiddleware"]
