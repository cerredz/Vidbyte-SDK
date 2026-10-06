"""FILE: vidbyte/agents/jev/agent.py

PURPOSE: Exposes the narrow JevAgent facade backed by JevRuntime, JevAgentSettings, and JevRuntimeSettings, and owns everything its opinionated features need for a run.
ROLE IN CODEBASE: Maps the immutable JevAgentSettings into established BaseAgent state, fixes the runtime to AgentRuntimeType.JEV (which RuntimeRegistry resolves to JevRuntime), and builds the JevPreflightGate, the JevRunState that runs the enabled done checks, the JevDoneContinuation that sends the main agent back to work when one fails, and the JevResponse writer that each run-local JevRuntime receives as parameters.
ARCHITECTURE NOTE: JevAgent is opinionated by design; callers cannot replace its runtime or pass arbitrary BaseAgent customization kwargs. Every fixed-question preset and threshold is fixed here at construction in the gate, and every done check in JevRunState; the runtime still reads JevRuntimeSettings only for the tool selector, which keeps its own path. A JevSpecialist the gate chooses runs its own agent instead of this one.
COMMON MODIFICATION PATTERNS: Build a new feature's run-time object here from JevAgentSettings and pass it through _runtime_extension_kwargs; report its outcome through JevResponse so it appears on `response`.
KNOWN EDGE CASES: Jev's TypeSafe model is not the reply-generating model; settings validation prevents that provider mix-up. `response` describes only the most recent run and is replaced when the next run starts.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-specialist-routing.md, docs/design/jev-multipart-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_done.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.continuation import JevDoneContinuation, JevFreshContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.lib.dataclasses.jev import JevAgentResponse
from vidbyte.lib.enums import AgentRuntimeType, JevContinuationGate
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
        self.settings = settings
        self.runtime_settings = runtime_settings
        self._response = JevResponse()
        self.preflight = JevPreflightGate(settings, runtime_settings, self._response)
        self.run_state = JevRunState(settings, runtime_settings, self._response) if runtime_settings.continual.checks else None
        if self.run_state is None:
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
        # Passes the runtime settings, the gate, the done checks, the continuation, and the response writer built at construction to each run-local JevRuntime.
        return {"runtime_settings": self.runtime_settings, "preflight": self.preflight, "run_state": self.run_state, "continuation": self.continuation, "response": self._response}


__all__ = ["JevAgent"]
