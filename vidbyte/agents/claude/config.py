"""FILE: vidbyte/agents/claude/config.py

PURPOSE: Owns Vidbyte-to-Claude and Claude-to-SDK translation as two separate boundaries.
ROLE IN CODEBASE: agent.py translates once at construction; transport.py serializes per turn.
ARCHITECTURE NOTE: Only ClaudeContentTranslator names claude-agent-sdk argument keys.
COMMON MODIFICATION PATTERNS: Add a validated record field, then emit it from option_kwargs.
KNOWN EDGE CASES: Pydantic emits draft 2020-12; the provider validator requires draft-07.
RELATED DOCS: docs/design/claude-harness-agent.md; https://code.claude.com/docs/en/agent-sdk/python.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from vidbyte.lib.constants.claude import (
    CLAUDE_ALL_SKILLS,
    CLAUDE_CODE_PRESET_NAME,
    CLAUDE_FILE_TYPE,
    CLAUDE_JSON_SCHEMA_DRAFT,
    CLAUDE_OUTPUT_FORMAT_TYPE,
    CLAUDE_PRESET_TYPE,
    CLAUDE_SCHEMA_DRAFT_KEY,
)
from vidbyte.lib.dataclasses.claude import (
    ClaudeAgentSettings,
    ClaudeAgentTranslation,
    ClaudeHarnessAgentSettings,
    ClaudeModelSettings,
    ClaudeSubagentSettings,
    ClaudeSystemPromptSettings,
    ClaudeToolSettings,
)
from vidbyte.lib.enums.claude import ClaudeSystemPromptKind, ClaudeThinkingMode
from vidbyte.lib.errors import ConfigurationError
from vidbyte.providers.output_schema import OutputSchemaFormatter

# One system-prompt builder: the SDK accepts a bare string or a typed union member.
_PromptBuilder = Callable[[str, ClaudeSystemPromptSettings], "str | dict[str, Any]"]


class ClaudeSettingsValidator:
    """Validates provider compatibility that spans separate settings records."""

    @staticmethod
    def validate(settings: ClaudeAgentSettings, session_id: str) -> None:
        # @intent one-authoritative-session-identity
        # A caller-held session_id and a settings-level resume can name different
        # sessions, and the adapter must not silently prefer one over the other.
        resume = settings.session.resume
        if session_id and resume and session_id != resume:
            raise ConfigurationError(
                "Claude agent session_id and session.resume must agree when both are set."
            )
        if session_id and settings.session.continue_conversation:
            raise ConfigurationError(
                "Claude agent session_id cannot combine with session.continue_conversation."
            )


class ClaudeVidbyteTranslator:
    """Translates Vidbyte abstractions before any Claude subprocess starts."""

    def __init__(self) -> None:
        # Holds the shared schema formatter so every turn reuses one wire shape.
        self._schemas = OutputSchemaFormatter()

    def translate_agent(
        self, settings: ClaudeHarnessAgentSettings
    ) -> ClaudeAgentTranslation:
        # @intent validate-shared-abstractions-at-construction
        # Resolve shared schemas once so invalid Vidbyte configuration cannot launch
        # a CLI subprocess and every later turn uses one deterministic wire shape.
        ClaudeSettingsValidator.validate(settings.claude, settings.session_id.strip())
        translated = replace(
            settings,
            name=settings.name.strip(),
            system_prompt=self.system_prompt(settings.system_prompt),
            additional_context=self.additional_context(settings.additional_context),
            description=settings.description.strip(),
            capabilities=tuple(value.strip() for value in settings.capabilities),
            metadata=dict(settings.metadata),
            session_id=settings.session_id.strip(),
        )
        return ClaudeAgentTranslation(
            settings=translated,
            output_schema=self.output_schema(settings.output_schema),
        )

    def output_schema(
        self, schema: type | Mapping[str, Any] | None
    ) -> Mapping[str, Any]:
        # Resolves and annotates a Vidbyte schema, then pins it to the provider's draft.
        if schema is None:
            return {}
        resolved = self._schemas.annotate(self._schemas.resolve_schema(schema))
        return self.as_draft_07(resolved)

    @staticmethod
    def as_draft_07(schema: Mapping[str, Any]) -> dict[str, Any]:
        # @intent match-the-provider-validator-draft
        # The SDK validates against draft-07 and rejects a newer declared draft, but
        # Pydantic's model_json_schema emits 2020-12, so every model would fail.
        rewritten = dict(schema)
        rewritten[CLAUDE_SCHEMA_DRAFT_KEY] = CLAUDE_JSON_SCHEMA_DRAFT
        return rewritten

    @staticmethod
    def system_prompt(value: str) -> str:
        # Normalizes surrounding whitespace without altering interior prompt content.
        return value.strip()

    @staticmethod
    def additional_context(value: str) -> str:
        # Normalizes surrounding whitespace on the static context block.
        return value.strip()


class ClaudeContentTranslator:
    """Converts validated Claude records into claude-agent-sdk option arguments."""

    @classmethod
    def option_kwargs(
        cls,
        system_prompt: str,
        session_id: str,
        settings: ClaudeAgentSettings,
        output_schema: Mapping[str, Any],
    ) -> dict[str, Any]:
        # Assembles every ClaudeAgentOptions field the adapter owns for one turn.
        values: dict[str, Any] = {
            "system_prompt": cls.system_prompt_value(
                system_prompt, settings.system_prompt
            )
        }
        values.update(cls._session_kwargs(session_id, settings))
        values.update(cls._model_kwargs(settings.model))
        values.update(cls._loop_kwargs(settings))
        values.update(cls._tool_kwargs(settings))
        values.update(cls._process_kwargs(settings))
        values.update(cls._extension_kwargs(settings, output_schema))
        return cls._without_empty(values)

    @classmethod
    def system_prompt_value(
        cls, system_prompt: str, settings: ClaudeSystemPromptSettings
    ) -> str | dict[str, Any]:
        # Resolves the prompt into the SDK's string, preset, or file union member.
        builders: dict[ClaudeSystemPromptKind, _PromptBuilder] = {
            ClaudeSystemPromptKind.TEXT: cls._prompt_as_text,
            ClaudeSystemPromptKind.PRESET: cls._prompt_as_preset,
            ClaudeSystemPromptKind.FILE: cls._prompt_as_file,
        }
        return builders[settings.kind](system_prompt, settings)

    @classmethod
    def agent_definitions(
        cls, settings: ClaudeSubagentSettings
    ) -> dict[str, dict[str, Any]]:
        # @intent child-policy-must-survive-serialization
        # A dropped or snake_cased permission or tool key would silently widen a child
        # agent's authority, so each field is named in the provider's own casing.
        return {
            name: cls._without_empty(
                {
                    "description": role.description,
                    "prompt": role.prompt,
                    "tools": list(role.tools) or None,
                    "disallowedTools": list(role.disallowed_tools) or None,
                    "model": role.model,
                    "skills": list(role.skills) or None,
                    "maxTurns": role.max_turns or None,
                    "background": role.background or None,
                    "effort": cls._enum(role.effort),
                    "permissionMode": cls._enum(role.permission_mode),
                }
            )
            for name, role in settings.roles.items()
        }

    @classmethod
    def thinking_config(cls, settings: ClaudeModelSettings) -> dict[str, Any] | None:
        # @intent one-union-member-per-mode
        # The provider rejects a config mixing members, and a budget sent outside
        # ENABLED mode is silently ignored rather than refused.
        if settings.thinking_mode is ClaudeThinkingMode.PROVIDER_DEFAULT:
            return None
        values: dict[str, Any] = {"type": settings.thinking_mode.value}
        if settings.thinking_mode is ClaudeThinkingMode.ENABLED:
            values["budget_tokens"] = settings.thinking_budget_tokens
        display = cls._enum(settings.thinking_display)
        if display and settings.thinking_mode is not ClaudeThinkingMode.DISABLED:
            values["display"] = display
        return values

    @classmethod
    def output_format(cls, schema: Mapping[str, Any]) -> dict[str, Any] | None:
        # Wraps a resolved schema in the provider's structured-output envelope.
        if not schema:
            return None
        return {"type": CLAUDE_OUTPUT_FORMAT_TYPE, "schema": dict(schema)}

    @staticmethod
    def _prompt_as_text(
        system_prompt: str, settings: ClaudeSystemPromptSettings
    ) -> str:
        # Sends the Vidbyte prompt as the provider's whole system prompt.
        return system_prompt

    @staticmethod
    def _prompt_as_preset(
        system_prompt: str, settings: ClaudeSystemPromptSettings
    ) -> dict[str, Any]:
        # Appends the Vidbyte prompt to the provider's own Claude Code preset.
        values: dict[str, Any] = {
            "type": CLAUDE_PRESET_TYPE,
            "preset": CLAUDE_CODE_PRESET_NAME,
        }
        if settings.append_to_preset and system_prompt:
            values["append"] = system_prompt
        if settings.exclude_dynamic_sections:
            values["exclude_dynamic_sections"] = True
        return values

    @staticmethod
    def _prompt_as_file(
        system_prompt: str, settings: ClaudeSystemPromptSettings
    ) -> dict[str, Any]:
        # Points the provider at an explicitly trusted prompt file on disk.
        return {"type": CLAUDE_FILE_TYPE, "path": settings.path}

    @classmethod
    def _session_kwargs(
        cls, session_id: str, settings: ClaudeAgentSettings
    ) -> dict[str, Any]:
        # @intent adopted-identity-wins
        # The agent's live session_id is the identity the last successful run
        # confirmed; a settings-level resume only seeds the very first turn.
        session = settings.session
        adopted = bool(session_id)
        return {
            "resume": session_id or session.resume,
            # fork_session and continue_conversation only describe how the FIRST turn
            # finds its parent. Once the agent adopted its own id, resending them
            # would branch again from the child's own session on every later turn.
            "fork_session": (session.fork_session and not adopted) or None,
            "continue_conversation": (session.continue_conversation and not adopted)
            or None,
            "resume_session_at": "" if adopted else session.resume_session_at,
        }

    @classmethod
    def _model_kwargs(cls, settings: ClaudeModelSettings) -> dict[str, Any]:
        # @intent provider-fallback-is-not-vidbyte-fallback
        # fallback_model is switched inside Claude's loop, so it must stay distinct from
        # AgentFallbackSettings attempts or the same retry is counted twice.
        return {
            "model": settings.model,
            "fallback_model": settings.fallback_model,
            "effort": cls._enum(settings.effort),
            "betas": list(settings.betas) or None,
            "thinking": cls.thinking_config(settings),
        }

    @staticmethod
    def _loop_kwargs(settings: ClaudeAgentSettings) -> dict[str, Any]:
        # Emits the provider-enforced turn and dollar ceilings when a caller set them.
        loop = settings.loop
        return {
            "max_turns": loop.max_turns or None,
            "max_budget_usd": loop.max_budget_usd or None,
        }

    @classmethod
    def _tool_kwargs(cls, settings: ClaudeAgentSettings) -> dict[str, Any]:
        # @intent every-authority-field-in-one-place
        # Tool access, permission mode, and MCP reach are one policy decision; splitting
        # them across emitters is how a deny list gets dropped without anyone noticing.
        tools = settings.tools
        return {
            "tools": cls._tools_value(tools),
            "allowed_tools": list(tools.allowed_tools) or None,
            "disallowed_tools": list(tools.disallowed_tools) or None,
            "permission_mode": cls._enum(tools.permission_mode),
            "permission_prompt_tool_name": tools.permission_prompt_tool_name,
            "skills": cls._skills_value(tools),
            "mcp_servers": {
                name: dict(config) for name, config in tools.mcp_servers.items()
            }
            or None,
            "strict_mcp_config": tools.strict_mcp_config or None,
        }

    @staticmethod
    def _tools_value(tools: ClaudeToolSettings) -> list[str] | dict[str, Any] | None:
        # Prefers an explicit tool list, else the provider's own Claude Code preset.
        if tools.tools:
            return list(tools.tools)
        if tools.use_claude_code_preset:
            return {"type": CLAUDE_PRESET_TYPE, "preset": CLAUDE_CODE_PRESET_NAME}
        return None

    @staticmethod
    def _skills_value(tools: ClaudeToolSettings) -> list[str] | str | None:
        # Emits the provider's "all" sentinel or an explicit allowlist of skills.
        if tools.all_skills:
            return CLAUDE_ALL_SKILLS
        return list(tools.skills) or None

    @staticmethod
    def _process_kwargs(settings: ClaudeAgentSettings) -> dict[str, Any]:
        # @intent declare-configuration-loading-explicitly
        # Omitting setting_sources makes the provider load user, project, and local
        # settings, so a harness would silently inherit whatever is on disk.
        process = settings.process
        return {
            "cwd": process.cwd,
            "cli_path": process.cli_path,
            "settings": process.settings,
            "add_dirs": list(process.add_dirs) or None,
            "env": dict(process.env) or None,
            "extra_args": dict(process.extra_args) or None,
            "max_buffer_size": process.max_buffer_size or None,
            "load_timeout_ms": process.load_timeout_ms or None,
            "setting_sources": [source.value for source in process.setting_sources],
            "user": process.user,
        }

    @classmethod
    def _extension_kwargs(
        cls, settings: ClaudeAgentSettings, output_schema: Mapping[str, Any]
    ) -> dict[str, Any]:
        # Emits subagents, sandbox posture, plugins, and structured output.
        return {
            "agents": cls.agent_definitions(settings.subagents) or None,
            "sandbox": cls._sandbox_value(settings),
            "plugins": [{"path": plugin.path} for plugin in settings.plugins] or None,
            "output_format": cls.output_format(output_schema),
        }

    @staticmethod
    def _sandbox_value(settings: ClaudeAgentSettings) -> dict[str, Any] | None:
        # Emits sandbox configuration only when a caller explicitly enabled it.
        sandbox = settings.sandbox
        if not sandbox.enabled:
            return None
        values: dict[str, Any] = {
            "enabled": True,
            "allow_network": sandbox.allow_network,
        }
        if sandbox.allowed_domains:
            values["allowed_domains"] = list(sandbox.allowed_domains)
        return values

    @staticmethod
    def _enum(value: object) -> str | None:
        # Unwraps a provider enum, treating the PROVIDER_DEFAULT sentinel as unset.
        raw = getattr(value, "value", value)
        return str(raw) if raw else None

    @staticmethod
    def _without_empty(values: Mapping[str, Any]) -> dict[str, Any]:
        # @intent let-the-provider-own-its-defaults
        # An adapter sentinel sent as None or "" would override a provider default
        # with an explicit empty value, changing behavior the caller never asked for.
        return {
            key: value
            for key, value in values.items()
            if value is not None and value != ""
        }


__all__ = [
    "ClaudeContentTranslator",
    "ClaudeSettingsValidator",
    "ClaudeVidbyteTranslator",
]
