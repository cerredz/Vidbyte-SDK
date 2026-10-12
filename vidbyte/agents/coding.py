"""FILE: vidbyte/agents/coding.py

PURPOSE: Defines CodingAgent, a BaseAgent that takes every BaseAgent keyword unchanged plus a required root_dir, four optional fetch keys, an optional verification command, optional readonly_paths, and a write_text rewrite limit (max_rewrite_lines, 300 by default), and preloads seven tools over one root folder: bash, read_lines, write_text, replace_text, glob, grep, and one web-fetch tool picked by the key passed. With verify_command set, the run may not finish until that command exits with code 0.
ROLE IN CODEBASE: Exported by vidbyte/agents/__init__.py and the root vidbyte package; builds on vidbyte/agents/base.py (BaseAgent), vidbyte/lib/dataclasses/coding.py (CodingAgentSettings), vidbyte/tools/toolsets/coding.py (CodingAgentTools), vidbyte/middleware/builtins/readonly_paths.py (ReadonlyPathsMiddleware), and vidbyte/middleware/builtins/verify_command.py (VerifyCommandMiddleware).
ARCHITECTURE NOTE: CodingAgent only gathers its own arguments into one validated CodingAgentSettings, builds CodingAgentTools from it, appends its own middleware after the caller's (ReadonlyPathsMiddleware when readonly_paths is non-empty, then VerifyCommandMiddleware when verify_command is set), and hands everything to BaseAgent.__init__; it overrides no BaseAgent method, so runs, forks, sessions, and JevAgent specialist checks behave exactly as for a BaseAgent holding the same tools, policy, and middleware. With neither set, the BaseAgent keywords are untouched. The verification runs through the runtime's review_finish middleware hook, never through an override.
FUNCTION INVENTORY: CodingAgent.__init__ is the narrated main function and the only method.
COMMON MODIFICATION PATTERNS: A new keyed fetch provider adds one key parameter on __init__, one key field on CodingAgentSettings, and one row in CodingAgentTools.authenticate_tools. A new check belongs in CodingAgentSettings, never in __init__, so a bad argument still fails before BaseAgent builds anything. Behavior at the end of a run belongs in a middleware hook, never in an override.
WHAT NOT TO DO IN THIS FILE: 1. Do not override generate_reply or any other BaseAgent method (JevAgent rejects specialists that replace generate_reply). 2. Do not read fetch keys from environment variables. 3. Do not supply a default system prompt or name. 4. Do not keep the settings record on the agent; a key lives only inside its provider client.
KNOWN EDGE CASES: CodingAgent.restore(state) raises TypeError for the missing root_dir; use BaseAgent.restore(state, tools=CodingAgent(...).tools.all(), middleware=agent.middleware), because exported state holds no middleware, so without middleware= the restored agent neither verifies nor protects readonly_paths. fork() returns a plain BaseAgent with the same tools, the same policy, and the same middleware, so a fork verifies too. The default allow-all policy also covers caller tools with WRITE or EXECUTE permission. Bash is not confined to root_dir. readonly_paths covers only write_text and replace_text, so bash and caller tools can still change a protected file. The verification command runs even under a read-only policy, because the developer wrote it. A non-linear runtime with verify_command or readonly_paths fails in BaseAgent, which rejects middleware there.
RELATED DOCS: docs/spec/coding-agent/spec.md; docs/design/coding-agent-verify-command.md; docs/design/coding-agent-readonly-paths.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_acceptance.py, tests/features/coding_agent/test_coding_agent_contract.py, tests/features/coding_agent/test_coding_agent_web_fetch.py, tests/features/coding_agent/test_coding_agent_readonly_paths.py, and tests/features/coding_agent/test_coding_agent_verify_command.py
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.constants.coding import CODING_DEFAULT_MAX_VERIFY_ATTEMPTS
from vidbyte.lib.dataclasses.coding import CodingAgentSettings
from vidbyte.middleware.builtins.readonly_paths import ReadonlyPathsMiddleware
from vidbyte.middleware.builtins.verify_command import VerifyCommandMiddleware
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.toolsets.coding import CodingAgentTools


class CodingAgent(BaseAgent):
    """BaseAgent preloaded with bash, read, write, edit, glob, grep, and one web-fetch tool over one root folder."""

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
        # builds anything, so a bad root folder, key, limit, or
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
        )

        # Build the seven coding tools over the root folder, which the
        # record has already resolved to an absolute path. write_text
        # refuses to replace an existing file over max_rewrite_lines.
        coding_tools = CodingAgentTools(settings)
        self.root_dir = Path(settings.root_dir)

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
            **kwargs,
        )


__all__ = ["CodingAgent"]
