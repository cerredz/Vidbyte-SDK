"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.codex.acceptance import CodexAcceptanceGate
from vidbyte.agents.codex.capture import CodexTrajectoryCapture
from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.continual import CodexContinualTraceBridge
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.metrics import CodexMetricsTranslator
from vidbyte.agents.codex.middleware import CodexMiddlewareRunner
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import CODEX_MIDDLEWARE_METADATA_KEY
from vidbyte.lib.dataclasses.codex import (
    CodexAcceptanceRequest,
    CodexContextTranslationRequest,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexMiddlewareRequest,
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
        self.last_trace: dict[str, Any] | None = None
        self.last_capture: dict[str, Any] | None = None
        self._transport = CodexTransport()
        self._results = CodexResultTranslator()
        self._usage = UsageTracker()
        self._forks = CodexFork(self._transport)
        self._middleware = CodexMiddlewareRunner(self.settings.middleware)

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def system_prompt(self) -> str:
        return self.settings.system_prompt

    async def arun(self, request: CodexRunInput) -> AgentMessage:
        # @intent export-before-success-publication
        # Required capture must finish before history commits, without retrying native effects.
        capture = CodexTrajectoryCapture(self.settings.capture, self.settings, request) if self.settings.capture else None
        self.last_capture = None
        try:
            try:
                reply, prompt = await self._run_candidate(request, capture)
            except BaseException as exc:
                if capture is not None:
                    await capture.failed(exc)
                raise
            if capture is not None:
                reply = await capture.finish(reply)
            self.history.append(reply)
            self.last_prompt = prompt
            self.last_reply = reply
            return reply
        finally:
            if capture is not None:
                self.last_capture = capture.receipt()

    async def _run_candidate(self, request: CodexRunInput, capture: CodexTrajectoryCapture | None) -> tuple[AgentMessage, str]:
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
        if capture is not None:
            capture.set_prompt(translated)
        boundary = CodexMiddlewareRequest(
            agent_name=self.settings.name, prompt=translated.user_prompt
        )
        before_metadata = await self._middleware.before_run(boundary)
        self.last_trace = None
        continual = self._continual_bridge()
        observation = self.settings.observation
        if continual is not None:
            observation = replace(observation, observers=(*observation.observers, continual.observe))
        if capture is not None:
            observation = replace(observation, observers=(capture.observe, *observation.observers))
        try:
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
                    observation=observation,
                    tool_bridge=self.settings.tool_bridge,
                    control=self.settings.control,
                )
            )
        # Cancellation is not a model error, so it propagates without running
        # caller code during unwinding; only Exception reaches on_model_error.
        except Exception as exc:
            await self._middleware.on_model_error(
                CodexMiddlewareRequest(
                    agent_name=self.settings.name,
                    prompt=translated.user_prompt,
                    error=exc,
                )
            )
            raise
        self.thread_id = result.thread_id
        if capture is not None:
            capture.set_result(result)
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
        after_metadata = await self._middleware.after_run(boundary)
        reply = self._with_middleware_metadata(reply, before_metadata, after_metadata)
        if continual is not None:
            await continual.finalize()
            self.last_trace = continual.artifact()
            reply = replace(reply, metadata={**dict(reply.metadata), "trace": continual.artifact(), "trace_metadata": continual.metadata()})
        if capture is not None:
            capture.set_candidate(reply)
        reply = await self._accept_candidate(reply, continual)
        return reply, translated.user_prompt

    async def _accept_candidate(self, reply: AgentMessage, continual: CodexContinualTraceBridge | None) -> AgentMessage:
        # @intent commit-only-accepted-replies
        # Use actual producer evidence; caller metadata cannot forge trace readiness.
        if self.settings.acceptance is None:
            return reply
        request = CodexAcceptanceRequest(reply, continual.artifact() if continual else None, continual.metadata() if continual else {})
        return await CodexAcceptanceGate(self.settings.acceptance).accept(request)

    def _continual_bridge(self) -> CodexContinualTraceBridge | None:
        # Create isolated trace state for this run without sharing artifacts across forks.
        if self.settings.continual_trace is None:
            return None
        return CodexContinualTraceBridge(self.settings.continual_trace, self.settings.codex)

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
