"""FILE: vidbyte/lib/dataclasses/claude.py

PURPOSE: Defines immutable inputs, settings, and outputs for the Claude harness adapter.
ROLE IN CODEBASE: Centralizes validation and typed boundaries consumed by Claude agent collaborators.
ARCHITECTURE NOTE: Provider behavior stays in vidbyte.agents.claude; this module owns data only.
COMMON MODIFICATION PATTERNS: Add a frozen slots dataclass and validate public input in __post_init__.
KNOWN EDGE CASES: Some unions are structurally required for existing ContextManager and schema contracts.
RELATED DOCS: docs/design/claude-harness-agent.md.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.lib.constants.claude import (
    CLAUDE_DEFAULT_RECIPIENT,
    CLAUDE_MAX_THINKING_BUDGET_TOKENS,
    CLAUDE_MIN_THINKING_BUDGET_TOKENS,
    CLAUDE_PROVIDER_DEFAULT_TIMEOUT_MS,
    CLAUDE_RESERVED_SUBAGENT_NAMES,
    CLAUDE_ROOT_FORK_DEPTH,
    CLAUDE_UNBOUNDED_BUDGET_USD,
    CLAUDE_UNBOUNDED_TURNS,
    CLAUDE_UNSET_THINKING_BUDGET_TOKENS,
)
from vidbyte.lib.enums.claude import (
    ClaudeEffortLevel,
    ClaudePermissionMode,
    ClaudeSettingSource,
    ClaudeSystemPromptKind,
    ClaudeThinkingDisplay,
    ClaudeThinkingMode,
)
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem


def _require_text(owner: str, field_name: str, value: str) -> None:
    # Rejects a non-string or blank value for a field that must carry content.
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{owner} {field_name} must be a non-empty string.")


def _optional_text(owner: str, field_name: str, value: str) -> None:
    # Accepts an empty string as "unset" but rejects whitespace-only content.
    if not isinstance(value, str):
        raise ConfigurationError(f"{owner} {field_name} must be a string.")
    if value and not value.strip():
        raise ConfigurationError(
            f"{owner} {field_name} cannot contain only whitespace."
        )


def _require_bool(owner: str, field_name: str, value: object) -> None:
    # Rejects truthy non-boolean values that would silently pass an if check.
    if not isinstance(value, bool):
        raise ConfigurationError(f"{owner} {field_name} must be a boolean.")


def _require_non_negative_int(owner: str, field_name: str, value: object) -> None:
    # Rejects booleans explicitly because bool is a subclass of int in Python.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(
            f"{owner} {field_name} must be a non-negative integer."
        )


def _require_non_negative_float(owner: str, field_name: str, value: object) -> None:
    # Accepts ints as floats but rejects booleans and negative budgets.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ConfigurationError(f"{owner} {field_name} must be a non-negative number.")


def _require_text_tuple(owner: str, field_name: str, values: object) -> None:
    # Requires a tuple of non-empty strings so ordering and immutability both hold.
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ConfigurationError(
            f"{owner} {field_name} must contain non-empty strings."
        )


def _require_instance(
    owner: str, field_name: str, value: object, expected: type
) -> None:
    # Blocks a raw string or loose mapping from standing in for a validated record.
    if not isinstance(value, expected):
        raise ConfigurationError(f"{owner} {field_name} must be {expected.__name__}.")


def _require_string_mapping(owner: str, field_name: str, values: object) -> None:
    # Requires named string values, used for environment and CLI argument passthrough.
    if not isinstance(values, Mapping) or any(
        not isinstance(key, str) or not key or not isinstance(value, str)
        for key, value in values.items()
    ):
        raise ConfigurationError(
            f"{owner} {field_name} must map non-empty string names to string values."
        )


def _is_json_value(value: object) -> bool:
    # Reports whether a nested value can survive JSON serialization to the provider.
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and bool(key) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


@dataclass(frozen=True, slots=True)
class ClaudeProcessSettings:
    """Subprocess, filesystem, and configuration-loading controls on ClaudeAgentOptions."""

    cwd: str = ""
    cli_path: str = ""
    settings: str = ""
    add_dirs: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    extra_args: Mapping[str, str] = field(default_factory=dict)
    max_buffer_size: int = 0
    load_timeout_ms: int = CLAUDE_PROVIDER_DEFAULT_TIMEOUT_MS
    setting_sources: tuple[ClaudeSettingSource, ...] = ()
    user: str = ""

    def __post_init__(self) -> None:
        # Validates process controls before any provider subprocess can be launched.
        for field_name in ("cwd", "cli_path", "settings", "user"):
            _optional_text("Claude process", field_name, getattr(self, field_name))
        _require_text_tuple("Claude process", "add_dirs", self.add_dirs)
        _require_string_mapping("Claude process", "env", self.env)
        _require_string_mapping("Claude process", "extra_args", self.extra_args)
        _require_non_negative_int(
            "Claude process", "max_buffer_size", self.max_buffer_size
        )
        _require_non_negative_int(
            "Claude process", "load_timeout_ms", self.load_timeout_ms
        )
        self._validate_setting_sources()

    def _validate_setting_sources(self) -> None:
        # Rejects duplicates so the declared configuration precedence stays unambiguous.
        if not isinstance(self.setting_sources, tuple) or any(
            not isinstance(value, ClaudeSettingSource) for value in self.setting_sources
        ):
            raise ConfigurationError(
                "Claude process setting_sources must contain ClaudeSettingSource values."
            )
        if len(set(self.setting_sources)) != len(self.setting_sources):
            raise ConfigurationError(
                "Claude process setting_sources cannot repeat a source."
            )


@dataclass(frozen=True, slots=True)
class ClaudeModelSettings:
    """Model selection, fallback, effort, and extended-thinking controls."""

    model: str = ""
    fallback_model: str = ""
    effort: ClaudeEffortLevel = ClaudeEffortLevel.PROVIDER_DEFAULT
    thinking_mode: ClaudeThinkingMode = ClaudeThinkingMode.PROVIDER_DEFAULT
    thinking_budget_tokens: int = CLAUDE_UNSET_THINKING_BUDGET_TOKENS
    thinking_display: ClaudeThinkingDisplay = ClaudeThinkingDisplay.PROVIDER_DEFAULT
    betas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Validates model identity and keeps the thinking budget consistent with its mode.
        for field_name in ("model", "fallback_model"):
            _optional_text("Claude model", field_name, getattr(self, field_name))
        _require_instance("Claude model", "effort", self.effort, ClaudeEffortLevel)
        _require_instance(
            "Claude model", "thinking_mode", self.thinking_mode, ClaudeThinkingMode
        )
        _require_instance(
            "Claude model",
            "thinking_display",
            self.thinking_display,
            ClaudeThinkingDisplay,
        )
        _require_text_tuple("Claude model", "betas", self.betas)
        _require_non_negative_int(
            "Claude model", "thinking_budget_tokens", self.thinking_budget_tokens
        )
        self._validate_thinking_budget()

    def _validate_thinking_budget(self) -> None:
        # @intent budget-only-where-it-applies
        # A budget outside ENABLED mode is silently ignored by the provider, which
        # makes a caller believe they configured a ceiling that never took effect.
        if self.thinking_mode is not ClaudeThinkingMode.ENABLED:
            if self.thinking_budget_tokens:
                raise ConfigurationError(
                    "Claude model thinking_budget_tokens requires thinking_mode ENABLED."
                )
            return
        if not (
            CLAUDE_MIN_THINKING_BUDGET_TOKENS
            <= self.thinking_budget_tokens
            <= CLAUDE_MAX_THINKING_BUDGET_TOKENS
        ):
            raise ConfigurationError(
                "Claude model thinking_budget_tokens must be between "
                f"{CLAUDE_MIN_THINKING_BUDGET_TOKENS} and "
                f"{CLAUDE_MAX_THINKING_BUDGET_TOKENS} when thinking_mode is ENABLED."
            )


@dataclass(frozen=True, slots=True)
class ClaudeLoopSettings:
    """Provider-enforced ceilings on one run; zero means no Vidbyte-declared bound."""

    max_turns: int = CLAUDE_UNBOUNDED_TURNS
    max_budget_usd: float = CLAUDE_UNBOUNDED_BUDGET_USD

    def __post_init__(self) -> None:
        # Validates the two provider-side ceilings the adapter forwards.
        _require_non_negative_int("Claude loop", "max_turns", self.max_turns)
        _require_non_negative_float(
            "Claude loop", "max_budget_usd", self.max_budget_usd
        )


@dataclass(frozen=True, slots=True)
class ClaudeToolSettings:
    """Tool availability, permission posture, MCP servers, and skill exposure."""

    use_claude_code_preset: bool = True
    tools: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    permission_mode: ClaudePermissionMode = ClaudePermissionMode.PROVIDER_DEFAULT
    permission_prompt_tool_name: str = ""
    skills: tuple[str, ...] = ()
    all_skills: bool = False
    mcp_servers: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    strict_mcp_config: bool = False

    def __post_init__(self) -> None:
        # @intent settle-tool-authority-at-construction
        # Tool access, permission mode, MCP reach, and skill exposure are one authority
        # decision; validating them together is what makes a contradiction reachable.
        _require_bool(
            "Claude tools", "use_claude_code_preset", self.use_claude_code_preset
        )
        _require_bool("Claude tools", "all_skills", self.all_skills)
        _require_bool("Claude tools", "strict_mcp_config", self.strict_mcp_config)
        for field_name in ("tools", "allowed_tools", "disallowed_tools", "skills"):
            _require_text_tuple("Claude tools", field_name, getattr(self, field_name))
        _require_instance(
            "Claude tools",
            "permission_mode",
            self.permission_mode,
            ClaudePermissionMode,
        )
        _optional_text(
            "Claude tools",
            "permission_prompt_tool_name",
            self.permission_prompt_tool_name,
        )
        self._validate_exclusive_choices()
        self._validate_mcp_servers()

    def _validate_exclusive_choices(self) -> None:
        # @intent fail-closed-on-contradictory-tool-policy
        # An allow/deny conflict has no safe resolution the adapter can pick for the
        # caller, and all_skills alongside a skill list hides which set actually loads.
        conflicts = set(self.allowed_tools) & set(self.disallowed_tools)
        if conflicts:
            raise ConfigurationError(
                "Claude tools cannot allow and disallow the same tool: "
                f"{sorted(conflicts)}."
            )
        if self.all_skills and self.skills:
            raise ConfigurationError(
                "Claude tools cannot set all_skills together with an explicit skills list."
            )

    def _validate_mcp_servers(self) -> None:
        # @intent reject-unserializable-server-config-early
        # A non-JSON value fails inside the provider's own startup, where the error names
        # neither the server nor the field that caused it.
        if not isinstance(self.mcp_servers, Mapping) or any(
            not isinstance(key, str) or not key for key in self.mcp_servers
        ):
            raise ConfigurationError(
                "Claude tools mcp_servers must use non-empty string server names."
            )
        for name, config in self.mcp_servers.items():
            if not isinstance(config, Mapping) or not _is_json_value(config):
                raise ConfigurationError(
                    f"Claude tools mcp_servers[{name!r}] must be a JSON-compatible mapping."
                )


@dataclass(frozen=True, slots=True)
class ClaudeAgentDefinition:
    """One provider subagent role; the SDK receives these field names in camelCase."""

    description: str
    prompt: str
    tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    model: str = ""
    skills: tuple[str, ...] = ()
    max_turns: int = 0
    background: bool = False
    effort: ClaudeEffortLevel = ClaudeEffortLevel.PROVIDER_DEFAULT
    permission_mode: ClaudePermissionMode = ClaudePermissionMode.PROVIDER_DEFAULT

    def __post_init__(self) -> None:
        # @intent a-child-cannot-outrank-its-declaration
        # A child agent runs with its own tools, model, and permission mode, so an
        # invalid definition must fail before the parent can delegate work to it.
        _require_text("Claude agent definition", "description", self.description)
        _require_text("Claude agent definition", "prompt", self.prompt)
        _optional_text("Claude agent definition", "model", self.model)
        for field_name in ("tools", "disallowed_tools", "skills"):
            _require_text_tuple(
                "Claude agent definition", field_name, getattr(self, field_name)
            )
        _require_non_negative_int(
            "Claude agent definition", "max_turns", self.max_turns
        )
        _require_bool("Claude agent definition", "background", self.background)
        _require_instance(
            "Claude agent definition", "effort", self.effort, ClaudeEffortLevel
        )
        _require_instance(
            "Claude agent definition",
            "permission_mode",
            self.permission_mode,
            ClaudePermissionMode,
        )


@dataclass(frozen=True, slots=True)
class ClaudeSubagentSettings:
    """Named provider subagent roles reachable from the parent session."""

    roles: Mapping[str, ClaudeAgentDefinition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Rejects role names that would shadow a provider-owned agent identity.
        if not isinstance(self.roles, Mapping):
            raise ConfigurationError("Claude subagent roles must be a mapping.")
        for name, definition in self.roles.items():
            _require_text("Claude subagent role", "name", name)
            if name in CLAUDE_RESERVED_SUBAGENT_NAMES:
                raise ConfigurationError(
                    f"Claude subagent role {name!r} conflicts with a reserved agent name."
                )
            if not isinstance(definition, ClaudeAgentDefinition):
                raise ConfigurationError(
                    "Each Claude subagent role must be a ClaudeAgentDefinition."
                )


@dataclass(frozen=True, slots=True)
class ClaudeSessionSettings:
    """Provider session identity, continuation, and branch selection."""

    resume: str = ""
    fork_session: bool = False
    continue_conversation: bool = False
    resume_session_at: str = ""

    def __post_init__(self) -> None:
        # @intent one-unambiguous-session-parent
        # continue_conversation selects the most recent session in cwd while resume
        # names a specific one; together the effective parent session is undefined.
        for field_name in ("resume", "resume_session_at"):
            _optional_text("Claude session", field_name, getattr(self, field_name))
        _require_bool("Claude session", "fork_session", self.fork_session)
        _require_bool(
            "Claude session", "continue_conversation", self.continue_conversation
        )
        if self.continue_conversation and self.resume:
            raise ConfigurationError(
                "Claude session cannot set both continue_conversation and resume."
            )
        if self.fork_session and not (self.resume or self.continue_conversation):
            raise ConfigurationError(
                "Claude session fork_session requires resume or continue_conversation."
            )
        if self.resume_session_at and not self.resume:
            raise ConfigurationError(
                "Claude session resume_session_at requires resume."
            )


@dataclass(frozen=True, slots=True)
class ClaudeSandboxSettings:
    """Provider sandbox posture; platform support varies and is not claimed uniform."""

    enabled: bool = False
    allow_network: bool = False
    allowed_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Rejects sandbox detail supplied without the sandbox actually being enabled.
        _require_bool("Claude sandbox", "enabled", self.enabled)
        _require_bool("Claude sandbox", "allow_network", self.allow_network)
        _require_text_tuple("Claude sandbox", "allowed_domains", self.allowed_domains)
        if not self.enabled and (self.allow_network or self.allowed_domains):
            raise ConfigurationError(
                "Claude sandbox network settings require enabled sandbox."
            )
        if self.allowed_domains and not self.allow_network:
            raise ConfigurationError(
                "Claude sandbox allowed_domains require allow_network."
            )


@dataclass(frozen=True, slots=True)
class ClaudePluginConfig:
    """One locally trusted provider plugin, loaded by path."""

    path: str

    def __post_init__(self) -> None:
        # Requires an explicit local path; the adapter never discovers plugins itself.
        _require_text("Claude plugin", "path", self.path)


@dataclass(frozen=True, slots=True)
class ClaudeSystemPromptSettings:
    """How the Vidbyte system prompt reaches the provider's system_prompt union."""

    kind: ClaudeSystemPromptKind = ClaudeSystemPromptKind.TEXT
    path: str = ""
    append_to_preset: bool = True
    exclude_dynamic_sections: bool = False

    def __post_init__(self) -> None:
        # Requires a path for FILE mode and forbids a stale path in the other modes.
        _require_instance(
            "Claude system prompt", "kind", self.kind, ClaudeSystemPromptKind
        )
        _optional_text("Claude system prompt", "path", self.path)
        _require_bool("Claude system prompt", "append_to_preset", self.append_to_preset)
        _require_bool(
            "Claude system prompt",
            "exclude_dynamic_sections",
            self.exclude_dynamic_sections,
        )
        if self.kind is ClaudeSystemPromptKind.FILE and not self.path:
            raise ConfigurationError(
                "Claude system prompt path is required when kind is FILE."
            )
        if self.kind is not ClaudeSystemPromptKind.FILE and self.path:
            raise ConfigurationError(
                "Claude system prompt path is only valid when kind is FILE."
            )


@dataclass(frozen=True, slots=True)
class ClaudeAgentSettings:
    """Complete provider settings grouped by concern, not by SDK lifecycle stage."""

    process: ClaudeProcessSettings = field(default_factory=ClaudeProcessSettings)
    model: ClaudeModelSettings = field(default_factory=ClaudeModelSettings)
    loop: ClaudeLoopSettings = field(default_factory=ClaudeLoopSettings)
    tools: ClaudeToolSettings = field(default_factory=ClaudeToolSettings)
    session: ClaudeSessionSettings = field(default_factory=ClaudeSessionSettings)
    subagents: ClaudeSubagentSettings = field(default_factory=ClaudeSubagentSettings)
    sandbox: ClaudeSandboxSettings = field(default_factory=ClaudeSandboxSettings)
    system_prompt: ClaudeSystemPromptSettings = field(
        default_factory=ClaudeSystemPromptSettings
    )
    plugins: tuple[ClaudePluginConfig, ...] = ()

    def __post_init__(self) -> None:
        # Confirms every group is its own validated record rather than a loose mapping.
        expected = (
            ("process", self.process, ClaudeProcessSettings),
            ("model", self.model, ClaudeModelSettings),
            ("loop", self.loop, ClaudeLoopSettings),
            ("tools", self.tools, ClaudeToolSettings),
            ("session", self.session, ClaudeSessionSettings),
            ("subagents", self.subagents, ClaudeSubagentSettings),
            ("sandbox", self.sandbox, ClaudeSandboxSettings),
            ("system_prompt", self.system_prompt, ClaudeSystemPromptSettings),
        )
        for field_name, value, settings_type in expected:
            _require_instance("Claude agent", field_name, value, settings_type)
        if not isinstance(self.plugins, tuple) or any(
            not isinstance(value, ClaudePluginConfig) for value in self.plugins
        ):
            raise ConfigurationError(
                "Claude agent plugins must contain ClaudePluginConfig records."
            )


@dataclass(frozen=True, slots=True)
class ClaudeHarnessAgentSettings:
    """Validated Vidbyte-facing construction input for one Claude harness agent.

    ``output_schema`` and ``context_manager`` retain unions because their concrete
    forms are existing Vidbyte abstractions that cannot be resolved until the
    construction translator runs.
    """

    name: str
    system_prompt: str
    claude: ClaudeAgentSettings = field(default_factory=ClaudeAgentSettings)
    additional_context: str = ""
    context_manager: ContextManager | None = None
    output_schema: type | Mapping[str, Any] | None = None
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    session_id: str = ""

    def __post_init__(self) -> None:
        # @intent one-validated-public-entry-point
        # This is the only record a caller builds by hand, so every downstream
        # collaborator may assume its name, prompt, and provider settings are valid.
        _require_text("Claude harness agent", "name", self.name)
        _require_text("Claude harness agent", "system_prompt", self.system_prompt)
        for field_name in ("additional_context", "description", "session_id"):
            _optional_text(
                "Claude harness agent", field_name, getattr(self, field_name)
            )
        _require_instance(
            "Claude harness agent", "claude", self.claude, ClaudeAgentSettings
        )
        _require_text_tuple("Claude harness agent", "capabilities", self.capabilities)
        if not isinstance(self.metadata, Mapping):
            raise ConfigurationError("Claude harness agent metadata must be a mapping.")
        _require_context_manager(
            "Claude harness agent", "context_manager", self.context_manager
        )


def _require_context_manager(owner: str, field_name: str, value: object) -> None:
    # Duck-types a ContextManager so importing it at runtime stays unnecessary.
    if value is not None and not callable(
        getattr(value, "render_primitives_zone", None)
    ):
        raise ConfigurationError(f"{owner} {field_name} must be a ContextManager.")


@dataclass(frozen=True, slots=True)
class ClaudeRunInput:
    """One typed request for a single Claude turn; the provider prompt is text."""

    prompt: str
    recipient: str = CLAUDE_DEFAULT_RECIPIENT
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None

    def __post_init__(self) -> None:
        # Requires real prompt content so an empty turn cannot reach the provider.
        _require_text("Claude run input", "prompt", self.prompt)
        _require_text("Claude run input", "recipient", self.recipient)
        if not isinstance(self.metadata, Mapping):
            raise ConfigurationError("Claude run input metadata must be a mapping.")
        if not isinstance(self.context_items, tuple) or any(
            not callable(getattr(item, "to_context_text", None))
            for item in self.context_items
        ):
            raise ConfigurationError(
                "Claude run input context_items must contain ContextItem values."
            )
        _require_context_manager(
            "Claude run input", "context_manager", self.context_manager
        )

    @classmethod
    def text(
        cls, prompt: str, *, recipient: str = CLAUDE_DEFAULT_RECIPIENT
    ) -> ClaudeRunInput:
        # Builds the common single-prompt request without naming every default.
        return cls(prompt=prompt, recipient=recipient)


@dataclass(frozen=True, slots=True)
class ClaudePrompt:
    """Translated provider input plus safe Vidbyte message context."""

    user_prompt: str
    recipient: str
    metadata: Mapping[str, Any]
    developer_context: str = ""


@dataclass(frozen=True, slots=True)
class ClaudeContextSource:
    """One context manager whose live registry remains caller-owned."""

    manager: ContextManager | None = None


@dataclass(frozen=True, slots=True)
class ClaudeRenderedContext:
    """Rendering snapshot without references to mutable registry internals."""

    developer_context: str = ""
    before_input: tuple[str, ...] = ()
    after_input: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClaudeContextTranslationRequest:
    """Complete Vidbyte context input for one native Claude turn."""

    input: ClaudeRunInput
    static_context: str
    context_manager: ContextManager | None = None


@dataclass(frozen=True, slots=True)
class ClaudeAgentTranslation:
    """Constructor-time translation of Vidbyte agent settings."""

    settings: ClaudeHarnessAgentSettings
    output_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ClaudeForkSettings:
    """Validated overrides for one lazy provider-native Claude session fork."""

    name: str = ""
    system_prompt: str = ""
    claude: ClaudeAgentSettings | None = None
    additional_context: str | None = None
    context_manager: ContextManager | None = None
    output_schema: type | Mapping[str, Any] | None = None
    description: str | None = None
    capabilities: tuple[str, ...] | None = None
    clear_context_manager: bool = False
    clear_output_schema: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Distinguishes inherit, replace, and clear before any child is constructed.
        for field_name in ("name", "system_prompt"):
            _optional_text("Claude fork", field_name, getattr(self, field_name))
        if self.additional_context is not None:
            _optional_text("Claude fork", "additional_context", self.additional_context)
        if self.description is not None:
            _optional_text("Claude fork", "description", self.description)
        if self.capabilities is not None:
            _require_text_tuple("Claude fork", "capabilities", self.capabilities)
        _require_bool(
            "Claude fork", "clear_context_manager", self.clear_context_manager
        )
        _require_bool("Claude fork", "clear_output_schema", self.clear_output_schema)
        if self.claude is not None:
            _require_instance("Claude fork", "claude", self.claude, ClaudeAgentSettings)
        if not isinstance(self.metadata, Mapping):
            raise ConfigurationError("Claude fork metadata must be a mapping.")
        _require_context_manager("Claude fork", "context_manager", self.context_manager)
        self._validate_clear_overrides()

    def _validate_clear_overrides(self) -> None:
        # @intent no-simultaneous-clear-and-replace
        # Clearing and replacing the same field has two contradictory outcomes, so
        # the adapter must not silently pick one for the caller.
        if self.clear_context_manager and self.context_manager is not None:
            raise ConfigurationError(
                "Claude fork cannot clear and replace context_manager together."
            )
        if self.clear_output_schema and self.output_schema is not None:
            raise ConfigurationError(
                "Claude fork cannot clear and replace output_schema together."
            )


@dataclass(frozen=True, slots=True)
class ClaudeForkRequest:
    """Complete parent state and overrides required for one fork."""

    parent: ClaudeHarnessAgentSettings
    parent_session_id: str
    overrides: ClaudeForkSettings


@dataclass(frozen=True, slots=True)
class ClaudeForkResult:
    """Validated child construction settings produced by the fork collaborator."""

    settings: ClaudeHarnessAgentSettings


@dataclass(frozen=True, slots=True)
class ClaudeUsage:
    """Provider token counters plus the provider's own settled cost figure."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    total_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class ClaudeItem:
    """One bounded assistant content block with its stable type and serialized fields."""

    id: str
    type: str
    fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaudeRunResult:
    """Native snapshot; the result translator populates ``structured`` after validation.

    Missing timing, turn counts, and text remain distinguishable from zero and empty
    through ``usage_available`` and ``result_available``.
    """

    session_id: str
    subtype: str
    terminal_reason: str
    result: str | None
    duration_ms: int | None
    duration_api_ms: int | None
    num_turns: int | None
    usage: ClaudeUsage
    items: tuple[ClaudeItem, ...]
    structured_output: Mapping[str, Any] | None = None
    usage_available: bool = False
    result_available: bool = False
    structured: Any = None


@dataclass(frozen=True, slots=True)
class ClaudeMessageData:
    """Typed Claude result attached to ``AgentMessage.claude``."""

    session_id: str
    subtype: str
    terminal_reason: str
    usage: ClaudeUsage
    items: tuple[ClaudeItem, ...]
    subagents: tuple[ClaudeItem, ...]
    forked_from_session_id: str = ""
    fork_depth: int = CLAUDE_ROOT_FORK_DEPTH
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    num_turns: int | None = None
    usage_available: bool = False
    result: str | None = None
    structured: Any = None


@dataclass(frozen=True, slots=True)
class ClaudeResultTranslationRequest:
    """Complete input required to build one Vidbyte AgentMessage."""

    result: ClaudeRunResult
    agent: ClaudeHarnessAgentSettings
    input_metadata: Mapping[str, Any]
    recipient: str


@dataclass(frozen=True, slots=True)
class ClaudeTransportRunRequest:
    """Complete input to one transport run operation."""

    session_id: str
    system_prompt: str
    prompt: ClaudePrompt
    settings: ClaudeAgentSettings
    output_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ClaudeSdkTypes:
    """Lazily imported SDK callables and classes needed by transport and results."""

    query: Callable[..., Any]
    options: type
    assistant_message: type
    system_message: type
    result_message: type
    text_block: type
    thinking_block: type
    tool_use_block: type
    tool_result_block: type
    sdk_error: type
    cli_not_found_error: type
    cli_connection_error: type
    process_error: type
    cli_json_decode_error: type


__all__ = [name for name in globals() if name.startswith("Claude")]
