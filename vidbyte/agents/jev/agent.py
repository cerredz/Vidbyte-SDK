"""FILE: vidbyte/agents/jev/agent.py

PURPOSE: Exposes the narrow JevAgent facade backed by JevRuntime, JevAgentSettings, and optional named done-criteria presets.
ROLE IN CODEBASE: Maps one immutable settings object into established BaseAgent state and fixes the runtime to AgentRuntimeType.JEV, which RuntimeRegistry resolves to JevRuntime.
ARCHITECTURE NOTE: JevAgent is opinionated by design; callers cannot replace its runtime or pass arbitrary BaseAgent customization kwargs.
COMMON MODIFICATION PATTERNS: Evolve JevAgentSettings and JevRuntime together, leaving this mapping intentionally small.
KNOWN EDGE CASES: Jev's TypeSafe model is not the reply-generating model; settings validation prevents that provider mix-up. Enabling a done-criteria preset requires a resolvable TypeSafe key at construction.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-motivating-case.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_motivating_case.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.presets import JevPresets
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError


class JevAgent(BaseAgent):
    """Opinionated agent whose future decision policies are owned by JevRuntime."""

    def __init__(self, settings: JevAgentSettings, *, done_criteria: JevPresets | None = None) -> None:
        # Maps the settings object and one optional named done-criteria preset into BaseAgent while fixing the jev runtime.
        # @intent closed-jev-construction-surface
        # Rejecting arbitrary objects keeps runtime selection and future decision policy owned by this package.
        if not isinstance(settings, JevAgentSettings):
            raise ConfigurationError("JevAgent requires a JevAgentSettings instance.")
        if done_criteria is not None and not isinstance(done_criteria, JevPresets):
            raise ConfigurationError("JevAgent.done_criteria must be a JevPresets member, such as JevPresets.MotivatingCase, or None.")
        if done_criteria is not None:
            # @intent enabled-preset-needs-jev-credentials
            # A preset asks Jev at every run, so a missing TypeSafe key is reported here instead of
            # surfacing later as a wrapped run failure; without a preset construction stays credential-free.
            settings.decision.validate()
        self.settings = settings
        self.done_criteria = done_criteria
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
        # Passes the settings, the preset, and this agent (whose model the preset's helper agents reuse) to each run-local JevRuntime.
        return {"jev_settings": self.settings, "done_criteria": self.done_criteria, "source_agent": self}


__all__ = ["JevAgent"]
