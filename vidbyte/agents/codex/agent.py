"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio

from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.codex import (
    CodexContextTranslationRequest,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexResultTranslationRequest,
    CodexRunInput,
    CodexTransportRunRequest,
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
