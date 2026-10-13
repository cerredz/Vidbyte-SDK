"""FILE: vidbyte/lib/dataclasses/harness_backends.py

PURPOSE: Defines the GLM and DeepSeek backend records: a declared backend profile, the Claude Code environment built from it (with its key hidden), the opencode provider wiring, a feature-compatibility request, the DeepSeek balance, and backend readiness.
ROLE IN CODEBASE: Declared by vidbyte/lib/configs/harness_backends.py (HarnessBackend); built and returned by HarnessBackends in vidbyte/harnesses/native/backends/profiles.py; read by OpencodeServer when an opencode host adds backends; encoded by vidbyte/tools/builtins/harness_backends/.
ARCHITECTURE NOTE: Data only; frozen, slotted, validated in __post_init__. Only ClaudeBackendEnv ever holds a key value, in a repr=False field that as_environ() adds as ANTHROPIC_AUTH_TOKEN; every other record holds variable names, never values.
FUNCTION INVENTORY: HarnessBackend, ClaudeBackendEnv (as_environ returns the public pairs plus ANTHROPIC_AUTH_TOKEN), OpencodeBackendProvider, BackendCompatRequest, DeepseekBalanceEntry, DeepseekBalance, BackendReadiness.
COMMON MODIFICATION PATTERNS: A new profile field adds a validated field here and its value in both declared profiles.
WHAT NOT TO DO IN THIS FILE: 1. Do not put a key value in HarnessBackend.claude_env; it holds fixed public pairs only. 2. Do not show auth_token in repr, str or an error message. 3. Do not import from a layer above vidbyte.lib.
KNOWN EDGE CASES: claude_env rejects any key CredentialKeyPolicy reads as a credential, so a token cannot be declared by mistake. DeepSeek balances arrive as strings and are parsed to Decimal by the backend service before these records are built.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1 (vidbyte.lib.dataclasses.harness_backends), EC-134
TESTS: tests/features/native_backends/test_native_backends_records.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlsplit

from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.harness_backends import BackendFeature, HarnessBackendName
from vidbyte.lib.enums.native_hosts import NativeHarness
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.util.credential_keys import CredentialKeyPolicy

_ENV_NAME_PATTERN = r"^[A-Z][A-Z0-9_]{0,63}$"
_ENV_NAME_MAX_CHARS = 64
_ID_MAX_CHARS = 128
_URL_MAX_CHARS = 2048
_CURRENCY_MAX_CHARS = 16
_AUTH_ENV_KEY = "ANTHROPIC_AUTH_TOKEN"


@dataclass(frozen=True, slots=True)
class HarnessBackend:
    """One declared Anthropic-compatible backend profile: endpoint, key variable, models, fixed environment and limits."""

    name: HarnessBackendName
    anthropic_base_url: str
    auth_env_var: str
    claude_models: tuple[str, ...]
    claude_env: Mapping[str, str]
    unsupported_features: frozenset[BackendFeature]
    allowed_harnesses: frozenset[NativeHarness]
    opencode_provider_id: str
    opencode_key_env_var: str
    opencode_models: tuple[str, ...]
    balance_url: str | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.name, HarnessBackendName, "HarnessBackend.name")
        RecordFieldValidator.require_text(self.anthropic_base_url, "HarnessBackend.anthropic_base_url", max_chars=_URL_MAX_CHARS)
        if urlsplit(self.anthropic_base_url).scheme != "https" or not urlsplit(self.anthropic_base_url).hostname:
            raise ConfigurationError("HarnessBackend.anthropic_base_url must be an https URL with a host.")
        RecordFieldValidator.require_text(self.auth_env_var, "HarnessBackend.auth_env_var", max_chars=_ENV_NAME_MAX_CHARS, pattern=_ENV_NAME_PATTERN)
        claude_models = RecordFieldConverter.to_tuple(self.claude_models, "HarnessBackend.claude_models", item_type=str)
        if not claude_models:
            raise ConfigurationError("HarnessBackend.claude_models must hold at least one model.")
        object.__setattr__(self, "claude_models", claude_models)
        claude_env = RecordFieldConverter.to_mapping(self.claude_env, "HarnessBackend.claude_env")
        if any(CredentialKeyPolicy.is_secret_key(key) for key in claude_env):
            raise ConfigurationError("HarnessBackend.claude_env holds fixed public pairs only; a credential-named key is not allowed.")
        object.__setattr__(self, "claude_env", claude_env)
        object.__setattr__(self, "unsupported_features", RecordFieldValidator.require_enum_set(self.unsupported_features, BackendFeature, "HarnessBackend.unsupported_features"))
        object.__setattr__(self, "allowed_harnesses", RecordFieldValidator.require_enum_set(self.allowed_harnesses, NativeHarness, "HarnessBackend.allowed_harnesses"))
        RecordFieldValidator.require_text(self.opencode_provider_id, "HarnessBackend.opencode_provider_id", max_chars=_ID_MAX_CHARS)
        RecordFieldValidator.require_text(self.opencode_key_env_var, "HarnessBackend.opencode_key_env_var", max_chars=_ENV_NAME_MAX_CHARS, pattern=_ENV_NAME_PATTERN)
        opencode_models = RecordFieldConverter.to_tuple(self.opencode_models, "HarnessBackend.opencode_models", item_type=str)
        if not opencode_models:
            raise ConfigurationError("HarnessBackend.opencode_models must hold at least one model.")
        object.__setattr__(self, "opencode_models", opencode_models)
        RecordFieldValidator.require_optional_text(self.balance_url, "HarnessBackend.balance_url", max_chars=_URL_MAX_CHARS)
        if self.balance_url is not None and (urlsplit(self.balance_url).scheme != "https" or not urlsplit(self.balance_url).hostname):
            raise ConfigurationError("HarnessBackend.balance_url must be an https URL with a host.")


@dataclass(frozen=True, slots=True)
class ClaudeBackendEnv:
    """The environment that points Claude Code at a backend; the key lives only in auth_token and as_environ()."""

    backend: HarnessBackendName
    model: str
    public_env: Mapping[str, str]
    auth_token: str = field(repr=False)

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.backend, HarnessBackendName, "ClaudeBackendEnv.backend")
        RecordFieldValidator.require_text(self.model, "ClaudeBackendEnv.model", max_chars=_ID_MAX_CHARS)
        object.__setattr__(self, "public_env", RecordFieldConverter.to_mapping(self.public_env, "ClaudeBackendEnv.public_env"))
        RecordFieldConverter.require_instance(self.auth_token, "ClaudeBackendEnv.auth_token", str)

    def as_environ(self) -> dict[str, str]:
        # The public pairs plus the key under the variable Claude Code reads.
        return {**self.public_env, _AUTH_ENV_KEY: self.auth_token}


@dataclass(frozen=True, slots=True)
class OpencodeBackendProvider:
    """How an owned opencode server reaches a backend: the provider id, which variable to copy into which, and the models."""

    backend: HarnessBackendName
    provider_id: str
    source_env_var: str
    child_env_var: str
    model_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.backend, HarnessBackendName, "OpencodeBackendProvider.backend")
        RecordFieldValidator.require_text(self.provider_id, "OpencodeBackendProvider.provider_id", max_chars=_ID_MAX_CHARS)
        RecordFieldValidator.require_text(self.source_env_var, "OpencodeBackendProvider.source_env_var", max_chars=_ENV_NAME_MAX_CHARS, pattern=_ENV_NAME_PATTERN)
        RecordFieldValidator.require_text(self.child_env_var, "OpencodeBackendProvider.child_env_var", max_chars=_ENV_NAME_MAX_CHARS, pattern=_ENV_NAME_PATTERN)
        object.__setattr__(self, "model_ids", RecordFieldConverter.to_tuple(self.model_ids, "OpencodeBackendProvider.model_ids", item_type=str))


@dataclass(frozen=True, slots=True)
class BackendCompatRequest:
    """Which harness will use a backend, and which Anthropic request features it plans to send."""

    harness: NativeHarness
    features: frozenset[BackendFeature] = frozenset()

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.harness, NativeHarness, "BackendCompatRequest.harness")
        object.__setattr__(self, "features", RecordFieldValidator.require_enum_set(self.features, BackendFeature, "BackendCompatRequest.features"))


@dataclass(frozen=True, slots=True)
class DeepseekBalanceEntry:
    """One currency's DeepSeek balance, parsed from the vendor's decimal strings."""

    currency: str
    total_balance: Decimal
    granted_balance: Decimal
    topped_up_balance: Decimal

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.currency, "DeepseekBalanceEntry.currency", max_chars=_CURRENCY_MAX_CHARS)
        RecordFieldConverter.require_instance(self.total_balance, "DeepseekBalanceEntry.total_balance", Decimal)
        RecordFieldConverter.require_instance(self.granted_balance, "DeepseekBalanceEntry.granted_balance", Decimal)
        RecordFieldConverter.require_instance(self.topped_up_balance, "DeepseekBalanceEntry.topped_up_balance", Decimal)


@dataclass(frozen=True, slots=True)
class DeepseekBalance:
    """Whether the DeepSeek account can serve calls, and its balance per currency."""

    is_available: bool
    balances: tuple[DeepseekBalanceEntry, ...]

    def __post_init__(self) -> None:
        RecordFieldValidator.require_bool(self.is_available, "DeepseekBalance.is_available")
        object.__setattr__(self, "balances", RecordFieldConverter.to_tuple(self.balances, "DeepseekBalance.balances", item_type=DeepseekBalanceEntry))


@dataclass(frozen=True, slots=True)
class BackendReadiness:
    """What check_backend_ready found: the backend, whether a remote call verified the key, and the balance when known."""

    backend: HarnessBackendName
    remote_verified: bool
    balance: DeepseekBalance | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.backend, HarnessBackendName, "BackendReadiness.backend")
        RecordFieldValidator.require_bool(self.remote_verified, "BackendReadiness.remote_verified")
        RecordFieldConverter.require_instance(self.balance, "BackendReadiness.balance", DeepseekBalance, optional=True)


__all__ = [
    "BackendCompatRequest",
    "BackendReadiness",
    "ClaudeBackendEnv",
    "DeepseekBalance",
    "DeepseekBalanceEntry",
    "HarnessBackend",
    "OpencodeBackendProvider",
]
