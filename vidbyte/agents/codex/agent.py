"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio

from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.metrics import CodexMetricsTranslator
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import CODEX_MAX_CONCURRENT_TURNS
from vidbyte.lib.dataclasses.codex import (
    CodexAgentInput,
    CodexContextTranslationRequest,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexResultTranslationRequest,
    CodexRunInput,
    CodexTransportRunRequest,
    CodexUsageTranslationRequest,
)
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
        # Per instance, never shared: distinct agents stay concurrent in a fan-out
        # while the same agent used twice runs its turns in sequence. A Semaphore
        # rather than a Lock because the SDK bans asyncio.Lock and already uses
        # Semaphore for concurrency bounds in aggregation.py and evals/runner.py.
        self._turns = asyncio.Semaphore(CODEX_MAX_CONCURRENT_TURNS)
        self._forks = CodexFork(self._transport)

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def system_prompt(self) -> str:
        return self.settings.system_prompt

    async def arun(self, request: CodexAgentInput) -> AgentMessage:
        # @intent typed-native-turn-boundary
        # Execute Codex only after Vidbyte input is translated; bypassing this
        # boundary would silently drop context or native input modalities. The lock
        # spans the whole turn, not just the transport call, because the racing
        # state — thread_id, history, last_prompt, last_reply, usage — is written
        # after the provider returns.
        async with self._turns:
            return await self._run_turn(self._translate_input(request))

    def _translate_input(self, request: CodexAgentInput) -> CodexRunInput:
        # @intent reject-input-before-any-native-work
        # Convert a generic caller shape into one native request before any facade
        # state is read, so a rejected input cannot start a Codex thread.
        try:
            return self._vidbyte.translate_input(request)
        except Exception as exc:
            raise CodexAgentError(
                "Vidbyte agent input could not be translated for Codex.",
                failure_code=FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value,
                operation="translate_input",
                error_type=type(exc).__name__,
            ) from exc

    async def generate_reply(
        self, message: CodexAgentInput, **options: object
    ) -> AgentMessage:
        """Produce one reply for a caller that dispatches by this name."""
        # @intent refuse-an-option-this-adapter-cannot-honor
        # BasePipeline._invoke forwards whatever the caller passed to run(**options).
        # Silently dropping context= or history= would return an answer computed
        # without them, which reads to the caller as the setting having applied.
        if options:
            raise CodexAgentError(
                "CodexHarnessAgent.generate_reply does not support run options "
                f"{', '.join(sorted(options))}; Codex owns its own loop, history, "
                "and context window.",
                failure_code=FailureCode.CODEX_RUN_OPTION_UNSUPPORTED.value,
                operation="generate_reply",
                error_type=",".join(sorted(options)),
            )
        return await self.arun(message)

    async def _run_turn(self, request: CodexRunInput) -> AgentMessage:
        # @intent mutate-facade-state-only-under-the-turn-guard
        # thread_id, history, last_prompt, last_reply, and the usage ledger are all
        # written here. The caller holds this agent's turn guard for the whole
        # method, which is why a fan-out reusing one agent cannot interleave them.
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
        result = await self._transport.run(
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
            )
        )
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

    def get_usage(self) -> UsageRollup:
        """Return the token-usage rollup for the current or most recent turn."""
        return self._usage.rollup()

    def get_cost_usd(self) -> float | None:
        """Return the estimated USD cost of the most recent turn, or None when unpriced."""
        # @intent estimate-not-invoice
        # Codex may bill against subscription credits, so this is a local pricing-table
        # estimate; UsageRollup.cost_complete says whether every call was priced.
        return self.get_usage().cost_usd

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
