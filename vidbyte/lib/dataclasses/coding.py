"""FILE: vidbyte/lib/dataclasses/coding.py

PURPOSE: Defines CodingAgentSettings, the validated record of every CodingAgent constructor argument: the root folder, at most one web-fetch key, the caller's own tools, the permission policy, and the write_text rewrite limit.
ROLE IN CODEBASE: Built by vidbyte/agents/coding.py (CodingAgent.__init__) and read by vidbyte/tools/toolsets/coding.py (CodingAgentTools); exported by the root vidbyte package.
ARCHITECTURE NOTE: Every check lives in __post_init__, so a constructed record is always valid and neither CodingAgent nor CodingAgentTools re-checks it. root_dir is stored as the resolved absolute Path, so a later change of the process working directory never moves the tools. Key fields are repr=False, so printing the record never shows a key.
FUNCTION INVENTORY: CodingAgentSettings.__post_init__ is the narrated main function; _resolved_root checks and resolves root_dir; _check_fetch_keys checks the four keys; _check_tools_and_policy checks the caller's tools and the policy; _check_max_rewrite_lines checks the rewrite limit.
COMMON MODIFICATION PATTERNS: A new keyed fetch provider adds one key field here (repr=False), one row in _check_fetch_keys, and one row in CodingAgentTools.authenticate_tools.
WHAT NOT TO DO IN THIS FILE: 1. Do not read keys from environment variables. 2. Do not put a key value in an error message or its details; name the parameter instead. 3. Do not drop repr=False from a key field. 4. Do not import from vidbyte.tools or vidbyte.agents; vidbyte/lib is the bottom layer.
KNOWN EDGE CASES: root_dir="" is rejected even though Path("") is the current folder, which is why root_dir keeps its raw type until __post_init__ checks it. Caller tools are only checked to be a tuple here; BaseAgent decides which items are tools.
RELATED DOCS: docs/spec/coding-agent/spec.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_contract.py and tests/features/coding_agent/test_coding_agent_web_fetch.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class CodingAgentSettings:
    """Validated CodingAgent arguments: the root folder, at most one fetch key, the caller's tools, the policy, and the rewrite limit.

    root_dir is typed Path | str because the record must see the raw
    value: Path("") is the current folder, so converting first would
    accept an empty string. After __post_init__ it is always the
    resolved absolute Path.
    """

    root_dir: Path | str
    permission_policy: PermissionPolicy
    max_rewrite_lines: int | None
    tools: tuple[object, ...] = ()
    firecrawl_api_key: str | None = field(default=None, repr=False)
    browserbase_api_key: str | None = field(default=None, repr=False)
    parallel_api_key: str | None = field(default=None, repr=False)
    tavily_api_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # Check the root folder and keep its absolute path, so a later
        # change of the working directory never moves the tools.
        object.__setattr__(self, "root_dir", self._resolved_root())

        # Check the fetch keys: each one is non-blank text, and the
        # caller supplied no more than one.
        self._check_fetch_keys()

        # Check the caller's tools and the policy every call runs under.
        self._check_tools_and_policy()

        # Check the rewrite limit: None turns it off, and a number is
        # the most lines an existing file may have and still be
        # replaced whole.
        self._check_max_rewrite_lines()

    def _resolved_root(self) -> Path:
        """Return root_dir as an absolute path, or raise when it is not an existing directory."""
        # os.path.isdir, not Path.is_dir: Path("") is the current
        # folder, so an empty string would pass.
        root = self.root_dir
        if not isinstance(root, (str, os.PathLike)) or not os.path.isdir(root):
            raise ConfigurationError("CodingAgent root_dir must be an existing directory.", details={"root_dir": str(root)})
        return Path(root).resolve()

    def _check_fetch_keys(self) -> None:
        """Raise unless every supplied fetch key is non-blank text and at most one was supplied."""
        # @intent the-supplied-key-picks-one-fetch-provider
        # The key parameter the caller set picks the fetch provider. A
        # blank or non-string key would turn every fetch into a 401,
        # and two keys would bill one vendor while silently ignoring
        # the other, so both fail here. Errors name the parameter,
        # never the value, so a key cannot leak through an exception.
        keys = (
            ("firecrawl_api_key", self.firecrawl_api_key),
            ("browserbase_api_key", self.browserbase_api_key),
            ("parallel_api_key", self.parallel_api_key),
            ("tavily_api_key", self.tavily_api_key),
        )
        supplied = [name for name, key in keys if key is not None]
        blank = [name for name, key in keys if key is not None and (not isinstance(key, str) or not key.strip())]
        if blank:
            raise ConfigurationError(f"CodingAgent {', '.join(blank)} must be a non-blank string.", details={"parameters": blank})
        if len(supplied) > 1:
            raise ConfigurationError(f"CodingAgent accepts at most one fetch key, but got {', '.join(supplied)}.", details={"parameters": supplied})

    def _check_tools_and_policy(self) -> None:
        """Raise unless tools is a tuple and permission_policy is a PermissionPolicy."""
        # @intent policy-is-checked-before-any-tool-runs
        # The agent runs every tool call under this permission policy,
        # so anything that is not a PermissionPolicy fails here, at
        # construction, instead of on the first tool call of a run.
        if not isinstance(self.tools, tuple):
            raise ConfigurationError("CodingAgent tools must be a tuple.", details={"tools_type": type(self.tools).__name__})
        if not isinstance(self.permission_policy, PermissionPolicy):
            raise ConfigurationError("CodingAgent permission_policy must be a PermissionPolicy.", details={"permission_policy_type": type(self.permission_policy).__name__})

    def _check_max_rewrite_lines(self) -> None:
        """Raise unless max_rewrite_lines is None or an int of at least 1."""
        # @intent big-existing-files-are-edited-not-rewritten
        # True or 2.5 would quietly set a different limit than the
        # caller meant, and 0 would refuse every existing file, so all
        # of them fail here instead of on the first write_text call.
        limit = self.max_rewrite_lines
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
            raise ConfigurationError("CodingAgent max_rewrite_lines must be None or an int of at least 1.", details={"max_rewrite_lines": repr(limit)})


__all__ = ["CodingAgentSettings"]
