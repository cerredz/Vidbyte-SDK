"""FILE: vidbyte/agents/browser/settings.py

PURPOSE: Defines the two public configuration objects of BrowserAgent: BrowserServerSettings, one MCP server given as a registered preset or a command, with the keys it needs in its own env and its request timeout; and BrowserAgentSettings, the model, the prompt, the three server roles (action, search, fetch), the done criteria, the developer's extra tools, the loop limits, the per-episode caps, the recheck cadence, and the event sink.
ROLE IN CODEBASE: Built by the developer and passed to BrowserAgent (vidbyte/agents/browser/agent.py), which queues each server through the MCP mixin; read by the runtime, the episode tool, the goal card, and the checks. Exported by vidbyte/agents/browser/__init__.py, vidbyte/agents/__init__.py, and the root vidbyte package.
ARCHITECTURE NOTE: Settings objects live in the owning agent's settings.py (AGENTS.md Placement Rules, exception 1). Every check runs in __post_init__, so a constructed object is always valid and nothing downstream checks it again. Each field check is one call to RecordFieldValidator or RecordFieldConverter (vidbyte/lib/dataclasses/validation.py); the preset check is McpPresetRegistry's own build_config, the model check is ProviderModelRegistry's, and the key match is ProviderKeyMatcher's. Only the rules that tie fields together are written here. Server keys are read only from BrowserServerSettings.env, never from os.environ, because the MCP transport passes a child process an allowlisted environment that would never carry a parent key.
FUNCTION INVENTORY: BrowserServerSettings.__post_init__ and BrowserAgentSettings.__post_init__ are the narrated main functions; BrowserAgentSettings._require_distinct_servers is their one private helper, which requires an action server and refuses a server repeated across the roles.
COMMON MODIFICATION PATTERNS: A new setting adds one field, one RecordFieldValidator or RecordFieldConverter call in its __post_init__, a named default in vidbyte/lib/constants/browser.py, and one row in the folder README.
WHAT NOT TO DO IN THIS FILE: 1. Do not read os.environ; a key in it never reaches the server. 2. Do not put env, api_keys, or vidbyte_api_key in an error message or in repr. 3. Do not accept an unregistered McpPresetDefinition; the registered preset of that name would run instead. 4. Do not add a field whose name contains submit; no code acts on ready_to_submit, the no-submit rule lives in the prompts, and permission_policy is the only code gate.
KNOWN EDGE CASES: A preset given by name or by its registered definition is stored as the registered McpPresetDefinition. A blank env value is refused, because build_config accepts a present-but-blank key and the server would start unauthenticated. A duplicate command is reported by its program name only, since later arguments may carry a key. True is refused for every cap, although Python counts it as an int.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 8.5, 9.2, and 9.3); vidbyte/agents/browser/README.md
TESTS: tests/features/browser_agent/test_browser_agent_settings.py
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import cast

from vidbyte.agents.settings import AgentLoopSettings, ToolSettings
from vidbyte.lib.constants.browser import (
    BROWSER_DEFAULT_KEEP_OBSERVATIONS,
    BROWSER_DEFAULT_MAX_ACTIONS,
    BROWSER_DEFAULT_MAX_ITERATIONS,
    BROWSER_DEFAULT_MAX_SCREENSHOTS,
    BROWSER_DEFAULT_MAX_STALLS,
    BROWSER_DEFAULT_RECHECK_EVERY,
    BROWSER_DEFAULT_SERVER_TIMEOUT_SECONDS,
    BROWSER_ITEM_MAX_CHARS,
    BROWSER_MAX_CRITERIA,
    BROWSER_MAX_SERVER_TIMEOUT_SECONDS,
    BROWSER_MIN_CAP,
    BROWSER_RESERVED_TOOL_NAMES,
    BROWSER_TOOL_RESULT_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import ProviderKeys
from vidbyte.lib.dataclasses.browser import BrowserEvent
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.text_model import TextModelMode
from vidbyte.lib.errors import ConfigurationError, ToolRegistrationError
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher
from vidbyte.tools.adapters import ToolInput
from vidbyte.tools.catalog import Tools
from vidbyte.tools.mcp import (
    McpPresetConfigurationError,
    McpPresetDefinition,
    McpPresetNotFoundError,
    McpPresetRegistry,
)


@dataclass(frozen=True, slots=True)
class BrowserServerSettings:
    """One MCP server of a BrowserAgent: a registered preset or a command, the keys it needs in env, and its request timeout.

    After __post_init__ preset is the registered McpPresetDefinition or
    None, command a tuple or None, and env a read-only mapping.
    """

    preset: str | McpPresetDefinition | None = None
    command: tuple[str, ...] | None = None
    env: Mapping[str, str] = field(default_factory=dict, repr=False)
    timeout: float = BROWSER_DEFAULT_SERVER_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        # A server is either a registered preset or a command the
        # developer runs, never both and never neither.
        if (self.preset is None) == (self.command is None):
            raise ConfigurationError("BrowserServerSettings needs exactly one of preset or command: a registered preset name or McpPresetDefinition, or the command that starts the server.", details={"field": "BrowserServerSettings.preset"})

        # @intent only-registered-presets-run
        # The mixin queues a preset by its name, so a definition is
        # accepted only when it is the registered one; otherwise the
        # registered preset of that name would run instead, silently.
        if self.preset is not None:
            name = self.preset.name if isinstance(self.preset, McpPresetDefinition) else self.preset
            try:
                registered = McpPresetRegistry.get(RecordFieldValidator.require_text(name, "BrowserServerSettings.preset"))
            except McpPresetNotFoundError as exc:
                raise ConfigurationError(f"BrowserServerSettings.preset must name a registered MCP preset; got {name!r}. Register a custom definition with McpPresetRegistry.register, or pass command= instead.", details={"field": "BrowserServerSettings.preset"}) from exc
            if isinstance(self.preset, McpPresetDefinition) and self.preset != registered:
                raise ConfigurationError(f"BrowserServerSettings.preset differs from the registered preset {name!r}. Register it with McpPresetRegistry.register, or pass command= instead.", details={"field": "BrowserServerSettings.preset"})
            object.__setattr__(self, "preset", registered)

        # A command is a real argument list, never one string that
        # would split into characters.
        if self.command is not None:
            object.__setattr__(self, "command", RecordFieldValidator.require_argv(self.command, "BrowserServerSettings.command"))

        # @intent server-keys-come-only-from-env
        # Keep a read-only copy of env, so a key cannot change after
        # this check, and refuse a blank value, which the server would
        # read as no key at all. Messages name the variable and, for a
        # preset server, the preset, never the value.
        env = RecordFieldConverter.to_mapping(self.env, "BrowserServerSettings.env")
        owner = f" for the {self.preset.name!r} preset" if isinstance(self.preset, McpPresetDefinition) else ""
        for variable, value in env.items():
            try:
                RecordFieldValidator.require_text(value, f"BrowserServerSettings.env[{variable}]")
            except ConfigurationError as exc:
                raise ConfigurationError(f"BrowserServerSettings.env[{variable}]{owner} must not be blank; put its value in env, since os.environ is never read.", details=exc.details) from exc
        object.__setattr__(self, "env", env)
        RecordFieldValidator.require_number(self.timeout, "BrowserServerSettings.timeout", maximum=BROWSER_MAX_SERVER_TIMEOUT_SECONDS)

        # @intent required-keys-are-checked-before-any-run
        # The preset's own config builder names every required variable
        # missing from env; os.environ is never consulted, because the
        # server process would never receive a key from it.
        if isinstance(self.preset, McpPresetDefinition):
            try:
                McpPresetRegistry.build_config(self.preset.name, env=env, timeout=self.timeout)
            except McpPresetConfigurationError as exc:
                raise ConfigurationError(f"BrowserServerSettings.env must hold the keys the {self.preset.name!r} preset requires; {exc}. Put each key in env; os.environ is never read.", details={"field": "BrowserServerSettings.env"}) from exc


@dataclass(frozen=True, slots=True)
class BrowserAgentSettings:
    """Everything a BrowserAgent run uses: the model, the prompt, the servers by role, the done criteria, the extra tools, the loop limits, the episode caps, the recheck cadence, and the event sink.

    After __post_init__ provider is a ModelProvider, api_keys the
    matched ProviderKeys record, and every sequence field a tuple.
    """

    name: str
    system_prompt: str
    provider: ModelProvider | str
    model_name: str
    action_servers: tuple[BrowserServerSettings, ...]
    search_servers: tuple[BrowserServerSettings, ...] = ()
    fetch_servers: tuple[BrowserServerSettings, ...] = ()
    done_when: tuple[str, ...] = ()
    api_keys: ProviderKeys | Iterable[str | None] | None = field(default_factory=ProviderKeys, repr=False)
    vidbyte_api_key: str | None = field(default=None, repr=False)
    model_mode: TextModelMode = TextModelMode.AUTO
    temperature: float | None = None
    timeout_seconds: float | None = None
    episode_model_name: str | None = None
    recheck_model_name: str | None = None
    tools: tuple[object, ...] = ()
    permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy.allow_all)
    loop: AgentLoopSettings = field(
        default_factory=partial(
            AgentLoopSettings,
            max_iterations=BROWSER_DEFAULT_MAX_ITERATIONS,
            tool_settings=ToolSettings(result_max_chars=BROWSER_TOOL_RESULT_MAX_CHARS),
        )
    )
    max_actions: int = BROWSER_DEFAULT_MAX_ACTIONS
    max_screenshots: int = BROWSER_DEFAULT_MAX_SCREENSHOTS
    keep_observations: int = BROWSER_DEFAULT_KEEP_OBSERVATIONS
    recheck_every: int = BROWSER_DEFAULT_RECHECK_EVERY
    max_stalls: int = BROWSER_DEFAULT_MAX_STALLS
    on_event: Callable[[BrowserEvent], None] | None = None

    def __post_init__(self) -> None:
        # @intent one-closed-surface-for-the-whole-run
        # These settings configure the orchestrator, every worker, and
        # every check, so a bad value is refused here, before any server
        # starts, and the error names the field that must change.
        for name in ("name", "system_prompt", "model_name"):
            RecordFieldValidator.require_text(getattr(self, name), f"BrowserAgentSettings.{name}")
        RecordFieldValidator.require_optional_text(self.episode_model_name, "BrowserAgentSettings.episode_model_name")
        RecordFieldValidator.require_optional_text(self.recheck_model_name, "BrowserAgentSettings.recheck_model_name")

        # Developers may name the provider as text; the enum is stored,
        # and every model the run uses must run under it. A worker or
        # check model left unset uses model_name.
        object.__setattr__(self, "provider", RecordFieldConverter.to_enum(self.provider, ModelProvider, "BrowserAgentSettings.provider"))
        checking = "provider"
        try:
            ProviderModelRegistry.validate_provider(cast("ModelProvider", self.provider).value)
            checking = "model_name"
            ProviderModelRegistry.validate_provider_model_pair(self.provider, self.model_name)
            checking = "episode_model_name"
            ProviderModelRegistry.validate_provider_model_pair(self.provider, self.episode_model_name or self.model_name)
            checking = "recheck_model_name"
            ProviderModelRegistry.validate_provider_model_pair(self.provider, self.recheck_model_name or self.model_name)
        except ConfigurationError as exc:
            raise ConfigurationError(f"BrowserAgentSettings.{checking} must name a provider and models the SDK can run together; {exc.message}", details={"field": f"BrowserAgentSettings.{checking}"}) from exc

        # Keep each role's servers as a tuple, with at least one action
        # server and no server in two places.
        roles = {name: RecordFieldConverter.to_tuple(getattr(self, name), f"BrowserAgentSettings.{name}", item_type=BrowserServerSettings) for name in ("action_servers", "search_servers", "fetch_servers")}
        self._require_distinct_servers(roles)
        for name, servers in roles.items():
            object.__setattr__(self, name, servers)

        # The done criteria are fixed for the run: each is one short
        # line, and an empty tuple means one call derives them.
        RecordFieldValidator.require_text_items(self.done_when, "BrowserAgentSettings.done_when", max_items=BROWSER_MAX_CRITERIA, max_chars=BROWSER_ITEM_MAX_CHARS, one_line=True)

        # Match the developer's keys once against the provider; every
        # agent of the run carries this one record, never shown.
        matched = ProviderKeyMatcher.match(self.api_keys, primary=self.provider, vidbyte_api_key=self.vidbyte_api_key, field_name="BrowserAgentSettings.api_keys")
        object.__setattr__(self, "api_keys", matched)
        object.__setattr__(self, "vidbyte_api_key", matched.vidbyte_api_key)
        RecordFieldValidator.require_enum(self.model_mode, TextModelMode, "BrowserAgentSettings.model_mode")
        RecordFieldConverter.require_instance(self.temperature, "BrowserAgentSettings.temperature", (int, float), optional=True)
        RecordFieldConverter.require_instance(self.timeout_seconds, "BrowserAgentSettings.timeout_seconds", (int, float), optional=True)

        # @intent run-bound-names-stay-reserved
        # The extras must form a valid catalog, and none may take the
        # name of run_episode or patch_goal, or the model could not tell
        # which tool it is calling.
        tools = RecordFieldConverter.to_tuple(self.tools, "BrowserAgentSettings.tools", item_type=object)
        try:
            names = Tools(cast("tuple[ToolInput, ...]", tools)).names()
        except (ToolRegistrationError, TypeError) as exc:
            raise ConfigurationError("BrowserAgentSettings.tools must hold tools with distinct names.", details={"field": "BrowserAgentSettings.tools"}) from exc
        taken = [name for name in names if name in BROWSER_RESERVED_TOOL_NAMES]
        if taken:
            raise ConfigurationError(f"BrowserAgentSettings.tools must not reuse a reserved tool name; got {', '.join(taken)}. Reserved: {', '.join(BROWSER_RESERVED_TOOL_NAMES)}.", details={"field": "BrowserAgentSettings.tools"})
        object.__setattr__(self, "tools", tools)

        # The policy and the loop must be the SDK's own objects, which
        # have checked themselves.
        RecordFieldConverter.require_instance(self.permission_policy, "BrowserAgentSettings.permission_policy", PermissionPolicy)
        RecordFieldConverter.require_instance(self.loop, "BrowserAgentSettings.loop", AgentLoopSettings)

        # @intent caps-are-whole-numbers-in-code
        # Every cap is a whole number of at least one, enforced by code,
        # so no prompt states a number the code could contradict.
        for name in ("max_actions", "max_screenshots", "keep_observations", "recheck_every", "max_stalls"):
            RecordFieldValidator.require_int(getattr(self, name), f"BrowserAgentSettings.{name}", minimum=BROWSER_MIN_CAP)

        # @intent the-event-sink-is-a-plain-function
        # The sink is called in line and never awaited, so an async
        # function would only make coroutines that never run.
        sink = self.on_event
        if sink is not None and (not callable(sink) or inspect.iscoroutinefunction(sink) or inspect.iscoroutinefunction(getattr(sink, "__call__", None))):
            raise ConfigurationError(f"BrowserAgentSettings.on_event must be None or a plain function that takes one BrowserEvent; got a value of type {type(sink).__name__}.", details={"field": "BrowserAgentSettings.on_event"})

    @staticmethod
    def _require_distinct_servers(roles: Mapping[str, tuple[BrowserServerSettings, ...]]) -> None:
        # @intent each-server-runs-once-in-one-role
        # Workers get only the action servers, and the orchestrator only
        # the search and fetch servers, so at least one action server is
        # needed, and one server in two places would start twice or put
        # its tools in the wrong agent. A command is named by its
        # program only, because later arguments may carry a key.
        if not roles["action_servers"]:
            raise ConfigurationError("BrowserAgentSettings.action_servers must hold at least one server; workers act on pages only through its tools.", details={"field": "BrowserAgentSettings.action_servers"})
        seen: set[object] = set()
        for name, servers in roles.items():
            for index, server in enumerate(servers):
                preset = server.preset.name if isinstance(server.preset, McpPresetDefinition) else None
                key, label = (("preset", preset), preset) if preset else (("command", server.command), cast("tuple[str, ...]", server.command)[0])
                if key in seen:
                    raise ConfigurationError(f"BrowserAgentSettings.{name}[{index}] repeats the server {label!r}; each preset and each command may appear once across action_servers, search_servers, and fetch_servers.", details={"field": f"BrowserAgentSettings.{name}[{index}]"})
                seen.add(key)

__all__ = ["BrowserAgentSettings", "BrowserServerSettings"]
