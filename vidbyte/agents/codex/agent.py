"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.failures import CodexFailureLedger, CodexFailureTranslator
from vidbyte.agents.codex.fallback import CodexFallbackCoordinator
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.metrics import CodexMetricsTranslator
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import (
    CODEX_FIRST_ATTEMPT,
    CODEX_PRIMARY_CHAIN_INDEX,
)
from vidbyte.lib.dataclasses.codex import (
    CodexContextTranslationRequest,
    CodexFailureTranslationRequest,
    CodexFallbackAttempt,
    CodexFallbackDecision,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
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
        self._usage.reset()
        self._failures.reset()
        outcome = await self._attempt_turn(
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

    def get_usage(self) -> UsageRollup:
        """Return the token-usage rollup for the current or most recent turn."""
        return self._usage.rollup()

    def get_cost_usd(self) -> float | None:
        """Return the estimated USD cost of the most recent turn, or None when unpriced."""
        # @intent estimate-not-invoice
        # Codex may bill against subscription credits, so this is a local pricing-table
        # estimate; UsageRollup.cost_complete says whether every call was priced.
        return self.get_usage().cost_usd

    async def _attempt_turn(
        self, request: CodexTransportRunRequest
    ) -> CodexTurnOutcome:
        """Run the turn, walking the fallback chain while a failure justifies another model."""
        # @intent one-attempt-per-model-never-mid-turn
        # Each attempt is a whole new native turn on the same thread. A switch is only
        # ever decided after a turn has ended, because an in-flight turn may already
        # have edited files, and its outcome would be unknown if abandoned.
        attempts: list[CodexFallbackAttempt] = []
        index = CODEX_PRIMARY_CHAIN_INDEX
        while True:
            try:
                result = await self._transport.run(
                    self._request_for(request, index)
                )
            except CodexAgentError as exc:
                index = self._route_failure(
                    exc, index, len(attempts) + CODEX_FIRST_ATTEMPT, attempts
                )
                continue
            if self._fallback.enabled:
                attempts.append(self._fallback.attempt(index))
            return CodexTurnOutcome(
                result=result,
                attempts=tuple(attempts),
                answering_model=self._answering_model(index),
            )

    def _route_failure(
        self,
        error: CodexAgentError,
        index: int,
        attempt: int,
        attempts: list[CodexFallbackAttempt],
    ) -> int:
        """Record the classified failure and return the next chain index, or re-raise."""
        # @intent record-first-then-decide
        # The failure is recorded before the routing decision, so a recovered turn
        # still reports what it survived rather than discarding it on success.
        record = self._failures.record(
            CodexFailureTranslator.translate(
                CodexFailureTranslationRequest(
                    error=error, attempt=attempt, chain_index=index
                )
            )
        )
        if self._fallback.enabled:
            attempts.append(self._fallback.attempt(index, error.failure_code))
        next_index = self._fallback.next_index(
            CodexFallbackDecision(record=record, error=error, index=index)
        )
        if next_index is None:
            raise error
        return next_index

    def _request_for(
        self, request: CodexTransportRunRequest, index: int
    ) -> CodexTransportRunRequest:
        """Return the transport request for one attempt, with that attempt's model."""
        # @intent override-only-the-model
        # Only turn.model changes between attempts; a fallback that also widened the
        # sandbox or approval mode would be a silent security regression.
        if not self._fallback.enabled or index == CODEX_PRIMARY_CHAIN_INDEX:
            return request
        return replace(
            request, settings=self._fallback.settings_for(request.settings, index)
        )

    def _answering_model(self, index: int) -> str:
        """Return the model that produced the reply, or empty when no chain is configured."""
        # @intent absent-means-no-chain-not-first-entry
        # Empty rather than the configured model, so a caller can tell "no fallback
        # chain" from "the chain answered on its first entry".
        return self._fallback.model_name(index) if self._fallback.enabled else ""

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
