"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Defines JevAgent's public configuration objects: JevAgentSettings for the agent and its alignment switches, and JevRuntimeSettings for Jev's own decision policy, whose `continual` field holds JevContinualSettings for the done checks and continuations.
ROLE IN CODEBASE: JevAgent maps JevAgentSettings into BaseAgent and builds its preflight gate from both objects at construction, so JevRuntime never reads settings to decide what to ask.
ARCHITECTURE NOTE: The surface is intentionally closed; named Jev capabilities belong here as explicit settings instead of a generic decisions collection. JevAgentSettings holds the main agent, specialist candidates, and one JevAlignmentSettings object with prompt and tool alignment switches; JevRuntimeSettings holds the decision model, preflight flags, continuation settings, and tool-selector threshold.
COMMON MODIFICATION PATTERNS: Add a generative-agent field to JevAgentSettings or a Jev policy setting to JevRuntimeSettings, then implement its fixed policy in vidbyte/agents/jev/gate/ without exposing runtime replacement hooks.
KNOWN EDGE CASES: The generative provider cannot be TypeSafe because Jev is a decision model; neither generative nor decision API keys appear in repr output. Specialist titles must be unique because each one is a Choice option name. Preflight presets are validated by JevPreflightRegistry and done checks by JevDoneRegistry at construction, every continuation limit rejects booleans and non-integers, so no TypeSafe key is needed until a run asks Jev; the tool-selector threshold rejects booleans, non-finite values, and out-of-range probabilities.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, docs/design/jev-multipart-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, tests/test_jev_done.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_DONE_MAX_CONTINUATIONS,
    JEV_HANDOFF_MAX_ITERATIONS,
    JEV_HANDOFF_MAX_TOKENS,
    JEV_RUN_STATE_MAX_ITERATIONS,
    JEV_RUN_STATE_MAX_TOKENS,
    JEV_SPECIALIST_MAX_COUNT,
    JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD,
    JEV_TOOL_SELECTOR_MAX_THRESHOLD,
    JEV_TOOL_SELECTOR_MIN_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevSpecialist
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.dataclasses.tool_catalogs import ToolCatalogCredentials
from vidbyte.lib.enums import JevDoneCheck, JevPreflightPreset, ModelProvider
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevDoneRegistry, JevPreflightRegistry
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
PIPEDREAM_ENVIRONMENTS = frozenset({"development", "production"})
_REQUIRED_CATALOG_CREDENTIALS: Mapping[ToolCatalogName, tuple[str, ...]] = {
    ToolCatalogName.GLAMA: ("api_key",),
    ToolCatalogName.COMPOSIO: ("api_key",),
    ToolCatalogName.ARCADE: ("api_key",),
    ToolCatalogName.PIPEDREAM: ("client_id", "client_secret", "project_id", "environment"),
}
_END_USER_CATALOGS = frozenset({ToolCatalogName.COMPOSIO, ToolCatalogName.PIPEDREAM, ToolCatalogName.ARCADE})


@dataclass(frozen=True, slots=True)
class JevToolAlignmentSettings:
    """Validated settings for discovering and attaching approved catalog tools per run."""

    catalogs: tuple[ToolCatalogName | str, ...] = DEFAULT_TOOL_CATALOGS
    catalog_credentials: Mapping[ToolCatalogName | str, ToolCatalogCredentials] = field(default_factory=dict, repr=False)
    secrets: Mapping[str, str] = field(default_factory=dict, repr=False)
    install_kinds: frozenset[ToolInstallKind | str] = DEFAULT_TOOL_INSTALL_KINDS
    allow_unpinned_packages: bool = False
    allow_high_impact: bool = False
    max_attached_tools: int = TOOL_ALIGN_DEFAULT_MAX_ATTACHED
    time_budget_seconds: float = TOOL_ALIGN_DEFAULT_TIME_BUDGET_SECONDS
    announce: bool = True
    user_id: str | None = None

    def __post_init__(self) -> None:
        catalogs = self._normalized_catalogs()
        credentials = self._normalized_credentials()
        secrets = self._normalized_secrets()
        install_kinds = self._normalized_install_kinds()
        self._validate_catalog_access(catalogs, credentials)
        self._validate_tool_alignment_bounds()
        object.__setattr__(self, "catalogs", catalogs)
        object.__setattr__(self, "catalog_credentials", MappingProxyType(credentials))
        object.__setattr__(self, "secrets", MappingProxyType(secrets))
        object.__setattr__(self, "install_kinds", install_kinds)

    def _normalized_catalogs(self) -> tuple[ToolCatalogName, ...]:
        if isinstance(self.catalogs, (str, bytes)):
            raise ConfigurationError("JevToolAlignmentSettings.catalogs must be a tuple of catalog names, not a string.")
        try:
            catalogs = tuple(dict.fromkeys(ToolCatalogName(name) for name in self.catalogs))
        except ValueError as exc:
            raise ConfigurationError("JevToolAlignmentSettings.catalogs has an unknown catalog.") from exc
        if not catalogs:
            raise ConfigurationError("JevToolAlignmentSettings.catalogs must name at least one catalog.")
        return catalogs

    def _normalized_credentials(self) -> dict[ToolCatalogName, ToolCatalogCredentials]:
        credentials: dict[ToolCatalogName, ToolCatalogCredentials] = {}
        for name, credential in dict(self.catalog_credentials).items():
            if not isinstance(credential, ToolCatalogCredentials):
                raise ConfigurationError("JevToolAlignmentSettings.catalog_credentials values must be ToolCatalogCredentials.")
            try:
                credentials[ToolCatalogName(name)] = credential
            except ValueError as exc:
                raise ConfigurationError(f"JevToolAlignmentSettings.catalog_credentials names an unknown catalog {name!r}.") from exc
        return credentials

    def _normalized_secrets(self) -> dict[str, str]:
        secrets = dict(self.secrets)
        if not all(isinstance(key, str) and key.strip() and isinstance(value, str) and value for key, value in secrets.items()):
            raise ConfigurationError("JevToolAlignmentSettings.secrets must map non-blank names to non-empty string values.")
        return secrets

    def _normalized_install_kinds(self) -> frozenset[ToolInstallKind]:
        try:
            kinds = frozenset(ToolInstallKind(kind) for kind in self.install_kinds)
        except ValueError as exc:
            raise ConfigurationError("JevToolAlignmentSettings.install_kinds has an unknown kind.") from exc
        if not kinds or ToolInstallKind.OPENAPI in kinds:
            raise ConfigurationError("JevToolAlignmentSettings.install_kinds must allow attachable install kinds, not openapi.")
        return kinds

    def _validate_catalog_access(self, catalogs: tuple[ToolCatalogName, ...], credentials: Mapping[ToolCatalogName, ToolCatalogCredentials]) -> None:
        for catalog in catalogs:
            required = _REQUIRED_CATALOG_CREDENTIALS.get(catalog, ())
            credential = credentials.get(catalog)
            if any(not getattr(credential, key, None) for key in required):
                raise ConfigurationError(f"The {catalog.value} catalog needs catalog_credentials with: {', '.join(required)}.")
            if catalog is ToolCatalogName.PIPEDREAM and credential is not None and credential.environment not in PIPEDREAM_ENVIRONMENTS:
                raise ConfigurationError("The pipedream catalog environment must be 'development' or 'production'.")
            if catalog in _END_USER_CATALOGS and not (isinstance(self.user_id, str) and self.user_id.strip()):
                raise ConfigurationError(f"The {catalog.value} catalog runs tools for an end user; set JevToolAlignmentSettings.user_id.")

    def _validate_tool_alignment_bounds(self) -> None:
        for name in ("allow_unpinned_packages", "allow_high_impact", "announce"):
            if not isinstance(getattr(self, name), bool):
                raise ConfigurationError(f"JevToolAlignmentSettings.{name} must be True or False.")
        cap = self.max_attached_tools
        if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= TOOL_ALIGN_MAX_ATTACHED_CEILING:
            raise ConfigurationError(f"JevToolAlignmentSettings.max_attached_tools must be an integer from 1 to {TOOL_ALIGN_MAX_ATTACHED_CEILING}.")
        budget = self.time_budget_seconds
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget <= 0:
            raise ConfigurationError("JevToolAlignmentSettings.time_budget_seconds must be a finite number greater than zero.")

    def credentials_for(self, catalog: ToolCatalogName) -> ToolCatalogCredentials | None:
        return self.catalog_credentials.get(catalog)


@dataclass(frozen=True, slots=True)
class JevAlignmentSettings:
    """Select which request-time alignment passes JevAgent runs and their tool catalog policy."""

    system_prompt: bool = False
    tool_settings: bool = False
    tool_options: JevToolAlignmentSettings = field(default_factory=JevToolAlignmentSettings)

    def __post_init__(self) -> None:
        # Keeps both visible alignment switches explicit while allowing catalog policy to be tuned separately.
        for name in ("system_prompt", "tool_settings"):
            if not isinstance(getattr(self, name), bool):
                raise ConfigurationError(f"JevAlignmentSettings.{name} must be True or False.")
        if not isinstance(self.tool_options, JevToolAlignmentSettings):
            raise ConfigurationError("JevAlignmentSettings.tool_options must be a JevToolAlignmentSettings instance.")


@dataclass(frozen=True, slots=True)
class JevAgentSettings:
    """Validated settings for the agent JevAgent runs by default and the specialists Jev may hand a run to instead."""

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
    agents: tuple[JevSpecialist, ...] = ()
    alignment: JevAlignmentSettings = field(default_factory=JevAlignmentSettings)

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
        if not isinstance(self.alignment, JevAlignmentSettings):
            raise ConfigurationError("JevAgentSettings.alignment must be a JevAlignmentSettings instance.")
        self._validate_agents()

    def _validate_agents(self) -> None:
        # Freezes the specialists in the order given, which is also the order Jev reads their options.
        if isinstance(self.agents, (str, bytes)):
            raise ConfigurationError("JevAgentSettings.agents must be an iterable of JevSpecialist values, not a string.")
        try:
            agents = tuple(self.agents)
        except TypeError as exc:
            raise ConfigurationError("JevAgentSettings.agents must be an iterable of JevSpecialist values.") from exc
        if not all(isinstance(agent, JevSpecialist) for agent in agents):
            raise ConfigurationError("JevAgentSettings.agents must contain only JevSpecialist values.")
        if len(agents) > JEV_SPECIALIST_MAX_COUNT:
            raise ConfigurationError(f"JevAgentSettings.agents can hold at most {JEV_SPECIALIST_MAX_COUNT} specialists.")
        titles = [agent.title for agent in agents]
        if len(set(titles)) != len(titles):
            raise ConfigurationError("JevAgentSettings.agents must have unique titles.", details={"titles": titles})
        object.__setattr__(self, "agents", agents)

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


@dataclass(frozen=True, slots=True)
class JevContinualSettings:
    """Validated continuation settings: the done checks run at every finish attempt, how often a failed one may send the main agent back to work, and the limits of the run-state and handoff agents."""

    checks: tuple[JevDoneCheck | str, ...] = ()
    max_continuations: int = JEV_DONE_MAX_CONTINUATIONS
    run_state_max_iterations: int = JEV_RUN_STATE_MAX_ITERATIONS
    run_state_max_tokens: int = JEV_RUN_STATE_MAX_TOKENS
    handoff_max_iterations: int = JEV_HANDOFF_MAX_ITERATIONS
    handoff_max_tokens: int = JEV_HANDOFF_MAX_TOKENS

    def __post_init__(self) -> None:
        # Rejects unknown or repeated done checks and non-integer limits before JevAgent builds its run state.
        # @intent zero-continuations-still-checks
        # max_continuations may be 0: the checks still run and report on JevAgent.response, but a failed
        # check never sends the main agent back to work.
        object.__setattr__(self, "checks", JevDoneRegistry.validate(self.checks))
        self._validate_count("max_continuations", minimum=0)
        for field_name in ("run_state_max_iterations", "run_state_max_tokens", "handoff_max_iterations", "handoff_max_tokens"):
            self._validate_count(field_name, minimum=1)

    def _validate_count(self, field_name: str, *, minimum: int) -> None:
        # Requires a whole number at or above the minimum, excluding bool.
        value = getattr(self, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ConfigurationError(f"JevContinualSettings.{field_name} must be an integer of at least {minimum}.", details={"received": repr(value)})


@dataclass(frozen=True, slots=True)
class JevRuntimeSettings:
    """Validated Jev decision policy: the TypeSafe model, the preflight flags, the continuation settings, and the tool-selector threshold."""

    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig, repr=False)
    preflight: tuple[JevPreflightPreset | str, ...] = ()
    continual: JevContinualSettings = field(default_factory=JevContinualSettings)
    tool_selector_threshold: float = JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD

    def __post_init__(self) -> None:
        # Rejects invalid decision policy before JevAgent builds its preflight gate and run state.
        if not isinstance(self.decision, DecisionModelConfig):
            raise ConfigurationError("JevRuntimeSettings.decision must be a DecisionModelConfig instance.")
        object.__setattr__(self, "preflight", JevPreflightRegistry.validate(self.preflight))
        if not isinstance(self.continual, JevContinualSettings):
            raise ConfigurationError("JevRuntimeSettings.continual must be a JevContinualSettings instance.")
        self._validate_tool_selector_threshold()

    def _validate_tool_selector_threshold(self) -> None:
        # Accepts calibrated probabilities on the closed unit interval, but excludes bool and non-finite values.
        value = self.tool_selector_threshold
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not JEV_TOOL_SELECTOR_MIN_THRESHOLD <= value <= JEV_TOOL_SELECTOR_MAX_THRESHOLD
        ):
            raise ConfigurationError("JevRuntimeSettings.tool_selector_threshold must be a finite probability between 0 and 1 inclusive.")
        object.__setattr__(self, "tool_selector_threshold", float(value))


__all__ = ["JevAgentSettings", "JevAlignmentSettings", "JevContinualSettings", "JevRuntimeSettings", "JevToolAlignmentSettings"]
