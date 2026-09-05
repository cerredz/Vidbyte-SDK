"""FILE: vidbyte/lib/dataclasses/codex.py

PURPOSE: Defines immutable inputs, settings, and outputs for the Codex harness adapter.
ROLE IN CODEBASE: Centralizes validation and typed boundaries consumed by Codex agent collaborators.
ARCHITECTURE NOTE: Provider behavior stays in vidbyte.agents.codex; this module owns data only.
COMMON MODIFICATION PATTERNS: Add a frozen slots dataclass and validate public input in __post_init__.
KNOWN EDGE CASES: Some unions are structurally required for existing ContextManager and schema contracts.
RELATED DOCS: docs/design/codex-harness-agent.md.
TESTS: python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from vidbyte.lib.constants.codex import (
    CODEX_RESERVED_SUBAGENT_NAMES,
    CODEX_ROOT_FORK_DEPTH,
)
from vidbyte.lib.enums.codex import (
    CodexApprovalMode,
    CodexInputType,
    CodexPersonality,
    CodexReasoningEffort,
    CodexReasoningSummary,
    CodexSandbox,
    CodexThreadSource,
    CodexThreadStartSource,
)
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem


def _require_text(owner: str, field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{owner} {field_name} must be a non-empty string.")


def _optional_text(owner: str, field_name: str, value: str) -> None:
    if not isinstance(value, str):
        raise ConfigurationError(f"{owner} {field_name} must be a string.")
    if value and not value.strip():
        raise ConfigurationError(
            f"{owner} {field_name} cannot contain only whitespace."
        )


def _require_bool(owner: str, field_name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{owner} {field_name} must be a boolean.")


def _is_json_value(value: object) -> bool:
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
class CodexClientSettings:
    """Every process/client option accepted by ``CodexConfig`` in SDK 0.147."""

    codex_bin: str = ""
    launch_args_override: tuple[str, ...] = ()
    config_overrides: tuple[str, ...] = ()
    cwd: str = ""
    env: Mapping[str, str] = field(default_factory=dict)
    client_name: str = "codex_python_sdk"
    client_title: str = "Codex Python SDK"
    client_version: str = "0.147.0"
    experimental_api: bool = True

    def __post_init__(self) -> None:
        _require_bool("Codex client", "experimental_api", self.experimental_api)
        for field_name in ("codex_bin", "cwd"):
            _optional_text("Codex client", field_name, getattr(self, field_name))
        for field_name in ("client_name", "client_title", "client_version"):
            _require_text("Codex client", field_name, getattr(self, field_name))
        for field_name in ("launch_args_override", "config_overrides"):
            values = getattr(self, field_name)
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ConfigurationError(
                    f"Codex client {field_name} must contain non-empty strings."
                )
        if not isinstance(self.env, Mapping) or any(
            not isinstance(key, str) or not key or not isinstance(value, str)
            for key, value in self.env.items()
        ):
            raise ConfigurationError(
                "Codex client env must map non-empty string names to string values."
            )


@dataclass(frozen=True, slots=True)
class CodexSubagentSettings:
    """All documented scalar controls under Codex's ``agents`` config table."""

    enabled: bool = True
    max_concurrent_threads: int = 0
    default_model: str = ""
    default_reasoning_effort: CodexReasoningEffort = (
        CodexReasoningEffort.PROVIDER_DEFAULT
    )
    interrupt_message: bool = True
    roles: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_bool("Codex subagent", "enabled", self.enabled)
        _require_bool("Codex subagent", "interrupt_message", self.interrupt_message)
        if (
            isinstance(self.max_concurrent_threads, bool)
            or not isinstance(self.max_concurrent_threads, int)
            or self.max_concurrent_threads < 0
        ):
            raise ConfigurationError(
                "Codex subagent max_concurrent_threads must be a non-negative integer."
            )
        _optional_text("Codex subagent", "default_model", self.default_model)
        if not isinstance(self.default_reasoning_effort, CodexReasoningEffort):
            raise ConfigurationError(
                "Codex subagent default_reasoning_effort must be CodexReasoningEffort."
            )
        if not isinstance(self.roles, Mapping):
            raise ConfigurationError("Codex subagent roles must be a mapping.")
        for name, role in self.roles.items():
            _require_text("Codex subagent role", "name", name)
            if name in CODEX_RESERVED_SUBAGENT_NAMES:
                raise ConfigurationError(
                    f"Codex subagent role {name!r} conflicts with a reserved agents setting."
                )
            if not isinstance(role, Mapping):
                raise ConfigurationError("Each Codex subagent role must be a mapping.")
            if set(role) - {"description", "config_file"}:
                raise ConfigurationError(
                    "Codex subagent roles support only description and config_file."
                )
            for field_name, value in role.items():
                _require_text(f"Codex subagent role {name!r}", field_name, value)


@dataclass(frozen=True, slots=True)
class CodexThreadSettings:
    """Every thread start/resume/fork option exposed by openai-codex 0.147."""

    approval_mode: CodexApprovalMode = CodexApprovalMode.PROVIDER_DEFAULT
    base_instructions: str = ""
    cwd: str = ""
    model: str = ""
    model_provider: str = ""
    personality: CodexPersonality = CodexPersonality.PROVIDER_DEFAULT
    sandbox: CodexSandbox = CodexSandbox.PROVIDER_DEFAULT
    service_name: str = ""
    service_tier: str = ""
    session_start_source: CodexThreadStartSource = (
        CodexThreadStartSource.PROVIDER_DEFAULT
    )
    thread_source: CodexThreadSource = CodexThreadSource.PROVIDER_DEFAULT
    ephemeral: bool = False
    config: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_bool("Codex thread", "ephemeral", self.ephemeral)
        if not isinstance(self.approval_mode, CodexApprovalMode):
            raise ConfigurationError(
                "Codex thread approval_mode must be CodexApprovalMode."
            )
        if not isinstance(self.personality, CodexPersonality):
            raise ConfigurationError(
                "Codex thread personality must be CodexPersonality."
            )
        if not isinstance(self.sandbox, CodexSandbox):
            raise ConfigurationError("Codex thread sandbox must be CodexSandbox.")
        if not isinstance(self.session_start_source, CodexThreadStartSource):
            raise ConfigurationError(
                "Codex thread session_start_source must be CodexThreadStartSource."
            )
        if not isinstance(self.thread_source, CodexThreadSource):
            raise ConfigurationError(
                "Codex thread thread_source must be CodexThreadSource."
            )
        for field_name in (
            "base_instructions",
            "cwd",
            "model",
            "model_provider",
            "service_name",
            "service_tier",
        ):
            _optional_text("Codex thread", field_name, getattr(self, field_name))
        if not isinstance(self.config, Mapping) or any(
            not isinstance(key, str) or not key for key in self.config
        ):
            raise ConfigurationError(
                "Codex thread config must use non-empty string keys."
            )
        if not _is_json_value(self.config):
            raise ConfigurationError(
                "Codex thread config must contain only JSON-compatible values."
            )


@dataclass(frozen=True, slots=True)
class CodexTurnSettings:
    """Every per-turn override accepted by ``AsyncThread.run`` in SDK 0.147."""

    approval_mode: CodexApprovalMode = CodexApprovalMode.PROVIDER_DEFAULT
    cwd: str = ""
    effort: CodexReasoningEffort = CodexReasoningEffort.PROVIDER_DEFAULT
    model: str = ""
    personality: CodexPersonality = CodexPersonality.PROVIDER_DEFAULT
    sandbox: CodexSandbox = CodexSandbox.PROVIDER_DEFAULT
    service_tier: str = ""
    summary: CodexReasoningSummary = CodexReasoningSummary.PROVIDER_DEFAULT

    def __post_init__(self) -> None:
        typed_fields = {
            "approval_mode": (self.approval_mode, CodexApprovalMode),
            "effort": (self.effort, CodexReasoningEffort),
            "personality": (self.personality, CodexPersonality),
            "sandbox": (self.sandbox, CodexSandbox),
            "summary": (self.summary, CodexReasoningSummary),
        }
        for field_name, (value, expected) in typed_fields.items():
            if not isinstance(value, expected):
                raise ConfigurationError(
                    f"Codex turn {field_name} must be {expected.__name__}."
                )
        for field_name in ("cwd", "model", "service_tier"):
            _optional_text("Codex turn", field_name, getattr(self, field_name))


@dataclass(frozen=True, slots=True)
class CodexAgentSettings:
    """Complete provider settings grouped by their SDK lifecycle boundary."""

    client: CodexClientSettings = field(default_factory=CodexClientSettings)
    thread: CodexThreadSettings = field(default_factory=CodexThreadSettings)
    turn: CodexTurnSettings = field(default_factory=CodexTurnSettings)
    subagents: CodexSubagentSettings = field(default_factory=CodexSubagentSettings)

    def __post_init__(self) -> None:
        expected = (
            ("client", self.client, CodexClientSettings),
            ("thread", self.thread, CodexThreadSettings),
            ("turn", self.turn, CodexTurnSettings),
            ("subagents", self.subagents, CodexSubagentSettings),
        )
        for field_name, value, settings_type in expected:
            if not isinstance(value, settings_type):
                raise ConfigurationError(
                    f"Codex agent {field_name} must be {settings_type.__name__}."
                )


@dataclass(frozen=True, slots=True)
class CodexHarnessAgentSettings:
    """Validated Vidbyte-facing construction input for one Codex harness agent.

    ``output_schema`` and ``context_manager`` retain unions because their concrete
    forms are existing Vidbyte abstractions that cannot be resolved until the
    construction translator runs.
    """

    name: str
    system_prompt: str
    codex: CodexAgentSettings = field(default_factory=CodexAgentSettings)
    additional_context: str = ""
    context_manager: ContextManager | None = None
    output_schema: type | Mapping[str, Any] | None = None
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    thread_id: str = ""

    def __post_init__(self) -> None:
        _require_text("Codex harness agent", "name", self.name)
        _require_text("Codex harness agent", "system_prompt", self.system_prompt)
        for field_name in ("additional_context", "description", "thread_id"):
            _optional_text("Codex harness agent", field_name, getattr(self, field_name))
        if not isinstance(self.codex, CodexAgentSettings):
            raise ConfigurationError(
                "Codex harness agent codex must be CodexAgentSettings."
            )
        if not isinstance(self.capabilities, tuple) or any(
            not isinstance(value, str) or not value.strip()
            for value in self.capabilities
        ):
            raise ConfigurationError(
                "Codex harness agent capabilities must contain non-empty strings."
            )
        if not isinstance(self.metadata, Mapping):
            raise ConfigurationError("Codex harness agent metadata must be a mapping.")
        if self.context_manager is not None and not callable(
            getattr(self.context_manager, "render_primitives_zone", None)
        ):
            raise ConfigurationError(
                "Codex harness agent context_manager must be a ContextManager."
            )


@dataclass(frozen=True, slots=True)
class CodexTextInput:
    """Text input accepted by a Codex turn."""

    text: str
    type: CodexInputType = field(default=CodexInputType.TEXT, init=False)

    def __post_init__(self) -> None:
        _require_text("Codex text input", "text", self.text)


@dataclass(frozen=True, slots=True)
class CodexImageInput:
    """Image data-URL input accepted by a Codex turn."""

    url: str
    type: CodexInputType = field(default=CodexInputType.IMAGE, init=False)

    def __post_init__(self) -> None:
        _require_text("Codex image input", "url", self.url)


@dataclass(frozen=True, slots=True)
class CodexLocalImageInput:
    """Local image-path input accepted by a Codex turn."""

    path: str
    type: CodexInputType = field(default=CodexInputType.LOCAL_IMAGE, init=False)

    def __post_init__(self) -> None:
        _require_text("Codex local image input", "path", self.path)


@dataclass(frozen=True, slots=True)
class CodexSkillInput:
    """Named skill input accepted by a Codex turn."""

    name: str
    path: str
    type: CodexInputType = field(default=CodexInputType.SKILL, init=False)

    def __post_init__(self) -> None:
        _require_text("Codex skill input", "name", self.name)
        _require_text("Codex skill input", "path", self.path)


@dataclass(frozen=True, slots=True)
class CodexMentionInput:
    """Named resource mention accepted by a Codex turn."""

    name: str
    path: str
    type: CodexInputType = field(default=CodexInputType.MENTION, init=False)

    def __post_init__(self) -> None:
        _require_text("Codex mention input", "name", self.name)
        _require_text("Codex mention input", "path", self.path)


CodexInputItem = (
    CodexTextInput
    | CodexImageInput
    | CodexLocalImageInput
    | CodexSkillInput
    | CodexMentionInput
)


@dataclass(frozen=True, slots=True)
class CodexRunInput:
    """One typed request whose item variants exactly match Codex ``RunInput``."""

    items: tuple[CodexInputItem, ...]
    recipient: str = "user"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.items, tuple)
            or not self.items
            or any(
                not isinstance(
                    item,
                    (
                        CodexTextInput,
                        CodexImageInput,
                        CodexLocalImageInput,
                        CodexSkillInput,
                        CodexMentionInput,
                    ),
                )
                for item in self.items
            )
        ):
            raise ConfigurationError(
                "Codex run input requires at least one supported Codex input item."
            )
        _require_text("Codex run input", "recipient", self.recipient)
        if not isinstance(self.metadata, Mapping):
            raise ConfigurationError("Codex run input metadata must be a mapping.")
        if not isinstance(self.context_items, tuple) or any(
            not callable(getattr(item, "to_context_text", None))
            for item in self.context_items
        ):
            raise ConfigurationError(
                "Codex run input context_items must contain ContextItem values."
            )
        if self.context_manager is not None and not callable(
            getattr(self.context_manager, "render_primitives_zone", None)
        ):
            raise ConfigurationError(
                "Codex run input context_manager must be a ContextManager."
            )

    @classmethod
    def text(cls, prompt: str, *, recipient: str = "user") -> CodexRunInput:
        return cls(items=(CodexTextInput(prompt),), recipient=recipient)


@dataclass(frozen=True, slots=True)
class CodexPrompt:
    """Translated SDK input plus safe Vidbyte message context."""

    items: tuple[CodexInputItem, ...]
    user_prompt: str
    recipient: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CodexContextTranslationRequest:
    """Complete Vidbyte context input for one native Codex turn."""

    input: CodexRunInput
    static_context: str
    context_manager: ContextManager | None


@dataclass(frozen=True, slots=True)
class CodexAgentTranslation:
    """Constructor-time translation of Vidbyte agent settings."""

    settings: CodexHarnessAgentSettings
    output_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CodexForkSettings:
    """Validated overrides for one provider-native Codex fork."""

    name: str = ""
    system_prompt: str = ""
    codex: CodexAgentSettings | None = None
    additional_context: str | None = None
    context_manager: ContextManager | None = None
    output_schema: type | Mapping[str, Any] | None = None
    description: str | None = None
    capabilities: tuple[str, ...] | None = None
    clear_context_manager: bool = False
    clear_output_schema: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("name", "system_prompt"):
            _optional_text("Codex fork", field_name, getattr(self, field_name))
        if self.additional_context is not None:
            _optional_text("Codex fork", "additional_context", self.additional_context)
        if self.description is not None:
            _optional_text("Codex fork", "description", self.description)
        if self.capabilities is not None and (
            not isinstance(self.capabilities, tuple)
            or any(
                not isinstance(value, str) or not value.strip()
                for value in self.capabilities
            )
        ):
            raise ConfigurationError(
                "Codex fork capabilities must contain non-empty strings."
            )
        _require_bool("Codex fork", "clear_context_manager", self.clear_context_manager)
        _require_bool("Codex fork", "clear_output_schema", self.clear_output_schema)
        if self.clear_context_manager and self.context_manager is not None:
            raise ConfigurationError(
                "Codex fork cannot clear and replace context_manager together."
            )
        if self.clear_output_schema and self.output_schema is not None:
            raise ConfigurationError(
                "Codex fork cannot clear and replace output_schema together."
            )
        if self.codex is not None and not isinstance(self.codex, CodexAgentSettings):
            raise ConfigurationError("Codex fork codex must be CodexAgentSettings.")
        if not isinstance(self.metadata, Mapping):
            raise ConfigurationError("Codex fork metadata must be a mapping.")
        if self.context_manager is not None and not callable(
            getattr(self.context_manager, "render_primitives_zone", None)
        ):
            raise ConfigurationError(
                "Codex fork context_manager must be a ContextManager."
            )


@dataclass(frozen=True, slots=True)
class CodexForkRequest:
    """Complete parent state and overrides required for one fork."""

    parent: CodexHarnessAgentSettings
    parent_thread_id: str
    overrides: CodexForkSettings


@dataclass(frozen=True, slots=True)
class CodexForkResult:
    """Validated child construction settings produced by the fork collaborator."""

    settings: CodexHarnessAgentSettings


@dataclass(frozen=True, slots=True)
class CodexUsage:
    """Stable token-usage shape returned by a Codex turn."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0
    model_context_window: int = 0


@dataclass(frozen=True, slots=True)
class CodexItem:
    """One bounded current-turn SDK item with its stable type and serialized fields."""

    id: str
    type: str
    fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CodexMessageData:
    """Typed Codex result attached to ``AgentMessage.codex``."""

    thread_id: str
    turn_id: str
    status: str
    duration_ms: int
    usage: CodexUsage
    items: tuple[CodexItem, ...]
    subagents: tuple[CodexItem, ...]
    forked_from_thread_id: str = ""
    fork_depth: int = CODEX_ROOT_FORK_DEPTH


@dataclass(frozen=True, slots=True)
class CodexRunResult:
    """Transport snapshot of one completed Codex turn."""

    thread_id: str
    turn_id: str
    status: str
    final_response: str
    duration_ms: int
    usage: CodexUsage
    items: tuple[CodexItem, ...]


@dataclass(frozen=True, slots=True)
class CodexResultTranslationRequest:
    """Complete input required to build one Vidbyte AgentMessage."""

    result: CodexRunResult
    agent: CodexHarnessAgentSettings
    input_metadata: Mapping[str, Any]
    recipient: str


@dataclass(frozen=True, slots=True)
class CodexTransportRunRequest:
    """Complete input to one transport run operation."""

    thread_id: str
    system_prompt: str
    prompt: CodexPrompt
    settings: CodexAgentSettings
    output_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CodexTransportForkRequest:
    """Complete input to one transport fork operation."""

    thread_id: str
    system_prompt: str
    settings: CodexAgentSettings


@dataclass(frozen=True, slots=True)
class CodexThreadIdentity:
    """Provider-confirmed identity returned by a thread lifecycle operation."""

    thread_id: str


@dataclass(frozen=True, slots=True)
class CodexSdkTypes:
    """Lazily imported SDK classes needed by transport and translation."""

    async_codex: type
    codex_config: type
    approval_mode: type
    sandbox: type
    personality: type
    reasoning_effort: type
    reasoning_summary: type[BaseModel]
    thread_source: type
    thread_start_source: type
    text_input: type
    image_input: type
    local_image_input: type
    skill_input: type
    mention_input: type


__all__ = [name for name in globals() if name.startswith("Codex")]
