"""FILE: vidbyte/agents/claude_code/agent.py

PURPOSE: Defines ClaudeCodeHarnessAgent, an agent object that is one Claude Code conversation on the user's machine: its first arun starts a session in Claude Code's print mode (--session-id with a fresh UUID), every later arun resumes that session (--resume), and each run returns a ClaudeCodeRunResult with the structured output, the final text, the session id, this run's token usage and cost as Claude Code reported them, and the model that answered.
ROLE IN CODEBASE: The public facade of vidbyte.agents.claude_code, re-exported from vidbyte.agents and the root vidbyte package. vidbyte-cli's `agents suggest` runs every generator and critic turn of an Anthropic user through it (the bring-your-own-key path), as it runs Codex turns through CodexHarnessAgent. It coordinates ClaudeCodeLauncher, ClaudeCodeWorkspace, ClaudeCodeCommand, CliRunner (vidbyte/lib/process) and ClaudeCodeWire, and builds one ClaudeCodeFailures per run.
ARCHITECTURE NOTE: The user's own `claude` runs every model turn under the user's own login or API key, so Anthropic bills the user; this SDK only starts the process. Each run is one process: prompt and images go in on stdin as one stream-json message, the instructions through a private --system-prompt-file, and the process inherits the caller's environment minus the variables a parent Claude Code session sets (CLAUDE_CODE_PARENT_SESSION_VARIABLES). One semaphore per agent serializes runs, because the session id and the running cost total are written after the process exits (the SDK bans asyncio.Lock).
COMMON MODIFICATION PATTERNS: A new per-run step goes into arun() with its narration, calling one helper class; keep arun the only place that orders the steps. A new setting reaches the command line through ClaudeCodeCommandRequest and ClaudeCodeCommand.argv.
WHAT NOT TO DO IN THIS FILE: 1. Do not change os.environ; removals go through CliInvocation.env_remove. 2. Do not set session_id before a run succeeds: a failed first run starts a fresh session next time. 3. Do not run Claude Code with --bare, which ignores the Claude login. 4. Do not swallow cancellation; CliRunner stops the process tree and the instructions file is still removed.
KNOWN EDGE CASES: A run cancelled or failed after launch leaves session_id unchanged. close() forgets the session when it removes the agent's own temporary folder, because Claude Code finds a session only from its folder. An agent built with a saved session_id has no cost baseline, so its first run's cost_usd is None only when Claude Code also omits the per-run cost.
RELATED DOCS: docs/design/claude-code-harness-agent.md; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/test_claude_code_agent.py, tests/features/claude_code_agent/test_claude_code_failures.py, tests/features/claude_code_agent/test_claude_code_live.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from vidbyte.agents.claude_code.command import ClaudeCodeCommand
from vidbyte.agents.claude_code.failures import ClaudeCodeFailures
from vidbyte.agents.claude_code.launcher import ClaudeCodeLauncher
from vidbyte.agents.claude_code.settings import ClaudeCodeHarnessAgentSettings
from vidbyte.agents.claude_code.wire import ClaudeCodeWire
from vidbyte.agents.claude_code.workspace import ClaudeCodeWorkspace
from vidbyte.lib.constants.claude_code import (
    CLAUDE_CODE_IMAGE_MEDIA_TYPES,
    CLAUDE_CODE_MAX_CONCURRENT_RUNS,
    CLAUDE_CODE_MAX_OUTPUT_BYTES,
    CLAUDE_CODE_PARENT_SESSION_VARIABLES,
    CLAUDE_CODE_WINDOWS_COMMAND_LINE_MAX_UNITS,
    CLAUDE_CODE_WINDOWS_PLATFORM,
)
from vidbyte.lib.dataclasses.claude_code import (
    ClaudeCodeCommandRequest,
    ClaudeCodeRunInput,
    ClaudeCodeRunResult,
    ClaudeCodeWireRequest,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOutcome
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.claude_code import ClaudeCodeFailureKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.process import CliRunner


class ClaudeCodeHarnessAgent:
    """One Claude Code conversation: the first arun starts it, every later arun continues it."""

    def __init__(self, settings: ClaudeCodeHarnessAgentSettings) -> None:
        self.settings: ClaudeCodeHarnessAgentSettings = RecordFieldConverter.require_instance(settings, "settings", ClaudeCodeHarnessAgentSettings)
        # The session this agent continues; None until its first run succeeds,
        # unless the settings name a saved session to resume.
        self.session_id: str | None = self.settings.session_id
        # Claude Code's running cost total for the session, the baseline of the
        # next run's cost when Claude Code omits its per-run cost. A new session
        # starts at zero; a saved one has no known total yet.
        self._session_cost_usd: float | None = None if self.settings.session_id else 0.0
        self._workspace = ClaudeCodeWorkspace(self.settings.workspace)
        self._runs = asyncio.Semaphore(CLAUDE_CODE_MAX_CONCURRENT_RUNS)

    @property
    def name(self) -> str:
        """The agent's name from its settings."""
        return self.settings.name

    @property
    def workspace(self) -> Path | None:
        """The folder Claude Code runs in, or None before the first run when the agent makes its own."""
        return self._workspace.folder

    async def arun(self, request: ClaudeCodeRunInput | str) -> ClaudeCodeRunResult:
        # @intent one-subprocess-run-per-turn-on-one-session
        # Each turn is one `claude` process on this agent's session. Checks
        # that need no process run first, so a bad attachment or a missing
        # install never starts anything; the session id is kept only after a
        # run succeeds, so a failed first run starts cleanly next time.
        run_input = ClaudeCodeRunInput(prompt=request) if isinstance(request, str) else RecordFieldConverter.require_instance(request, "request", ClaudeCodeRunInput)
        failures = ClaudeCodeFailures()
        async with self._runs:
            # Refuse an attachment Claude Code cannot take before anything starts.
            self._refuse_unsupported_attachments(run_input, failures)

            # Find the user's claude executable.
            launcher = ClaudeCodeLauncher.resolve(self.settings.claude_bin, failures)

            # Continue this agent's session, or start one under a new id.
            resume = self.session_id is not None
            session_id = self.session_id or str(uuid.uuid4())

            # Run in the agent's folder, so a resume finds the session's
            # transcript, with the instructions in a private file.
            folder = await asyncio.to_thread(self._workspace.ensure)
            instructions = await asyncio.to_thread(ClaudeCodeWorkspace.write_instructions, self.settings.instructions)
            try:
                argv = ClaudeCodeCommand.argv(
                    ClaudeCodeCommandRequest(
                        launcher=launcher,
                        instructions_file=instructions,
                        allowed_tools=self.settings.allowed_tools,
                        model=self.settings.model,
                        effort=self.settings.effort,
                        output_schema_json=self.settings.output_schema_json,
                        session_id=session_id,
                        resume=resume,
                    )
                )
                # Windows cannot start a command line past its length limit.
                self._refuse_long_command_line(argv, failures)

                # Run claude once, headless, with the message on stdin and the
                # parent session's variables left out of its environment.
                outcome = await CliRunner().run(
                    CliInvocation(
                        argv=argv,
                        env_overlay={},
                        timeout_seconds=self.settings.timeout_seconds,
                        max_output_bytes=CLAUDE_CODE_MAX_OUTPUT_BYTES,
                        cwd=folder,
                        stdin_text=ClaudeCodeCommand.stdin(run_input),
                        env_remove=CLAUDE_CODE_PARENT_SESSION_VARIABLES,
                    )
                )
            finally:
                # The instructions file is removed whatever happened, cancellation included.
                await asyncio.to_thread(ClaudeCodeWorkspace.remove_instructions, instructions)

            # A program the operating system would not start counts as not installed.
            self._refuse_launch_failure(outcome, launcher, failures)

            # Read the answer, or raise what the outcome means.
            result = ClaudeCodeWire.read(
                ClaudeCodeWireRequest(
                    outcome=outcome,
                    session_id=session_id,
                    expects_output=self.settings.output_schema is not None,
                    allowed_tools=self.settings.allowed_tools,
                    previous_session_cost_usd=self._session_cost_usd,
                    timeout_seconds=self.settings.timeout_seconds,
                ),
                failures,
            )

            # Keep the session, and its running cost total, for the next run.
            self.session_id = result.session_id
            self._session_cost_usd = result.session_cost_usd
            return result

    def run(self, request: ClaudeCodeRunInput | str) -> ClaudeCodeRunResult:
        """Run one turn from synchronous code; inside an event loop, await arun() instead."""
        # @intent no-nested-event-loop
        # asyncio.run inside a running loop fails after partly preparing the
        # run, so the synchronous twin refuses that case up front.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(request))
        raise ConfigurationError("ClaudeCodeHarnessAgent.run() cannot be called inside a running event loop; use await agent.arun(...).", details={"field": "run"})

    def close(self) -> None:
        """Remove the temporary folder this agent made; its session cannot be resumed afterwards."""
        if self._workspace.owned and self._workspace.folder is not None:
            self._workspace.close()
            self.session_id = None
            self._session_cost_usd = 0.0

    @staticmethod
    def _refuse_unsupported_attachments(run_input: ClaudeCodeRunInput, failures: ClaudeCodeFailures) -> None:
        # Claude Code takes png, jpeg, gif and webp images; anything else is
        # named before a process starts. Text files are the caller's to inline.
        unsupported = ClaudeCodeCommand.unsupported_media_types(run_input)
        if unsupported:
            raise failures.failure(ClaudeCodeFailureKind.UNSUPPORTED_INPUT, f"The run input holds attachments of type {', '.join(unsupported)}, which Claude Code cannot take; it accepts {', '.join(CLAUDE_CODE_IMAGE_MEDIA_TYPES)} images.")

    @staticmethod
    def _refuse_long_command_line(argv: tuple[str, ...], failures: ClaudeCodeFailures) -> None:
        # The prompt and instructions never reach argv, so only a very large
        # output_schema can pass the Windows limit; that is refused, not launched.
        if sys.platform != CLAUDE_CODE_WINDOWS_PLATFORM:
            return
        units = ClaudeCodeCommand.windows_command_line_units(argv)
        if units > CLAUDE_CODE_WINDOWS_COMMAND_LINE_MAX_UNITS:
            raise failures.failure(ClaudeCodeFailureKind.UNSUPPORTED_INPUT, f"The Claude Code command line would be {units} UTF-16 units long, above the Windows limit of {CLAUDE_CODE_WINDOWS_COMMAND_LINE_MAX_UNITS}; output_schema is too large to pass on it.")

    @staticmethod
    def _refuse_launch_failure(outcome: CliOutcome, launcher: tuple[str, ...], failures: ClaudeCodeFailures) -> None:
        # The file was found but the operating system would not start it.
        if outcome.launch_failure is None:
            return
        program, *_arguments = launcher
        raise failures.failure(ClaudeCodeFailureKind.NOT_INSTALLED, f"The operating system could not start {program} ({outcome.launch_failure.value}).")


__all__ = ["ClaudeCodeHarnessAgent"]
