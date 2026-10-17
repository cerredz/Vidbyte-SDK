"""FILE: vidbyte/harnesses/native/muse/mounts.py

PURPOSE: Defines MuseMounts, the compile helpers that turn one call's BrowserMount into the `muse/settings.json` text Muse Code reads from its private config folder, and that refuse, before any I/O, what Muse cannot carry safely: a keyed tool, a narrowed tool, and a stdio tool in WSL mode.
ROLE IN CODEBASE: MuseBrowserHarness.check (muse/browser.py) calls check with the call's WSL mode before any I/O; MuseThreadRun.execute (muse/threads.py) passes settings to _prepare_config, which writes it into the per-call config folder.
ARCHITECTURE NOTE: Pure helpers: no process, no file and no await, and nothing imported from this subpackage, so threads and browser import this module one way (spec D-27). The settings top level is exactly {"schema_version": 1, "mcpServers": {...}}: without schema_version Muse exits 1, and a malformed entry silently disables every server, so only the verified shapes are compiled: a stdio entry with a string command, a separate args list and a string-valued env, and a remote entry with the streamable_http transport and no env (vendor facts section 1, AC-26). Muse passes no environment to its servers and cannot filter a server's tools, so a key could only be a literal in the file and a narrowing could not be enforced: both are refused (D-9). In WSL mode the distro has no Node, so only keyless remote tools mount. Every member name and text comes from vidbyte/lib/constants/browser_tools.py (spec INV-15).
FUNCTION INVENTORY: check refuses keyed tools, narrowed tools and stdio tools in WSL mode; settings builds the settings text; _server builds one mcpServers entry.
COMMON MODIFICATION PATTERNS: A new settings member is one constant name and one key in settings or _server, after it is verified against the vendor; a new refusal is one more branch in check with its own observation text.
WHAT NOT TO DO IN THIS FILE: 1. Do not write a key into the settings; Muse would read it as a literal from a file. 2. Do not add env to a remote entry or another transport value; either silently disables every server (EC-39). 3. Do not compile a narrowed tool; Muse would expose every tool of the server.
KNOWN EDGE CASES: Every configured server is required, so one that fails to start fails the whole run with Muse's own reason (EC-18), which muse/browser.py turns into browser.tools_unavailable. Muse normalizes a dash in a server name to an underscore, which no BrowserTool value contains. The WSL refusal names the keyless remote tools from the registry, so it stays true when a row changes.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_mounts.py
"""

from __future__ import annotations

import json

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import browser_tools
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserMount,
    BrowserServer,
    BrowserToolSelection,
)
from vidbyte.lib.dataclasses.native_threads import NativeThreadRequest
from vidbyte.lib.enums.browser_tools import (
    BrowserKeyRequirement,
    BrowserTool,
    BrowserToolTransport,
)
from vidbyte.lib.enums.native_threads import NativeThreadProblem
from vidbyte.lib.registries.browser_tools import BrowserToolRegistry


class MuseMounts:
    """Compiles one call's browser mount into Muse's settings text, and refuses what Muse cannot carry."""

    @staticmethod
    def check(selections: tuple[BrowserToolSelection, ...], request: NativeThreadRequest, errors: NativeErrorFactory, *, wsl_mode: bool) -> None:
        # @intent muse-mounts-only-keyless-whole-servers
        # A key could only be written into the settings file, a narrowed
        # server would expose every tool, and in WSL mode the distro has
        # no Node for a stdio server: each is refused before any I/O,
        # naming what Muse can mount instead.
        remote = errors.listing(tool.value for tool in BrowserTool if BrowserToolRegistry.definition(tool).transport is BrowserToolTransport.REMOTE and BrowserToolRegistry.definition(tool).key_rule is not BrowserKeyRequirement.REQUIRED)
        for selection in selections:
            definition = selection.definition
            tool = definition.tool.value
            if selection.key is not None:
                detail = browser_tools.BROWSER_MUSE_KEYED_DETAIL.format(tool=tool)
            elif selection.denied:
                detail = browser_tools.BROWSER_MUSE_NARROWED_DETAIL.format(tool=tool)
            elif wsl_mode and definition.transport is BrowserToolTransport.STDIO:
                detail = browser_tools.BROWSER_MUSE_WSL_DETAIL.format(remote=remote, tool=tool)
            else:
                continue
            raise errors.failure(NativeThreadProblem.MOUNT_UNSUPPORTED, request=request, searched=detail)

    @staticmethod
    def settings(mount: BrowserMount) -> str:
        # @intent muse-settings-have-the-one-verified-shape
        # Exactly the schema version and the servers by tool name; any
        # other top-level shape makes Muse exit or drop every server.
        servers = {server.selection.definition.tool.value: MuseMounts._server(server) for server in mount.servers}
        return json.dumps({browser_tools.MUSE_SETTINGS_VERSION_FIELD: browser_tools.MUSE_SETTINGS_SCHEMA_VERSION, browser_tools.MUSE_SETTINGS_SERVERS_FIELD: servers})

    @staticmethod
    def _server(server: BrowserServer) -> dict[str, object]:
        # A remote entry is the streamable HTTP transport and its URL,
        # never env; a stdio entry is node as one string, the entry and
        # arguments as a list, and the non-secret environment.
        definition = server.selection.definition
        if definition.transport is BrowserToolTransport.REMOTE:
            return {browser_tools.MUSE_SERVER_TRANSPORT_FIELD: browser_tools.MUSE_STREAMABLE_HTTP_TRANSPORT, browser_tools.MUSE_SERVER_URL_FIELD: definition.url}
        program, *arguments = server.command
        return {browser_tools.MUSE_SERVER_COMMAND_FIELD: program, browser_tools.MUSE_SERVER_ARGS_FIELD: arguments, browser_tools.MUSE_SERVER_ENV_FIELD: dict(definition.environment)}


__all__ = ["MuseMounts"]
