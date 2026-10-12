"""FILE: vidbyte/middleware/builtins/readonly_paths.py

PURPOSE: Defines ReadonlyPathsMiddleware, which denies a write_text or replace_text call whose target file matches one of the caller's readonly_paths glob patterns, so the model can read those files but never edit them.
ROLE IN CODEBASE: Built by vidbyte/agents/coding.py (CodingAgent) from the patterns CodingAgentSettings (vidbyte/lib/dataclasses/coding.py) has already checked, and appended after the caller's own middleware; runs in AgentRuntime's before_tool_call hook. Follows ToolPolicyMiddleware (tool_policy.py).
ARCHITECTURE NOTE: The target is resolved with FileSystemPermissions.resolve_scoped_path over the same root the file tools use, so the check sees the file the tool would write however the model spells the path. Each pattern is matched with fnmatch.fnmatchcase against the root-relative POSIX path, where * also matches /, so tests/* and tests/** both cover everything under tests/. os.path.normcase on both sides makes the match case-insensitive on Windows.
FUNCTION INVENTORY: ReadonlyPathsMiddleware.before_tool_call is the narrated main function; _target resolves the call's path to a root-relative POSIX path, or None when the tool will reject the path itself; _matching_pattern returns the first pattern that matches.
COMMON MODIFICATION PATTERNS: A new file-editing tool on CodingAgent adds its name to _EDIT_TOOL_NAMES, provided it takes its target in a "path" argument.
WHAT NOT TO DO IN THIS FILE: 1. Do not parse bash commands; bash is deliberately unconfined. 2. Do not deny a path the tool would reject anyway; continue, so the tool's own error reaches the model unchanged. 3. Do not hold the CodingAgentSettings record; it carries API keys.
KNOWN EDGE CASES: bash and caller-supplied tools can still change a protected file. A pattern without a wildcard, such as tests, matches only that exact path. A symlink inside root that points at a protected file is denied, because the tool would write through it.
RELATED DOCS: docs/design/coding-agent-readonly-paths.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_readonly_paths.py
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Sequence
from pathlib import Path

from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.middleware.base import AgentMiddleware

_EDIT_TOOL_NAMES = frozenset({"write_text", "replace_text"})


class ReadonlyPathsMiddleware(AgentMiddleware):
    """Deny write_text and replace_text calls whose target file matches a readonly_paths pattern."""

    def __init__(self, root_dir: Path, readonly_paths: Sequence[str]) -> None:
        # Keeps a config over the file tools' root, so a path resolves
        # to the same file the tool would write.
        self._config = FileSystemToolConfig(root=root_dir)
        self._readonly_paths = tuple(readonly_paths)

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Deny an edit of a protected file before the tool runs; let every other call through."""
        # Only the two file-editing tools are checked. Reads, searches,
        # bash, and caller tools pass untouched.
        call = ctx.tool_call
        if call is None or call.tool_name not in _EDIT_TOOL_NAMES:
            return MiddlewareDecision.continue_()

        # Work out which file the tool would write. When the tool
        # would reject the path itself, such as a path outside the
        # root, let it run so the model sees the tool's own error.
        target = self._target(call.arguments.get("path", ""))
        if target is None:
            return MiddlewareDecision.continue_()

        # An unprotected file is edited as usual.
        pattern = self._matching_pattern(target)
        if pattern is None:
            return MiddlewareDecision.continue_()

        # Refuse the edit and tell the model which file and pattern
        # stopped it, so it changes other files instead of retrying.
        return MiddlewareDecision.deny_tool(
            f"`{target}` is read-only for this run (readonly_paths: `{pattern}`). Change other files instead; if it is a test, fix the code under test, not the test.",
            metadata={"path": target, "readonly_path": pattern},
        )

    def _target(self, path: str | Path) -> str | None:
        """Return the root-relative POSIX path the tool would write, or None when the tool will reject the path."""
        # The model may send any JSON value. The tools catch every
        # error from this resolution and report it themselves, so any
        # error here means "let the tool run".
        try:
            resolved = FileSystemPermissions.resolve_scoped_path(self._config, path)
            return resolved.relative_to(self._config.resolved_root()).as_posix()
        except Exception:
            return None

    def _matching_pattern(self, target: str) -> str | None:
        """Return the first readonly_paths pattern that matches target, ignoring case on Windows."""
        name = os.path.normcase(target)
        return next((pattern for pattern in self._readonly_paths if fnmatch.fnmatchcase(name, os.path.normcase(pattern))), None)


__all__ = ["ReadonlyPathsMiddleware"]
