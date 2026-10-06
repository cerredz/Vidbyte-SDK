"""FILE: tests/agent_test_support.py

PURPOSE:
    Creates offline BaseAgent fixtures that follow the production constructor's
    provider/model contract while replacing only the external runner boundary.
    This module must never restore removed public runner or modality arguments.
ROLE IN CODEBASE:
    Existing agent tests call build_test_agent or bind_test_runner; both target
    BaseAgent's private runner cache so no provider network call is made.
ARCHITECTURE NOTE:
    The helper is test-only infrastructure for the runner-inference design in
    docs/design/agent-runner-inference.md.
FUNCTION INVENTORY:
    OfflineTestAgent.fork(settings) -> BaseAgent: rebinds the same offline runner
    only when the child keeps the parent model identity.
    bind_test_runner(agent, runner, runner_type) -> agent: binds one offline
    runner and returns the same agent. Covered by the agent test modules.
    build_test_agent(runner, agent_type, agent_options) -> BaseAgent: constructs
    a production-signature agent and binds the offline runner.
COMMON MODIFICATION PATTERNS:
    Add runner kinds by passing runner_type; add specialized agents through
    agent_type instead of adding compatibility behavior to production code.
WHAT NOT TO DO IN THIS FILE:
    1. Do not monkeypatch BaseAgent.__init__; production signature tests own it.
    2. Do not make provider calls; tests must stay deterministic and offline.
    3. Do not export this helper from vidbyte; it belongs only to tests.
KNOWN EDGE CASES:
    BaseAgent still resolves runner type from model identity before consulting
    the cache, so fixtures must retain a valid provider and model name.
RELATED DOCS:
    docs/design/agent-runner-inference.md
    docs/design/green-ci-pipeline-and-design-skill-enforcement.md
TESTS:
    Used by the existing tests/test_agent_*.py and related runtime test modules.
"""

from __future__ import annotations

from typing import TypeVar

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.dataclasses.agents import AgentForkSettings

AgentT = TypeVar("AgentT", bound=BaseAgent)


class OfflineTestAgent(BaseAgent):
    """BaseAgent fixture that keeps fake runners across identity-preserving forks."""

    def fork(self, settings: AgentForkSettings | None = None) -> BaseAgent:
        """Fork normally, then carry fakes only when model identity is unchanged."""
        child = super().fork(settings)
        if settings is None or all(
            getattr(settings, field, None) is None
            for field in ("provider", "model_name", "temperature")
        ):
            child._runner_cache.update(self._runner_cache)
        return child


def bind_test_runner(agent: AgentT, runner: object, runner_type: str = RUNNER_TYPE_TEXT) -> AgentT:
    """Bind an offline runner to an already configured test agent."""
    agent._runner_cache[runner_type] = runner
    return agent


def build_test_agent(*agent_args: object, runner: object, agent_type: type[AgentT] = OfflineTestAgent, **agent_options: object) -> AgentT:
    """Construct an agent through the public model-identity API and bind a fake."""
    agent_options.setdefault("provider", "openai")
    agent_options.setdefault("model_name", "gpt-4.1-mini")
    agent = agent_type(*agent_args, **agent_options)
    return bind_test_runner(agent, runner)
