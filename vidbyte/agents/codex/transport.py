"""Official Codex Python SDK transport for CodexHarnessAgent."""

from __future__ import annotations

import asyncio
from typing import Protocol

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


class _CodexThread(Protocol):
    id: str

    async def run(self, input: object, **kwargs: object) -> object: ...


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
                except Exception as exc:
                    raise CodexAgentError(
                        "Codex settings or input could not be translated for the SDK.",
                        failure_code=FailureCode.CODEX_CONTENT_TRANSLATION_FAILED.value,
                        operation="translate_turn",
                        error_type=type(exc).__name__,
                    ) from exc
                try:
                    result = await thread.run(sdk_input, **turn_kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    raise CodexAgentError(
                        "Codex failed to execute the requested turn.",
                        failure_code=FailureCode.CODEX_TURN_FAILED.value,
                        operation="turn_run",
                        error_type=type(exc).__name__,
                    ) from exc
                try:
                    return CodexResultSerializer.from_sdk(thread.id, result)
                except CodexAgentError:
                    raise
                except Exception as exc:
                    raise CodexAgentError(
                        "Codex returned a result that could not be normalized.",
                        failure_code=FailureCode.CODEX_RESPONSE_INVALID.value,
                        operation="normalize_result",
                        error_type=type(exc).__name__,
                    ) from exc
        except asyncio.CancelledError:
            raise
        except CodexAgentError:
            raise
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
                if not thread_id:
                    raise CodexAgentError(
                        "Codex fork returned no thread id.",
                        failure_code=FailureCode.CODEX_RESPONSE_INVALID.value,
                        operation="thread_fork_result",
                    )
                return CodexThreadIdentity(thread_id=thread_id)
        except asyncio.CancelledError:
            raise
        except CodexAgentError:
            raise
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
        except asyncio.CancelledError:
            raise
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
