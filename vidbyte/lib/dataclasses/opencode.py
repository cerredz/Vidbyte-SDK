"""FILE: vidbyte/lib/dataclasses/opencode.py

PURPOSE: Defines the opencode host's records: the host settings, permission rules, prompt and spawn requests, MCP server configs, the read results (readiness, models, providers, auth methods, sessions, messages, message pages, file diffs, MCP status), and the inbound records the host parses from opencode's HTTP bodies (permission and question requests, session statuses and assistant errors).
ROLE IN CODEBASE: Built by callers and by vidbyte/tools/builtins/opencode/ (settings and requests), by OpencodeHost and OpencodeWire in vidbyte/harnesses/native/opencode/ (outputs and inbound records); read by OpencodeClient, OpencodeServer and OpencodeTurnWatcher.
ARCHITECTURE NOTE: Data only; frozen, slotted, validated in __post_init__ through RecordFieldValidator and RecordFieldConverter. Secret-bearing fields (server_password, MCP environment and headers) are repr=False and never quoted in a message. Inbound records mirror only the members the host relies on and keep vendor vocabularies verbatim (D-13).
FUNCTION INVENTORY: OpencodePermissionRule, OpencodePromptRequest, OpencodeSpawnRequest, OpencodeMcpServerConfig, OpencodeHostSettings, OpencodeReadiness, OpencodeModel, OpencodeProvider, OpencodeAuthMethod, OpencodeProviderAuth, OpencodeAssistantError, OpencodeSession, OpencodeMessage, OpencodeMessagePage, OpencodeFileDiff, OpencodeMcpStatus, OpencodePermissionRequest, OpencodeQuestionRequest, OpencodeSessionStatus.
COMMON MODIFICATION PATTERNS: A new request option adds a validated field here, its body member in opencode/client.py or host.py, and its tool parameter in vidbyte/tools/builtins/opencode/.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept the allow-everything permission rule ("*", "*", ALLOW) (INV-9). 2. Do not allow plain http to a non-loopback host; basic-auth credentials would cross the network in clear text (EC-152). 3. Do not quote a URL, password, environment value or header value in a message.
KNOWN EDGE CASES: A model id is provider/model, and the model part may itself contain slashes. OpencodeMessage.completed_ms has no default because the record keeps the spec's field order; hosts always pass it.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1 (vidbyte.lib.dataclasses.opencode), EC-66, EC-91, EC-152
TESTS: tests/features/opencode_host/test_opencode_host_records.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from vidbyte.lib.constants.native_hosts import (
    NATIVE_CONTROL_TIMEOUT_MAX_SECONDS,
    NATIVE_ID_MAX_CHARS,
    NATIVE_MAX_LIVE_TURNS_DEFAULT,
    NATIVE_MAX_LIVE_TURNS_LIMIT,
    NATIVE_MIN_LIVE_TURNS,
    NATIVE_PROMPT_MAX_CHARS,
    NATIVE_RESULT_TEXT_MAX_CHARS,
    NATIVE_TURN_DEFAULT_SECONDS,
    NATIVE_TURN_MAX_SECONDS,
    NATIVE_URL_MAX_CHARS,
    NATIVE_VENDOR_ID_PATTERN,
    OPENCODE_CREDENTIAL_MAX_CHARS,
    OPENCODE_ENV_KEY_PATTERN,
    OPENCODE_MAX_MCP_SERVERS,
    OPENCODE_MAX_PERMISSION_RULES,
    OPENCODE_MCP_MAP_MAX_ITEMS,
    OPENCODE_MCP_NAME_MAX_CHARS,
    OPENCODE_MCP_NAME_PATTERN,
    OPENCODE_MCP_TIMEOUT_MAX_MS,
    OPENCODE_MCP_TIMEOUT_MIN_MS,
    OPENCODE_PROVIDER_MODEL_MAX_CHARS,
    OPENCODE_REQUEST_TIMEOUT_SECONDS,
    OPENCODE_RETRY_STATE,
    OPENCODE_RULE_MAX_CHARS,
    OPENCODE_SESSION_ID_PATTERN,
    OPENCODE_STARTUP_TIMEOUT_SECONDS,
    OPENCODE_SYSTEM_MAX_CHARS,
)
from vidbyte.lib.dataclasses.native_hosts import NativeTokenUsage
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.harness_backends import HarnessBackendName
from vidbyte.lib.enums.native_hosts import OpencodeMcpKind, OpencodePermissionAction
from vidbyte.lib.errors import ConfigurationError

_PROVIDER_MODEL_PATTERN = r"^[^\s/-][^\s/]{0,127}/[^\s]{1,128}$"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_PERMISSION_REQUEST_PREFIX = "per"
_QUESTION_REQUEST_PREFIX = "que"



@dataclass(frozen=True, slots=True)
class OpencodePermissionRule:
    """One opencode permission rule applied to a spawned session; the allow-everything rule is refused."""

    permission: str
    pattern: str
    action: OpencodePermissionAction

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.permission, "OpencodePermissionRule.permission", max_chars=OPENCODE_RULE_MAX_CHARS)
        RecordFieldValidator.require_text(self.pattern, "OpencodePermissionRule.pattern", max_chars=OPENCODE_RULE_MAX_CHARS)
        RecordFieldValidator.require_enum(self.action, OpencodePermissionAction, "OpencodePermissionRule.action")
        if self.permission == "*" and self.pattern == "*" and self.action is OpencodePermissionAction.ALLOW:
            raise ConfigurationError("OpencodePermissionRule.permission, OpencodePermissionRule.pattern and OpencodePermissionRule.action may not allow everything; narrow the permission or the pattern.", details={"field": "OpencodePermissionRule.permission"})


@dataclass(frozen=True, slots=True)
class OpencodePromptRequest:
    """One opencode turn: the prompt, optional provider/model, agent and system text, and the turn ceiling."""

    prompt: str
    model: str | None = None
    agent: str | None = None
    system: str | None = None
    max_turn_seconds: float = NATIVE_TURN_DEFAULT_SECONDS

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.prompt, "OpencodePromptRequest.prompt", max_chars=NATIVE_PROMPT_MAX_CHARS)
        RecordFieldValidator.require_optional_text(self.model, "OpencodePromptRequest.model", max_chars=OPENCODE_PROVIDER_MODEL_MAX_CHARS, pattern=_PROVIDER_MODEL_PATTERN)
        RecordFieldValidator.require_optional_text(self.agent, "OpencodePromptRequest.agent", max_chars=NATIVE_ID_MAX_CHARS, pattern=NATIVE_VENDOR_ID_PATTERN)
        RecordFieldValidator.require_optional_text(self.system, "OpencodePromptRequest.system", max_chars=OPENCODE_SYSTEM_MAX_CHARS)
        RecordFieldValidator.require_number(self.max_turn_seconds, "OpencodePromptRequest.max_turn_seconds", maximum=NATIVE_TURN_MAX_SECONDS)


@dataclass(frozen=True, slots=True)
class OpencodeSpawnRequest:
    """A new opencode session: its first turn, an optional title and the permission rules it starts with."""

    turn: OpencodePromptRequest
    title: str | None = None
    permission_rules: tuple[OpencodePermissionRule, ...] = ()

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.turn, "OpencodeSpawnRequest.turn", OpencodePromptRequest)
        RecordFieldValidator.require_optional_text(self.title, "OpencodeSpawnRequest.title", max_chars=NATIVE_ID_MAX_CHARS)
        rules = RecordFieldConverter.to_tuple(self.permission_rules, "OpencodeSpawnRequest.permission_rules", item_type=OpencodePermissionRule, max_items=OPENCODE_MAX_PERMISSION_RULES)
        object.__setattr__(self, "permission_rules", rules)


@dataclass(frozen=True, slots=True)
class OpencodeMcpServerConfig:
    """One MCP server the opencode host may register: a local command or a remote URL, with its environment or headers."""

    name: str
    kind: OpencodeMcpKind
    command: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    url: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.name, "OpencodeMcpServerConfig.name", max_chars=OPENCODE_MCP_NAME_MAX_CHARS, pattern=OPENCODE_MCP_NAME_PATTERN)
        RecordFieldValidator.require_enum(self.kind, OpencodeMcpKind, "OpencodeMcpServerConfig.kind")
        if self.kind is OpencodeMcpKind.LOCAL:
            RecordFieldValidator.require_argv(self.command, "OpencodeMcpServerConfig.command")
            if self.url is not None:
                raise ConfigurationError("OpencodeMcpServerConfig.url must be None for a LOCAL server.", details={"field": "OpencodeMcpServerConfig.url"})
        else:
            if self.command != ():
                raise ConfigurationError("OpencodeMcpServerConfig.command must be empty for a REMOTE server.", details={"field": "OpencodeMcpServerConfig.command"})
            RecordFieldConverter.require_url(self.url, "OpencodeMcpServerConfig.url", max_chars=NATIVE_URL_MAX_CHARS, plain_http_hosts=_LOOPBACK_HOSTS)
        environment = RecordFieldValidator.require_text_mapping(self.environment, "OpencodeMcpServerConfig.environment", key_pattern=OPENCODE_ENV_KEY_PATTERN, max_items=OPENCODE_MCP_MAP_MAX_ITEMS)
        headers = RecordFieldValidator.require_text_mapping(self.headers, "OpencodeMcpServerConfig.headers", key_pattern=OPENCODE_ENV_KEY_PATTERN, max_items=OPENCODE_MCP_MAP_MAX_ITEMS)
        object.__setattr__(self, "environment", MappingProxyType(dict(environment)))
        object.__setattr__(self, "headers", MappingProxyType(dict(headers)))
        if self.timeout_ms is not None:
            RecordFieldValidator.require_int(self.timeout_ms, "OpencodeMcpServerConfig.timeout_ms", minimum=OPENCODE_MCP_TIMEOUT_MIN_MS, maximum=OPENCODE_MCP_TIMEOUT_MAX_MS)


@dataclass(frozen=True, slots=True)
class OpencodeHostSettings:
    """Where an OpencodeHost works, whether it owns a server or attaches to one, its backends, MCP servers and bounds."""

    workspace: Path
    opencode_command: tuple[str, ...] | None = None
    server_url: str | None = None
    server_username: str | None = None
    server_password: str | None = field(default=None, repr=False)
    backends: tuple[HarnessBackendName, ...] = ()
    startup_timeout_seconds: float = OPENCODE_STARTUP_TIMEOUT_SECONDS
    request_timeout_seconds: float = OPENCODE_REQUEST_TIMEOUT_SECONDS
    mcp_servers: Mapping[str, OpencodeMcpServerConfig] = field(default_factory=dict)
    max_live_turns: int = NATIVE_MAX_LIVE_TURNS_DEFAULT

    def __post_init__(self) -> None:
        RecordFieldValidator.require_directory(self.workspace, "OpencodeHostSettings.workspace")
        if self.opencode_command is not None:
            RecordFieldValidator.require_argv(self.opencode_command, "OpencodeHostSettings.opencode_command")
        if self.server_url is not None:
            RecordFieldConverter.require_url(self.server_url, "OpencodeHostSettings.server_url", max_chars=NATIVE_URL_MAX_CHARS, plain_http_hosts=_LOOPBACK_HOSTS, allow_extras=False)
        if self.opencode_command is not None and self.server_url is not None:
            raise ConfigurationError("OpencodeHostSettings.opencode_command and OpencodeHostSettings.server_url cannot both be set; own a server or attach to one.", details={"field": "OpencodeHostSettings.opencode_command"})
        RecordFieldValidator.require_optional_text(self.server_username, "OpencodeHostSettings.server_username", max_chars=OPENCODE_CREDENTIAL_MAX_CHARS)
        RecordFieldValidator.require_optional_text(self.server_password, "OpencodeHostSettings.server_password", max_chars=OPENCODE_CREDENTIAL_MAX_CHARS)
        if (self.server_username is None) != (self.server_password is None):
            raise ConfigurationError("OpencodeHostSettings.server_username and OpencodeHostSettings.server_password must be set together.", details={"field": "OpencodeHostSettings.server_username"})
        if self.server_username is not None and self.server_url is None:
            raise ConfigurationError("OpencodeHostSettings.server_username and OpencodeHostSettings.server_password need OpencodeHostSettings.server_url.", details={"field": "OpencodeHostSettings.server_username"})
        backends = RecordFieldConverter.to_tuple(self.backends, "OpencodeHostSettings.backends", item_type=HarnessBackendName)
        if len(set(backends)) != len(backends):
            raise ConfigurationError("OpencodeHostSettings.backends must not repeat a backend.", details={"field": "OpencodeHostSettings.backends"})
        object.__setattr__(self, "backends", backends)
        RecordFieldValidator.require_number(self.startup_timeout_seconds, "OpencodeHostSettings.startup_timeout_seconds", maximum=NATIVE_CONTROL_TIMEOUT_MAX_SECONDS)
        RecordFieldValidator.require_number(self.request_timeout_seconds, "OpencodeHostSettings.request_timeout_seconds", maximum=NATIVE_CONTROL_TIMEOUT_MAX_SECONDS)
        if not isinstance(self.mcp_servers, Mapping) or len(self.mcp_servers) > OPENCODE_MAX_MCP_SERVERS:
            raise ConfigurationError(f"OpencodeHostSettings.mcp_servers must be a mapping of at most {OPENCODE_MAX_MCP_SERVERS} servers.", details={"field": "OpencodeHostSettings.mcp_servers"})
        if not all(isinstance(config, OpencodeMcpServerConfig) and key == config.name for key, config in self.mcp_servers.items()):
            raise ConfigurationError("OpencodeHostSettings.mcp_servers must map each name to an OpencodeMcpServerConfig with that same name.", details={"field": "OpencodeHostSettings.mcp_servers"})
        object.__setattr__(self, "mcp_servers", MappingProxyType(dict(self.mcp_servers)))
        RecordFieldValidator.require_int(self.max_live_turns, "OpencodeHostSettings.max_live_turns", minimum=NATIVE_MIN_LIVE_TURNS, maximum=NATIVE_MAX_LIVE_TURNS_LIMIT)


@dataclass(frozen=True, slots=True)
class OpencodeReadiness:
    """What check_opencode_ready found: the server version, its URL without credentials, connected providers and default models."""

    version: str
    server_url: str
    connected_providers: tuple[str, ...]
    default_models: Mapping[str, str]

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.version, "OpencodeReadiness.version", str)
        RecordFieldConverter.require_instance(self.server_url, "OpencodeReadiness.server_url", str)
        object.__setattr__(self, "connected_providers", RecordFieldConverter.to_tuple(self.connected_providers, "OpencodeReadiness.connected_providers", item_type=str))
        object.__setattr__(self, "default_models", RecordFieldConverter.to_mapping(self.default_models, "OpencodeReadiness.default_models"))


@dataclass(frozen=True, slots=True)
class OpencodeModel:
    """One model a provider offers on the server."""

    provider_id: str
    model_id: str
    name: str | None = None
    status: str | None = None
    context_limit: int | None = None
    output_limit: int | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.provider_id, "OpencodeModel.provider_id", str)
        RecordFieldConverter.require_instance(self.model_id, "OpencodeModel.model_id", str)
        RecordFieldConverter.require_instance(self.name, "OpencodeModel.name", str, optional=True)
        RecordFieldConverter.require_instance(self.status, "OpencodeModel.status", str, optional=True)
        RecordFieldValidator.require_optional_count(self.context_limit, "OpencodeModel.context_limit")
        RecordFieldValidator.require_optional_count(self.output_limit, "OpencodeModel.output_limit")


@dataclass(frozen=True, slots=True)
class OpencodeProvider:
    """One provider the server knows, whether it is connected, and its models; never its key or options."""

    provider_id: str
    name: str
    source: str
    env_vars: tuple[str, ...]
    connected: bool
    model_ids: tuple[str, ...]
    default_model_id: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.provider_id, "OpencodeProvider.provider_id", str)
        RecordFieldConverter.require_instance(self.name, "OpencodeProvider.name", str)
        RecordFieldConverter.require_instance(self.source, "OpencodeProvider.source", str)
        object.__setattr__(self, "env_vars", RecordFieldConverter.to_tuple(self.env_vars, "OpencodeProvider.env_vars", item_type=str))
        RecordFieldValidator.require_bool(self.connected, "OpencodeProvider.connected")
        object.__setattr__(self, "model_ids", RecordFieldConverter.to_tuple(self.model_ids, "OpencodeProvider.model_ids", item_type=str))
        RecordFieldConverter.require_instance(self.default_model_id, "OpencodeProvider.default_model_id", str, optional=True)


@dataclass(frozen=True, slots=True)
class OpencodeAuthMethod:
    """One way a provider can be connected, verbatim from the server."""

    method_type: str
    label: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.method_type, "OpencodeAuthMethod.method_type", str)
        RecordFieldConverter.require_instance(self.label, "OpencodeAuthMethod.label", str)


@dataclass(frozen=True, slots=True)
class OpencodeProviderAuth:
    """The auth methods one provider offers."""

    provider_id: str
    methods: tuple[OpencodeAuthMethod, ...]

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.provider_id, "OpencodeProviderAuth.provider_id", str)
        object.__setattr__(self, "methods", RecordFieldConverter.to_tuple(self.methods, "OpencodeProviderAuth.methods", item_type=OpencodeAuthMethod))


@dataclass(frozen=True, slots=True)
class OpencodeAssistantError:
    """Inbound: an assistant message's error object; name verbatim, with data.message, data.statusCode and data.isRetryable when present."""

    name: str
    message: str | None = None
    status_code: int | None = None
    retryable: bool | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.name, "OpencodeAssistantError.name", str)
        RecordFieldConverter.require_instance(self.message, "OpencodeAssistantError.message", str, optional=True)
        RecordFieldConverter.require_instance(self.status_code, "OpencodeAssistantError.status_code", int, optional=True)
        if self.retryable is not None:
            RecordFieldValidator.require_bool(self.retryable, "OpencodeAssistantError.retryable")


@dataclass(frozen=True, slots=True)
class OpencodeSession:
    """One opencode session: ids, title, folder, parent, times, usage and revert point."""

    session_id: str
    title: str
    directory: str
    parent_id: str | None
    created_ms: int
    updated_ms: int
    usage: NativeTokenUsage | None = None
    revert_message_id: str | None = None
    revert_part_id: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "OpencodeSession.session_id", str)
        RecordFieldConverter.require_instance(self.title, "OpencodeSession.title", str)
        RecordFieldConverter.require_instance(self.directory, "OpencodeSession.directory", str)
        RecordFieldConverter.require_instance(self.parent_id, "OpencodeSession.parent_id", str, optional=True)
        RecordFieldConverter.require_instance(self.created_ms, "OpencodeSession.created_ms", int)
        RecordFieldConverter.require_instance(self.updated_ms, "OpencodeSession.updated_ms", int)
        RecordFieldConverter.require_instance(self.usage, "OpencodeSession.usage", NativeTokenUsage, optional=True)
        RecordFieldConverter.require_instance(self.revert_message_id, "OpencodeSession.revert_message_id", str, optional=True)
        RecordFieldConverter.require_instance(self.revert_part_id, "OpencodeSession.revert_part_id", str, optional=True)


@dataclass(frozen=True, slots=True)
class OpencodeMessage:
    """One opencode message: role, times, joined capped text, parent, model, finish, error and usage."""

    message_id: str
    session_id: str
    role: str
    created_ms: int
    completed_ms: int | None
    text: str
    text_truncated: bool
    parent_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    finish: str | None = None
    error: OpencodeAssistantError | None = None
    usage: NativeTokenUsage | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.message_id, "OpencodeMessage.message_id", str)
        RecordFieldConverter.require_instance(self.session_id, "OpencodeMessage.session_id", str)
        RecordFieldConverter.require_instance(self.role, "OpencodeMessage.role", str)
        RecordFieldConverter.require_instance(self.created_ms, "OpencodeMessage.created_ms", int)
        RecordFieldConverter.require_instance(self.completed_ms, "OpencodeMessage.completed_ms", int, optional=True)
        RecordFieldValidator.require_text(self.text, "OpencodeMessage.text", max_chars=NATIVE_RESULT_TEXT_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_bool(self.text_truncated, "OpencodeMessage.text_truncated")
        RecordFieldConverter.require_instance(self.parent_id, "OpencodeMessage.parent_id", str, optional=True)
        RecordFieldConverter.require_instance(self.provider_id, "OpencodeMessage.provider_id", str, optional=True)
        RecordFieldConverter.require_instance(self.model_id, "OpencodeMessage.model_id", str, optional=True)
        RecordFieldConverter.require_instance(self.finish, "OpencodeMessage.finish", str, optional=True)
        RecordFieldConverter.require_instance(self.error, "OpencodeMessage.error", OpencodeAssistantError, optional=True)
        RecordFieldConverter.require_instance(self.usage, "OpencodeMessage.usage", NativeTokenUsage, optional=True)


@dataclass(frozen=True, slots=True)
class OpencodeMessagePage:
    """One page of a session's messages, oldest first, and the id to page back from when the page is full."""

    session_id: str
    messages: tuple[OpencodeMessage, ...]
    next_before: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "OpencodeMessagePage.session_id", str)
        object.__setattr__(self, "messages", RecordFieldConverter.to_tuple(self.messages, "OpencodeMessagePage.messages", item_type=OpencodeMessage))
        RecordFieldConverter.require_instance(self.next_before, "OpencodeMessagePage.next_before", str, optional=True)


@dataclass(frozen=True, slots=True)
class OpencodeFileDiff:
    """One file a session changed, with its capped patch."""

    path: str
    status: str
    additions: int
    deletions: int
    patch: str
    patch_truncated: bool

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.path, "OpencodeFileDiff.path", str)
        RecordFieldConverter.require_instance(self.status, "OpencodeFileDiff.status", str)
        RecordFieldValidator.require_optional_count(self.additions, "OpencodeFileDiff.additions")
        RecordFieldConverter.require_instance(self.additions, "OpencodeFileDiff.additions", int)
        RecordFieldValidator.require_optional_count(self.deletions, "OpencodeFileDiff.deletions")
        RecordFieldConverter.require_instance(self.deletions, "OpencodeFileDiff.deletions", int)
        RecordFieldConverter.require_instance(self.patch, "OpencodeFileDiff.patch", str)
        RecordFieldValidator.require_bool(self.patch_truncated, "OpencodeFileDiff.patch_truncated")


@dataclass(frozen=True, slots=True)
class OpencodeMcpStatus:
    """The verbatim status the server reported for one MCP server."""

    name: str
    status: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.name, "OpencodeMcpStatus.name", str)
        RecordFieldConverter.require_instance(self.status, "OpencodeMcpStatus.status", str)


@dataclass(frozen=True, slots=True)
class OpencodePermissionRequest:
    """Inbound: one GET /permission entry the watcher must answer."""

    request_id: str
    session_id: str
    permission: str
    patterns: tuple[str, ...]

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.request_id, "OpencodePermissionRequest.request_id", max_chars=NATIVE_ID_MAX_CHARS)
        if not self.request_id.startswith(_PERMISSION_REQUEST_PREFIX):
            raise ConfigurationError("OpencodePermissionRequest.request_id must start with per.", details={"field": "OpencodePermissionRequest.request_id"})
        RecordFieldValidator.require_text(self.session_id, "OpencodePermissionRequest.session_id", max_chars=NATIVE_ID_MAX_CHARS, pattern=OPENCODE_SESSION_ID_PATTERN)
        RecordFieldConverter.require_instance(self.permission, "OpencodePermissionRequest.permission", str)
        object.__setattr__(self, "patterns", RecordFieldConverter.to_tuple(self.patterns, "OpencodePermissionRequest.patterns", item_type=str))


@dataclass(frozen=True, slots=True)
class OpencodeQuestionRequest:
    """Inbound: one GET /question entry the watcher must reject."""

    request_id: str
    session_id: str

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.request_id, "OpencodeQuestionRequest.request_id", max_chars=NATIVE_ID_MAX_CHARS)
        if not self.request_id.startswith(_QUESTION_REQUEST_PREFIX):
            raise ConfigurationError("OpencodeQuestionRequest.request_id must start with que.", details={"field": "OpencodeQuestionRequest.request_id"})
        RecordFieldValidator.require_text(self.session_id, "OpencodeQuestionRequest.session_id", max_chars=NATIVE_ID_MAX_CHARS, pattern=OPENCODE_SESSION_ID_PATTERN)


@dataclass(frozen=True, slots=True)
class OpencodeSessionStatus:
    """Inbound: one GET /session/status entry; retry_attempt is set exactly when the state is retry."""

    session_id: str
    state: str
    retry_attempt: int | None = None
    retry_message: str | None = None
    retry_reason: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "OpencodeSessionStatus.session_id", str)
        RecordFieldConverter.require_instance(self.state, "OpencodeSessionStatus.state", str)
        RecordFieldValidator.require_optional_count(self.retry_attempt, "OpencodeSessionStatus.retry_attempt")
        if (self.state == OPENCODE_RETRY_STATE) != (self.retry_attempt is not None):
            raise ConfigurationError("OpencodeSessionStatus.retry_attempt must be set exactly when OpencodeSessionStatus.state is retry.", details={"field": "OpencodeSessionStatus.retry_attempt"})
        RecordFieldConverter.require_instance(self.retry_message, "OpencodeSessionStatus.retry_message", str, optional=True)
        RecordFieldConverter.require_instance(self.retry_reason, "OpencodeSessionStatus.retry_reason", str, optional=True)


__all__ = [
    "OpencodeAssistantError",
    "OpencodeAuthMethod",
    "OpencodeFileDiff",
    "OpencodeHostSettings",
    "OpencodeMcpServerConfig",
    "OpencodeMcpStatus",
    "OpencodeMessage",
    "OpencodeMessagePage",
    "OpencodeModel",
    "OpencodePermissionRequest",
    "OpencodePermissionRule",
    "OpencodePromptRequest",
    "OpencodeProvider",
    "OpencodeProviderAuth",
    "OpencodeQuestionRequest",
    "OpencodeReadiness",
    "OpencodeSession",
    "OpencodeSessionStatus",
    "OpencodeSpawnRequest",
]
