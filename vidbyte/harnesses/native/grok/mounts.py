"""FILE: vidbyte/harnesses/native/grok/mounts.py

PURPOSE: Defines GrokMounts, the compile helpers that turn one call's BrowserMount into what Grok Build reads: the per-call agent file whose frontmatter lists the servers, the repeated --allow and --deny rules, --disable-web-search, and the environment the servers inherit; and that refuse, before any I/O, what Grok cannot carry safely.
ROLE IN CODEBASE: GrokBrowserHarness (grok/browser.py) calls check before any I/O and writes agent_text to agent_path through NativeBrowserTools.write_file; GrokThreadRun.execute (grok/threads.py) adds options before --single, environment to the overlay and env_remove to the CliInvocation.
ARCHITECTURE NOTE: Pure helpers: no process, no file and no await, and nothing imported from this subpackage, so threads and browser import this module one way (spec D-27). The agent file is one JSON object between two fences, which Grok reads as YAML flow style, with mcpServers in its sequence form: a stdio entry is node with the absolute entry and its arguments plus the non-secret environment as name/value pairs, a keyless remote entry is its name and URL (D-7, Q-18). Keys never go into the file: a stdio tool's key travels in Grok's environment, which agent-file servers inherit, and a keyed remote tool is refused because agent-file headers do not expand variables (D-9). Narrowing fails closed: an exact allow per allowed tool and an exact deny per other known tool, never a wildcard allow (D-10). Every member name, rule and text comes from vidbyte/lib/constants/browser_tools.py or native_threads.py (spec INV-15).
FUNCTION INVENTORY: check refuses keyed remote tools and rules past the command-line budget; agent_path names the agent file in the per-call folder; agent_text builds the file; options builds the argv options; environment builds the overlay; env_remove names the unpassed key variables; _server builds one mcpServers entry; _rules builds the allow and deny options.
COMMON MODIFICATION PATTERNS: A new Grok mount option is one GrokFlag member and one CliOption in options; a new agent-file member is one constant name and one key in _server or agent_text.
WHAT NOT TO DO IN THIS FILE: 1. Do not write a key into the agent file, not even as a header. 2. Do not add a wildcard allow for a narrowed server; a tool the registry does not list must stay unruled, so a headless run cancels instead of using it. 3. Do not name a tool or say that tools are mounted in the agent body; it becomes the thread's system prompt (D-18).
KNOWN EDGE CASES: The budget is checked before the per-call folder exists, so the agent path is estimated with a folder name of the real length in the temp folder (spec NFR-6). A tool the registry does not list has neither rule, so headless Grok cancels the turn when the agent calls it (EC-41). Every stdio server inherits Grok's whole environment, every key of the call included (T-6, accepted).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_mounts.py
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import browser_tools, native_threads
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserMount,
    BrowserServer,
    BrowserToolSelection,
)
from vidbyte.lib.dataclasses.native_threads import NativeThreadRequest
from vidbyte.lib.dataclasses.process import CliOption
from vidbyte.lib.enums.browser_tools import BrowserToolTransport
from vidbyte.lib.enums.native_threads import (
    GrokFlag,
    NativeEnvironmentVariable,
    NativeThreadProblem,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.process import CliArgv


class GrokMounts:
    """Compiles one call's browser mount into Grok's agent file, argv rules and environment, and refuses what Grok cannot carry."""

    @staticmethod
    def check(selections: tuple[BrowserToolSelection, ...], request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        # @intent grok-never-writes-a-key-into-the-agent-file
        # Agent-file headers do not expand variables, so a keyed remote
        # tool would need its key written into the file; it is refused.
        for selection in selections:
            definition = selection.definition
            if definition.transport is BrowserToolTransport.REMOTE and selection.key is not None:
                detail = browser_tools.BROWSER_GROK_KEYED_REMOTE_DETAIL.format(tool=definition.tool.value)
                raise errors.failure(NativeThreadProblem.MOUNT_UNSUPPORTED, request=request, searched=detail)

        # @intent grok-rules-fit-the-windows-command-line
        # The agent option, the rules and the web switch must fit their
        # share of the command line, counted the way Windows quotes and
        # counts it, so that a long prompt still fits beside them; the
        # folder does not exist yet, so its path is estimated.
        agent = Path(tempfile.gettempdir(), browser_tools.BROWSER_CALL_FOLDER_ESTIMATE, browser_tools.GROK_BROWSER_AGENT_FILE)
        options = (CliOption(GrokFlag.AGENT, str(agent)), *GrokMounts._rules(selections), CliOption(GrokFlag.DISABLE_WEB_SEARCH))
        line = subprocess.list2cmdline(CliArgv.build((), options=options, style=CliOptionStyle.JOINED))
        units = len(line.encode(native_threads.NATIVE_WINDOWS_COMMAND_LINE_ENCODING)) // native_threads.NATIVE_UTF16_UNIT_BYTES
        if units > browser_tools.GROK_BROWSER_RULES_MAX_UNITS:
            detail = browser_tools.BROWSER_GROK_BUDGET_DETAIL.format(units=units, limit=browser_tools.GROK_BROWSER_RULES_MAX_UNITS)
            raise errors.failure(NativeThreadProblem.MOUNT_UNSUPPORTED, request=request, searched=detail)

    @staticmethod
    def agent_path(mount: BrowserMount) -> Path:
        # The agent file lives in the per-call folder, so it goes with
        # the folder and never touches the workspace or the Grok home.
        return mount.folder / browser_tools.GROK_BROWSER_AGENT_FILE

    @staticmethod
    def agent_text(mount: BrowserMount) -> str:
        # @intent grok-agent-file-is-json-frontmatter-and-a-neutral-body
        # The frontmatter is one JSON object (valid YAML flow style, with
        # Windows paths escaped) naming the servers; the body is the
        # fixed neutral text that names no tool.
        front = {
            browser_tools.GROK_AGENT_NAME_FIELD: browser_tools.GROK_BROWSER_AGENT_NAME,
            browser_tools.GROK_AGENT_DESCRIPTION_FIELD: browser_tools.GROK_BROWSER_AGENT_DESCRIPTION,
            browser_tools.GROK_AGENT_SERVERS_FIELD: [GrokMounts._server(server) for server in mount.servers],
        }
        fence = browser_tools.GROK_BROWSER_AGENT_FENCE
        return native_threads.NATIVE_LINE_SEPARATOR.join((fence, json.dumps(front), fence, browser_tools.GROK_BROWSER_AGENT_BODY, ""))

    @staticmethod
    def options(mount: BrowserMount) -> tuple[CliOption, ...]:
        # The agent file, the allow and deny rules and the web switch,
        # which threads.py puts before --single.
        selections = tuple(server.selection for server in mount.servers)
        return (CliOption(GrokFlag.AGENT, str(GrokMounts.agent_path(mount))), *GrokMounts._rules(selections), CliOption(GrokFlag.DISABLE_WEB_SEARCH))

    @staticmethod
    def environment(mount: BrowserMount) -> dict[str, str]:
        # @intent grok-keys-travel-in-the-environment-servers-inherit
        # The Claude and Cursor compat scans are off, so no server from
        # another tool's config joins the run, and each passed key is
        # set under its tool's variable, which the servers inherit.
        overlay = {
            NativeEnvironmentVariable.GROK_CLAUDE_MCPS_ENABLED.value: native_threads.NATIVE_DISABLED_SWITCH,
            NativeEnvironmentVariable.GROK_CURSOR_MCPS_ENABLED.value: native_threads.NATIVE_DISABLED_SWITCH,
        }
        for server in mount.servers:
            selection = server.selection
            if selection.key is not None and selection.definition.key_variable is not None:
                overlay[selection.definition.key_variable.value] = selection.key
        return overlay

    @staticmethod
    def env_remove(mount: BrowserMount) -> tuple[str, ...]:
        # The key variable of each mounted tool the caller passed no key
        # for, so its server never reads one from the caller's own
        # environment.
        selections = [server.selection for server in mount.servers]
        return tuple(selection.definition.key_variable.value for selection in selections if selection.definition.key_variable is not None and selection.key is None)

    @staticmethod
    def _server(server: BrowserServer) -> dict[str, object]:
        # A keyless remote server is its name and URL; a stdio server is
        # node, the absolute entry and its arguments, and its non-secret
        # environment as name/value pairs.
        definition = server.selection.definition
        if definition.transport is BrowserToolTransport.REMOTE:
            return {browser_tools.GROK_AGENT_NAME_FIELD: definition.tool.value, browser_tools.GROK_AGENT_URL_FIELD: definition.url}
        program, *arguments = server.command
        pairs = [{browser_tools.GROK_AGENT_NAME_FIELD: name, browser_tools.GROK_AGENT_ENV_VALUE_FIELD: value} for name, value in definition.environment.items()]
        return {
            browser_tools.GROK_AGENT_NAME_FIELD: definition.tool.value,
            browser_tools.GROK_AGENT_COMMAND_FIELD: program,
            browser_tools.GROK_AGENT_ARGS_FIELD: arguments,
            browser_tools.GROK_AGENT_ENV_FIELD: pairs,
        }

    @staticmethod
    def _rules(selections: tuple[BrowserToolSelection, ...]) -> tuple[CliOption, ...]:
        # @intent grok-narrowing-fails-closed
        # A whole server is allowed by one wildcard; a narrowed server
        # gets an exact allow per allowed tool and an exact deny per
        # other known tool, and never a wildcard allow.
        rules: list[CliOption] = []
        for selection in selections:
            server = selection.definition.tool.value
            if not selection.denied:
                rules.append(CliOption(GrokFlag.ALLOW, browser_tools.GROK_MCP_TOOL_RULE.format(server=server, tool=browser_tools.GROK_MCP_TOOL_WILDCARD)))
                continue
            rules.extend(CliOption(GrokFlag.ALLOW, browser_tools.GROK_MCP_TOOL_RULE.format(server=server, tool=tool)) for tool in selection.allowed)
            rules.extend(CliOption(GrokFlag.DENY, browser_tools.GROK_MCP_TOOL_RULE.format(server=server, tool=tool)) for tool in selection.denied)
        return tuple(rules)


__all__ = ["GrokMounts"]
