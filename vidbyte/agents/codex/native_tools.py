"""Public CodexClient lifecycle for native Vidbyte functions.

PURPOSE: Register and service real experimental native dynamic tool requests.
ROLE IN CODEBASE: Opt-in transport selected by CodexTransport.
ARCHITECTURE NOTE: Uses public blocking SDK calls offloaded onto worker threads.
COMMON MODIFICATION PATTERNS: Preserve cancellation cleanup at every native boundary.
KNOWN EDGE CASES: The sole reader thread must not issue its own native requests.
RELATED DOCS: docs/design/codex-native-tools.md
TESTS: tests/codex_native_tools/test_native_tools.py
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from vidbyte.agents.codex.config import CodexContentTranslator
from vidbyte.agents.codex.result import CodexResultSerializer
from vidbyte.agents.codex.stream import CodexStreamRunner
from vidbyte.agents.codex.tool_dispatch import CodexToolDispatcher
from vidbyte.agents.codex.tool_wire import CodexToolWire
from vidbyte.lib.dataclasses.codex import (
    CodexObservation,
    CodexRunResult,
    CodexSdkTypes,
    CodexTransportRunRequest,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

if TYPE_CHECKING:
    from openai_codex.client import CodexClient
    from openai_codex.generated.v2_all import TurnInterruptResponse, TurnSteerResponse
    from openai_codex.models import Notification


class CodexNativeTurnStream:
    """One routed native notification queue with deterministic cleanup."""

    def __init__(self, client: CodexClient, turn_id: str, thread_id: str) -> None:
        # Retain only public client operations and the native routing identity.
        self.client = client
        self.id = turn_id
        self.thread_id = thread_id

    async def steer(self, input: str) -> TurnSteerResponse:
        # @intent native-low-level-steering
        # Send the expected turn ID so Codex cannot retarget feedback to a later turn.
        return await asyncio.to_thread(self.client.turn_steer, self.thread_id, self.id, input)

    async def interrupt(self) -> TurnInterruptResponse:
        # @intent native-low-level-interruption
        # Request actual native interruption without synthesizing a terminal event.
        return await asyncio.to_thread(self.client.turn_interrupt, self.thread_id, self.id)

    async def stream(self) -> AsyncGenerator[Notification, None]:
        # @intent single-native-notification-consumer
        # Release the registered queue even if an observer or caller cancels.
        from openai_codex.generated.v2_all import TurnCompletedNotification

        try:
            while True:
                event = await asyncio.to_thread(self.client.next_turn_notification, self.id)
                yield event
                if event.method == "turn/completed" and isinstance(event.payload, TurnCompletedNotification) and event.payload.turn.id == self.id:
                    break
        finally:
            self.client.unregister_turn_notifications(self.id)


class CodexNativeToolTransport:
    """Own the native connection for one fresh thread with registered tools."""

    async def run(self, request: CodexTransportRunRequest, sdk: CodexSdkTypes) -> CodexRunResult:
        # @intent validate-before-provider-effects
        # Reject unsupported continuity rather than silently dropping native tools.
        from openai_codex.client import CodexClient

        if request.tool_bridge is None or request.thread_id or not request.settings.client.experimental_api:
            raise ConfigurationError("Codex native tools require tool_bridge, a fresh thread, and experimental_api=True.")
        dispatcher = CodexToolDispatcher(request.tool_bridge)
        config = sdk.codex_config(**CodexContentTranslator.client_kwargs(request.settings))
        client = CodexClient(config, approval_handler=dispatcher.handle)
        started = asyncio.create_task(asyncio.to_thread(client.start))
        try:
            await asyncio.shield(started)
            await asyncio.to_thread(client.initialize)
            return await self.execute(client, dispatcher, request, sdk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise CodexAgentError("Codex native tool turn failed; inspect the operation and error_type before retrying side effects.", failure_code=FailureCode.CODEX_TURN_FAILED.value, operation="native_tool_turn", error_type=type(exc).__name__) from exc
        finally:
            dispatcher.close()
            try:
                await started
            finally:
                await asyncio.to_thread(client.close)

    async def execute(self, client: CodexClient, dispatcher: CodexToolDispatcher, request: CodexTransportRunRequest, sdk: CodexSdkTypes) -> CodexRunResult:
        # @intent register-before-model-execution
        # Register actual dynamicTools before starting the observed native turn.
        opened = await asyncio.to_thread(client.thread_start, CodexToolWire.thread(request, sdk, dispatcher.tools))
        dispatcher.thread_id = opened.thread.id
        values = CodexToolWire.turn(request, sdk, opened.thread.id)
        started = await asyncio.to_thread(client.turn_start, opened.thread.id, values["input"], values)
        identity = CodexObservation(0, "", opened.thread.id, started.turn.id)
        runner = CodexStreamRunner(request)
        runner.trace.start(identity)
        error: BaseException | None = None
        try:
            result = await runner.collect(CodexNativeTurnStream(client, started.turn.id, opened.thread.id), identity)
            return CodexResultSerializer.from_sdk(opened.thread.id, result)
        except BaseException as exc:
            error = exc
            raise
        finally:
            runner.trace.finish(error)


__all__ = ["CodexNativeToolTransport"]
