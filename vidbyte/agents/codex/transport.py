"""FILE: vidbyte/agents/codex/transport.py

PURPOSE: Owns the optional Codex app-server client, native threads, and turns.
ROLE IN CODEBASE: Agent and fork collaborators call these bounded wire operations.
ARCHITECTURE NOTE: Translation precedes SDK calls; result normalization follows them.
COMMON MODIFICATION PATTERNS: Keep errors specific to their lifecycle boundary.
WHAT NOT TO DO IN THIS FILE: Swallow cancellation or publish raw exception text.
KNOWN EDGE CASES: SDK run raises on failed turns; client exit may also fail.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/pull/409
TESTS: Offline transport checks and python scripts/run_ci.py.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from vidbyte.agents.codex.config import CodexContentTranslator
from vidbyte.agents.codex.result import CodexResultSerializer
from vidbyte.lib.dataclasses.codex import (
    CodexRunResult,
    CodexSdkTypes,
    CodexThreadIdentity,
    CodexTransportForkRequest,
    CodexTransportRunRequest,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError

if TYPE_CHECKING:
    from openai_codex import TurnResult


class _CodexThread(Protocol):
    id: str

    async def run(self, input: object, **kwargs: object) -> TurnResult: ...


class _CodexClient(Protocol):
    async def thread_start(self, **kwargs: object) -> _CodexThread: ...
    async def thread_resume(self, thread_id: str, **kwargs: object) -> _CodexThread: ...
    async def thread_fork(self, thread_id: str, **kwargs: object) -> _CodexThread: ...


class CodexTransport:
    """Owns Codex app-server process, thread, and turn operations."""

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # @intent bounded-app-server-lifecycle
        # Own the complete client/thread/turn lifetime so every success, failure,
        # and cancellation closes the native app-server connection.
        sdk = self._load_sdk()
        try:
            config = sdk.codex_config(
                **CodexContentTranslator.client_kwargs(request.settings)
            )
            async with sdk.async_codex(config) as client:
                thread = await self._open_thread(client, sdk, request)
                try:
                    sdk_input = CodexContentTranslator.run_input(request.prompt, sdk)
                    turn_kwargs = CodexContentTranslator.turn_kwargs(
                        request.settings, request.output_schema, sdk
                    )
                # SDK input constructors can reject values before a native turn starts.
                except Exception as exc:
                    raise CodexAgentError(
                        "Codex settings or input could not be translated for the SDK.",
                        failure_code=FailureCode.CODEX_CONTENT_TRANSLATION_FAILED.value,
                        operation="translate_turn",
                        error_type=type(exc).__name__,
                    ) from exc
                try:
                    result = await thread.run(sdk_input, **turn_kwargs)
                # Caller cancellation must retain asyncio semantics while the client closes.
                except asyncio.CancelledError:
                    raise
                # SDK execution raises on failed turns, protocol faults, or lost connections.
                except Exception as exc:
                    raise CodexAgentError(
                        "Codex failed to execute the requested turn.",
                        failure_code=FailureCode.CODEX_TURN_FAILED.value,
                        operation="turn_run",
                        error_type=type(exc).__name__,
                    ) from exc
                try:
                    return CodexResultSerializer.from_sdk(thread.id, result)
                # The serializer already classified missing/invalid native responses.
                except CodexAgentError:
                    raise
                # A mismatched SDK result contract can fail during typed field conversion.
                except Exception as exc:
                    raise CodexAgentError(
                        "Codex returned a result that could not be normalized.",
                        failure_code=FailureCode.CODEX_RESPONSE_INVALID.value,
                        operation="normalize_result",
                        error_type=type(exc).__name__,
                    ) from exc
        # Cancellation during client entry, thread opening, or exit is not a provider error.
        except asyncio.CancelledError:
            raise
        # Preserve the inner operation's failure code instead of relabeling it as startup.
        except CodexAgentError:
            raise
        # Client configuration, process startup, and context-manager shutdown can fail here.
        except Exception as exc:
            raise CodexAgentError(
                "Codex app-server could not be started or configured.",
                failure_code=FailureCode.CODEX_THREAD_START_FAILED.value,
                operation="client_start",
                error_type=type(exc).__name__,
            ) from exc

    async def fork_thread(
        self, request: CodexTransportForkRequest
    ) -> CodexThreadIdentity:
        # @intent transport-only-fork
        # Perform only the wire operation here so child policy and state cannot
        # become coupled to optional SDK runtime objects.
        sdk = self._load_sdk()
        try:
            config = sdk.codex_config(
                **CodexContentTranslator.client_kwargs(request.settings)
            )
            async with sdk.async_codex(config) as client:
                kwargs = CodexContentTranslator.thread_fork_kwargs(
                    request.system_prompt, request.settings, sdk
                )
                thread = await client.thread_fork(request.thread_id, **kwargs)
                thread_id = str(thread.id).strip()
                # Without a provider-confirmed id, a child cannot safely resume its fork.
                if not thread_id:
                    raise CodexAgentError(
                        "Codex fork returned no thread id.",
                        failure_code=FailureCode.CODEX_RESPONSE_INVALID.value,
                        operation="thread_fork_result",
                    )
                return CodexThreadIdentity(thread_id=thread_id)
        # Fork cancellation must unwind the client and remain visible to the caller.
        except asyncio.CancelledError:
            raise
        # A malformed fork result already has a more precise response failure code.
        except CodexAgentError:
            raise
        # Native fork/configuration/connection failures belong to the fork operation.
        except Exception as exc:
            raise CodexAgentError(
                "Codex failed to fork the requested thread.",
                failure_code=FailureCode.CODEX_FORK_FAILED.value,
                operation="thread_fork",
                error_type=type(exc).__name__,
            ) from exc

    async def _open_thread(
        self,
        client: _CodexClient,
        sdk: CodexSdkTypes,
        request: CodexTransportRunRequest,
    ) -> _CodexThread:
        # @intent explicit-thread-transition
        # Select exactly one thread transition and preserve its failure identity;
        # a generic open error would make resume recovery indistinguishable.
        operation = "thread_resume" if request.thread_id else "thread_start"
        failure_code = (
            FailureCode.CODEX_THREAD_RESUME_FAILED
            if request.thread_id
            else FailureCode.CODEX_THREAD_START_FAILED
        )
        try:
            if request.thread_id:
                kwargs = CodexContentTranslator.thread_resume_kwargs(
                    request.system_prompt, request.settings, sdk
                )
                return await client.thread_resume(request.thread_id, **kwargs)
            kwargs = CodexContentTranslator.thread_start_kwargs(
                request.system_prompt, request.settings, sdk
            )
            return await client.thread_start(**kwargs)
        # Stopping thread creation/resume must not become a retryable provider failure.
        except asyncio.CancelledError:
            raise
        # Invalid lifecycle settings or a missing/inaccessible saved thread fail here.
        except Exception as exc:
            raise CodexAgentError(
                f"Codex failed during {operation}.",
                failure_code=failure_code.value,
                operation=operation,
                error_type=type(exc).__name__,
            ) from exc

    @staticmethod
    def _load_sdk() -> CodexSdkTypes:
        try:
            from openai_codex import (
                ApprovalMode,
                AsyncCodex,
                CodexConfig,
                ImageInput,
                LocalImageInput,
                MentionInput,
                Sandbox,
                SkillInput,
                TextInput,
            )
            from openai_codex.generated.v2_all import (
                Personality,
                ReasoningEffort,
                ReasoningSummary,
                ThreadSource,
                ThreadStartSource,
            )
        # The optional extra may be absent, or an incompatible SDK may lack required types.
        except ImportError as exc:
            raise CodexAgentError(
                "CodexHarnessAgent requires the optional 'vidbyte-sdk[codex]' integration.",
                failure_code=FailureCode.CODEX_SDK_UNAVAILABLE.value,
                operation="load_sdk",
                error_type=type(exc).__name__,
            ) from exc
        return CodexSdkTypes(
            async_codex=AsyncCodex,
            codex_config=CodexConfig,
            approval_mode=ApprovalMode,
            sandbox=Sandbox,
            personality=Personality,
            reasoning_effort=ReasoningEffort,
            reasoning_summary=ReasoningSummary,
            thread_source=ThreadSource,
            thread_start_source=ThreadStartSource,
            text_input=TextInput,
            image_input=ImageInput,
            local_image_input=LocalImageInput,
            skill_input=SkillInput,
            mention_input=MentionInput,
        )


__all__ = ["CodexTransport"]
