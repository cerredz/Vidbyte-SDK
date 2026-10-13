"""FILE: vidbyte/harnesses/native/claude/sdk.py

PURPOSE: Loads claude-agent-sdk at first use and describes the client methods ClaudeHost calls.
ROLE IN CODEBASE: The one seam between ClaudeHost and the vendor SDK. Every star function of ClaudeHost (host.py) calls ClaudeSdkLoader.load first, and the session, probe, history and tool-server modules use only the ClaudeSdkTypes record it returns. Tests replace load with fakes.
ARCHITECTURE NOTE: The import sits inside load, so importing vidbyte or the Claude tools never imports claude_agent_sdk, and a missing extra surfaces as claude.sdk_unavailable on the first call instead of at import time. Nothing is cached, so a test can block the import and a later call loads again. _ClaudeClient is the Protocol the session and probe type their client with.
COMMON MODIFICATION PATTERNS: A newly needed SDK name adds one name to the import, one ClaudeSdkTypes field (vidbyte/lib/dataclasses/claude_host.py) and one keyword below. A newly needed client method adds one Protocol method.
WHAT NOT TO DO IN THIS FILE: 1. Do not import claude_agent_sdk anywhere else; every other module reads the loaded names from ClaudeSdkTypes. 2. Do not import private SDK modules (_internal) or the unexported MessageParseError; it is still caught as a ClaudeSDKError subclass. 3. Do not cache the loaded record.
KNOWN EDGE CASES: The SDK package imports jsonschema and mcp when it loads, so a broken install of either also reports claude.sdk_unavailable. The pinned range is claude-agent-sdk>=0.2.165,<0.3.0, and the names below are the ones 0.2.165 exports.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from typing import Any, Protocol

from vidbyte.lib.constants.claude import CLAUDE_FAILURE_NEXT_STEPS
from vidbyte.lib.dataclasses.claude_host import ClaudeSdkTypes
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeOperationError


class _ClaudeClient(Protocol):
    """The ClaudeSDKClient methods ClaudeHost calls, so the session and probe never type a client as Any."""

    async def connect(self, prompt: str | AsyncIterable[dict[str, Any]] | None = None) -> None: ...

    async def query(self, prompt: str | AsyncIterable[dict[str, Any]], session_id: str = "default") -> None: ...

    def receive_messages(self) -> AsyncIterator[Any]: ...

    async def interrupt(self) -> None: ...

    async def get_server_info(self) -> dict[str, Any] | None: ...

    async def disconnect(self) -> None: ...


class ClaudeSdkLoader:
    """Imports claude-agent-sdk on demand and returns the names ClaudeHost uses."""

    @staticmethod
    def load() -> ClaudeSdkTypes:
        """Return the loaded SDK names, or raise claude.sdk_unavailable when the extra is missing."""
        # @intent the-only-claude-agent-sdk-import
        # This is the single place claude_agent_sdk is imported, so importing
        # vidbyte never needs the optional extra and a missing extra becomes
        # one semantic error on first use (create_sdk_mcp_server included).
        try:
            from claude_agent_sdk import (
                AgentDefinition,
                AssistantMessage,
                ClaudeAgentOptions,
                ClaudeSDKClient,
                ClaudeSDKError,
                CLIConnectionError,
                CLIJSONDecodeError,
                CLINotFoundError,
                HookMatcher,
                ProcessError,
                RateLimitEvent,
                ResultError,
                ResultMessage,
                TaskNotificationMessage,
                TaskProgressMessage,
                create_sdk_mcp_server,
                fork_session,
                get_session_info,
                get_session_messages,
                list_sessions,
                tool,
            )
        except ImportError as exc:
            raise ClaudeOperationError(
                "Loading claude_agent_sdk failed with ImportError; the optional claude extra is missing or incomplete.",
                failure_code=FailureCode.CLAUDE_SDK_UNAVAILABLE.value,
                operation="load_sdk",
                next_step=CLAUDE_FAILURE_NEXT_STEPS[FailureCode.CLAUDE_SDK_UNAVAILABLE.value],
            ) from exc
        return ClaudeSdkTypes(
            client_class=ClaudeSDKClient,
            options_class=ClaudeAgentOptions,
            agent_definition_class=AgentDefinition,
            hook_matcher_class=HookMatcher,
            create_sdk_mcp_server=create_sdk_mcp_server,
            tool=tool,
            list_sessions=list_sessions,
            get_session_info=get_session_info,
            get_session_messages=get_session_messages,
            fork_session=fork_session,
            assistant_message=AssistantMessage,
            result_message=ResultMessage,
            rate_limit_event=RateLimitEvent,
            task_progress_message=TaskProgressMessage,
            task_notification_message=TaskNotificationMessage,
            sdk_error=ClaudeSDKError,
            cli_not_found_error=CLINotFoundError,
            cli_connection_error=CLIConnectionError,
            process_error=ProcessError,
            result_error=ResultError,
            cli_json_decode_error=CLIJSONDecodeError,
        )


__all__ = ["ClaudeSdkLoader"]
