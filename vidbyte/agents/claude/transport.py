"""FILE: vidbyte/agents/claude/transport.py

PURPOSE: Owns one bounded claude-agent-sdk query, its message stream, and its teardown.
ROLE IN CODEBASE: The agent facade calls this single wire operation once per turn.
ARCHITECTURE NOTE: Translation precedes the SDK call; stream accumulation follows it.
COMMON MODIFICATION PATTERNS: Keep failures specific to their lifecycle boundary.
KNOWN EDGE CASES: A single-shot query raises AFTER yielding its error result message.
RELATED DOCS: docs/design/claude-harness-agent.md; https://code.claude.com/docs/en/agent-sdk/sessions.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from vidbyte.agents.claude.config import ClaudeContentTranslator
from vidbyte.agents.claude.result import ClaudeResultSerializer, ClaudeStreamAccumulator
from vidbyte.lib.constants.claude import CLAUDE_SDK_EXTRA
from vidbyte.lib.dataclasses.claude import (
    ClaudeRunResult,
    ClaudeSdkTypes,
    ClaudeTransportRunRequest,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeAgentError


class ClaudeTransport:
    """Owns the Claude CLI subprocess, its message stream, and one turn's lifetime."""

    async def run(self, request: ClaudeTransportRunRequest) -> ClaudeRunResult:
        # @intent one-turn-one-bounded-process
        # This method owns the whole provider lifetime for a turn, so every success,
        # failure, and cancellation path has exactly one place that closes it.
        sdk = self._load_sdk()
        options = self._build_options(sdk, request)
        return await self._drain(sdk, options, request)

    @staticmethod
    def _build_options(sdk: ClaudeSdkTypes, request: ClaudeTransportRunRequest) -> Any:
        # @intent reject-options-before-spawning
        # An option the SDK refuses must fail while nothing is running; discovering it
        # after launch leaves a subprocess to clean up and a vaguer failure code.
        try:
            return sdk.options(
                **ClaudeContentTranslator.option_kwargs(
                    request.system_prompt,
                    request.session_id,
                    request.settings,
                    request.output_schema,
                )
            )
        # SDK option constructors can reject values before a native query starts.
        except Exception as exc:
            raise ClaudeAgentError(
                "Claude settings could not be translated for the SDK.",
                failure_code=FailureCode.CLAUDE_CONTENT_TRANSLATION_FAILED.value,
                operation="translate_options",
                error_type=type(exc).__name__,
            ) from exc

    async def _drain(
        self, sdk: ClaudeSdkTypes, options: Any, request: ClaudeTransportRunRequest
    ) -> ClaudeRunResult:
        # @intent keep-the-session-id-across-the-raise
        # A single-shot query raises AFTER yielding its error result, so returning the
        # accumulated result is the only way a caller can resume from a turn or budget
        # ceiling; discarding it here strands that conversation permanently.
        accumulator = ClaudeStreamAccumulator()
        stream = sdk.query(prompt=request.prompt.user_prompt, options=options)
        try:
            async for message in stream:
                accumulator.consume(message, sdk)
        # Caller cancellation must retain asyncio semantics while the subprocess closes.
        except asyncio.CancelledError:
            raise
        # The provider raises on failed runs, protocol faults, and lost connections.
        except Exception as exc:
            if not accumulator.has_result:
                raise self._failure(exc, sdk, bool(request.session_id)) from exc
        finally:
            await self._close(stream)
        return self._serialize(accumulator)

    @staticmethod
    def _serialize(accumulator: ClaudeStreamAccumulator) -> ClaudeRunResult:
        # Freezes the accumulated stream, keeping normalization failures distinguishable.
        try:
            return ClaudeResultSerializer.from_stream(accumulator)
        # The serializer already classified missing or unusable provider results.
        except ClaudeAgentError:
            raise
        # A mismatched SDK result contract can fail during typed field conversion.
        except Exception as exc:
            raise ClaudeAgentError(
                "Claude returned a result that could not be normalized.",
                failure_code=FailureCode.CLAUDE_RESPONSE_INVALID.value,
                operation="normalize_result",
                error_type=type(exc).__name__,
            ) from exc

    @staticmethod
    async def _close(stream: object) -> None:
        # @intent never-leak-the-cli-subprocess
        # Leaving an async generator unclosed keeps the CLI process and its task group
        # alive, so aclose is the only guaranteed teardown on every exit path.
        closer = getattr(stream, "aclose", None)
        if closer is None:
            return
        # This runs in a finally block, so raising here would discard the caller's real
        # error or result; a failed teardown is reported by the process exiting, not here.
        with contextlib.suppress(Exception):
            await closer()

    @classmethod
    def _failure(
        cls, exc: Exception, sdk: ClaudeSdkTypes, resumed: bool
    ) -> ClaudeAgentError:
        # @intent separate-setup-faults-from-model-faults
        # A missing CLI, an unreachable process, and a stale session id each need a
        # different repair, so collapsing them into one query failure hides the fix.
        codes = (
            (sdk.cli_not_found_error, FailureCode.CLAUDE_CLI_NOT_FOUND),
            (sdk.cli_connection_error, FailureCode.CLAUDE_CONNECTION_FAILED),
            (sdk.process_error, FailureCode.CLAUDE_PROCESS_FAILED),
            (sdk.cli_json_decode_error, FailureCode.CLAUDE_RESPONSE_INVALID),
        )
        for error_type, code in codes:
            if isinstance(exc, error_type):
                return cls._error(code, "query_run", exc)
        if resumed:
            return cls._error(
                FailureCode.CLAUDE_SESSION_RESUME_FAILED, "session_resume", exc
            )
        return cls._error(FailureCode.CLAUDE_QUERY_FAILED, "query_run", exc)

    @staticmethod
    def _error(code: FailureCode, operation: str, exc: Exception) -> ClaudeAgentError:
        # Builds one safe adapter error carrying no provider exception text.
        messages = {
            FailureCode.CLAUDE_CLI_NOT_FOUND: "Claude Code CLI could not be found.",
            FailureCode.CLAUDE_CONNECTION_FAILED: "Claude Code CLI could not be reached.",
            FailureCode.CLAUDE_PROCESS_FAILED: "Claude Code CLI exited with an error.",
            FailureCode.CLAUDE_RESPONSE_INVALID: "Claude returned output that could not be parsed.",
            FailureCode.CLAUDE_SESSION_RESUME_FAILED: "Claude failed to resume the requested session.",
            FailureCode.CLAUDE_QUERY_FAILED: "Claude failed to execute the requested query.",
        }
        return ClaudeAgentError(
            messages[code],
            failure_code=code.value,
            operation=operation,
            error_type=type(exc).__name__,
        )

    @staticmethod
    def _load_sdk() -> ClaudeSdkTypes:
        # Imports the optional integration lazily so the base install stays importable.
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ClaudeSDKError,
                CLIConnectionError,
                CLIJSONDecodeError,
                CLINotFoundError,
                ProcessError,
                ResultMessage,
                SystemMessage,
                TextBlock,
                ThinkingBlock,
                ToolResultBlock,
                ToolUseBlock,
                query,
            )
        # The optional extra may be absent, or an incompatible SDK may lack these names.
        except ImportError as exc:
            raise ClaudeAgentError(
                f"ClaudeHarnessAgent requires the optional '{CLAUDE_SDK_EXTRA}' integration.",
                failure_code=FailureCode.CLAUDE_SDK_UNAVAILABLE.value,
                operation="load_sdk",
                error_type=type(exc).__name__,
            ) from exc
        return ClaudeSdkTypes(
            query=query,
            options=ClaudeAgentOptions,
            assistant_message=AssistantMessage,
            system_message=SystemMessage,
            result_message=ResultMessage,
            text_block=TextBlock,
            thinking_block=ThinkingBlock,
            tool_use_block=ToolUseBlock,
            tool_result_block=ToolResultBlock,
            sdk_error=ClaudeSDKError,
            cli_not_found_error=CLINotFoundError,
            cli_connection_error=CLIConnectionError,
            process_error=ProcessError,
            cli_json_decode_error=CLIJSONDecodeError,
        )


__all__ = ["ClaudeTransport"]
