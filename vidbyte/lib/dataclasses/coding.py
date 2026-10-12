"""FILE: vidbyte/lib/dataclasses/coding.py

PURPOSE: Defines CodingAgentSettings, the validated record of every CodingAgent constructor argument: the root folder, at most one web-fetch key, the caller's own tools, the permission policy, and the context-section switches (load_agents, load_environment, progress_notes). Also defines CodingContextSectionText and CodingContextSectionItem, one section of the CodingAgent context window as text or as a ready context primitive, and EnvironmentProbeResult, what the environment section's bash probe reported.
ROLE IN CODEBASE: CodingAgentSettings is built by vidbyte/agents/coding.py (CodingAgent.__init__), read by vidbyte/tools/toolsets/coding.py (CodingAgentTools) and by the section loaders in vidbyte/agents/coding_context/, and exported by the root vidbyte package. CodingContextSectionText or CodingContextSectionItem is returned by each section loader and read by CodingContextWindow (vidbyte/agents/coding_context/window.py). EnvironmentProbeResult is returned by EnvironmentProbe (vidbyte/agents/coding_context/environment_probe.py) and read by EnvironmentLoader.
ARCHITECTURE NOTE: Every check lives in __post_init__, so a constructed record is always valid and neither CodingAgent nor CodingAgentTools re-checks it. root_dir is stored as the resolved absolute Path, so a later change of the process working directory never moves the tools. Key fields are repr=False, so printing the record never shows a key.
FUNCTION INVENTORY: CodingAgentSettings.__post_init__ is the narrated main function; _resolved_root checks and resolves root_dir; _check_fetch_keys checks the four keys; _check_tools_and_policy checks the caller's tools and the policy; _check_context_switches checks the section switches. CodingContextSectionText.__post_init__ checks the section kind and the text fields; CodingContextSectionItem.__post_init__ checks the section kind and, with _is_primitive, the item's shape; EnvironmentProbeResult.__post_init__ checks each reported field.
COMMON MODIFICATION PATTERNS: A new keyed fetch provider adds one key field here (repr=False), one row in _check_fetch_keys, and one row in CodingAgentTools.authenticate_tools. A context section with its own on/off switch adds one bool field here and one isinstance check in _check_context_switches.
WHAT NOT TO DO IN THIS FILE: 1. Do not read keys from environment variables. 2. Do not put a key value in an error message or its details; name the parameter instead. 3. Do not drop repr=False from a key field. 4. Do not import from vidbyte.tools or vidbyte.agents; vidbyte/lib is the bottom layer.
KNOWN EDGE CASES: root_dir="" is rejected even though Path("") is the current folder, which is why root_dir keeps its raw type until __post_init__ checks it. Caller tools are only checked to be a tuple here; BaseAgent decides which items are tools. load_agents=1 is rejected even though 1 == True, so a stray int or string never flips a switch through truthiness. CodingContextSectionText does not cap its content; each loader bounds its own text. CodingContextSectionItem checks its item by shape, not isinstance, because vidbyte/lib cannot import vidbyte.context.
RELATED DOCS: docs/spec/coding-agent/spec.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_contract.py, tests/features/coding_agent/test_coding_agent_web_fetch.py, tests/features/coding_agent/test_coding_agent_agents_md.py, tests/features/coding_agent/test_coding_agent_environment.py, and tests/features/coding_agent/test_coding_agent_progress_notes.py
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.context import EnvironmentTool
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.context.primitives import ContextItem


@dataclass(frozen=True, slots=True)
class CodingAgentSettings:
    """Validated CodingAgent arguments: the root folder, at most one fetch key, the caller's tools, the policy, and the section switches.

    root_dir is typed Path | str because the record must see the raw
    value: Path("") is the current folder, so converting first would
    accept an empty string. After __post_init__ it is always the
    resolved absolute Path.
    """

    root_dir: Path | str
    permission_policy: PermissionPolicy
    tools: tuple[object, ...] = ()
    firecrawl_api_key: str | None = field(default=None, repr=False)
    browserbase_api_key: str | None = field(default=None, repr=False)
    parallel_api_key: str | None = field(default=None, repr=False)
    tavily_api_key: str | None = field(default=None, repr=False)
    load_agents: bool = True
    load_environment: bool = True
    progress_notes: bool = True

    def __post_init__(self) -> None:
        # Check the root folder and keep its absolute path, so a later
        # change of the working directory never moves the tools.
        object.__setattr__(self, "root_dir", self._resolved_root())

        # Check the fetch keys: each one is non-blank text, and the
        # caller supplied no more than one.
        self._check_fetch_keys()

        # Check the caller's tools and the policy every call runs under.
        self._check_tools_and_policy()

        # Check the switches that turn context sections on or off: each
        # must be a real bool, so a string such as "no" cannot turn
        # loading on through truthiness.
        self._check_context_switches()

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

    def _check_context_switches(self) -> None:
        """Raise unless every context-section switch is a real bool, not a truthy stand-in such as 1 or "yes"."""
        if not isinstance(self.load_agents, bool):
            raise ConfigurationError("CodingAgent load_agents must be True or False.", details={"parameter": "load_agents", "load_agents_type": type(self.load_agents).__name__})
        if not isinstance(self.load_environment, bool):
            raise ConfigurationError("CodingAgent load_environment must be True or False.", details={"parameter": "load_environment", "load_environment_type": type(self.load_environment).__name__})
        if not isinstance(self.progress_notes, bool):
            raise ConfigurationError("CodingAgent progress_notes must be True or False.", details={"parameter": "progress_notes", "progress_notes_type": type(self.progress_notes).__name__})


@dataclass(frozen=True, slots=True)
class CodingContextSectionText:
    """One section of a CodingAgent context window: its kind, a title, the text the model sees, and where it came from.

    A section loader returns one of these, or None when it has nothing
    to add. CodingContextWindow places it after the system prompt under
    the primitive id section.value, in CodingContextSection order.
    """

    section: CodingContextSection
    title: str
    content: str
    source: str | None = None

    def __post_init__(self) -> None:
        # Check the section kind, which decides where the text renders
        # and which primitive id it is stored under.
        self._check_section()

        # Check the title and the text: a blank one would render an
        # empty heading or an empty section the model cannot use.
        self._check_text_fields()

    def _check_section(self) -> None:
        """Raise unless section is a CodingContextSection member."""
        if not isinstance(self.section, CodingContextSection):
            raise ConfigurationError("CodingContextSectionText section must be a CodingContextSection.", details={"field": "section", "section_type": type(self.section).__name__})

    def _check_text_fields(self) -> None:
        """Raise unless title and content are non-blank strings and source is None or a non-blank string."""
        texts = (("title", self.title), ("content", self.content))
        blank = [name for name, value in texts if not isinstance(value, str) or not value.strip()]
        if self.source is not None and (not isinstance(self.source, str) or not self.source.strip()):
            blank.append("source")
        if blank:
            raise ConfigurationError(f"CodingContextSectionText {', '.join(blank)} must be a non-blank string.", details={"fields": blank})


@dataclass(frozen=True, slots=True)
class CodingContextSectionItem:
    """One section of a CodingAgent context window given as a context primitive that formats its own text.

    A loader returns one of these when its facts are structured, as
    EnvironmentLoader does with an EnvironmentContextItem. The window
    places item under the primitive id section.value, so the loader
    leaves item.primitive_id unset.
    """

    section: CodingContextSection
    item: ContextItem

    def __post_init__(self) -> None:
        # Check the section kind, which decides where the item renders
        # and which primitive id it is stored under.
        if not isinstance(self.section, CodingContextSection):
            raise ConfigurationError("CodingContextSectionItem section must be a CodingContextSection.", details={"field": "section", "section_type": type(self.section).__name__})

        # Check that the item is a context primitive the window can
        # place and render.
        if not self._is_primitive(self.item):
            raise ConfigurationError("CodingContextSectionItem item must be a context primitive dataclass with a primitive_id field, a title, and to_context_text().", details={"field": "item", "item_type": type(self.item).__name__})

    @staticmethod
    def _is_primitive(item: object) -> bool:
        """Return whether item is a dataclass instance with a primitive_id field, a text title, and a to_context_text method."""
        # @intent section-item-is-checked-by-shape
        # vidbyte/lib cannot import the context layer, so the item is
        # checked by the surface the window uses: dataclasses.replace
        # on primitive_id, then the title and to_context_text().
        if not dataclasses.is_dataclass(item) or isinstance(item, type):
            return False
        has_id = "primitive_id" in {entry.name for entry in dataclasses.fields(item)}
        return has_id and isinstance(getattr(item, "title", None), str) and callable(getattr(item, "to_context_text", None))


@dataclass(frozen=True, slots=True)
class EnvironmentProbeResult:
    """What one bash probe reported: the bash version and uname, the tools and system package managers on bash's PATH, and why it failed.

    An empty record means no probe ran, because there was no bash.
    error is set when the probe timed out, exited non-zero, or could
    not start; the other fields still hold what it printed first.
    """

    bash_version: str | None = None
    uname: str | None = None
    tools: tuple[EnvironmentTool, ...] = ()
    package_managers: tuple[str, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        # Check each reported field, so the loader can hand them to the
        # environment primitive unchanged.
        texts = (("bash_version", self.bash_version), ("uname", self.uname), ("error", self.error))
        wrong = [name for name, value in texts if value is not None and (not isinstance(value, str) or not value.strip())]
        if not isinstance(self.tools, tuple) or not all(isinstance(tool, EnvironmentTool) for tool in self.tools):
            wrong.append("tools")
        if not isinstance(self.package_managers, tuple) or not all(isinstance(name, str) and name.strip() for name in self.package_managers):
            wrong.append("package_managers")
        if wrong:
            raise ConfigurationError(f"EnvironmentProbeResult {', '.join(wrong)} has the wrong type or is blank.", details={"fields": wrong})


__all__ = ["CodingAgentSettings", "CodingContextSectionItem", "CodingContextSectionText", "EnvironmentProbeResult"]
