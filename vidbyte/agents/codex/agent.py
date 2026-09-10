"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.failures import CodexFailureLedger, CodexFailureTranslator
from vidbyte.agents.codex.fallback import CodexFallbackCoordinator
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.metrics import CodexMetricsTranslator
from vidbyte.agents.codex.middleware import CodexMiddlewareRunner
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import (
    CODEX_FIRST_ATTEMPT,
    CODEX_MIDDLEWARE_METADATA_KEY,
    CODEX_PRIMARY_CHAIN_INDEX,
)
from vidbyte.lib.dataclasses.codex import (
    CodexAgentInput,
    CodexContextTranslationRequest,
    CodexFailureTranslationRequest,
    CodexFallbackAttempt,
    CodexFallbackDecision,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexMiddlewareRequest,
    CodexResultTranslationRequest,
    CodexRunInput,
    CodexTransportRunRequest,
    CodexTurnOutcome,
    CodexUsageTranslationRequest,
)
from vidbyte.lib.dataclasses.failure import Failure
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
        self._usage = UsageTracker()
        self._failures = CodexFailureLedger()
        self._fallback = CodexFallbackCoordinator.build(self.settings)
        self._forks = CodexFork(self._transport)
        self._middleware = CodexMiddlewareRunner(self.settings.middleware)

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def system_prompt(self) -> str:
        return self.settings.system_prompt

    async def arun(self, request: CodexAgentInput) -> AgentMessage:
        # @intent typed-native-turn-boundary
        # Execute Codex only after Vidbyte input is translated; bypassing this
        # boundary would silently drop context or native input modalities.
        run_input = self._translate_input(request)
        try:
            translated = CodexContextTranslator.translate(
                CodexContextTranslationRequest(
                    input=run_input,
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
        self._usage.reset()
        self._failures.reset()
        boundary = CodexMiddlewareRequest(
            agent_name=self.settings.name, prompt=translated.user_prompt
        )
        before_metadata = await self._middleware.before_run(boundary)
        outcome = await self._run_turn(
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
            ),
            boundary,
        )
        result = outcome.result
        self.thread_id = result.thread_id
        CodexMetricsTranslator.record_usage(
            CodexUsageTranslationRequest(
                result=result,
                settings=self.settings.codex,
                tracker=self._usage,
            )
        )
        reply = self._results.translate(
            CodexResultTranslationRequest(
                result=result,
                agent=self.settings,
                input_metadata=translated.metadata,
                recipient=translated.recipient,
                usage_rollup=self._usage.rollup(),
                failures=self._failures.failures,
                fallback_attempts=outcome.attempts,
                answering_model=outcome.answering_model,
            )
        )
        after_metadata = await self._middleware.after_run(boundary)
        reply = self._with_middleware_metadata(reply, before_metadata, after_metadata)
        self.history.append(reply)
        self.last_prompt = translated.user_prompt
        self.last_reply = reply
        return reply

    def run(self, request: CodexAgentInput) -> AgentMessage:
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

    def _with_middleware_metadata(
        self,
        reply: AgentMessage,
        before_metadata: Mapping[str, Any],
        after_metadata: Mapping[str, Any],
    ) -> AgentMessage:
        # AgentMessage is frozen, so publish middleware output as a replacement
        # rather than mutating the message the result translator already validated.
        if not self._middleware.enabled:
            return reply
        metadata = {
            **dict(reply.metadata),
            **dict(before_metadata),
            **dict(after_metadata),
        }
        pipeline_metadata = self._middleware.metadata()
        if pipeline_metadata:
            metadata[CODEX_MIDDLEWARE_METADATA_KEY] = pipeline_metadata
        return replace(reply, metadata=metadata)

    def get_usage(self) -> UsageRollup:
        """Return the token-usage rollup for the current or most recent turn."""
        return self._usage.rollup()

    def get_cost_usd(self) -> float | None:
        """Return the estimated USD cost of the most recent turn, or None when unpriced."""
        # @intent estimate-not-invoice
        # Codex may bill against subscription credits, so this is a local pricing-table
        # estimate; UsageRollup.cost_complete says whether every call was priced.
        return self.get_usage().cost_usd

    def _translate_input(self, request: CodexAgentInput) -> CodexRunInput:
        # @intent reject-input-before-any-native-work
        # Convert a generic Vidbyte call shape into one native request before any
        # facade state is read, so a rejected input cannot start a Codex thread
        # or leave this agent holding half-updated turn state.
        try:
            return self._vidbyte.translate_input(request)
        except Exception as exc:
            raise CodexAgentError(
                "Vidbyte agent input could not be translated for Codex.",
                failure_code=FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value,
                operation="translate_input",
                error_type=type(exc).__name__,
            ) from exc

    async def _run_turn(
        self, request: CodexTransportRunRequest, boundary: CodexMiddlewareRequest
    ) -> CodexTurnOutcome:
        """Run the turn, falling back to the next chain model while a failure allows it."""
        # @intent one-attempt-per-model-never-mid-turn
        # Each attempt is a whole new native turn on the same thread that overrides
        # only turn.model. A switch is decided only after a turn has ended, because an
        # in-flight turn may already have edited files and its outcome is unknown.
        attempts: list[CodexFallbackAttempt] = []
        index = CODEX_PRIMARY_CHAIN_INDEX
        while True:
            settings = self._fallback.settings_for(request.settings, index)
            try:
                result = await self._transport.run(replace(request, settings=settings))
            # Cancellation is not a model error, so it propagates without running
            # caller code during unwinding; only Exception reaches on_model_error.
            except Exception as exc:
                await self._middleware.on_model_error(replace(boundary, error=exc))
                if not isinstance(exc, CodexAgentError):
                    raise
                # Recorded before the routing decision, so a recovered turn still
                # reports what it survived rather than discarding it on success.
                record = self._failures.record(
                    CodexFailureTranslator.translate(
                        CodexFailureTranslationRequest(
                            error=exc,
                            attempt=len(attempts) + CODEX_FIRST_ATTEMPT,
                            chain_index=index,
                        )
                    )
                )
                if self._fallback.enabled:
                    attempts.append(self._fallback.attempt(index, exc.failure_code))
                next_index = self._fallback.next_index(
                    CodexFallbackDecision(record=record, error=exc, index=index)
                )
                if next_index is None:
                    raise
                index = next_index
                continue
            if self._fallback.enabled:
                attempts.append(self._fallback.attempt(index))
            return CodexTurnOutcome(
                result=result,
                attempts=tuple(attempts),
                answering_model=self._fallback.model_name(index),
            )

    @property
    def failures(self) -> tuple[Failure, ...]:
        """Return canonical failure records observed during the current or most recent turn."""
        return self._failures.failures

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
