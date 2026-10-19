"""FILE: vidbyte/harnesses/native/opencode/mounts.py

PURPOSE: Defines OpencodeMounts, the compile helpers that turn one call's BrowserMount into what opencode reads: the `mcp` member, with one `vidbyte-<tool>` server per mounted tool, and the fail-closed `permission` member of OPENCODE_CONFIG_CONTENT, plus the tool key variables the opencode child must not inherit.
ROLE IN CODEBASE: OpencodeWire.config_content (opencode/wire.py) adds config to the inline config, OpencodeThreadRun.execute (opencode/threads.py) passes env_remove to CliRunner, and OpencodeBrowserHarness.check (opencode/browser.py) calls check before any I/O.
ARCHITECTURE NOTE: Pure helpers: no process, no file and no await, and nothing imported from this subpackage, so threads, wire and browser all import this module one way (spec D-27). Every server id carries BROWSER_OPENCODE_SERVER_PREFIX and sets "enabled": true, so a user's global mcp entry of the same tool can neither merge into nor disable it (D-23). opencode applies the last matching permission rule, so a narrowed server's wildcard deny comes before its exact allows (D-10), and the built-in web tools are denied so the agent browses only through the mounted tools. A tool key travels only in its server's environment (stdio) or Authorization header (remote), so only inside OPENCODE_CONFIG_CONTENT. Every member name and value comes from vidbyte/lib/constants/browser_tools.py (spec INV-15).
FUNCTION INVENTORY: check is the seam's refusal step, which refuses nothing because opencode carries every selection; config builds the mcp and permission members; env_remove names the unpassed key variables; _server builds one server entry; _rules builds one server's permission rules.
COMMON MODIFICATION PATTERNS: A new server member is one more constant name and one more key in _server; a new built-in web tool to switch off is one more name in OPENCODE_WEB_TOOLS.
WHAT NOT TO DO IN THIS FILE: 1. Do not drop the prefix or "enabled": true from a server entry; a user's global entry would merge into it or switch it off. 2. Do not put the exact allows before the wildcard deny; the reverse order hides every tool. 3. Do not put a key anywhere but its server's environment or header; the caller registers the whole config value as a secret.
KNOWN EDGE CASES: opencode prints no per-server status, so a server that fails to start shows only as no mounted tool being used (spec EC-17). Every server inherits OPENCODE_CONFIG_CONTENT, which holds every key of the call (T-6, accepted). A key variable of a mounted tool that the caller did not pass is removed from the child, so a key in the caller's own environment is never used silently (D-20).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_mounts.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import browser_tools
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserMount,
    BrowserServer,
    BrowserToolSelection,
)
from vidbyte.lib.dataclasses.native_threads import NativeThreadRequest
from vidbyte.lib.enums.browser_tools import BrowserToolTransport


class OpencodeMounts:
    """Compiles one call's browser mount into opencode's inline mcp and permission members and its removed key variables."""

    @staticmethod
    def check(selections: tuple[BrowserToolSelection, ...], request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        # @intent opencode-carries-every-selection
        # opencode takes every transport, key and narrowing the registry
        # can select: keys travel inside OPENCODE_CONFIG_CONTENT and a
        # narrowing fails closed in its permission member, so no
        # selection is refused here.
        return None

    @staticmethod
    def config(mount: BrowserMount) -> dict[str, object]:
        # @intent opencode-servers-are-prefixed-and-fail-closed
        # One prefixed, enabled server per mounted tool, its permission
        # rules in mount order, then the built-in web tools denied.
        servers: dict[str, object] = {}
        permission: dict[str, str] = {}
        for server in mount.servers:
            name = browser_tools.BROWSER_OPENCODE_SERVER_PREFIX + server.selection.definition.tool.value
            servers[name] = OpencodeMounts._server(server)
            permission.update(OpencodeMounts._rules(name, server.selection))
        permission.update({tool: browser_tools.OPENCODE_PERMISSION_DENY for tool in browser_tools.OPENCODE_WEB_TOOLS})
        return {browser_tools.OPENCODE_CONFIG_MCP_FIELD: servers, browser_tools.OPENCODE_CONFIG_PERMISSION_FIELD: permission}

    @staticmethod
    def env_remove(mount: BrowserMount) -> tuple[str, ...]:
        # The key variable of each mounted tool the caller passed no key
        # for, so its server never reads one from the caller's own
        # environment.
        selections = [server.selection for server in mount.servers]
        return tuple(selection.definition.key_variable.value for selection in selections if selection.definition.key_variable is not None and selection.key is None)

    @staticmethod
    def _server(server: BrowserServer) -> dict[str, object]:
        # @intent opencode-key-travels-only-in-the-server-entry
        # A remote entry is its URL, with the key as a Bearer header
        # when one was passed; a local entry is the node command with
        # the server's non-secret environment and the key variable.
        # The key reaches opencode only here, inside
        # OPENCODE_CONFIG_CONTENT, never on argv or in a file (INV-4).
        selection = server.selection
        definition = selection.definition
        if definition.transport is BrowserToolTransport.REMOTE:
            entry: dict[str, object] = {
                browser_tools.OPENCODE_MCP_TYPE_FIELD: browser_tools.OPENCODE_MCP_REMOTE_TYPE,
                browser_tools.OPENCODE_MCP_URL_FIELD: definition.url,
                browser_tools.OPENCODE_MCP_OAUTH_FIELD: False,
                browser_tools.OPENCODE_MCP_ENABLED_FIELD: True,
            }
            if selection.key is not None:
                entry[browser_tools.OPENCODE_MCP_HEADERS_FIELD] = {browser_tools.BROWSER_AUTHORIZATION_HEADER: browser_tools.BROWSER_BEARER_TEMPLATE.format(value=selection.key)}
            return entry
        environment = dict(definition.environment)
        if selection.key is not None and definition.key_variable is not None:
            environment[definition.key_variable.value] = selection.key
        return {
            browser_tools.OPENCODE_MCP_TYPE_FIELD: browser_tools.OPENCODE_MCP_LOCAL_TYPE,
            browser_tools.OPENCODE_MCP_COMMAND_FIELD: list(server.command),
            browser_tools.OPENCODE_MCP_ENVIRONMENT_FIELD: environment,
            browser_tools.OPENCODE_MCP_ENABLED_FIELD: True,
        }

    @staticmethod
    def _rules(name: str, selection: BrowserToolSelection) -> dict[str, str]:
        # @intent opencode-rules-deny-the-server-before-exact-allows
        # A whole server is allowed by one wildcard; a narrowed server
        # is denied by the wildcard first, then each allowed tool is
        # allowed by its exact name, because the last match wins; a
        # tool the caller did not name stays denied (spec AC-6).
        wildcard = browser_tools.OPENCODE_PERMISSION_RULE.format(server=name, tool=browser_tools.OPENCODE_PERMISSION_WILDCARD)
        if not selection.denied:
            return {wildcard: browser_tools.OPENCODE_PERMISSION_ALLOW}
        rules = {wildcard: browser_tools.OPENCODE_PERMISSION_DENY}
        rules.update({browser_tools.OPENCODE_PERMISSION_RULE.format(server=name, tool=tool): browser_tools.OPENCODE_PERMISSION_ALLOW for tool in selection.allowed})
        return rules


__all__ = ["OpencodeMounts"]
