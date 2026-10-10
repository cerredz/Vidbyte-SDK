"""FILE: vidbyte/agents/jev/agent.py

PURPOSE: Exposes the narrow JevAgent facade backed by JevRuntime, JevAgentSettings, and JevRuntimeSettings, and owns everything its opinionated features need for a run.
ROLE IN CODEBASE: Maps the immutable JevAgentSettings into established BaseAgent state, fixes the runtime to AgentRuntimeType.JEV (which RuntimeRegistry resolves to JevRuntime), and builds the JevPreflightGate, the JevRunState that runs the enabled done checks, the JevDoneContinuation that sends the main agent back to work when one fails, and the JevResponse writer that each run-local JevRuntime receives as parameters. With JevRuntimeSettings.compute set, it also builds the JevComputeController that runs the mid-run compute checkpoint.
ARCHITECTURE NOTE: JevAgent is opinionated by design; callers cannot replace its runtime or pass arbitrary BaseAgent customization kwargs. Every fixed-question preset and threshold is fixed here at construction in the gate, and every done check in JevRunState; the runtime still reads JevRuntimeSettings only for the tool selector, which keeps its own path. A JevSpecialist the gate chooses runs its own agent instead of this one.
COMMON MODIFICATION PATTERNS: Build a new feature's run-time object here from JevAgentSettings and pass it through _runtime_extension_kwargs; report its outcome through JevResponse so it appears on `response`.
KNOWN EDGE CASES: Jev's TypeSafe model is not the reply-generating model; settings validation prevents that provider mix-up. A specialist must reply through BaseAgent.generate_reply, the hook that adds its usage to this agent's run total, so any other agent is rejected at construction. `response` describes only the most recent run and is replaced when the next run starts.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-specialist-routing.md, docs/design/jev-multipart-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_done.py, tests/test_jev_compute.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.alignment import JevAgentAlignment
from vidbyte.agents.jev.alignment.skills import JevSkillsPreload
from vidbyte.agents.jev.bulk_work import JevBulkWork
from vidbyte.agents.jev.compute import JevComputeController
from vidbyte.agents.jev.continuation import JevDoneContinuation, JevFreshContinuation
from vidbyte.agents.jev.done import JevRunState, JevRunStateRelation
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.lib.dataclasses.jev import JevAgentResponse
from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.enums import (
    AgentRuntimeType,
    JevContinuationGate,
    JevPreflightPreset,
    ModelProvider,
)
from vidbyte.lib.errors import ConfigurationError


class JevAgent(BaseAgent):
    """Opinionated agent whose preflight gate, done checks, and response are built once, here, and run by JevRuntime."""

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings | None = None) -> None:
        # Maps the agent settings into BaseAgent, fixes the jev runtime, and builds the preflight gate and done checks from both settings objects.
        # @intent closed-jev-construction-surface
        # Rejecting arbitrary objects keeps runtime selection and decision policy owned by this package.
        if not isinstance(settings, JevAgentSettings):
            raise ConfigurationError("JevAgent requires a JevAgentSettings instance.")
        runtime_settings = JevRuntimeSettings() if runtime_settings is None else runtime_settings
        if not isinstance(runtime_settings, JevRuntimeSettings):
            raise ConfigurationError("JevAgent runtime_settings must be a JevRuntimeSettings instance.")
        self._require_metered_specialists(settings)
        self.settings = settings
        self.runtime_settings = runtime_settings
        self._response = JevResponse()
        self.bulk_work = JevBulkWork(settings)
        self.preflight = JevPreflightGate(settings, runtime_settings, self._response)
        self.compute = None if runtime_settings.compute is None else JevComputeController(settings, runtime_settings.compute, runtime_settings.decision, self._response)
        relation_enabled = JevPreflightPreset.RUN_STATE_RELATION in self.preflight.presets
        if relation_enabled:
            self.run_state = JevRunStateRelation(settings, runtime_settings, self._response, self.preflight)
        elif runtime_settings.continual.checks:
            self.run_state = JevRunState(settings, runtime_settings, self._response)
        else:
            self.run_state = None
        if self.run_state is None or not runtime_settings.continual.checks:
            self.continuation = None
        elif runtime_settings.continual.gate is JevContinuationGate.FRESH:
            fresh_agent_factory = partial(
                BaseAgent,
                name=f"{settings.name}-fresh-continuation",
                system_prompt=settings.system_prompt,
                provider=settings.provider,
                model_name=settings.model_name,
                api_key=settings.api_key,
                temperature=settings.temperature,
                timeout_seconds=settings.timeout_seconds,
                tools=settings.tools,
                permission_policy=settings.permission_policy,
                agent_loop_settings=settings.loop,
            )
            self.continuation = JevFreshContinuation(self.run_state, runtime_settings.continual, self._response, fresh_agent_factory)
        else:
            self.continuation = JevDoneContinuation(self.run_state, runtime_settings.continual, self._response)
        # @intent alignment-gets-decision-from-runtime-settings
        # Grouped agent settings carry model identity while JevRuntimeSettings owns the separate decision-model configuration.
        self.alignment = JevAgentAlignment(settings, runtime_settings.decision) if settings.alignment.system_prompt or settings.alignment.tool_settings else None
        skill_candidates: list[SkillDocument | SkillSource] = []
        for candidate in settings.alignment.skills:
            if not isinstance(candidate, (SkillDocument, SkillSource)):
                raise ConfigurationError("JevAlignmentSettings.skills must be normalized before JevAgent construction.")
            skill_candidates.append(candidate)
        self.skill_preload = (
            JevSkillsPreload(
                skills=tuple(skill_candidates),
                decision=runtime_settings.decision,
                threshold=runtime_settings.skills_threshold,
                response=self._response,
                provider=settings._normalized_provider(),
                claude_api_key=settings.api_key if settings.provider is ModelProvider.ANTHROPIC else None,
            )
            if settings.alignment.skills
            else None
        )
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

    @staticmethod
    def _require_metered_specialists(settings: JevAgentSettings) -> None:
        # Rejects any specialist whose usage could not reach this agent's run total.
        # @intent specialist-usage-must-be-metered
        # JevAgent fails closed on usage, and a specialist's spend reaches the run ledger only through
        # BaseAgent.generate_reply; an agent that replaces that method, or is not a BaseAgent, would spend unseen.
        for specialist in settings.agents:
            agent = specialist.agent
            if not isinstance(agent, BaseAgent) or type(agent).generate_reply is not BaseAgent.generate_reply:
                raise ConfigurationError(
                    f"JevAgent specialist {specialist.title!r} must be a BaseAgent that replies through BaseAgent.generate_reply, so its usage counts toward the run total.",
                    details={"specialist": specialist.title, "agent_type": type(agent).__name__},
                )

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Passes the runtime settings, the gate, the done checks, the continuation, the compute controller, the optional run-local setup phases, and the response writer built at construction to each run-local JevRuntime.
        return {
            "runtime_settings": self.runtime_settings,
            "preflight": self.preflight,
            "run_state": self.run_state,
            "continuation": self.continuation,
            "compute": self.compute,
            "response": self._response,
            "alignment": self.alignment,
            "alignment_settings": self.settings.alignment,
            "skill_preload": self.skill_preload,
            "bulk_work": self.bulk_work,
        }


__all__ = ["JevAgent"]
