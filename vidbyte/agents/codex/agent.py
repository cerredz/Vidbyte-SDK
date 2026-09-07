"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio

from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.speed import CodexSpeedTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.speed.tracker import AgentSpeedTracker
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.codex import (
    CodexContextTranslationRequest,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexResultTranslationRequest,
    CodexRunInput,
    CodexRunResult,
    CodexSpeedTranslationRequest,
    CodexTransportRunRequest,
)
from vidbyte.lib.dataclasses.speed import AgentSpeedHistory, AgentSpeedRollup
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError

_DEFAULT_FORK_SETTINGS = CodexForkSettings()


class CodexHarnessAgent:
    """Small Vidbyte facade over a Codex-owned agent loop."""

    session_persistence_supported = False

    def __init__(self, settings: CodexHarnessAgentSettings) -> None:
        # @intent translate-vidbyte-settings-once
        # Construction resolves every shared Vidbyte abstraction before a run;
        # provider dictionaries are still created only at their SDK boundary.
        self._vidbyte = CodexVidbyteTranslator()
        try:
            self._translation = self._vidbyte.translate_agent(settings)
        except Exception as exc:
            raise CodexAgentError(
                "Vidbyte settings could not be translated for Codex.",
                failure_code=FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value,
                operation="translate_agent",
                error_type=type(exc).__name__,
            ) from exc
        self.settings = self._translation.settings
        self.thread_id = self.settings.thread_id
        self.history: list[AgentMessage] = []
        self.last_prompt = ""
        self.last_reply: AgentMessage | None = None
        self._transport = CodexTransport()
        self._results = CodexResultTranslator()
        self._speed = AgentSpeedTracker()
        self._forks = CodexFork(self._transport)

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def system_prompt(self) -> str:
        return self.settings.system_prompt

    async def arun(self, request: CodexRunInput) -> AgentMessage:
        # @intent typed-native-turn-boundary
        # Execute Codex only after Vidbyte input is translated; bypassing this
        # boundary would silently drop context or native input modalities.
        try:
            translated = CodexContextTranslator.translate(
                CodexContextTranslationRequest(
                    input=request,
                    static_context=self.settings.additional_context,
                    context_manager=self.settings.context_manager,
                    context_placements=self.settings.context_placements,
                )
            )
        except Exception as exc:
            raise CodexAgentError(
                "Vidbyte context could not be translated for Codex.",
                failure_code=FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value,
                operation="translate_context",
                error_type=type(exc).__name__,
            ) from exc
        result = await self._measured_turn(
            CodexTransportRunRequest(
                thread_id=self.thread_id,
                system_prompt="\n\n".join(
                    part
                    for part in (
                        self.settings.system_prompt,
                        translated.developer_context,
                    )
                    if part
                ),
                prompt=translated,
                settings=self.settings.codex,
                output_schema=self._translation.output_schema,
            )
        )
        self.thread_id = result.thread_id
        reply = self._results.translate(
            CodexResultTranslationRequest(
                result=result,
                agent=self.settings,
                input_metadata=translated.metadata,
                recipient=translated.recipient,
            )
        )
        self.history.append(reply)
        self.last_prompt = translated.user_prompt
        self.last_reply = reply
        return reply

    def run(self, request: CodexRunInput) -> AgentMessage:
        # @intent no-nested-event-loop
        # Guard the synchronous boundary because nesting asyncio.run would fail
        # after partially preparing mutable agent state.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(request))
        raise CodexAgentError(
            "CodexHarnessAgent.run() cannot run inside an active event loop; use await arun().",
            failure_code=FailureCode.CODEX_TURN_FAILED.value,
            operation="run_sync_guard",
        )

    async def _measured_turn(
        self, request: CodexTransportRunRequest
    ) -> CodexRunResult:
        # @intent close-the-run-on-every-exit-path
        # Cancellation arrives as BaseException, so an Exception-only handler would
        # leave the run open forever and corrupt every rollup that follows it.
        self._speed.reset()
        self._speed.record_run_start()
        dispatched_at = self._speed.now()
        try:
            result = await self._transport.run(request)
        except BaseException as exc:
            self._record_speed(dispatched_at, error=exc)
            self._speed.record_run_end()
            raise
        self._record_speed(dispatched_at, result=result)
        self._speed.record_run_end()
        return result

    def _record_speed(
        self,
        dispatched_at: float,
        *,
        result: CodexRunResult | None = None,
        error: BaseException | None = None,
    ) -> None:
        # @intent metering-never-replaces-the-turn-outcome
        # A raising translator would discard a completed turn's result, or replace the
        # caller's real exception with a measurement bug. Catch Exception only, so
        # cancellation still propagates, and report the loss through the tracker.
        try:
            CodexSpeedTranslator.record_turn(
                CodexSpeedTranslationRequest(
                    settings=self.settings.codex,
                    tracker=self._speed,
                    dispatched_at=dispatched_at,
                    result=result,
                    error=error,
                )
            )
        except Exception:
            self._speed.mark_recording_corrupted()

    def get_speed_stats(self) -> AgentSpeedRollup:
        """Return the speed rollup for the current or most recent turn."""
        return self._speed.rollup()

    def get_speed_history(self) -> AgentSpeedHistory:
        """Return bounded speed summaries for completed turns of this agent."""
        # History deliberately survives the per-turn reset that clears the ledger.
        return self._speed.history()

    async def afork(
        self, settings: CodexForkSettings = _DEFAULT_FORK_SETTINGS
    ) -> CodexHarnessAgent:
        # Delegate native branching and construct the facade only from typed child settings.
        result = await self._forks.afork(
            CodexForkRequest(
                parent=self.settings,
                parent_thread_id=self.thread_id,
                overrides=settings,
            )
        )
        return CodexHarnessAgent(result.settings)

    def fork(
        self, settings: CodexForkSettings = _DEFAULT_FORK_SETTINGS
    ) -> CodexHarnessAgent:
        # Delegate the synchronous fork wrapper without duplicating fork policy here.
        result = self._forks.fork(
            CodexForkRequest(
                parent=self.settings,
                parent_thread_id=self.thread_id,
                overrides=settings,
            )
        )
        return CodexHarnessAgent(result.settings)


__all__ = ["CodexHarnessAgent"]
