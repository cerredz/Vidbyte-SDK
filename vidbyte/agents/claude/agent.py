"""FILE: vidbyte/agents/claude/agent.py

PURPOSE: Exposes the developer-facing Claude Agent SDK-backed Vidbyte agent facade.
ROLE IN CODEBASE: The one public class; every step is delegated to a collaborator.
ARCHITECTURE NOTE: Vidbyte settings are translated at construction, context at each turn.
COMMON MODIFICATION PATTERNS: Add behavior to a collaborator, not to this facade.
KNOWN EDGE CASES: A forked child holds no session id until its own first successful run.
RELATED DOCS: docs/design/claude-harness-agent.md; https://code.claude.com/docs/en/agent-sdk/overview.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

import asyncio

from vidbyte.agents.claude.config import ClaudeVidbyteTranslator
from vidbyte.agents.claude.context import ClaudeContextTranslator
from vidbyte.agents.claude.fork import ClaudeFork
from vidbyte.agents.claude.result import ClaudeResultTranslator
from vidbyte.agents.claude.transport import ClaudeTransport
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.claude import (
    ClaudeContextTranslationRequest,
    ClaudeForkRequest,
    ClaudeForkSettings,
    ClaudeHarnessAgentSettings,
    ClaudePrompt,
    ClaudeResultTranslationRequest,
    ClaudeRunInput,
    ClaudeTransportRunRequest,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeAgentError

_DEFAULT_FORK_SETTINGS = ClaudeForkSettings()


class ClaudeHarnessAgent:
    """Small Vidbyte facade over a Claude-owned agent loop."""

    session_persistence_supported = False

    def __init__(self, settings: ClaudeHarnessAgentSettings) -> None:
        # @intent translate-vidbyte-settings-once
        # Construction resolves every shared Vidbyte abstraction before a run; provider
        # option dictionaries are still created only at their SDK boundary.
        self._vidbyte = ClaudeVidbyteTranslator()
        try:
            self._translation = self._vidbyte.translate_agent(settings)
        except Exception as exc:
            raise ClaudeAgentError(
                "Vidbyte settings could not be translated for Claude.",
                failure_code=FailureCode.CLAUDE_VIDBYTE_TRANSLATION_FAILED.value,
                operation="translate_agent",
                error_type=type(exc).__name__,
            ) from exc
        self.settings = self._translation.settings
        self.session_id = self.settings.session_id
        self.history: list[AgentMessage] = []
        self.last_prompt = ""
        self.last_reply: AgentMessage | None = None
        self._transport = ClaudeTransport()
        self._results = ClaudeResultTranslator()
        self._forks = ClaudeFork()

    @property
    def name(self) -> str:
        # Returns the validated agent name used as the reply sender.
        return self.settings.name

    @property
    def system_prompt(self) -> str:
        # Returns the normalized Vidbyte system prompt without rendered context.
        return self.settings.system_prompt

    async def arun(self, request: ClaudeRunInput) -> AgentMessage:
        # @intent typed-native-turn-boundary
        # Execute Claude only after Vidbyte input is translated; bypassing this boundary
        # would silently drop rendered context or the caller's session identity.
        prompt = self._prompt(request)
        result = await self._transport.run(
            ClaudeTransportRunRequest(
                session_id=self.session_id,
                system_prompt=self._instructions(prompt),
                prompt=prompt,
                settings=self.settings.claude,
                output_schema=self._translation.output_schema,
            )
        )
        # @intent adopt-provider-session-identity
        # The provider confirms identity on its result message, including on an error
        # result, which is the only way a caller can resume after a turn or cost ceiling.
        self.session_id = result.session_id
        reply = self._results.translate(
            ClaudeResultTranslationRequest(
                result=result,
                agent=self.settings,
                input_metadata=prompt.metadata,
                recipient=prompt.recipient,
            )
        )
        self.history.append(reply)
        self.last_prompt = prompt.user_prompt
        self.last_reply = reply
        return reply

    def run(self, request: ClaudeRunInput) -> AgentMessage:
        # @intent no-nested-event-loop
        # Guard the synchronous boundary because nesting asyncio.run would fail after
        # partially preparing mutable agent state.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(request))
        raise ClaudeAgentError(
            "ClaudeHarnessAgent.run() cannot run inside an active event loop; use await arun().",
            failure_code=FailureCode.CLAUDE_QUERY_FAILED.value,
            operation="run_sync_guard",
        )

    async def afork(
        self, settings: ClaudeForkSettings = _DEFAULT_FORK_SETTINGS
    ) -> ClaudeHarnessAgent:
        # @intent no-fork-policy-in-the-facade
        # Child settings are produced by one collaborator so the facade cannot grow a
        # second, divergent definition of what a fork inherits.
        result = await self._forks.afork(self._fork_request(settings))
        return ClaudeHarnessAgent(result.settings)

    def fork(
        self, settings: ClaudeForkSettings = _DEFAULT_FORK_SETTINGS
    ) -> ClaudeHarnessAgent:
        # @intent one-fork-definition-for-both-entry-points
        # The sync and async forks must resolve identical child settings, so both go
        # through the same collaborator rather than repeating the rules here.
        result = self._forks.fork(self._fork_request(settings))
        return ClaudeHarnessAgent(result.settings)

    def _prompt(self, request: ClaudeRunInput) -> ClaudePrompt:
        # @intent fail-before-the-subprocess
        # Context rendering runs before any CLI process exists, so a broken primitive
        # or manager cannot leave a launched subprocess behind.
        try:
            return ClaudeContextTranslator.translate(
                ClaudeContextTranslationRequest(
                    input=request,
                    static_context=self.settings.additional_context,
                    context_manager=self.settings.context_manager,
                )
            )
        except Exception as exc:
            raise ClaudeAgentError(
                "Vidbyte context could not be translated for Claude.",
                failure_code=FailureCode.CLAUDE_VIDBYTE_TRANSLATION_FAILED.value,
                operation="translate_context",
                error_type=type(exc).__name__,
            ) from exc

    def _instructions(self, prompt: ClaudePrompt) -> str:
        # Joins the system prompt and rendered primitives zone into one instruction block.
        return "\n\n".join(
            part
            for part in (self.settings.system_prompt, prompt.developer_context)
            if part
        )

    def _fork_request(self, settings: ClaudeForkSettings) -> ClaudeForkRequest:
        # @intent snapshot-identity-at-fork-time
        # The parent keeps running after a fork, so the child must capture the session
        # id as it stands now rather than reading a later, diverged value.
        return ClaudeForkRequest(
            parent=self.settings,
            parent_session_id=self.session_id,
            overrides=settings,
        )


__all__ = ["ClaudeHarnessAgent"]
