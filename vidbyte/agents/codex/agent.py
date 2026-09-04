"""Developer-facing Codex-backed Vidbyte agent."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.codex.config import (
    CodexAgentSettings,
    CodexConfigurationTranslator,
    CodexForkSettings,
)
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.agents.codex.result import CodexResultTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.context.manager import ContextManager
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.providers.output_schema import OutputSchemaFormatter

_ROOT_FORK_DEPTH = 0
_NEXT_FORK_DEPTH = 1


class CodexHarnessAgent:
    """Vidbyte-shaped facade over a Codex-owned agent loop."""

    session_persistence_supported = False

    # @intent explicit-provider-boundary
    # Keep provider-owned loop controls separate from Vidbyte's runtime so unsupported
    # abstractions fail visibly instead of being silently approximated.
    def __init__(self, *, name: str, system_prompt: str, settings: CodexAgentSettings | None = None, additional_context: str | None = None, context_manager: ContextManager | None = None, output_schema: type | Mapping[str, Any] | None = None, description: str = "", capabilities: Sequence[str] = (), metadata: Mapping[str, Any] | None = None, thread_id: str | None = None) -> None:
        # Validates identity and composes the provider-specific collaborators.
        self.name = self._required_text("name", name)
        self.system_prompt = self._required_text("system_prompt", system_prompt)
        self.settings = settings or CodexAgentSettings()
        self.additional_context = self._optional_text(
            "additional_context", additional_context
        )
        self.context_manager = context_manager
        self.output_schema = output_schema
        self.description = str(description)
        self.capabilities = tuple(str(capability) for capability in capabilities)
        self.metadata = dict(metadata or {})
        self.thread_id = self._optional_text("thread_id", thread_id)
        self.history: list[AgentMessage] = []
        self.last_prompt = ""
        self.last_reply: AgentMessage | None = None
        self._schemas = OutputSchemaFormatter()
        self._results = CodexResultTranslator()
        self._transport = CodexTransport()
        if self.output_schema is not None:
            self._schemas.resolve_schema(self.output_schema)

    # @intent one-turn-translation-boundary
    # Translate at the edge and retain the provider thread only after success; doing
    # otherwise can expose state that Codex never committed.
    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        # Translates one request, executes one Codex turn, and records its Vidbyte reply.
        recipient = self._recipient(options)
        translated = CodexContextTranslator.translate(
            message,
            static_context=self.additional_context,
            context_manager=self.context_manager,
        )
        wire_schema = self._wire_schema()
        result = await self._transport.run(
            thread_id=self.thread_id,
            system_prompt=self.system_prompt,
            prompt=translated.text,
            settings=self.settings,
            output_schema=wire_schema,
        )
        self.thread_id = result.thread_id
        reply = self._results.translate(
            result,
            agent_name=self.name,
            recipient=recipient,
            input_metadata=translated.metadata,
            output_schema=self.output_schema,
            agent_metadata=self.metadata,
        )
        self.history.append(reply)
        self.last_prompt = translated.user_prompt
        self.last_reply = reply
        return reply

    def run(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        # Runs one Codex turn from synchronous code and guards active event loops.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(message, **options))
        raise AgentExecutionError(
            "CodexHarnessAgent.run() cannot be called from an active event loop; use await arun()."
        )

    # @intent provider-native-forking
    # A fork must derive from an established Codex thread so the child preserves
    # provider conversation state rather than imitating lineage locally.
    async def afork(self, settings: CodexForkSettings | None = None) -> CodexHarnessAgent:
        # Forks the provider thread and returns an isolated child agent facade.
        if self.thread_id is None:
            raise AgentExecutionError(
                "CodexHarnessAgent cannot fork before its first successful thread start."
            )
        fork_settings = settings or CodexForkSettings()
        child_system_prompt = fork_settings.system_prompt or self.system_prompt
        child_settings = CodexConfigurationTranslator.with_fork_model(
            self.settings,
            fork_settings.model,
            fork_settings.ephemeral,
        )
        child_thread_id = await self._transport.fork(
            thread_id=self.thread_id,
            system_prompt=child_system_prompt,
            settings=child_settings,
            ephemeral=fork_settings.ephemeral,
        )
        return self._forked_agent(
            fork_settings, child_settings, child_system_prompt, child_thread_id
        )

    def fork(self, settings: CodexForkSettings | None = None) -> CodexHarnessAgent:
        # Runs the provider-native fork from synchronous code.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.afork(settings))
        raise AgentExecutionError(
            "CodexHarnessAgent.fork() cannot be called from an active event loop; use await afork()."
        )

    def _forked_agent(self, fork_settings: CodexForkSettings, child_settings: CodexAgentSettings, system_prompt: str, thread_id: str) -> CodexHarnessAgent:
        # Constructs child-local state while preserving definitive provider lineage.
        fork_depth = int(
            self.metadata.get("fork_depth", _ROOT_FORK_DEPTH) or _ROOT_FORK_DEPTH
        ) + _NEXT_FORK_DEPTH
        metadata = {
            **self.metadata,
            **dict(fork_settings.metadata),
            "forked_from_thread_id": self.thread_id,
            "fork_depth": fork_depth,
        }
        context_manager = (
            fork_settings.context_manager
            if fork_settings.context_manager is not None
            else self.context_manager
        )
        return CodexHarnessAgent(
            name=fork_settings.name or self.name,
            system_prompt=system_prompt,
            settings=child_settings,
            additional_context=self.additional_context
            if fork_settings.additional_context is None
            else fork_settings.additional_context,
            context_manager=copy.deepcopy(context_manager),
            output_schema=self.output_schema
            if fork_settings.output_schema is None
            else fork_settings.output_schema,
            description=self.description,
            capabilities=self.capabilities,
            metadata=metadata,
            thread_id=thread_id,
        )

    def _wire_schema(self) -> dict[str, Any] | None:
        # Resolves and annotates the schema sent to Codex for this turn.
        if self.output_schema is None:
            return None
        return self._schemas.annotate(self._schemas.resolve_schema(self.output_schema))

    @staticmethod
    def _recipient(options: dict[str, Any]) -> str:
        # Accepts only the shared recipient option so unsupported settings cannot vanish.
        recipient = str(options.pop("recipient", "user")).strip()
        if options:
            names = ", ".join(sorted(options))
            raise ConfigurationError(
                f"CodexHarnessAgent does not support run options: {names}."
            )
        if not recipient:
            raise ConfigurationError("CodexHarnessAgent recipient cannot be empty.")
        return recipient

    @staticmethod
    def _required_text(field_name: str, value: str) -> str:
        # Normalizes required identity fields and rejects blank values.
        normalized = str(value).strip()
        if not normalized:
            raise ConfigurationError(f"CodexHarnessAgent {field_name} is required.")
        return normalized

    @staticmethod
    def _optional_text(field_name: str, value: str | None) -> str | None:
        # Normalizes optional text while rejecting ambiguous blank overrides.
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ConfigurationError(
                f"CodexHarnessAgent {field_name} cannot be empty when provided."
            )
        return normalized


__all__ = ["CodexHarnessAgent"]
