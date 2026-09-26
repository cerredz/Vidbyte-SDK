"""FILE: vidbyte/agents/jev/agent.py

PURPOSE: Exposes the narrow JevAgent facade backed by JevRuntime and JevAgentSettings, and owns everything its opinionated features need for a run.
ROLE IN CODEBASE: Maps one immutable settings object into established BaseAgent state, fixes the runtime to AgentRuntimeType.JEV (which RuntimeRegistry resolves to JevRuntime), and builds the JevPreflightGate, the JevSpecialistRouter, and the JevResponse writer that each run-local JevRuntime receives as parameters.
ARCHITECTURE NOTE: JevAgent is opinionated by design; callers cannot replace its runtime or pass arbitrary BaseAgent customization kwargs. Every fixed-question preset and threshold is fixed here at construction in the gate, and the specialist catalog and match threshold in the router; the runtime still reads the settings only for the tool selector, which keeps its own path.
COMMON MODIFICATION PATTERNS: Build a new feature's run-time object here from JevAgentSettings and pass it through _runtime_extension_kwargs; report its outcome through JevResponse so it appears on `response`.
KNOWN EDGE CASES: Jev's TypeSafe model is not the reply-generating model; settings validation prevents that provider mix-up. `response` describes only the most recent run and is replaced when the next run starts.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-specialist-routing.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.jev.specialists import JevSpecialistRouter
from vidbyte.lib.dataclasses.jev import JevAgentResponse
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError


class JevAgent(BaseAgent):
    """Opinionated agent whose preflight gate, specialist router, and response are built once, here, and run by JevRuntime."""

    def __init__(self, settings: JevAgentSettings) -> None:
        # Maps the sole public settings object into BaseAgent, fixes the jev runtime, and builds the preflight gate and the specialist router.
        # @intent closed-jev-construction-surface
        # Rejecting arbitrary objects keeps runtime selection and decision policy owned by this package.
        if not isinstance(settings, JevAgentSettings):
            raise ConfigurationError("JevAgent requires a JevAgentSettings instance.")
        self.settings = settings
        self._response = JevResponse()
        self.preflight = JevPreflightGate(settings, self._response)
        self.specialists = JevSpecialistRouter(settings, self._response)
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

    @property
    def response(self) -> JevAgentResponse:
        """Return everything JevAgent's opinionated features produced for the most recent run."""
        return self._response.state

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Passes the settings, the gate, the router, and the response writer built at construction to each run-local JevRuntime.
        return {"jev_settings": self.settings, "preflight": self.preflight, "specialists": self.specialists, "response": self._response}


__all__ = ["JevAgent"]
