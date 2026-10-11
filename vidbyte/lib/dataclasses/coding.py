"""FILE: vidbyte/lib/dataclasses/coding.py

PURPOSE: Defines CodingAgentSettings, the validated record of every CodingAgent constructor argument: the root folder, at most one web-fetch key, the caller's own tools, the permission policy, and the read-only path patterns.
ROLE IN CODEBASE: Built by vidbyte/agents/coding.py (CodingAgent.__init__) and read by vidbyte/tools/toolsets/coding.py (CodingAgentTools); its readonly_paths feed vidbyte/middleware/builtins/readonly_paths.py; exported by the root vidbyte package.
ARCHITECTURE NOTE: Every check lives in __post_init__, so a constructed record is always valid and neither CodingAgent nor CodingAgentTools re-checks it. root_dir is stored as the resolved absolute Path, so a later change of the process working directory never moves the tools. Key fields are repr=False, so printing the record never shows a key.
FUNCTION INVENTORY: CodingAgentSettings.__post_init__ is the narrated main function; _resolved_root checks and resolves root_dir; _check_fetch_keys checks the four keys; _check_tools_and_policy checks the caller's tools and the policy; _readonly_paths checks the patterns and returns them as a tuple.
COMMON MODIFICATION PATTERNS: A new keyed fetch provider adds one key field here (repr=False), one row in _check_fetch_keys, and one row in CodingAgentTools.authenticate_tools.
WHAT NOT TO DO IN THIS FILE: 1. Do not read keys from environment variables. 2. Do not put a key value in an error message or its details; name the parameter instead. 3. Do not drop repr=False from a key field. 4. Do not import from vidbyte.tools or vidbyte.agents; vidbyte/lib is the bottom layer.
KNOWN EDGE CASES: root_dir="" is rejected even though Path("") is the current folder, which is why root_dir keeps its raw type until __post_init__ checks it. readonly_paths keeps its raw type for the same reason: tuple("tests/**") would split a bare string into characters. Caller tools are only checked to be a tuple here; BaseAgent decides which items are tools.
RELATED DOCS: docs/spec/coding-agent/spec.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_contract.py, tests/features/coding_agent/test_coding_agent_web_fetch.py, and tests/features/coding_agent/test_coding_agent_readonly_paths.py
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class CodingAgentSettings:
    """Validated CodingAgent arguments: the root folder, at most one fetch key, the caller's tools, the policy, and the read-only patterns.

    root_dir is typed Path | str because the record must see the raw
    value: Path("") is the current folder, so converting first would
    accept an empty string. After __post_init__ it is always the
    resolved absolute Path. readonly_paths is typed Sequence[str] for
    the same reason: tuple("tests/**") would split a bare string into
    characters. After __post_init__ it is always a tuple of str.
    """

    root_dir: Path | str
    permission_policy: PermissionPolicy
    tools: tuple[object, ...] = ()
    firecrawl_api_key: str | None = field(default=None, repr=False)
    browserbase_api_key: str | None = field(default=None, repr=False)
    parallel_api_key: str | None = field(default=None, repr=False)
    tavily_api_key: str | None = field(default=None, repr=False)
    readonly_paths: Sequence[str] = ()

    def __post_init__(self) -> None:
        # Check the root folder and keep its absolute path, so a later
        # change of the working directory never moves the tools.
        object.__setattr__(self, "root_dir", self._resolved_root())

        # Check the fetch keys: each one is non-blank text, and the
        # caller supplied no more than one.
        self._check_fetch_keys()

        # Check the caller's tools and the policy every call runs under.
        self._check_tools_and_policy()

        # Check the read-only patterns and keep them as a tuple.
        object.__setattr__(self, "readonly_paths", self._readonly_paths())

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

    def _readonly_paths(self) -> tuple[str, ...]:
        """Return readonly_paths as a tuple, or raise unless it is a list or tuple of non-blank strings."""
        # @intent readonly-paths-reject-a-bare-string
        # A bare string is a sequence of characters, so "tests/**"
        # would protect the files "t", "e", and so on, and the tests
        # would stay editable without any error.
        paths = self.readonly_paths
        if isinstance(paths, str) or not isinstance(paths, Sequence):
            raise ConfigurationError(f"CodingAgent readonly_paths must be a list or tuple of glob strings such as ['tests/**'], not a {type(paths).__name__}.", details={"readonly_paths_type": type(paths).__name__})
        bad = [repr(path) for path in paths if not isinstance(path, str) or not path.strip()]
        if bad:
            raise ConfigurationError("CodingAgent readonly_paths entries must be non-blank strings.", details={"bad_entries": bad})
        return tuple(paths)


__all__ = ["CodingAgentSettings"]
