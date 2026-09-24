"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Defines the single, opinionated public configuration object for JevAgent, and JevToolAlignmentSettings for its tool-alignment capability.
ROLE IN CODEBASE: JevAgentSettings is the only constructor input accepted by JevAgent and carries the future decision-model seam into JevRuntime.
ARCHITECTURE NOTE: The surface is intentionally closed; named Jev capabilities belong here as explicit settings instead of a generic decisions collection.
COMMON MODIFICATION PATTERNS: Add a validated named capability object, then implement its fixed policy in JevRuntime without exposing runtime replacement hooks.
KNOWN EDGE CASES: The generative provider cannot be TypeSafe because Jev is a decision model; neither generative nor decision API keys appear in repr output, and neither do tool-catalog credentials or install secrets.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.dataclasses.tool_catalogs import ToolCatalogCredentials
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.security import PermissionPolicy

DEFAULT_TOOL_CATALOGS: tuple[ToolCatalogName, ...] = (
    ToolCatalogName.MCP_REGISTRY,
    ToolCatalogName.GITHUB_MCP_REGISTRY,
    ToolCatalogName.DOCKER_MCP_CATALOG,
    ToolCatalogName.SMITHERY,
    ToolCatalogName.TOOLSDK,
)
DEFAULT_TOOL_INSTALL_KINDS: frozenset[ToolInstallKind] = frozenset({ToolInstallKind.REMOTE_HTTP, ToolInstallKind.MANAGED})
TOOL_ALIGN_MAX_ATTACHED_CEILING = 20
TOOL_ALIGN_DEFAULT_MAX_ATTACHED = 6
TOOL_ALIGN_DEFAULT_TIME_BUDGET_SECONDS = 60.0
TOOL_ALIGN_MIN_TIME_BUDGET_SECONDS = 0.0
PIPEDREAM_ENVIRONMENTS = frozenset({"development", "production"})
# Credential fields each keyed catalog cannot be searched or run without.
_REQUIRED_CATALOG_CREDENTIALS: Mapping[ToolCatalogName, tuple[str, ...]] = {
    ToolCatalogName.GLAMA: ("api_key",),
    ToolCatalogName.COMPOSIO: ("api_key",),
    ToolCatalogName.ARCADE: ("api_key",),
    ToolCatalogName.PIPEDREAM: ("client_id", "client_secret", "project_id", "environment"),
}
# Catalogs whose platforms run tools for an end user, so they need JevToolAlignmentSettings.user_id.
_END_USER_CATALOGS = frozenset({ToolCatalogName.COMPOSIO, ToolCatalogName.PIPEDREAM, ToolCatalogName.ARCADE})


@dataclass(frozen=True, slots=True)
class JevToolAlignmentSettings:
    """Validated settings for tool alignment: which catalogs to search, what may be attached, and the owner's secrets."""

    catalogs: tuple[ToolCatalogName | str, ...] = DEFAULT_TOOL_CATALOGS
    catalog_credentials: Mapping[ToolCatalogName | str, ToolCatalogCredentials] = field(default_factory=dict, repr=False)
    # Secret and config values catalog installs need, keyed by the name the install declares (such as BRAVE_API_KEY).
    secrets: Mapping[str, str] = field(default_factory=dict, repr=False)
    install_kinds: frozenset[ToolInstallKind | str] = DEFAULT_TOOL_INSTALL_KINDS
    allow_unpinned_packages: bool = False
    allow_high_impact: bool = False
    max_attached_tools: int = TOOL_ALIGN_DEFAULT_MAX_ATTACHED
    time_budget_seconds: float = TOOL_ALIGN_DEFAULT_TIME_BUDGET_SECONDS
    announce: bool = True
    # The end user a managed platform (Composio, Pipedream, Arcade) runs tools for.
    user_id: str | None = None

    def __post_init__(self) -> None:
        # Normalizes catalog and install names to enums and rejects settings that could never attach a tool.
        # @intent tool-align-settings-fail-before-runtime
        # A keyed catalog without its credential, a managed platform without an end user, or an install kind the
        # SDK cannot run would otherwise fail on every request; refusing at construction names the fix once.
        catalogs = self._normalized_catalogs()
        object.__setattr__(self, "catalogs", catalogs)
        object.__setattr__(self, "catalog_credentials", MappingProxyType(self._normalized_credentials()))
        object.__setattr__(self, "secrets", MappingProxyType(self._normalized_secrets()))
        object.__setattr__(self, "install_kinds", self._normalized_install_kinds())
        self._validate_catalog_credentials(catalogs)
        self._validate_bounds()

    def credentials_for(self, catalog: ToolCatalogName) -> ToolCatalogCredentials | None:
        """Return the owner's credentials for one catalog, or None when none were given."""
        return self.catalog_credentials.get(catalog)

    def _normalized_catalogs(self) -> tuple[ToolCatalogName, ...]:
        # Converts names to ToolCatalogName once, keeping the owner's order and dropping repeats.
        if isinstance(self.catalogs, (str, bytes)):
            raise ConfigurationError("JevToolAlignmentSettings.catalogs must be a tuple of catalog names, not a string.")
        try:
            normalized = tuple(dict.fromkeys(ToolCatalogName(name) for name in self.catalogs))
        except ValueError as exc:
            raise ConfigurationError(f"JevToolAlignmentSettings.catalogs has an unknown catalog; use {sorted(item.value for item in ToolCatalogName)}.") from exc
        if not normalized:
            raise ConfigurationError("JevToolAlignmentSettings.catalogs must name at least one catalog.")
        return normalized

    def _normalized_credentials(self) -> dict[ToolCatalogName, ToolCatalogCredentials]:
        # Keys credentials by ToolCatalogName and requires ToolCatalogCredentials values.
        normalized: dict[ToolCatalogName, ToolCatalogCredentials] = {}
        for name, credentials in dict(self.catalog_credentials).items():
            if not isinstance(credentials, ToolCatalogCredentials):
                raise ConfigurationError("JevToolAlignmentSettings.catalog_credentials values must be ToolCatalogCredentials.")
            try:
                normalized[ToolCatalogName(name)] = credentials
            except ValueError as exc:
                raise ConfigurationError(f"JevToolAlignmentSettings.catalog_credentials names an unknown catalog {name!r}.") from exc
        return normalized

    def _normalized_secrets(self) -> dict[str, str]:
        # Requires non-blank string names and values so a blank secret never reaches a header.
        secrets = dict(self.secrets)
        if not all(isinstance(key, str) and key.strip() and isinstance(value, str) and value for key, value in secrets.items()):
            raise ConfigurationError("JevToolAlignmentSettings.secrets must map non-blank names to non-empty string values.")
        return secrets

    def _normalized_install_kinds(self) -> frozenset[ToolInstallKind]:
        # Converts install kinds to ToolInstallKind and refuses OPENAPI, which cannot be attached yet.
        try:
            kinds = frozenset(ToolInstallKind(kind) for kind in self.install_kinds)
        except ValueError as exc:
            raise ConfigurationError(f"JevToolAlignmentSettings.install_kinds has an unknown kind; use {sorted(item.value for item in ToolInstallKind)}.") from exc
        if not kinds:
            raise ConfigurationError("JevToolAlignmentSettings.install_kinds must allow at least one install kind.")
        if ToolInstallKind.OPENAPI in kinds:
            raise ConfigurationError("JevToolAlignmentSettings.install_kinds cannot include openapi; OpenAPI entries are reported, not attached.")
        return kinds

    def _validate_catalog_credentials(self, catalogs: tuple[ToolCatalogName, ...]) -> None:
        # Requires every keyed catalog's credential fields, a valid Pipedream environment, and an end user for managed platforms.
        for catalog in catalogs:
            required = _REQUIRED_CATALOG_CREDENTIALS.get(catalog, ())
            credentials = self.credentials_for(catalog)
            missing = [name for name in required if credentials is None or not getattr(credentials, name)]
            if missing:
                raise ConfigurationError(f"The {catalog.value} catalog needs catalog_credentials with: {', '.join(missing)}.")
            if catalog is ToolCatalogName.PIPEDREAM and credentials is not None and credentials.environment not in PIPEDREAM_ENVIRONMENTS:
                raise ConfigurationError("The pipedream catalog environment must be 'development' or 'production'.")
            if catalog in _END_USER_CATALOGS and not (isinstance(self.user_id, str) and self.user_id.strip()):
                raise ConfigurationError(f"The {catalog.value} catalog runs tools for an end user; set JevToolAlignmentSettings.user_id.")

    def _validate_bounds(self) -> None:
        # Validates the booleans, the attach cap, and the time budget.
        for name in ("allow_unpinned_packages", "allow_high_impact", "announce"):
            if not isinstance(getattr(self, name), bool):
                raise ConfigurationError(f"JevToolAlignmentSettings.{name} must be True or False.")
        cap = self.max_attached_tools
        if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= TOOL_ALIGN_MAX_ATTACHED_CEILING:
            raise ConfigurationError(f"JevToolAlignmentSettings.max_attached_tools must be an integer from 1 to {TOOL_ALIGN_MAX_ATTACHED_CEILING}.")
        budget = self.time_budget_seconds
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget <= TOOL_ALIGN_MIN_TIME_BUDGET_SECONDS:
            raise ConfigurationError("JevToolAlignmentSettings.time_budget_seconds must be a finite number greater than zero.")


@dataclass(frozen=True, slots=True)
class JevAgentSettings:
    """Validated construction settings for the opinionated Jev agent."""

    name: str
    system_prompt: str
    provider: ModelProvider | str
    model_name: str
    api_key: str | None = field(default=None, repr=False)
    temperature: float | None = None
    timeout_seconds: float | None = None
    tools: tuple[object, ...] = ()
    permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)
    loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)
    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig, repr=False)
    self_align: bool = False
    # Tool alignment: None leaves the tool list fixed; settings turn on attaching existing catalog tools per run.
    tool_align: JevToolAlignmentSettings | None = None

    def __post_init__(self) -> None:
        # Normalizes immutable inputs and rejects invalid agent configuration before runtime construction.
        # @intent opinionated-settings-fail-before-runtime
        # A frozen, validated settings object prevents later capability code from inheriting ambiguous policy inputs.
        self._validate_text(self.name, "name")
        self._validate_text(self.system_prompt, "system_prompt")
        self._validate_text(self.model_name, "model_name")
        provider = self._normalized_provider()
        if provider is ModelProvider.TYPESAFE:
            raise ConfigurationError("JevAgentSettings.provider must be a generative model provider, not TypeSafe.")
        object.__setattr__(self, "provider", provider)
        if isinstance(self.tools, (str, bytes)):
            raise ConfigurationError("JevAgentSettings.tools must be an iterable of tool objects, not a string.")
        try:
            object.__setattr__(self, "tools", tuple(self.tools))
        except TypeError as exc:
            raise ConfigurationError("JevAgentSettings.tools must be an iterable of tool objects.") from exc
        self._validate_temperature()
        self._validate_timeout()
        if not isinstance(self.permission_policy, PermissionPolicy):
            raise ConfigurationError("JevAgentSettings.permission_policy must be a PermissionPolicy instance.")
        if not isinstance(self.loop, AgentLoopSettings):
            raise ConfigurationError("JevAgentSettings.loop must be an AgentLoopSettings instance.")
        if not isinstance(self.decision, DecisionModelConfig):
            raise ConfigurationError("JevAgentSettings.decision must be a DecisionModelConfig instance.")
        if not isinstance(self.self_align, bool):
            raise ConfigurationError("JevAgentSettings.self_align must be True or False.")
        if self.tool_align is not None and not isinstance(self.tool_align, JevToolAlignmentSettings):
            raise ConfigurationError("JevAgentSettings.tool_align must be a JevToolAlignmentSettings instance or None.")

    @staticmethod
    def _validate_text(value: object, field_name: str) -> None:
        # Requires identity and prompt fields to be non-blank strings.
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"JevAgentSettings.{field_name} must be a non-blank string.")

    def _normalized_provider(self) -> ModelProvider:
        # Converts the public string form into the SDK provider enum exactly once.
        # @intent generative-and-decision-providers-stay-distinct
        # Canonicalizing here lets construction reject TypeSafe before a decision model is mistaken for a text runner.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def _validate_temperature(self) -> None:
        # Applies the shared generative-model temperature range without accepting booleans or non-finite numbers.
        value = self.temperature
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 2.0:
            raise ConfigurationError("JevAgentSettings.temperature must be a finite number between 0 and 2.")

    def _validate_timeout(self) -> None:
        # Requires a finite positive generative-model timeout when one is supplied.
        value = self.timeout_seconds
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0:
            raise ConfigurationError("JevAgentSettings.timeout_seconds must be a finite number greater than zero.")


__all__ = ["DEFAULT_TOOL_CATALOGS", "DEFAULT_TOOL_INSTALL_KINDS", "JevAgentSettings", "JevToolAlignmentSettings"]
