"""FILE: vidbyte/agents/jev/agent.py

PURPOSE: Exposes the narrow JevAgent facade backed by JevRuntime and JevAgentSettings.
ROLE IN CODEBASE: Maps one immutable settings object into established BaseAgent state and fixes the runtime to AgentRuntimeType.JEV, which RuntimeRegistry resolves to JevRuntime.
ARCHITECTURE NOTE: JevAgent is opinionated by design; callers cannot replace its runtime or pass arbitrary BaseAgent customization kwargs.
COMMON MODIFICATION PATTERNS: Evolve JevAgentSettings and JevRuntime together, leaving this mapping intentionally small.
KNOWN EDGE CASES: Jev's TypeSafe model is not the reply-generating model; settings validation prevents that provider mix-up.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-documentation.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_documentation.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.documentation import JevDocumentation
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError


class JevAgent(BaseAgent):
    """Opinionated agent whose future decision policies are owned by JevRuntime."""

    def __init__(self, settings: JevAgentSettings) -> None:
        # Maps the sole public settings object into BaseAgent while fixing the jev runtime.
        # @intent closed-jev-construction-surface
        # Rejecting arbitrary objects keeps runtime selection and future decision policy owned by this package.
        if not isinstance(settings, JevAgentSettings):
            raise ConfigurationError("JevAgent requires a JevAgentSettings instance.")
        self.settings = settings
        # One search agent per agent; it runs before each run only when the documentation setting names a provider.
        self.documentation = JevDocumentation(settings) if settings.documentation is not None else None
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

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Passes the exact immutable settings object and the optional documentation agent to each run-local JevRuntime.
        return {"jev_settings": self.settings, "documentation": self.documentation}


__all__ = ["JevAgent"]
