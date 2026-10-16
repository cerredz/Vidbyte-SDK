"""FILE: vidbyte/agents/infinite/settings.py

PURPOSE: Defines the two public configuration objects of InfiniteMemoryAgent: InfiniteWorkspaceSettings, the one memory workspace folder with its memory preset, seed files, and caps; and InfiniteMemoryAgentSettings, the model, the prompt, the project folder, the developer's extra tools, the loop limits, and the delegation caps shared by every agent in the tree.
ROLE IN CODEBASE: Built by the developer and passed to InfiniteMemoryAgent (vidbyte/agents/infinite/agent.py), which builds InfiniteWorkspace (workspace.py) from the workspace settings; read by the runtime, the launch tool, and the memory tools. Exported by vidbyte/agents/infinite/__init__.py, vidbyte/agents/__init__.py, and the root vidbyte package.
ARCHITECTURE NOTE: Settings objects live in the owning agent's settings.py (AGENTS.md Placement Rules, exception 1). Every check runs in __post_init__, so a constructed object is always valid and nothing downstream checks it again. Each field check is one call to the SDK's canonical RecordFieldValidator or RecordFieldConverter (vidbyte/lib/dataclasses/validation.py), the model check is ProviderModelRegistry's, and the key match is ProviderKeyMatcher's; only the rules that tie two fields together or name the reserved tools are written here. Paths are stored resolved and absolute, so a later change of the working directory never moves the project or the memory. Checking settings never touches the disk beyond reading: the workspace folder is created by InfiniteWorkspace, never here.
FUNCTION INVENTORY: InfiniteWorkspaceSettings.__post_init__ and InfiniteMemoryAgentSettings.__post_init__ are narrated main functions with no private helpers, and InfiniteMemoryAgentSettings.delegation_limits builds the DelegationLimits record for the middleware: RecordFieldConverter.to_folder resolves root and root_dir, to_enum accepts the preset and the provider or their values, to_files checks and resolves the seed files, to_tuple and Tools(...) check the developer's tools, and RecordFieldValidator checks the text fields and the caps.
COMMON MODIFICATION PATTERNS: A new setting adds one field, one RecordFieldValidator or RecordFieldConverter call in its __post_init__ (a check they lack becomes a new option there, never a helper here), a named default in vidbyte/lib/constants/infinite.py, and one row in the folder README's limits table.
WHAT NOT TO DO IN THIS FILE: 1. Do not create the workspace folder or any file here; a refused setting must leave the disk unchanged. 2. Do not put api_keys or vidbyte_api_key in an error message or in repr. 3. Do not accept a bare string where a sequence is expected; it would split into characters.
KNOWN EDGE CASES: root="" and root_dir="" are refused even though Path("") is the current folder. A seed file is checked to exist now and copied later, at agent construction. Two seed files with the same file name are refused, because both would land at seed/<name>. True is refused for every cap, although Python counts it as an int. A refusal names the field as InfiniteWorkspaceSettings.<field> or InfiniteMemoryAgentSettings.<field>, in the message and in details["field"].
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.3); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py
"""

from __future__ import annotations

from collections.abc import Iterable
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
    INFINITE_LAUNCH_TASKS_ARGUMENT,
    INFINITE_LAUNCH_TOOL_NAME,
    INFINITE_MIN_AGENTS,
    INFINITE_MIN_CAP,
    INFINITE_RESERVED_TOOL_NAMES,
    INFINITE_TOOL_RESULT_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import ProviderKeys
from vidbyte.lib.dataclasses.middleware import DelegationLimits
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.infinite import InfiniteMemoryPreset
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.text_model import TextModelMode
from vidbyte.lib.errors import ConfigurationError, ToolRegistrationError
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher
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
        # not exist yet, because the workspace creates it when the agent
        # is built, but it may never be an existing file.
        object.__setattr__(self, "root", RecordFieldConverter.to_folder(self.root, "InfiniteWorkspaceSettings.root"))

        # Accept the preset's value as text too, and keep the enum; the
        # preset decides which memory tools every agent holds.
        object.__setattr__(self, "preset", RecordFieldConverter.to_enum(self.preset, InfiniteMemoryPreset, "InfiniteWorkspaceSettings.preset"))

        # @intent seeds-exist-and-keep-their-names-apart
        # Each seed is copied to seed/<file name>, so each must be an
        # existing file and no two may share a file name; keep their
        # absolute paths.
        object.__setattr__(self, "seed_files", RecordFieldConverter.to_files(self.seed_files, "InfiniteWorkspaceSettings.seed_files", distinct_names=True))

        # @intent workspace-caps-are-whole-numbers
        # Every cap is a whole number of at least 1, so no cap can be
        # switched off by 0, a fraction, or True, and one note may never
        # be larger than the whole workspace.
        for name in ("max_files", "max_tokens", "max_file_tokens", "max_entry_tokens", "max_entries_per_agent"):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteWorkspaceSettings.{name}", minimum=INFINITE_MIN_CAP)
        if self.max_file_tokens > self.max_tokens:
            raise ConfigurationError(f"InfiniteWorkspaceSettings.max_file_tokens must be at most max_tokens ({self.max_tokens}); got {self.max_file_tokens}.", details={"field": "InfiniteWorkspaceSettings.max_file_tokens"})


@dataclass(frozen=True, slots=True)
class InfiniteMemoryAgentSettings:
    """Everything every agent in an InfiniteMemory tree shares: the model, the prompt, the project folder, the workspace, the extra tools, the loop limits, and the delegation caps.

    root_dir keeps its raw type until __post_init__ checks it, because
    Path("") is the current folder. After __post_init__ it is a resolved
    Path, provider is a ModelProvider, api_keys is the matched
    ProviderKeys record, and tools is a tuple.
    """

    name: str
    system_prompt: str
    provider: ModelProvider | str
    model_name: str
    root_dir: str | Path
    workspace: InfiniteWorkspaceSettings
    api_keys: ProviderKeys | Iterable[str | None] | None = field(default_factory=ProviderKeys, repr=False)
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
    vidbyte_api_key: str | None = field(default=None, repr=False)
    model_mode: TextModelMode = TextModelMode.AUTO

    def __post_init__(self) -> None:
        # @intent one-closed-surface-for-every-agent
        # These settings configure the root and every subagent it
        # starts, so a bad value is refused here, before any agent or
        # workspace exists, and names the field that must change. The
        # provider, policy, and loop are applied to every agent as
        # given.
        for name in ("name", "system_prompt", "model_name"):
            RecordFieldValidator.require_text(getattr(self, name), f"InfiniteMemoryAgentSettings.{name}")

        # @intent provider-accepts-its-value
        # Developers may name the provider as text ("openai"); the enum
        # is stored, so every agent in the tree gets the same provider.
        object.__setattr__(self, "provider", RecordFieldConverter.to_enum(self.provider, ModelProvider, "InfiniteMemoryAgentSettings.provider"))

        # @intent the-model-runs-under-its-provider
        # Every agent in the tree uses this model, so one the SDK cannot
        # run under the provider is refused here, not at a child's call.
        try:
            ProviderModelRegistry.validate_provider_model_pair(self.provider, self.model_name)
        except ConfigurationError as exc:
            raise ConfigurationError(f"InfiniteMemoryAgentSettings.model_name must be a model the SDK can run under the given provider; {exc.message}", details={"field": "InfiniteMemoryAgentSettings.model_name"}) from exc

        # Bash runs in the project folder, so it must already exist;
        # keep its absolute path.
        object.__setattr__(self, "root_dir", RecordFieldConverter.to_folder(self.root_dir, "InfiniteMemoryAgentSettings.root_dir", must_exist=True))

        # The workspace, the policy, and the loop must be the SDK's own
        # objects, which have checked themselves.
        for name, kind in (("workspace", InfiniteWorkspaceSettings), ("permission_policy", PermissionPolicy), ("loop", AgentLoopSettings)):
            RecordFieldConverter.require_instance(getattr(self, name), f"InfiniteMemoryAgentSettings.{name}", kind)

        # Match the developer's keys once against the provider; the root
        # and every subagent carry this one record, which is never shown.
        matched = ProviderKeyMatcher.match(self.api_keys, primary=self.provider, vidbyte_api_key=self.vidbyte_api_key, field_name="InfiniteMemoryAgentSettings.api_keys")
        object.__setattr__(self, "api_keys", matched)
        object.__setattr__(self, "vidbyte_api_key", matched.vidbyte_api_key)
        RecordFieldValidator.require_enum(self.model_mode, TextModelMode, "InfiniteMemoryAgentSettings.model_mode")

        # The temperature and timeout are numbers or None, and BaseAgent
        # checks their ranges.
        for name in ("temperature", "timeout_seconds"):
            RecordFieldConverter.require_instance(getattr(self, name), f"InfiniteMemoryAgentSettings.{name}", (int, float), optional=True)

        # @intent extra-tools-never-shadow-preset-tools
        # The extras must form a valid catalog, and none may take the
        # name of a preset or run-bound tool, or the model could not
        # tell which one it is calling. They are kept as a tuple.
        tools = RecordFieldConverter.to_tuple(self.tools, "InfiniteMemoryAgentSettings.tools", item_type=object)
        try:
            names = Tools(cast("tuple[ToolInput, ...]", tools)).names()
        except (ToolRegistrationError, TypeError) as exc:
            raise ConfigurationError("InfiniteMemoryAgentSettings.tools must hold tools with distinct names.", details={"field": "InfiniteMemoryAgentSettings.tools"}) from exc
        taken = [name for name in names if name in INFINITE_RESERVED_TOOL_NAMES]
        if taken:
            raise ConfigurationError(f"InfiniteMemoryAgentSettings.tools must not reuse a reserved tool name; got {', '.join(taken)}. Reserved: {', '.join(INFINITE_RESERVED_TOOL_NAMES)}.", details={"field": "InfiniteMemoryAgentSettings.tools"})
        object.__setattr__(self, "tools", tools)

        # @intent delegation-caps-are-whole-numbers
        # The depth and batch caps allow at least one level and one
        # task, and the agent cap at least one generator and verifier
        # pair. DelegationLimitsMiddleware enforces the first two on
        # every agent in the tree.
        for name, minimum in (("max_depth", INFINITE_MIN_CAP), ("max_parallel", INFINITE_MIN_CAP), ("max_agents", INFINITE_MIN_AGENTS)):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteMemoryAgentSettings.{name}", minimum=minimum)

    @property
    def delegation_limits(self) -> DelegationLimits:
        """Return the depth and batch caps that DelegationLimitsMiddleware holds launch_subagent to on every delegating agent."""
        return DelegationLimits(tool_name=INFINITE_LAUNCH_TOOL_NAME, batch_argument=INFINITE_LAUNCH_TASKS_ARGUMENT, max_depth=self.max_depth, max_parallel=self.max_parallel)


__all__ = ["InfiniteMemoryAgentSettings", "InfiniteWorkspaceSettings"]
