"""FILE: vidbyte/agents/jev/agent.py

PURPOSE: Exposes the narrow JevAgent facade backed by JevRuntime and JevAgentSettings.
ROLE IN CODEBASE: Maps one immutable settings object into established BaseAgent state and fixes the runtime to AgentRuntimeType.JEV, which RuntimeRegistry resolves to JevRuntime.
ARCHITECTURE NOTE: JevAgent is opinionated by design; callers cannot replace its runtime or pass arbitrary BaseAgent customization kwargs.
COMMON MODIFICATION PATTERNS: Evolve JevAgentSettings and JevRuntime together, leaving this mapping intentionally small.
KNOWN EDGE CASES: Jev's TypeSafe model is not the reply-generating model; settings validation prevents that provider mix-up. The dynamic-compaction record writer shares this agent's usage tracker, so its calls count toward get_usage().
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.compaction import JevDynamicCompaction
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
        self.compaction = self._build_compaction(settings)

    def _build_compaction(self, settings: JevAgentSettings) -> JevDynamicCompaction | None:
        # Builds the dynamic-compaction agent when a trigger is enabled and points its usage at this agent's tracker.
        # @intent compaction-cost-is-agent-cost
        # Record-writing calls are part of what this agent spends, so sharing the tracker keeps get_usage() and cost honest.
        if settings.dynamic_compaction is None or not settings.dynamic_compaction.is_enabled():
            return None
        compaction = JevDynamicCompaction(settings)
        compaction._usage_tracker = self._usage_tracker
        return compaction

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Passes the exact immutable settings object and the shared compaction agent to each run-local JevRuntime.
        return {"jev_settings": self.settings, "jev_compaction": self.compaction}


__all__ = ["JevAgent"]
