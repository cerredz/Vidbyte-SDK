"""FILE: vidbyte/agents/coding.py

PURPOSE: Defines CodingAgent, a BaseAgent that takes every BaseAgent keyword unchanged plus a required root_dir, four optional fetch keys, an optional verification command, optional readonly_paths, a write_text rewrite limit (max_rewrite_lines, 300 by default), load_agents, load_environment, load_map, setup_commands, and progress_notes, and preloads seven tools over one root folder: bash, read_lines, write_text, replace_text, glob, grep, and one web-fetch tool picked by the key passed. With verify_command set, the run may not finish until that command exits with code 0. By default it also shows the root folder's AGENTS.md, a short block of environment facts (OS, date, shell, tools), then its MAP.md, to the model right after the system prompt, and keeps its own notes file, .vidbyte/coding-agent/progress.md, which it shows last and is told to keep up to date. Setup commands, when given, run once while the agent is built, and their pass/fail note is shown before the notes.
ROLE IN CODEBASE: Exported by vidbyte/agents/__init__.py and the root vidbyte package; builds on vidbyte/agents/base.py (BaseAgent), vidbyte/lib/dataclasses/coding.py (CodingAgentSettings), vidbyte/tools/toolsets/coding.py (CodingAgentTools), vidbyte/middleware/builtins/readonly_paths.py (ReadonlyPathsMiddleware), vidbyte/middleware/builtins/verify_command.py (VerifyCommandMiddleware), and vidbyte/agents/coding_context/ (AgentsMdLoader, EnvironmentLoader, MapMdLoader, SetupCommandsLoader, ProgressNotesLoader, and CodingContextWindow).
ARCHITECTURE NOTE: CodingAgent only gathers its own arguments into one validated CodingAgentSettings, builds CodingAgentTools from it, loads its context sections once, has CodingContextWindow put them ahead of the caller's context manager, appends its own middleware after the caller's (ReadonlyPathsMiddleware when readonly_paths is non-empty, then VerifyCommandMiddleware when verify_command is set), and hands everything to BaseAgent.__init__; it overrides no BaseAgent method, so runs, forks, sessions, and JevAgent specialist checks behave exactly as for a BaseAgent holding the same tools, policy, middleware, and context manager. With neither readonly_paths nor verify_command set, the caller's middleware reaches BaseAgent untouched. The verification runs through the runtime's review_finish middleware hook, never through an override.
FUNCTION INVENTORY: CodingAgent.__init__ is the narrated main function and the only method.
COMMON MODIFICATION PATTERNS: A new keyed fetch provider adds one key parameter on __init__, one key field on CodingAgentSettings, and one row in CodingAgentTools.authenticate_tools. A new context section adds one loader module in vidbyte/agents/coding_context/ that fills its reserved CodingContextSection member, plus its import and one entry in the sections tuple in __init__. A new check belongs in CodingAgentSettings, never in __init__, so a bad argument still fails before BaseAgent builds anything. Behavior at the end of a run belongs in a middleware hook, never in an override.
WHAT NOT TO DO IN THIS FILE: 1. Do not override generate_reply or any other BaseAgent method (JevAgent rejects specialists that replace generate_reply). 2. Do not read fetch keys from environment variables. 3. Do not supply a default system prompt or name. 4. Do not keep the settings record on the agent; a key lives only inside its provider client. 5. Do not add AGENTS.md or any other section to the system prompt string; sections go through CodingContextWindow.
KNOWN EDGE CASES: CodingAgent.restore(state) raises TypeError for the missing root_dir; use BaseAgent.restore(state, tools=CodingAgent(...).tools.all(), middleware=agent.middleware), because exported state holds no middleware, so without middleware= the restored agent neither verifies nor protects readonly_paths; restore does not bring back the AGENTS.md section either. fork() returns a plain BaseAgent with the same tools, the same policy, the same middleware, and a copy of the context manager, so a fork verifies too and keeps the section. The default allow-all policy also covers caller tools with WRITE or EXECUTE permission. Bash is not confined to root_dir. readonly_paths covers only write_text and replace_text, so bash and caller tools can still change a protected file. The verification command runs even under a read-only policy, because the developer wrote it. A non-linear runtime with verify_command or readonly_paths fails in BaseAgent, which rejects middleware there. AGENTS.md and MAP.md are read once, here; edits made later are not seen until a new agent is built. The environment section runs one bash probe per process (per bash and PATH) unless load_environment=False. Setup commands run here too, so construction blocks until they finish (up to the bash tool's time limit each), and a BaseAgent keyword error is raised after they ran. fork() keeps their section without running them again, and BaseAgent.restore() neither runs them nor brings the section back. When a section is loaded and the caller passes a context_manager, the agent renders a new manager, so tools bound to the caller's manager object (such as ContextWindowFactory tools) write to a manager this agent no longer shows.
RELATED DOCS: docs/spec/coding-agent/spec.md; docs/design/coding-agent-progress-notes.md; docs/design/coding-agent-verify-command.md; docs/design/coding-agent-readonly-paths.md; docs/design/coding-agent-environment-context.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_acceptance.py, tests/features/coding_agent/test_coding_agent_contract.py, tests/features/coding_agent/test_coding_agent_web_fetch.py, tests/features/coding_agent/test_coding_agent_agents_md.py, tests/features/coding_agent/test_coding_agent_environment.py, tests/features/coding_agent/test_coding_agent_map_md.py, tests/features/coding_agent/test_coding_agent_setup_commands.py, tests/features/coding_agent/test_coding_agent_progress_notes.py, tests/features/coding_agent/test_coding_agent_readonly_paths.py, and tests/features/coding_agent/test_coding_agent_verify_command.py
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.coding_context.agents_md import AgentsMdLoader
from vidbyte.agents.coding_context.environment import EnvironmentLoader
from vidbyte.agents.coding_context.map_md import MapMdLoader
from vidbyte.agents.coding_context.progress_notes import ProgressNotesLoader
from vidbyte.agents.coding_context.setup_commands import SetupCommandsLoader
from vidbyte.agents.coding_context.window import CodingContextWindow
from vidbyte.context.manager import ContextManager
from vidbyte.lib.constants.coding import CODING_DEFAULT_MAX_VERIFY_ATTEMPTS
from vidbyte.lib.dataclasses.coding import CodingAgentSettings
from vidbyte.middleware.builtins.readonly_paths import ReadonlyPathsMiddleware
from vidbyte.middleware.builtins.verify_command import VerifyCommandMiddleware
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.toolsets.coding import CodingAgentTools


class CodingAgent(BaseAgent):
    """BaseAgent preloaded with bash, read, write, edit, glob, grep, and one web-fetch tool over one root folder, showing its AGENTS.md, environment, and MAP.md."""

    def __init__(
        self,
        *,
        root_dir: str | Path,
        firecrawl_api_key: str | None = None,
        browserbase_api_key: str | None = None,
        parallel_api_key: str | None = None,
        tavily_api_key: str | None = None,
        verify_command: str | None = None,
        max_verify_attempts: int = CODING_DEFAULT_MAX_VERIFY_ATTEMPTS,
        tools: Sequence[object] | Tools = (),
        permission_policy: PermissionPolicy | None = None,
        readonly_paths: Sequence[str] = (),
        max_rewrite_lines: int | None = 300,
        load_agents: bool = True,
        load_environment: bool = True,
        load_map: bool = True,
        setup_commands: Sequence[str] = (),
        progress_notes: bool = True,
        context_manager: ContextManager | None = None,
        **kwargs: Any,
    ) -> None:
        # @intent coding-tools-run-by-default
        # BaseAgent allows only SAFE and READ tools by default, which
        # would deny bash, write_text, and replace_text on every call.
        # This agent therefore defaults to allow-all, while a policy
        # the caller passes is used as that exact object, so a caller
        # can still make the agent read-only. BaseAgent's own default
        # does not change.
        policy = PermissionPolicy.allow_all() if permission_policy is None else permission_policy

        # Check every argument in one validated record before BaseAgent
        # builds anything, so a bad root folder, key, switch, limit, or
        # verification setting fails here.
        settings = CodingAgentSettings(
            root_dir=root_dir,
            permission_policy=policy,
            max_rewrite_lines=max_rewrite_lines,
            tools=tools.all() if isinstance(tools, Tools) else tuple(tools),
            firecrawl_api_key=firecrawl_api_key,
            browserbase_api_key=browserbase_api_key,
            parallel_api_key=parallel_api_key,
            tavily_api_key=tavily_api_key,
            verify_command=verify_command,
            max_verify_attempts=max_verify_attempts,
            readonly_paths=readonly_paths,
            load_agents=load_agents,
            load_environment=load_environment,
            load_map=load_map,
            setup_commands=setup_commands,
            progress_notes=progress_notes,
        )

        # Build the seven coding tools over the root folder, which the
        # record has already resolved to an absolute path. write_text
        # refuses to replace an existing file over max_rewrite_lines.
        coding_tools = CodingAgentTools(settings)
        self.root_dir = Path(settings.root_dir)

        # Read each context section once, now, before the agent does
        # anything, so every run shows the model the same text. Each
        # loader returns None when it has nothing to add. The setup
        # commands run here, so the environment is ready before the
        # first turn, and construction waits for them. The notes
        # loader also creates the agent's notes file the first time.
        sections = (AgentsMdLoader.load(settings), EnvironmentLoader.load(settings), MapMdLoader.load(settings), SetupCommandsLoader.load(settings), ProgressNotesLoader.load(settings))

        # Put the sections right after the system prompt in their fixed
        # order, ahead of anything in the caller's own context manager,
        # which is never changed.
        context_window = CodingContextWindow.build(sections, context_manager)

        # Protect the read-only files by checking every edit after the
        # caller's own middleware has run. With no patterns nothing is
        # added, so the agent is exactly what it was before.
        if settings.readonly_paths:
            kwargs["middleware"] = (*kwargs.get("middleware", ()), ReadonlyPathsMiddleware(self.root_dir, settings.readonly_paths))

        # @intent the-run-ends-only-after-the-command-passes
        # With a verification command, the middleware that runs it at
        # every finish attempt goes after the caller's own middleware,
        # so the runtime's review_finish hook reaches it without any
        # BaseAgent override. Without one, the caller's keywords reach
        # BaseAgent untouched, so nothing about the run changes.
        if settings.verify_command is not None:
            verifier = VerifyCommandMiddleware(settings.verify_command, self.root_dir, settings.max_verify_attempts)
            kwargs["middleware"] = (*kwargs.get("middleware", ()), verifier)

        # Hand everything else to BaseAgent unchanged. The caller's own
        # tools follow the seven in the caller's order, and a clashing
        # name fails in BaseAgent's catalog.
        super().__init__(
            tools=(*coding_tools.all(), *settings.tools),
            permission_policy=settings.permission_policy,
            context_manager=context_window,
            **kwargs,
        )


__all__ = ["CodingAgent"]
