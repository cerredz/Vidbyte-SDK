"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.metrics import CodexMetricsTranslator
from vidbyte.agents.codex.middleware import CodexMiddlewareRunner
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.tools import CodexToolExecutor, CodexToolTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import CODEX_MIDDLEWARE_METADATA_KEY
from vidbyte.lib.dataclasses.codex import (
    CodexContextTranslationRequest,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexMiddlewareRequest,
    CodexResultTranslationRequest,
    CodexRunInput,
    CodexToolDefinition,
    CodexTransportRunRequest,
    CodexUsageTranslationRequest,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError

_DEFAULT_FORK_SETTINGS = CodexForkSettings()


class CodexHarnessAgent:
    """Small Vidbyte facade over a Codex-owned agent loop."""

    session_persistence_supported = False

    def __init__(
        self, settings: CodexHarnessAgentSettings, tools: Sequence[object] = ()
    ) -> None:
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
        self.tool_definitions = self._resolve_definitions(settings, tools)
        self._tool_executor = CodexToolExecutor(tools if tools else ())
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

    def describe_tools(self) -> str:
        # Render tool definitions as developer-context text for prompt-described tools.
        return CodexToolTranslator().to_prompt_block(self.tool_definitions)

    def build_mcp_config(self, command: str) -> Mapping[str, Any]:
        # @intent sidecar-config-boundary
        # The MCP block crosses into Codex-owned configuration, so build it in
        # one place; hand-editing the shape per call site would let the server
        # name or tool list drift from the translated definitions silently.
        # Build the thread-config block that exposes tools through an MCP sidecar.
        return CodexToolTranslator().to_mcp_config(self.tool_definitions, command)

    def has_tool(self, tool_name: str) -> bool:
        # Membership check against the in-process executable subset.
        return self._tool_executor.has_tool(tool_name)

    async def execute_tool_call(
        self, tool_name: str, arguments: Mapping[str, Any]
    ) -> Any:
        # Validate and run one tool call through the owning tool's contract.
        return await self._tool_executor.execute_tool_call(tool_name, arguments)

    def _resolve_definitions(
        self, settings: CodexHarnessAgentSettings, tools: Sequence[object]
    ) -> tuple[CodexToolDefinition, ...]:
        # Explicit constructor tools win; otherwise inherit translated settings tools.
        if tools:
            try:
                return CodexToolTranslator().from_sdk_tools(tools)
            except Exception as exc:
                raise CodexAgentError(
                    "Vidbyte tools could not be translated for Codex.",
                    failure_code=FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value,
                    operation="translate_tools",
                    error_type=type(exc).__name__,
                ) from exc
        return settings.tools

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
        boundary = CodexMiddlewareRequest(
            agent_name=self.settings.name, prompt=translated.user_prompt
        )
        before_metadata = await self._middleware.before_run(boundary)
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
        return self._child_with_tools(result.settings, settings)

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
        return self._child_with_tools(result.settings, settings)

    def _child_with_tools(
        self, settings: CodexHarnessAgentSettings, overrides: CodexForkSettings
    ) -> CodexHarnessAgent:
        # Children inherit live parent tools unless the fork replaces or clears them.
        child = CodexHarnessAgent(settings)
        if overrides.clear_tools or overrides.tools is not None:
            return child
        child._tool_executor = self._tool_executor
        return child


__all__ = ["CodexHarnessAgent"]
