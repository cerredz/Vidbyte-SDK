"""FILE: vidbyte/harnesses/native/claude/options.py

PURPOSE: Translates a validated ClaudeSpawnRequest into the claude-agent-sdk ClaudeAgentOptions for one turn, and into the prompt that turn sends.
ROLE IN CODEBASE: Called by ClaudeLiveSession (session.py) when it connects a turn. The host supplies the effective CLI path, the session id chosen by its natural-key rules, the in-process tool server built by tool_server.py and that server's auto-allowed tool names.
ARCHITECTURE NOTE: One static helper per option surface returns its fragment, and to_options merges the fragments and builds the options class it is handed, so this module never imports claude_agent_sdk. Fields left at their defaults are omitted, so the SDK's own defaults apply. Everything that reaches the claude command line through extra_args or env is exact text, or None for a bare flag.
COMMON MODIFICATION PATTERNS: A new request field adds one line to the helper for its surface. A new CLI flag adds a ClaudeCliFlag member and one entry in extra_args.
KNOWN EDGE CASES: The system prompt is always sent, because the SDK turns an unset one into an empty system prompt that drops Claude Code's own. permission_prompts NONE, the default, adds --permission-prompts none so a headless turn never waits on a prompt nobody answers. timeout_seconds maps to nothing here, because the session's watchdog enforces it. A worktree of "" lets Claude Code name the worktree itself.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from vidbyte.lib.constants.claude import (
    CLAUDE_MAX_OUTPUT_TOKENS_ENV,
    CLAUDE_PLUGIN_URL_MARKER,
    CLAUDE_SYSTEM_PROMPT_PRESET,
    CLAUDE_TOOL_SERVER_NAME,
)
from vidbyte.lib.dataclasses.claude import ClaudeImage, ClaudeSpawnRequest
from vidbyte.lib.dataclasses.claude_host import ClaudeSdkTypes
from vidbyte.lib.enums.claude import (
    ClaudeCliFlag,
    ClaudeMcpTransport,
    ClaudePermissionPrompts,
    ClaudeSystemPromptMode,
)


async def _image_prompt(text: str, images: tuple[ClaudeImage, ...]) -> AsyncIterator[dict[str, Any]]:
    """Yield the one user message that carries the prompt text and its images as content blocks."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    blocks.extend({"type": "image", "source": {"type": "base64", "media_type": image.media_type.value, "data": image.data}} for image in images)
    yield {"type": "user", "message": {"role": "user", "content": blocks}}


class ClaudeOptionsTranslator:
    """Builds the SDK options and the prompt of one Claude Code turn from a ClaudeSpawnRequest."""

    @staticmethod
    def to_options(request: ClaudeSpawnRequest, *, cli_path: str, session_id: str, tool_server: object | None, auto_allowed: tuple[str, ...], sdk: ClaudeSdkTypes) -> object:
        """Return the SDK's ClaudeAgentOptions for one turn of the request, leaving every unset field at the SDK's default."""
        # @intent options-carry-only-what-the-request-set
        # Each request field lands only on the option, CLI flag or
        # environment variable its mapping names, and unset fields are
        # left out; a stray option would change how Claude Code behaves
        # without the caller asking.
        #
        # Start with the model, the system prompt and the tools Claude
        # Code may use without asking.
        options = ClaudeOptionsTranslator.model_options(request)
        options.update(ClaudeOptionsTranslator.instruction_options(request))
        options.update(ClaudeOptionsTranslator.permission_options(request, auto_allowed))
        # Add the hooks, the MCP servers (the request's own tools ride
        # on the vidbyte one), skills, plugins and subagents.
        options.update(ClaudeOptionsTranslator.extension_options(request, tool_server, sdk))
        # Add which settings load, the sandbox, and the turn and dollar
        # budgets.
        options.update(ClaudeOptionsTranslator.config_options(request))
        options.update(ClaudeOptionsTranslator.budget_options(request))
        # Name the session to start, resume or fork, and say what the
        # output must look like.
        options.update(ClaudeOptionsTranslator.session_options(request, session_id))
        options.update(ClaudeOptionsTranslator.output_options(request))
        # Say which CLI to start, where and as whom, plus the flags and
        # environment the SDK has no option for.
        options.update(ClaudeOptionsTranslator.process_options(request, cli_path))
        options["extra_args"] = ClaudeOptionsTranslator.extra_args(request)
        options["env"] = ClaudeOptionsTranslator.child_env(request)
        return sdk.options_class(**options)

    @staticmethod
    def to_prompt(request: ClaudeSpawnRequest) -> str | AsyncIterable[dict[str, Any]]:
        """Return the prompt as the SDK sends it: the text itself, or a stream of one user message when images come along."""
        # @intent images-travel-in-one-streamed-message
        # The SDK sends a str prompt as one text message, and only the
        # streamed form carries content blocks, so a prompt with images
        # becomes a stream of exactly one user message whose first block
        # is the text.
        if not request.images:
            return request.prompt
        return _image_prompt(request.prompt, request.images)

    @staticmethod
    def model_options(spawn: ClaudeSpawnRequest) -> dict[str, Any]:
        """Return the model, fallback models, effort, thinking and beta options."""
        # @intent fallback-models-travel-comma-joined
        # The SDK takes one fallback_model string, so several fallbacks
        # are joined with commas for Claude Code to split; any other
        # join would turn the whole list into one unknown model name.
        options: dict[str, Any] = {}
        if spawn.model:
            options["model"] = spawn.model
        if spawn.fallback_model:
            options["fallback_model"] = ",".join(spawn.fallback_model)
        if spawn.effort.value:
            options["effort"] = spawn.effort.value
        thinking = spawn.thinking
        if thinking is not None:
            options["thinking"] = {"type": thinking.mode.value}
            if thinking.budget_tokens is not None:
                options["thinking"]["budget_tokens"] = thinking.budget_tokens
            if thinking.display.value:
                options["thinking"]["display"] = thinking.display.value
        if spawn.betas:
            options["betas"] = [beta.value for beta in spawn.betas]
        return options

    @staticmethod
    def instruction_options(spawn: ClaudeSpawnRequest) -> dict[str, Any]:
        """Return the system prompt in the SDK's preset, custom or file form."""
        prompt = spawn.system_prompt
        if prompt.mode is ClaudeSystemPromptMode.FILE:
            return {"system_prompt": {"type": "file", "path": prompt.text}}
        if prompt.mode is ClaudeSystemPromptMode.REPLACE:
            system: dict[str, Any] = {"type": "custom", "prompt": prompt.text}
        else:
            system = {"type": "preset", "preset": CLAUDE_SYSTEM_PROMPT_PRESET}
            if prompt.text:
                system["append"] = prompt.text
        if spawn.exclude_dynamic_system_prompt_sections:
            system["exclude_dynamic_sections"] = True
        if spawn.system_prompt_snapshot is not None:
            system["snapshot"] = spawn.system_prompt_snapshot
        return {"system_prompt": system}

    @staticmethod
    def permission_options(spawn: ClaudeSpawnRequest, auto_allowed: tuple[str, ...]) -> dict[str, Any]:
        """Return the built-in tool set, the allowed and disallowed tools, the permission mode and the host's prompt callback."""
        # @intent prompts-reach-a-callback-only-under-host
        # A can_use_tool callback makes the SDK route permission prompts
        # to it, so it is passed only with permission_prompts HOST;
        # otherwise the --permission-prompts none flag makes Claude Code
        # deny them itself.
        options: dict[str, Any] = {}
        if spawn.builtin_tools is not None:
            options["tools"] = list(spawn.builtin_tools)
        allowed = [*spawn.allowed_tools, *auto_allowed]
        if allowed:
            options["allowed_tools"] = allowed
        if spawn.disallowed_tools:
            options["disallowed_tools"] = list(spawn.disallowed_tools)
        if spawn.permission_mode.value:
            options["permission_mode"] = spawn.permission_mode.value
        if spawn.can_use_tool is not None:
            options["can_use_tool"] = spawn.can_use_tool
        return options

    @staticmethod
    def extension_options(spawn: ClaudeSpawnRequest, tool_server: object | None, sdk: ClaudeSdkTypes) -> dict[str, Any]:
        """Return the hooks, MCP servers, skills, local plugins and subagents the request adds to Claude Code."""
        # @intent request-tools-ride-the-vidbyte-mcp-server
        # The request's own tools reach Claude through the one
        # in-process server named vidbyte, beside the external servers;
        # another name would break the mcp__vidbyte__ tool names that
        # allowed_tools carries.
        hooks: dict[str, list[object]] = {}
        for hook in spawn.hooks:
            hooks.setdefault(hook.event.value, []).append(sdk.hook_matcher_class(matcher=hook.matcher or None, hooks=list(hook.callbacks), timeout=hook.timeout_seconds))
        servers: dict[str, object] = {
            server.name: {"type": server.transport.value, "command": server.command, "args": list(server.args), "env": dict(server.env)}
            if server.transport is ClaudeMcpTransport.STDIO
            else {"type": server.transport.value, "url": server.url, "headers": dict(server.headers)}
            for server in spawn.mcp_servers
        }
        if tool_server is not None:
            servers[CLAUDE_TOOL_SERVER_NAME] = tool_server
        agents = {
            agent.name: sdk.agent_definition_class(
                description=agent.description,
                prompt=agent.prompt,
                tools=None if agent.tools is None else list(agent.tools),
                disallowedTools=list(agent.disallowed_tools) or None,
                model=agent.model or None,
                skills=None if agent.skills is None else list(agent.skills),
                memory=None if agent.memory is None else agent.memory.value,
                mcpServers=list(agent.mcp_servers) or None,
                initialPrompt=agent.initial_prompt or None,
                maxTurns=agent.max_turns,
                background=agent.background,
                effort=agent.effort.value or None,
                permissionMode=agent.permission_mode.value or None,
            )
            for agent in spawn.agents
        }
        local_plugins = [{"type": "local", "path": plugin} for plugin in spawn.plugins if CLAUDE_PLUGIN_URL_MARKER not in plugin]
        named: dict[str, Any] = {"hooks": hooks, "mcp_servers": servers, "agents": agents, "plugins": local_plugins}
        options = {name: value for name, value in named.items() if value}
        if spawn.strict_mcp_config:
            options["strict_mcp_config"] = True
        if spawn.skills is not None:
            options["skills"] = list(spawn.skills)
        return options

    @staticmethod
    def config_options(spawn: ClaudeSpawnRequest) -> dict[str, Any]:
        """Return which settings sources load, the settings path or JSON, and the bash sandbox."""
        options: dict[str, Any] = {}
        if spawn.setting_sources is not None:
            options["setting_sources"] = [source.value for source in spawn.setting_sources]
        if spawn.settings:
            options["settings"] = spawn.settings
        sandbox = spawn.sandbox
        if sandbox is not None:
            network = {key: list(domains) for key, domains in (("allowedDomains", sandbox.allowed_domains), ("deniedDomains", sandbox.denied_domains)) if domains}
            options["sandbox"] = {"enabled": sandbox.enabled}
            if sandbox.auto_allow_bash is not None:
                options["sandbox"]["autoAllowBashIfSandboxed"] = sandbox.auto_allow_bash
            if sandbox.excluded_commands:
                options["sandbox"]["excludedCommands"] = list(sandbox.excluded_commands)
            if network:
                options["sandbox"]["network"] = network
        return options

    @staticmethod
    def budget_options(spawn: ClaudeSpawnRequest) -> dict[str, Any]:
        """Return the turn, dollar and task-token budgets."""
        options: dict[str, Any] = {}
        if spawn.max_turns is not None:
            options["max_turns"] = spawn.max_turns
        if spawn.max_budget_usd is not None:
            options["max_budget_usd"] = spawn.max_budget_usd
        if spawn.task_budget is not None:
            options["task_budget"] = {"total": spawn.task_budget}
        return options

    @staticmethod
    def session_options(spawn: ClaudeSpawnRequest, session_id: str) -> dict[str, Any]:
        """Return the session to start, resume or fork, file checkpointing and the session store."""
        named = {
            "session_id": session_id,
            "resume": spawn.resume,
            "continue_conversation": spawn.continue_conversation,
            "fork_session": spawn.fork_session,
            "resume_session_at": spawn.resume_session_at,
            "resume_drops_turn": spawn.resume_drops_turn,
            "enable_file_checkpointing": spawn.enable_file_checkpointing,
        }
        options: dict[str, Any] = {name: value for name, value in named.items() if value}
        if spawn.session_store is not None:
            options["session_store"] = spawn.session_store
        if spawn.load_timeout_ms is not None:
            options["load_timeout_ms"] = spawn.load_timeout_ms
        return options

    @staticmethod
    def output_options(spawn: ClaudeSpawnRequest) -> dict[str, Any]:
        """Return the structured-output schema and the extra message kinds the stream should include."""
        named = {
            "include_partial_messages": spawn.include_partial_messages,
            "include_hook_events": spawn.include_hook_events,
            "forward_subagent_text": spawn.forward_subagent_text,
        }
        options: dict[str, Any] = {name: True for name, wanted in named.items() if wanted}
        if spawn.output_schema is not None:
            options["output_format"] = {"type": "json_schema", "schema": dict(spawn.output_schema)}
        return options

    @staticmethod
    def process_options(spawn: ClaudeSpawnRequest, cli_path: str) -> dict[str, Any]:
        """Return the CLI to start, its working folder, the extra folders it may read, and the user to run as."""
        options: dict[str, Any] = {"cli_path": cli_path}
        if spawn.cwd:
            options["cwd"] = spawn.cwd
        if spawn.add_dirs:
            options["add_dirs"] = list(spawn.add_dirs)
        if spawn.user:
            options["user"] = spawn.user
        return options

    @staticmethod
    def extra_args(spawn: ClaudeSpawnRequest) -> dict[str, str | None]:
        """Return the CLI flags the SDK has no option for, each a bare flag (None) or exact text."""
        # @intent cli-flags-carry-only-text
        # The SDK writes each entry as --flag [value] using str(), so a
        # value is None or exact text; an enum or an int would reach
        # Claude Code in a form it rejects. persist_session=False and
        # permission prompts NONE, the default, are the only settings
        # whose value adds a flag.
        bare_flags = (
            (ClaudeCliFlag.RESTRICTED, spawn.restricted),
            (ClaudeCliFlag.BARE, spawn.bare),
            (ClaudeCliFlag.SAFE_MODE, spawn.safe_mode),
            (ClaudeCliFlag.NO_SESSION_PERSISTENCE, not spawn.persist_session),
            (ClaudeCliFlag.WORKTREE, spawn.worktree == ""),
        )
        valued_flags = (
            (ClaudeCliFlag.FILE, spawn.files[0] if spawn.files else ""),
            (ClaudeCliFlag.PLUGIN_URL, next((plugin for plugin in spawn.plugins if CLAUDE_PLUGIN_URL_MARKER in plugin), "")),
            (ClaudeCliFlag.AGENT, spawn.main_agent),
            (ClaudeCliFlag.AUTOCOMPACT, "" if spawn.autocompact is None else str(spawn.autocompact)),
            (ClaudeCliFlag.NAME, spawn.name),
            (ClaudeCliFlag.WORKTREE, spawn.worktree or ""),
            (ClaudeCliFlag.PERMISSION_PROMPTS, spawn.permission_prompts.value if spawn.permission_prompts is ClaudePermissionPrompts.NONE else ""),
        )
        flags: dict[str, str | None] = {flag.value: None for flag, wanted in bare_flags if wanted}
        flags.update({flag.value: text for flag, text in valued_flags if text})
        return flags

    @staticmethod
    def child_env(spawn: ClaudeSpawnRequest) -> dict[str, str]:
        """Return the environment added to Claude Code's process, including the output cap when one is set."""
        env = dict(spawn.env)
        if spawn.max_output_tokens is not None:
            env[CLAUDE_MAX_OUTPUT_TOKENS_ENV] = str(spawn.max_output_tokens)
        return env


__all__ = ["ClaudeOptionsTranslator"]
