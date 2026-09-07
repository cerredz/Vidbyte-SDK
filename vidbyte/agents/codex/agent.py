"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio

from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.session import CodexSessionTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import (
    CODEX_PROVIDER_NAME,
    CODEX_PROVIDER_STATE_KIND,
    CODEX_RUNTIME_TYPE,
)
from vidbyte.lib.dataclasses.codex import (
    CodexContextTranslationRequest,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexResultTranslationRequest,
    CodexRunInput,
    CodexSessionExportRequest,
    CodexTransportRunRequest,
)
from vidbyte.lib.dataclasses.sessions import SESSION_SCHEMA_VERSION, RunState
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError
from vidbyte.lib.registries.session_restore import SessionRestoreRegistry

_DEFAULT_FORK_SETTINGS = CodexForkSettings()


class CodexHarnessAgent:
    """Small Vidbyte facade over a Codex-owned agent loop."""

    session_persistence_supported = True

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

    def export_state(self) -> RunState:
        """Capture a serializable checkpoint of this agent (no live objects, no secrets)."""
        # @intent checkpoint-the-thread-not-the-workspace
        # The native thread id is what makes a resume possible. Files edited by
        # earlier turns are not captured and are not restored; only the
        # conversation is durable, and callers must reconcile the workspace.
        from vidbyte.sessions.serialization import SessionSerializer

        serializer = SessionSerializer()
        return RunState(
            schema_version=SESSION_SCHEMA_VERSION,
            agent_name=self.settings.name,
            system_prompt=self.settings.system_prompt,
            description=self.settings.description,
            capabilities=tuple(self.settings.capabilities),
            provider=CODEX_PROVIDER_NAME,
            model_name=self.settings.codex.turn.model or self.settings.codex.thread.model,
            temperature=None,
            runtime_type=CODEX_RUNTIME_TYPE,
            runtime_config={},
            algorithm="default",
            metadata=dict(self.settings.metadata),
            agent_metadata={},
            tool_names=(),
            history=tuple(
                serializer.message_to_dict(message) for message in self.history
            ),
            provider_state=CodexSessionTranslator.to_provider_state(
                CodexSessionExportRequest(
                    settings=self.settings, thread_id=self.thread_id
                )
            ),
        )

    @classmethod
    def restore(
        cls,
        state: RunState,
        *,
        output_schema: object | None = None,
        context_manager: object | None = None,
        **_ignored: object,
    ) -> CodexHarnessAgent:
        """Rebuild a live agent from a checkpoint, re-supplying non-serializable parts."""
        # @intent refuse-before-building-anything
        # An unresumable checkpoint must fail here, not produce an agent whose next
        # turn quietly starts a fresh thread. _ignored absorbs the tools, tracer,
        # and middleware arguments Session passes every restore factory; this agent
        # runs no Vidbyte tool loop and holds no middleware on main. Placements are
        # restored only alongside a re-supplied manager, because they address
        # primitives inside one and the settings record rejects them without it.
        from vidbyte.sessions.serialization import SessionSerializer

        thread_id = CodexSessionTranslator.require_resumable(state.provider_state)
        settings = CodexHarnessAgentSettings(
            name=state.agent_name,
            system_prompt=state.system_prompt,
            codex=CodexSessionTranslator.to_settings(state.provider_state),
            additional_context=str(state.provider_state.get("additional_context", "")),
            context_manager=context_manager,  # type: ignore[arg-type]
            output_schema=output_schema,  # type: ignore[arg-type]
            description=state.description,
            capabilities=tuple(state.capabilities),
            metadata=dict(state.metadata),
            thread_id=thread_id,
            context_placements=(
                CodexSessionTranslator.to_placements(state.provider_state)
                if context_manager is not None
                else ()
            ),
        )
        agent = cls(settings)
        serializer = SessionSerializer()
        agent.history = [
            serializer.message_from_dict(item) for item in state.history
        ]
        return agent

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


SessionRestoreRegistry.register(CODEX_PROVIDER_STATE_KIND, CodexHarnessAgent.restore)

__all__ = ["CodexHarnessAgent"]
