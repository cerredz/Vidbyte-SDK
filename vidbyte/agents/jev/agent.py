"""FILE: vidbyte/agents/jev/agent.py

PURPOSE: Exposes JevAgent, the opinionated linear agent that runs configured preflight questions before its normal generative loop.
ROLE IN CODEBASE: Callers construct JevAgent with JevAgentSettings and JevRuntimeSettings; this module builds the preflight gate and response writer, while JevRuntime applies the gate before delegating to AgentRuntime.
ARCHITECTURE NOTE: Specialist descriptions are decision metadata only. A selection is reported on JevAgent.response; it does not fork or replace the linear generative agent.
FUNCTION INVENTORY: JevAgent(settings, runtime_settings) configures the inherited BaseAgent and preflight collaborators; response returns the latest JevAgentResponse; _runtime_extension_kwargs passes validated settings and collaborators to each JevRuntime.
COMMON MODIFICATION PATTERNS: Add fixed Jev questions through JevPreflightGate and typed prompt records; retain the ordinary BaseAgent constructor and loop for generation.
WHAT NOT TO DO IN THIS FILE: 1. Do not define Jev question vocabularies; vidbyte/lib/enums/jev.py owns them. 2. Do not execute candidate agents; specialists.py holds only selection metadata.
KNOWN EDGE CASES: A failed or unavailable decision follows the established preflight fail-open policy; the selected profile does not change model execution.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/jev-agent/SKILL.md
TESTS: tests/test_jev_agent.py and tests/test_jev_preflight.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.lib.dataclasses.jev import JevAgentResponse
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError


class JevAgent(BaseAgent):
    """Linear generative agent preceded by a Jev preflight decision."""

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings | None = None) -> None:
        # @intent preserve-one-linear-generator
        # The candidate profiles describe task scopes for TypeSafe to classify; they do not carry executable agents
        # or permissions. Keeping model execution on this configured BaseAgent avoids accidentally changing tools,
        # security policy, or runtime semantics based on an advisory profile label.
        # Keeps the generative agent's configuration independent of Jev's decision policy.
        if not isinstance(settings, JevAgentSettings):
            raise ConfigurationError("JevAgent requires a JevAgentSettings instance.")
        runtime = runtime_settings or JevRuntimeSettings()
        if not isinstance(runtime, JevRuntimeSettings):
            raise ConfigurationError("JevAgent runtime_settings must be a JevRuntimeSettings instance.")
        self.settings = settings
        self.runtime_settings = runtime
        self._response = JevResponse()
        super().__init__(
            name=settings.name,
            system_prompt=settings.system_prompt,
            runtime=AgentRuntimeType.JEV,
            tools=settings.tools,
            permission_policy=settings.permission_policy,
            agent_loop_settings=settings.loop,
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
        )
        self.preflight = JevPreflightGate(settings, runtime, self._response, self)

    @property
    def response(self) -> JevAgentResponse:
        """Return the decision and output record for the most recent run."""
        return self._response.state

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Gives the run-local runtime the same validated policy and gate built for this agent.
        return {"jev_settings": self.settings, "runtime_settings": self.runtime_settings, "preflight": self.preflight, "response": self._response}


Jev = JevAgent

__all__ = ["Jev", "JevAgent"]
