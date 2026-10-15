"""FILE: vidbyte/agents/infinite/settings.py

PURPOSE: Defines the two public configuration objects of InfiniteMemoryAgent: InfiniteWorkspaceSettings, the one memory workspace folder with its memory preset, seed files, and caps; and InfiniteMemoryAgentSettings, the model, the prompt, the project folder, the developer's extra tools, the loop limits, and the delegation caps shared by every agent in the tree.
ROLE IN CODEBASE: Built by the developer and passed to InfiniteMemoryAgent (vidbyte/agents/infinite/agent.py), which builds InfiniteWorkspace (workspace.py) from the workspace settings; read by the runtime, the launch tool, and the memory tools. Exported by vidbyte/agents/infinite/__init__.py, vidbyte/agents/__init__.py, and the root vidbyte package.
ARCHITECTURE NOTE: Settings objects live in the owning agent's settings.py (AGENTS.md Placement Rules, exception 1). Every check runs in __post_init__, so a constructed object is always valid and nothing downstream checks it again. Paths are stored resolved and absolute, so a later change of the working directory never moves the project or the memory. Checking settings never touches the disk beyond reading: the workspace folder is created by InfiniteWorkspace, never here.
FUNCTION INVENTORY: InfiniteWorkspaceSettings.__post_init__ is a narrated main function; _resolved_root checks and resolves root; _preset accepts the preset or its value; _seed_paths checks and resolves the seed files. InfiniteMemoryAgentSettings.__post_init__ is a narrated main function; _provider accepts the provider or its value; _resolved_root_dir checks and resolves root_dir; _extra_tools checks the developer's tools against Tools(...) and the reserved names.
COMMON MODIFICATION PATTERNS: A new setting adds one field, one check in its __post_init__, a named default in vidbyte/lib/constants/infinite.py, and one row in the folder README's limits table.
WHAT NOT TO DO IN THIS FILE: 1. Do not create the workspace folder or any file here; a refused setting must leave the disk unchanged. 2. Do not put api_key in an error message or in repr. 3. Do not accept a bare string where a sequence is expected; it would split into characters.
KNOWN EDGE CASES: root="" and root_dir="" are refused even though Path("") is the current folder. A seed file is checked to exist now and copied later, at agent construction. Two seed files with the same file name are refused, because both would land at seed/<name>. True is refused for every cap, although Python counts it as an int.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.3); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import cast

from vidbyte.agents.settings import AgentLoopSettings, ToolSettings
from vidbyte.lib.constants.infinite import (
    INFINITE_DEFAULT_MAX_AGENTS,
    INFINITE_DEFAULT_MAX_DEPTH,
    INFINITE_DEFAULT_MAX_ENTRIES_PER_AGENT,
    INFINITE_DEFAULT_MAX_ENTRY_TOKENS,
    INFINITE_DEFAULT_MAX_FILE_TOKENS,
    INFINITE_DEFAULT_MAX_FILES,
    INFINITE_DEFAULT_MAX_ITERATIONS,
    INFINITE_DEFAULT_MAX_PARALLEL,
    INFINITE_DEFAULT_MAX_TOKENS,
    INFINITE_MIN_AGENTS,
    INFINITE_MIN_CAP,
    INFINITE_RESERVED_TOOL_NAMES,
    INFINITE_TOOL_RESULT_MAX_CHARS,
)
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.enums.infinite import InfiniteMemoryPreset
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.errors import ConfigurationError, ToolRegistrationError
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.tools.adapters import ToolInput
from vidbyte.tools.catalog import Tools


@dataclass(frozen=True, slots=True)
class InfiniteWorkspaceSettings:
    """The one memory workspace: its folder, the memory preset, the seed files copied into it, and its caps.

    root and seed_files keep their raw types until __post_init__ checks
    them, because Path("") is the current folder and a bare string is a
    sequence of characters. After __post_init__ root is a resolved Path
    and seed_files a tuple of resolved Paths.
    """

    root: str | Path
    preset: InfiniteMemoryPreset = InfiniteMemoryPreset.SPARSE
    seed_files: tuple[str | Path, ...] = ()
    max_files: int = INFINITE_DEFAULT_MAX_FILES
    max_tokens: int = INFINITE_DEFAULT_MAX_TOKENS
    max_file_tokens: int = INFINITE_DEFAULT_MAX_FILE_TOKENS
    max_entry_tokens: int = INFINITE_DEFAULT_MAX_ENTRY_TOKENS
    max_entries_per_agent: int = INFINITE_DEFAULT_MAX_ENTRIES_PER_AGENT

    def __post_init__(self) -> None:
        # Keep the workspace folder as an absolute path. The folder may
        # not exist yet; the workspace creates it when the agent is
        # built.
        object.__setattr__(self, "root", self._resolved_root())

        # Accept the preset's value as text too, and keep the enum.
        object.__setattr__(self, "preset", self._preset())

        # Check that every seed file exists and that no two share a file
        # name, and keep their absolute paths.
        object.__setattr__(self, "seed_files", self._seed_paths())

        # @intent workspace-caps-are-whole-numbers
        # Every cap is a whole number of at least 1, so no cap can be
        # switched off by 0, a fraction, or True, and one note may never
        # be larger than the whole workspace.
        for name in ("max_files", "max_tokens", "max_file_tokens", "max_entry_tokens", "max_entries_per_agent"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < INFINITE_MIN_CAP:
                raise ConfigurationError(f"InfiniteWorkspaceSettings.{name} must be a whole number of at least {INFINITE_MIN_CAP}; got {value!r}.", details={"field": name})
        if self.max_file_tokens > self.max_tokens:
            raise ConfigurationError(f"InfiniteWorkspaceSettings.max_file_tokens must be at most max_tokens ({self.max_tokens}); got {self.max_file_tokens}.", details={"field": "max_file_tokens"})

    def _resolved_root(self) -> Path:
        # The folder path must be non-blank, and it may be missing or a
        # folder, but never an existing file.
        if not isinstance(self.root, (str, Path)) or not str(self.root).strip():
            raise ConfigurationError(f"InfiniteWorkspaceSettings.root must be a folder path; got {self.root!r}.", details={"field": "root"})
        root = Path(self.root).expanduser().resolve()
        if root.exists() and not root.is_dir():
            raise ConfigurationError(f"InfiniteWorkspaceSettings.root must be a folder, but {root} is a file.", details={"field": "root"})
        return root

    def _preset(self) -> InfiniteMemoryPreset:
        # The preset decides which memory tools every agent holds.
        try:
            return InfiniteMemoryPreset(self.preset)
        except ValueError as exc:
            choices = ", ".join(preset.value for preset in InfiniteMemoryPreset)
            raise ConfigurationError(f"InfiniteWorkspaceSettings.preset must be one of {choices}; got {self.preset!r}.", details={"field": "preset"}) from exc

    def _seed_paths(self) -> tuple[Path, ...]:
        # Each seed is copied to seed/<file name>, so each must be an
        # existing file and no two may share a file name.
        if isinstance(self.seed_files, (str, bytes)) or not isinstance(self.seed_files, Sequence):
            raise ConfigurationError(f"InfiniteWorkspaceSettings.seed_files must be a tuple or list of file paths; got {self.seed_files!r}.", details={"field": "seed_files"})
        seeds: list[Path] = []
        for raw in self.seed_files:
            path = Path(raw).expanduser().resolve() if isinstance(raw, (str, Path)) and str(raw).strip() else None
            if path is None or not path.is_file():
                raise ConfigurationError(f"InfiniteWorkspaceSettings.seed_files must name existing files; {raw} is not one.", details={"field": "seed_files"})
            clash = next((seed for seed in seeds if seed.name == path.name), None)
            if clash is not None:
                raise ConfigurationError(f"InfiniteWorkspaceSettings.seed_files must have distinct file names, but {clash} and {path} are both named {path.name}.", details={"field": "seed_files"})
            seeds.append(path)
        return tuple(seeds)


@dataclass(frozen=True, slots=True)
class InfiniteMemoryAgentSettings:
    """Everything every agent in an InfiniteMemory tree shares: the model, the prompt, the project folder, the workspace, the extra tools, the loop limits, and the delegation caps.

    root_dir keeps its raw type until __post_init__ checks it, because
    Path("") is the current folder. After __post_init__ it is a resolved
    Path, provider is a ModelProvider, and tools is a tuple.
    """

    name: str
    system_prompt: str
    provider: ModelProvider | str
    model_name: str
    root_dir: str | Path
    workspace: InfiniteWorkspaceSettings
    api_key: str | None = field(default=None, repr=False)
    temperature: float | None = None
    timeout_seconds: float | None = None
    tools: tuple[object, ...] = ()
    permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy.allow_all)
    loop: AgentLoopSettings = field(
        default_factory=partial(
            AgentLoopSettings,
            max_iterations=INFINITE_DEFAULT_MAX_ITERATIONS,
            tool_settings=ToolSettings(result_max_chars=INFINITE_TOOL_RESULT_MAX_CHARS),
        )
    )
    max_depth: int = INFINITE_DEFAULT_MAX_DEPTH
    max_parallel: int = INFINITE_DEFAULT_MAX_PARALLEL
    max_agents: int = INFINITE_DEFAULT_MAX_AGENTS

    def __post_init__(self) -> None:
        # @intent one-closed-surface-for-every-agent
        # These settings configure the root and every subagent it
        # starts, so a bad value is refused here, before any agent or
        # workspace exists, and names the field that must change. The
        # provider, policy, and loop are applied to every agent as
        # given.
        for name in ("name", "system_prompt", "model_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"InfiniteMemoryAgentSettings.{name} must be non-blank text; got {value!r}.", details={"field": name})

        # Accept the provider's value as text too, and keep the enum.
        object.__setattr__(self, "provider", self._provider())

        # @intent the-model-runs-under-its-provider
        # Every agent in the tree uses this model, so one the SDK cannot
        # run under the provider is refused here, not at a child's call.
        try:
            ProviderModelRegistry.validate_provider_model_pair(self.provider, self.model_name)
        except ConfigurationError as exc:
            raise ConfigurationError(f"InfiniteMemoryAgentSettings.model_name must be a model the SDK can run under the given provider; {exc.message}", details={"field": "model_name"}) from exc

        # Bash runs in the project folder, so it must exist; keep its
        # absolute path.
        object.__setattr__(self, "root_dir", self._resolved_root_dir())

        # The workspace, the policy, and the loop must be the SDK's own
        # objects, which have checked themselves.
        for name, kind in (("workspace", InfiniteWorkspaceSettings), ("permission_policy", PermissionPolicy), ("loop", AgentLoopSettings)):
            if not isinstance(getattr(self, name), kind):
                raise ConfigurationError(f"InfiniteMemoryAgentSettings.{name} must be a {kind.__name__}; got {type(getattr(self, name)).__name__}.", details={"field": name})

        # The key is text or None and never shown; the temperature and
        # timeout are numbers or None, and BaseAgent checks their
        # ranges.
        if self.api_key is not None and not isinstance(self.api_key, str):
            raise ConfigurationError(f"InfiniteMemoryAgentSettings.api_key must be text or None; got a {type(self.api_key).__name__}.", details={"field": "api_key"})
        for name in ("temperature", "timeout_seconds"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ConfigurationError(f"InfiniteMemoryAgentSettings.{name} must be a number or None; got {value!r}.", details={"field": name})

        # Check the developer's extra tools and keep them as a tuple.
        object.__setattr__(self, "tools", self._extra_tools())

        # @intent delegation-caps-are-whole-numbers
        # The depth and batch caps allow at least one level and one
        # task, and the agent cap at least one generator and verifier
        # pair.
        for name, minimum in (("max_depth", INFINITE_MIN_CAP), ("max_parallel", INFINITE_MIN_CAP), ("max_agents", INFINITE_MIN_AGENTS)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ConfigurationError(f"InfiniteMemoryAgentSettings.{name} must be a whole number of at least {minimum}; got {value!r}.", details={"field": name})

    def _provider(self) -> ModelProvider:
        # @intent provider-accepts-its-value
        # Developers may name the provider as text ("openai"); the enum
        # is stored, so every agent in the tree gets the same provider.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"InfiniteMemoryAgentSettings.provider must be a ModelProvider or its value; got {self.provider!r}.", details={"field": "provider"}) from exc

    def _resolved_root_dir(self) -> Path:
        # The project folder is where bash runs, so it must already
        # exist.
        root_dir = Path(self.root_dir).expanduser().resolve() if isinstance(self.root_dir, (str, Path)) and str(self.root_dir).strip() else None
        if root_dir is None or not root_dir.is_dir():
            raise ConfigurationError(f"InfiniteMemoryAgentSettings.root_dir must be an existing folder; got {self.root_dir}.", details={"field": "root_dir"})
        return root_dir

    def _extra_tools(self) -> tuple[object, ...]:
        # @intent extra-tools-never-shadow-preset-tools
        # The extras must form a valid catalog, and none may take the
        # name of a preset or run-bound tool, or the model could not
        # tell which one it is calling.
        if isinstance(self.tools, (str, bytes)) or not isinstance(self.tools, Sequence):
            raise ConfigurationError(f"InfiniteMemoryAgentSettings.tools must be a tuple or list of tools; got a {type(self.tools).__name__}.", details={"field": "tools"})
        try:
            names = Tools(cast("tuple[ToolInput, ...]", self.tools)).names()
        except (ToolRegistrationError, TypeError) as exc:
            raise ConfigurationError("InfiniteMemoryAgentSettings.tools must hold tools with distinct names.", details={"field": "tools"}) from exc
        taken = [name for name in names if name in INFINITE_RESERVED_TOOL_NAMES]
        if taken:
            raise ConfigurationError(f"InfiniteMemoryAgentSettings.tools must not reuse a reserved tool name; got {', '.join(taken)}. Reserved: {', '.join(INFINITE_RESERVED_TOOL_NAMES)}.", details={"field": "tools"})
        return tuple(self.tools)


__all__ = ["InfiniteMemoryAgentSettings", "InfiniteWorkspaceSettings"]
