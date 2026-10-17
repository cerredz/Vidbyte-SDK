"""FILE: vidbyte/agents/browser/agent.py

PURPOSE: Exposes BrowserAgent, an agent for long-running browser tasks built from one validated BrowserAgentSettings: an orchestrator that plans, keeps a goal card, and hands bounded page work to fresh episode workers that act through the developer's own browser MCP servers.
ROLE IN CODEBASE: Maps the settings into BaseAgent with AgentRuntimeType.BROWSER, which RuntimeRegistry resolves to BrowserAgentRuntime (runtime.py). Queues each configured server under its role name (tools.py), and passes the settings, the role map, the live servers, the response writer (response.py), and the event emitter (events.py) to each run-local runtime through _runtime_extension_kwargs.
ARCHITECTURE NOTE: A closed construction surface like JevAgent and InfiniteMemoryAgent: callers pass only the settings object, and the runtime, the orchestrator rules, and the server names are fixed here. The servers are queued through the MCP mixin's own builders (with_preset_mcp_server and with_mcp_server), which start them lazily on the first run, each with only its own env. The orchestrator has no compaction middleware; the runtime rebuilds its stored conversation instead (spec D-11). Durable sessions are not supported, because a restored agent would be a plain BaseAgent that the runtime refuses.
FUNCTION INVENTORY: __init__ is the narrated main function; response returns the most recent run's record; _runtime_extension_kwargs hands the run-time objects to the runtime.
COMMON MODIFICATION PATTERNS: A new agent-level capability is a validated field on BrowserAgentSettings (settings.py) used here or passed to the runtime through _runtime_extension_kwargs.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept BaseAgent keyword arguments; everything comes from the settings. 2. Do not build an McpServerConfig or read os.environ here; the mixin builds the configs from the settings' env. 3. Do not log or print mcp_servers(); a live handle's config holds the server's env.
KNOWN EDGE CASES: The servers start on the first run and stay up between runs of the same agent; the synchronous run() starts them again on its own event loop (EC-22). response describes only the most recent run and is replaced when the next run starts. Overlapping runs on one agent are unsupported (EC-21).
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 4, 8.1 D-1, D-7, D-21, and 8.5); vidbyte/agents/browser/README.md; vidbyte/agents/infinite/agent.py (the pattern this follows)
TESTS: tests/features/browser_agent/test_browser_agent_contract.py, tests/features/browser_agent/test_browser_agent_acceptance.py, and tests/features/browser_agent/test_browser_agent_observability.py
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.browser.events import BrowserAgentEvents
from vidbyte.agents.browser.response import BrowserResponse
from vidbyte.agents.browser.settings import BrowserAgentSettings
from vidbyte.agents.browser.tools import BrowserAgentTools
from vidbyte.lib.dataclasses.browser import BrowserAgentResponse
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.mcp import McpPresetDefinition


class BrowserAgent(BaseAgent):
    """An orchestrator that plans long browser tasks and hands bounded page work to fresh episode workers."""

    session_persistence_supported = False

    def __init__(self, settings: BrowserAgentSettings) -> None:
        # @intent closed-browser-construction-surface
        # Only the validated settings object configures this agent, so
        # the runtime, the rules, the server names, and the keys stay
        # owned by this package.
        if not isinstance(settings, BrowserAgentSettings):
            raise ConfigurationError(f"BrowserAgent requires a BrowserAgentSettings instance; got {type(settings).__name__}.", details={"settings": type(settings).__name__})
        self.settings = settings

        # Build the run's collaborators once: the map from server name
        # to role, the record a developer reads, and the event emitter.
        self.browser_tools = BrowserAgentTools(settings)
        self._response = BrowserResponse()
        self.events = BrowserAgentEvents(settings.on_event)

        # Build the orchestrator: the developer's prompt plus the rules
        # for planning and delegating, the developer's extra tools, and
        # no history trim, because the runtime rebuilds the history.
        # @intent limits-in-code-behavior-in-the-prompt
        # The rules describe how to plan and delegate; every cap is
        # enforced in code, so the prompt holds no numbers the code
        # could contradict.
        rules = Prompts().get(Prompt.BROWSER_AGENT_ORCHESTRATOR_SYSTEM_PROMPT)
        super().__init__(
            name=settings.name,
            system_prompt=f"{settings.system_prompt}\n\n{rules}",
            runtime=AgentRuntimeType.BROWSER,
            tools=settings.tools,
            permission_policy=settings.permission_policy,
            agent_loop_settings=settings.loop,
            api_keys=settings.api_keys,
            model_mode=settings.model_mode,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
        )

        # Queue every server under its role name with only its own env
        # and timeout; the mixin starts them on the first run.
        # @intent each-server-gets-only-its-own-keys
        # A key given to one server must never reach another server, a
        # tool, an event, or a model, so each server's env is handed
        # only to that server's own config.
        for name, _role, server in BrowserAgentTools.named_servers(settings):
            if isinstance(server.preset, McpPresetDefinition):
                self.with_preset_mcp_server(server.preset.name, name=name, env=server.env, timeout=server.timeout)
            elif server.command is not None:
                self.with_mcp_server(server.command, name=name, env=server.env, timeout=server.timeout)

    @property
    def response(self) -> BrowserAgentResponse:
        """Return everything the most recent run produced: the goal card, the episode cards, the rechecks, the rebuild count, and the usage."""
        return self._response.state

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # @intent live-servers-reach-only-the-runtime
        # Hands the settings, the role map, the live servers, the
        # response writer, and the event emitter to each run-local
        # BrowserAgentRuntime. The servers are read per run, after they
        # connect, and their configs hold each server's env, so they go
        # to the runtime only.
        return {"settings": self.settings, "browser_tools": self.browser_tools, "servers": self.mcp_servers(), "response": self._response, "events": self.events}


__all__ = ["BrowserAgent"]
