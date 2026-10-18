"""FILE: vidbyte/lib/dataclasses/browser_tools.py

PURPOSE: Defines the validated records of the browser tools the harness thread functions mount: BrowserCapabilityDefinition and BrowserToolDefinition (one registry row and its named tool subsets), BrowserToolRequest (the caller's tools and tool_keys), BrowserToolSelection (one resolved tool string), BrowserServer and BrowserMount (what one call mounts and where), BrowserToolCall and BrowserToolCalls (what the vendor reported), and BrowserThreadResult (what a browser function returns).
ROLE IN CODEBASE: BrowserToolDefinition rows live in BrowserToolRegistry (vidbyte/lib/registries/browser_tools.py), which turns a BrowserToolRequest into BrowserToolSelection records. hostkit/browser.py under vidbyte/harnesses/native/ builds the BrowserServer and BrowserMount records and the BrowserThreadResult; the per-harness wire readers build BrowserToolCall and BrowserToolCalls. BrowserThreadResult and BrowserToolCall are re-exported from vidbyte.harnesses.native.
ARCHITECTURE NOTE: Every check lives in __post_init__, so a constructed record is always valid. BrowserToolRequest holds caller text that may be a key (a tools item, a tool_keys name or value), so it never passes that text to require_text or require_text_items, whose messages quote short values; it checks it with the non-raising accepts_text and refuses with a constant message from vidbyte/lib/constants/browser_tools.py that names only an index, a registry name or a position (spec D-28). The other records hold SDK-built values and use the ordinary validators.
FUNCTION INVENTORY: BrowserToolRequest.__post_init__ is the narrated main function; _checked_tools checks the tools items and _checked_tool_keys the tool_keys entries. BrowserToolDefinition.__post_init__ checks the common fields and then, by transport, _checked_stdio or _checked_remote. BrowserCapabilityDefinition, BrowserToolSelection, BrowserServer, BrowserMount, BrowserToolCall, BrowserToolCalls and BrowserThreadResult have only __post_init__.
COMMON MODIFICATION PATTERNS: A new bound adds its constant to vidbyte/lib/constants/browser_tools.py and one validator call here. A new field of BrowserThreadResult is a public contract change of the nine browser functions and needs a spec change first.
WHAT NOT TO DO IN THIS FILE: 1. Do not quote a tools item, a tool_keys name or a tool_keys value in a message, and do not pass one to a quoting validator. 2. Do not drop repr=False from BrowserToolRequest.tools, BrowserToolRequest.tool_keys or BrowserToolSelection.key. 3. Do not import from vidbyte.harnesses; vidbyte/lib is the bottom layer. 4. Do not resolve a tool string's meaning here; that is the registry's job.
KNOWN EDGE CASES: tools must be a list or tuple; a bare string is refused naming tools, never split into characters. A tool_keys name that is not a registry name (mountable or excluded) is refused by position, as `tool_keys entry <i>`, whatever its value, because the name may be a key the caller swapped with the tool name. A remote server's command is the empty tuple. Artifacts must be absolute; the readers build a BrowserToolCall only after accepts_text passed on the vendor's name, so its own name check never fires on vendor output.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_contract.py, tests/features/harness_threads/test_harness_threads_browser_registry.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from vidbyte.lib.constants.browser_tools import (
    BROWSER_ARTIFACTS_FOLDER,
    BROWSER_ARTIFACTS_MAX_ITEMS,
    BROWSER_EXACT_VERSION_PATTERN,
    BROWSER_NODE_MODULES_FOLDER,
    BROWSER_PACKAGE_PATH_SEPARATOR,
    BROWSER_REMOTE_URL_PREFIX,
    BROWSER_TOOL_CALLS_MAX_ITEMS,
    BROWSER_TOOL_ITEM_FIELD,
    BROWSER_TOOL_ITEM_TEXT,
    BROWSER_TOOL_KEY_ENTRY_FIELD,
    BROWSER_TOOL_KEY_NAME_FIELD,
    BROWSER_TOOL_KEY_NAME_TEXT,
    BROWSER_TOOL_KEY_VALUE_TEXT,
    BROWSER_TOOL_KEYS_FIELD,
    BROWSER_TOOL_STRING_MAX_CHARS,
    BROWSER_TOOL_STRING_PATTERN,
    BROWSER_TOOLS_COUNT_TEXT,
    BROWSER_TOOLS_FIELD,
    BROWSER_TOOLS_MAX_PER_CALL,
)
from vidbyte.lib.constants.native_threads import (
    NATIVE_API_KEY_MAX_CHARS,
    NATIVE_API_KEY_PATTERN,
    NATIVE_FIELD_DETAIL_KEY,
    NATIVE_NAME_MAX_CHARS,
    NATIVE_NAME_PATTERN,
    NATIVE_PROCESS_FLAG_MAX_CHARS,
    NATIVE_PROCESS_FLAG_PATTERN,
    NATIVE_THREAD_ID_MAX_CHARS,
    NATIVE_THREAD_ID_PATTERN,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.browser_tools import (
    BrowserCapability,
    BrowserKeyRequirement,
    BrowserTool,
    BrowserToolCallStatus,
    BrowserToolExclusion,
    BrowserToolTransport,
    BrowserToolVariable,
)
from vidbyte.lib.enums.native_threads import NativeHarness
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class BrowserCapabilityDefinition:
    """One named subset of a tool's own tools; a server_value names the server flag value that turns the subset on (Playwright --caps)."""

    name: BrowserCapability
    tools: tuple[str, ...]
    server_value: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", RecordFieldConverter.to_enum(self.name, BrowserCapability, "BrowserCapabilityDefinition.name"))
        tools = RecordFieldValidator.require_text_items(self.tools, "BrowserCapabilityDefinition.tools", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        if not tools or len(set(tools)) != len(tools):
            raise ConfigurationError("BrowserCapabilityDefinition.tools must list at least one tool, each once.", details={NATIVE_FIELD_DETAIL_KEY: "BrowserCapabilityDefinition.tools"})
        RecordFieldValidator.require_optional_text(self.server_value, "BrowserCapabilityDefinition.server_value", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)


@dataclass(frozen=True, slots=True)
class BrowserToolDefinition:
    """One pinned registry row: how the tool is reached, its key rule, its server options and its named capabilities."""

    tool: BrowserTool
    transport: BrowserToolTransport
    package: str | None
    version: str | None
    entry: tuple[str, ...]
    url: str | None
    key_rule: BrowserKeyRequirement
    key_variable: BrowserToolVariable | None
    arguments: tuple[str, ...]
    environment: Mapping[str, str]
    profile_option: str | None
    output_option: str | None
    caps_option: str | None
    needs_chrome: bool
    capabilities: tuple[BrowserCapabilityDefinition, ...]
    default_capabilities: tuple[BrowserCapability, ...]

    def __post_init__(self) -> None:
        # @intent browser-tool-row-fails-at-load-not-mid-call
        # A registry row is checked whole when the registry module
        # loads, so a bad pin fails at import, never inside a caller's
        # run. Pin the closed vocabularies first, because the
        # transport decides which of the other fields are required.
        object.__setattr__(self, "tool", RecordFieldConverter.to_enum(self.tool, BrowserTool, "BrowserToolDefinition.tool"))
        object.__setattr__(self, "transport", RecordFieldConverter.to_enum(self.transport, BrowserToolTransport, "BrowserToolDefinition.transport"))
        object.__setattr__(self, "key_rule", RecordFieldConverter.to_enum(self.key_rule, BrowserKeyRequirement, "BrowserToolDefinition.key_rule"))
        if self.key_variable is not None:
            object.__setattr__(self, "key_variable", RecordFieldConverter.to_enum(self.key_variable, BrowserToolVariable, "BrowserToolDefinition.key_variable"))

        # The server arguments, options and non-secret environment.
        RecordFieldValidator.require_text_items(self.arguments, "BrowserToolDefinition.arguments", max_chars=NATIVE_PROCESS_FLAG_MAX_CHARS, pattern=NATIVE_PROCESS_FLAG_PATTERN)
        for name in ("profile_option", "output_option", "caps_option"):
            RecordFieldValidator.require_optional_text(getattr(self, name), f"BrowserToolDefinition.{name}", max_chars=NATIVE_PROCESS_FLAG_MAX_CHARS, pattern=NATIVE_PROCESS_FLAG_PATTERN)
        object.__setattr__(self, "environment", RecordFieldConverter.to_mapping(self.environment, "BrowserToolDefinition.environment"))
        RecordFieldValidator.require_bool(self.needs_chrome, "BrowserToolDefinition.needs_chrome")

        # The capabilities have unique names, and the defaults are some
        # of them.
        capabilities = RecordFieldConverter.to_tuple(self.capabilities, "BrowserToolDefinition.capabilities", item_type=BrowserCapabilityDefinition)
        names = [capability.name for capability in capabilities]
        defaults = tuple(RecordFieldConverter.to_enum(item, BrowserCapability, "BrowserToolDefinition.default_capabilities") for item in RecordFieldConverter.to_tuple(self.default_capabilities, "BrowserToolDefinition.default_capabilities", item_type=str))
        if not names or len(set(names)) != len(names) or not defaults or not set(defaults) <= set(names):
            raise ConfigurationError("BrowserToolDefinition.capabilities must have unique names, and default_capabilities must name at least one of them.", details={NATIVE_FIELD_DETAIL_KEY: "BrowserToolDefinition.capabilities"})
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "default_capabilities", defaults)

        # A stdio row is a pinned package; a remote row is an https URL.
        if self.transport is BrowserToolTransport.STDIO:
            self._checked_stdio()
        else:
            self._checked_remote()

    def _checked_stdio(self) -> None:
        # A stdio row pins an exact x.y.z package version and the entry
        # path under the install prefix, node_modules and the package's
        # own path parts first, and has no URL.
        package = RecordFieldValidator.require_text(self.package, "BrowserToolDefinition.package", max_chars=NATIVE_NAME_MAX_CHARS)
        RecordFieldValidator.require_text(self.version, "BrowserToolDefinition.version", max_chars=NATIVE_NAME_MAX_CHARS, pattern=BROWSER_EXACT_VERSION_PATTERN)
        entry = RecordFieldValidator.require_text_items(self.entry, "BrowserToolDefinition.entry", max_chars=NATIVE_NAME_MAX_CHARS)
        prefix = (BROWSER_NODE_MODULES_FOLDER, *package.split(BROWSER_PACKAGE_PATH_SEPARATOR))
        if len(entry) <= len(prefix) or entry[: len(prefix)] != prefix or self.url is not None:
            raise ConfigurationError("A stdio BrowserToolDefinition needs a package, an exact version and an entry under node_modules/<package>, and no url.", details={NATIVE_FIELD_DETAIL_KEY: "BrowserToolDefinition.entry"})

    def _checked_remote(self) -> None:
        # A remote row is an https URL; there is nothing to install, and
        # a key travels as a Bearer header, never in a variable.
        url = RecordFieldValidator.require_text(self.url, "BrowserToolDefinition.url", max_chars=NATIVE_PROCESS_FLAG_MAX_CHARS)
        if not url.startswith(BROWSER_REMOTE_URL_PREFIX) or self.package is not None or self.version is not None or self.entry or self.key_variable is not None or self.needs_chrome:
            raise ConfigurationError("A remote BrowserToolDefinition needs an https url and no package, version, entry, key variable or Chrome.", details={NATIVE_FIELD_DETAIL_KEY: "BrowserToolDefinition.url"})


@dataclass(frozen=True, slots=True)
class BrowserToolRequest:
    """The caller's tools and tool_keys, checked for shape only; neither shows in repr, because a key may sit in either.

    tools is typed Sequence[str] because the record must see the raw
    value: a bare string is refused, not split into characters. After
    __post_init__ tools is a tuple and tool_keys a read-only mapping;
    None becomes an empty mapping.
    """

    tools: Sequence[str] = field(repr=False)
    tool_keys: Mapping[str, str] = field(repr=False)

    def __post_init__(self) -> None:
        # @intent browser-request-never-quotes-caller-text
        # A tools item or a tool_keys entry may be a key the caller
        # pasted in the wrong place, and no key is registered as a
        # secret yet, so every refusal is a constant text naming only
        # an index, a registry name or a position (spec D-28).

        # The tools: a list of 1 to BROWSER_TOOLS_MAX_PER_CALL strings,
        # each one line of the tool-string grammar.
        object.__setattr__(self, "tools", self._checked_tools())

        # The keys: a mapping from a registry name to one key each.
        object.__setattr__(self, "tool_keys", self._checked_tool_keys())

    def _checked_tools(self) -> tuple[str, ...]:
        # to_tuple refuses a bare string naming only its type.
        tools = RecordFieldConverter.to_tuple(self.tools, BROWSER_TOOLS_FIELD, item_type=str)
        if not tools or len(tools) > BROWSER_TOOLS_MAX_PER_CALL:
            raise ConfigurationError(BROWSER_TOOLS_COUNT_TEXT.format(max_items=BROWSER_TOOLS_MAX_PER_CALL), details={NATIVE_FIELD_DETAIL_KEY: BROWSER_TOOLS_FIELD})
        for index, item in enumerate(tools):
            if not RecordFieldValidator.accepts_text(item, max_chars=BROWSER_TOOL_STRING_MAX_CHARS, pattern=BROWSER_TOOL_STRING_PATTERN):
                raise ConfigurationError(BROWSER_TOOL_ITEM_TEXT.format(max_chars=BROWSER_TOOL_STRING_MAX_CHARS), details={NATIVE_FIELD_DETAIL_KEY: BROWSER_TOOL_ITEM_FIELD.format(index=index)})
        return tools

    def _checked_tool_keys(self) -> MappingProxyType[str, str]:
        # A name is shown only when it is a registry name; any other
        # name is named by its position, because it may be the key.
        given: object = self.tool_keys
        keys = RecordFieldConverter.to_mapping({} if given is None else given, BROWSER_TOOL_KEYS_FIELD)
        registry_names = {member.value for member in BrowserTool} | {member.value for member in BrowserToolExclusion}
        for index, (name, value) in enumerate(keys.items()):
            if name not in registry_names:
                raise ConfigurationError(BROWSER_TOOL_KEY_NAME_TEXT, details={NATIVE_FIELD_DETAIL_KEY: BROWSER_TOOL_KEY_ENTRY_FIELD.format(index=index)})
            if not RecordFieldValidator.accepts_text(value, max_chars=NATIVE_API_KEY_MAX_CHARS, pattern=NATIVE_API_KEY_PATTERN):
                raise ConfigurationError(BROWSER_TOOL_KEY_VALUE_TEXT.format(max_chars=NATIVE_API_KEY_MAX_CHARS), details={NATIVE_FIELD_DETAIL_KEY: BROWSER_TOOL_KEY_NAME_FIELD.format(name=name)})
        return keys


@dataclass(frozen=True, slots=True)
class BrowserToolSelection:
    """One resolved tool string: the row, the named capabilities, the tools allowed and denied, the server flag values and the key; the key never shows in repr."""

    definition: BrowserToolDefinition
    capabilities: tuple[BrowserCapability, ...]
    allowed: tuple[str, ...]
    denied: tuple[str, ...]
    server_capabilities: tuple[str, ...]
    key: str | None = field(repr=False)

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.definition, "BrowserToolSelection.definition", BrowserToolDefinition)
        object.__setattr__(self, "capabilities", tuple(RecordFieldConverter.to_enum(item, BrowserCapability, "BrowserToolSelection.capabilities") for item in RecordFieldConverter.to_tuple(self.capabilities, "BrowserToolSelection.capabilities", item_type=str)))
        allowed = RecordFieldValidator.require_text_items(self.allowed, "BrowserToolSelection.allowed", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        if not allowed:
            raise ConfigurationError("BrowserToolSelection.allowed must hold at least one tool.", details={NATIVE_FIELD_DETAIL_KEY: "BrowserToolSelection.allowed"})
        RecordFieldValidator.require_text_items(self.denied, "BrowserToolSelection.denied", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        RecordFieldValidator.require_text_items(self.server_capabilities, "BrowserToolSelection.server_capabilities", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        RecordFieldConverter.require_instance(self.key, "BrowserToolSelection.key", str, optional=True)


@dataclass(frozen=True, slots=True)
class BrowserServer:
    """One mounted server: its selection and, for a stdio tool, the absolute command that starts it; a remote server's command is empty."""

    selection: BrowserToolSelection
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        # @intent browser-server-command-matches-its-transport
        # A stdio server needs the command that starts it and a remote
        # one has none, so a mount never starts a URL as a program or
        # leaves a stdio server without its command.
        RecordFieldConverter.require_instance(self.selection, "BrowserServer.selection", BrowserToolSelection)
        command = RecordFieldConverter.to_tuple(self.command, "BrowserServer.command", item_type=str)
        if bool(command) is not (self.selection.definition.transport is BrowserToolTransport.STDIO):
            raise ConfigurationError("BrowserServer.command must start a stdio server and be empty for a remote one.", details={NATIVE_FIELD_DETAIL_KEY: "BrowserServer.command"})
        object.__setattr__(self, "command", command)


@dataclass(frozen=True, slots=True)
class BrowserMount:
    """What one call mounts: its servers, its own folder outside the workspace and the artifacts folder inside it."""

    servers: tuple[BrowserServer, ...]
    folder: Path
    artifacts: Path

    def __post_init__(self) -> None:
        servers = RecordFieldConverter.to_tuple(self.servers, "BrowserMount.servers", item_type=BrowserServer)
        folder = RecordFieldConverter.require_instance(self.folder, "BrowserMount.folder", Path)
        artifacts = RecordFieldConverter.require_instance(self.artifacts, "BrowserMount.artifacts", Path)
        if not servers or not folder.is_absolute() or artifacts != folder / BROWSER_ARTIFACTS_FOLDER:
            raise ConfigurationError("BrowserMount needs at least one server, an absolute folder and the artifacts folder inside it.", details={NATIVE_FIELD_DETAIL_KEY: "BrowserMount.folder"})
        object.__setattr__(self, "servers", servers)


@dataclass(frozen=True, slots=True)
class BrowserToolCall:
    """One call the harness made to a mounted tool, as the vendor reported it."""

    tool: BrowserTool
    name: str
    status: BrowserToolCallStatus

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool", RecordFieldConverter.to_enum(self.tool, BrowserTool, "BrowserToolCall.tool"))
        RecordFieldValidator.require_text(self.name, "BrowserToolCall.name", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        object.__setattr__(self, "status", RecordFieldConverter.to_enum(self.status, BrowserToolCallStatus, "BrowserToolCall.status"))


@dataclass(frozen=True, slots=True)
class BrowserToolCalls:
    """The calls a reader found, in the order the vendor printed them, and whether more were cut at the cap."""

    calls: tuple[BrowserToolCall, ...]
    truncated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "calls", RecordFieldConverter.to_tuple(self.calls, "BrowserToolCalls.calls", item_type=BrowserToolCall, max_items=BROWSER_TOOL_CALLS_MAX_ITEMS))
        RecordFieldValidator.require_bool(self.truncated, "BrowserToolCalls.truncated")


@dataclass(frozen=True, slots=True)
class BrowserThreadResult:
    """What a browser function returns: the thread to continue or fork, the answer, the vendor's own tool calls and the files the tools saved."""

    harness: NativeHarness
    thread_id: str
    text: str
    text_truncated: bool
    tool_calls: tuple[BrowserToolCall, ...]
    tool_calls_truncated: bool
    artifacts: tuple[Path, ...]
    artifacts_truncated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "BrowserThreadResult.harness"))
        RecordFieldValidator.require_text(self.thread_id, "BrowserThreadResult.thread_id", max_chars=NATIVE_THREAD_ID_MAX_CHARS, pattern=NATIVE_THREAD_ID_PATTERN)
        RecordFieldConverter.require_instance(self.text, "BrowserThreadResult.text", str)
        RecordFieldValidator.require_bool(self.text_truncated, "BrowserThreadResult.text_truncated")
        object.__setattr__(self, "tool_calls", RecordFieldConverter.to_tuple(self.tool_calls, "BrowserThreadResult.tool_calls", item_type=BrowserToolCall, max_items=BROWSER_TOOL_CALLS_MAX_ITEMS))
        RecordFieldValidator.require_bool(self.tool_calls_truncated, "BrowserThreadResult.tool_calls_truncated")
        artifacts = RecordFieldConverter.to_tuple(self.artifacts, "BrowserThreadResult.artifacts", item_type=Path, max_items=BROWSER_ARTIFACTS_MAX_ITEMS)
        if not all(path.is_absolute() for path in artifacts):
            raise ConfigurationError("BrowserThreadResult.artifacts must hold absolute paths.", details={NATIVE_FIELD_DETAIL_KEY: "BrowserThreadResult.artifacts"})
        object.__setattr__(self, "artifacts", artifacts)
        RecordFieldValidator.require_bool(self.artifacts_truncated, "BrowserThreadResult.artifacts_truncated")


__all__ = [
    "BrowserCapabilityDefinition",
    "BrowserMount",
    "BrowserServer",
    "BrowserThreadResult",
    "BrowserToolCall",
    "BrowserToolCalls",
    "BrowserToolDefinition",
    "BrowserToolRequest",
    "BrowserToolSelection",
]
