"""Vidbyte-to-Codex and Codex-to-SDK translation boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexAgentTranslation,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexImageInput,
    CodexLocalImageInput,
    CodexMentionInput,
    CodexPrompt,
    CodexSdkTypes,
    CodexSkillInput,
    CodexSubagentSettings,
    CodexTextInput,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.providers.output_schema import OutputSchemaFormatter


class CodexSettingsValidator:
    """Validates provider compatibility that spans settings records."""

    @staticmethod
    def validate(settings: CodexAgentSettings) -> None:
        # @intent reject-conflicting-cwd-sources
        # Different cwd values at client/thread/turn layers are legal in Codex,
        # but make a reusable adapter's repository boundary ambiguous.
        values = {
            value
            for value in (settings.client.cwd, settings.thread.cwd, settings.turn.cwd)
            if value
        }
        if len(values) > 1:
            raise ConfigurationError(
                "Codex client, thread, and turn cwd settings must agree when combined."
            )


class CodexVidbyteTranslator:
    """Translates Vidbyte abstractions before any Codex process starts."""

    def __init__(self) -> None:
        self._schemas = OutputSchemaFormatter()

    def translate_agent(
        self, settings: CodexHarnessAgentSettings
    ) -> CodexAgentTranslation:
        # @intent validate-shared-abstractions-at-construction
        # Resolve shared schemas once so invalid Vidbyte configuration cannot
        # launch Codex and every later turn uses one deterministic wire shape.
        CodexSettingsValidator.validate(settings.codex)
        translated = replace(
            settings,
            name=settings.name.strip(),
            system_prompt=self.system_prompt(settings.system_prompt),
            additional_context=self.additional_context(settings.additional_context),
            description=settings.description.strip(),
            capabilities=tuple(value.strip() for value in settings.capabilities),
            metadata=dict(settings.metadata),
            thread_id=settings.thread_id.strip(),
        )
        return CodexAgentTranslation(
            settings=translated,
            output_schema=self.output_schema(settings.output_schema),
        )

    def output_schema(
        self, schema: type | Mapping[str, Any] | None
    ) -> Mapping[str, Any]:
        if schema is None:
            return {}
        return self._schemas.annotate(self._schemas.resolve_schema(schema))

    @staticmethod
    def system_prompt(value: str) -> str:
        return value.strip()

    @staticmethod
    def additional_context(value: str) -> str:
        return value.strip()


class CodexContentTranslator:
    """Converts validated Codex records into openai-codex SDK arguments."""

    @classmethod
    def client_kwargs(cls, settings: CodexAgentSettings) -> dict[str, Any]:
        # @intent preserve-sdk-process-controls
        # Retain every CodexConfig control while omitting adapter sentinels.
        client = settings.client
        return cls._without_empty(
            {
                "codex_bin": client.codex_bin,
                "launch_args_override": client.launch_args_override or None,
                "config_overrides": client.config_overrides,
                "cwd": client.cwd,
                "env": dict(client.env) if client.env else None,
                "client_name": client.client_name,
                "client_title": client.client_title,
                "client_version": client.client_version,
                "experimental_api": client.experimental_api,
            }
        )

    @classmethod
    def thread_start_kwargs(
        cls, system_prompt: str, settings: CodexAgentSettings, sdk: CodexSdkTypes
    ) -> dict[str, Any]:
        values = cls._thread_common(system_prompt, settings, sdk)
        thread = settings.thread
        values.update(
            cls._without_empty(
                {
                    "ephemeral": thread.ephemeral,
                    "personality": cls._enum(thread.personality, sdk.personality),
                    "service_name": thread.service_name,
                    "session_start_source": cls._enum(
                        thread.session_start_source, sdk.thread_start_source
                    ),
                }
            )
        )
        return values

    @classmethod
    def thread_resume_kwargs(
        cls, system_prompt: str, settings: CodexAgentSettings, sdk: CodexSdkTypes
    ) -> dict[str, Any]:
        values = cls._thread_common(system_prompt, settings, sdk)
        values.pop("thread_source", None)
        values.update(
            cls._without_empty(
                {"personality": cls._enum(settings.thread.personality, sdk.personality)}
            )
        )
        return values

    @classmethod
    def thread_fork_kwargs(
        cls, system_prompt: str, settings: CodexAgentSettings, sdk: CodexSdkTypes
    ) -> dict[str, Any]:
        values = cls._thread_common(system_prompt, settings, sdk)
        values["ephemeral"] = settings.thread.ephemeral
        return values

    @classmethod
    def turn_kwargs(
        cls,
        settings: CodexAgentSettings,
        output_schema: Mapping[str, Any],
        sdk: CodexSdkTypes,
    ) -> dict[str, Any]:
        turn = settings.turn
        return cls._without_empty(
            {
                "approval_mode": cls._enum(turn.approval_mode, sdk.approval_mode),
                "cwd": turn.cwd,
                "effort": cls._enum(turn.effort, sdk.reasoning_effort),
                "model": turn.model,
                "output_schema": dict(output_schema) if output_schema else None,
                "personality": cls._enum(turn.personality, sdk.personality),
                "sandbox": cls._enum(turn.sandbox, sdk.sandbox),
                "service_tier": turn.service_tier,
                "summary": sdk.reasoning_summary.model_validate(turn.summary.value)
                if turn.summary.value
                else None,
            }
        )

    @classmethod
    def run_input(cls, prompt: CodexPrompt, sdk: CodexSdkTypes) -> object:
        # @intent retain-native-codex-input-modalities
        # Map each local input record to the matching SDK RunInput dataclass;
        # context may add text without flattening image, skill, or mention input.
        translated: list[object] = []
        for item in prompt.items:
            if isinstance(item, CodexTextInput):
                translated.append(sdk.text_input(item.text))
            elif isinstance(item, CodexImageInput):
                translated.append(sdk.image_input(item.url))
            elif isinstance(item, CodexLocalImageInput):
                translated.append(sdk.local_image_input(item.path))
            elif isinstance(item, CodexSkillInput):
                translated.append(sdk.skill_input(item.name, item.path))
            elif isinstance(item, CodexMentionInput):
                translated.append(sdk.mention_input(item.name, item.path))
        return translated[0] if len(translated) == 1 else translated

    @classmethod
    def _thread_common(
        cls, system_prompt: str, settings: CodexAgentSettings, sdk: CodexSdkTypes
    ) -> dict[str, Any]:
        # @intent lifecycle-specific-sdk-fields
        # Build only shared thread fields so unsupported operation-specific keys
        # cannot leak into resume or fork requests.
        thread = settings.thread
        config = dict(thread.config)
        config["agents"] = cls._subagent_config(settings.subagents)
        return cls._without_empty(
            {
                "approval_mode": cls._enum(thread.approval_mode, sdk.approval_mode),
                "base_instructions": thread.base_instructions,
                "config": config,
                "cwd": thread.cwd,
                "developer_instructions": system_prompt,
                "model": thread.model,
                "model_provider": thread.model_provider,
                "sandbox": cls._enum(thread.sandbox, sdk.sandbox),
                "service_tier": thread.service_tier,
                "thread_source": cls._enum(thread.thread_source, sdk.thread_source),
            }
        )

    @staticmethod
    def _subagent_config(settings: CodexSubagentSettings) -> dict[str, Any]:
        values: dict[str, Any] = {
            "enabled": settings.enabled,
            "interrupt_message": settings.interrupt_message,
        }
        if settings.max_concurrent_threads:
            values["max_concurrent_threads_per_session"] = (
                settings.max_concurrent_threads
            )
        if settings.default_model:
            values["default_subagent_model"] = settings.default_model
        if settings.default_reasoning_effort.value:
            values["default_subagent_reasoning_effort"] = (
                settings.default_reasoning_effort.value
            )
        values.update({name: dict(role) for name, role in settings.roles.items()})
        return values

    @staticmethod
    def _enum(value: object, sdk_type: type) -> object | None:
        raw = getattr(value, "value", value)
        return sdk_type(raw) if raw else None

    @staticmethod
    def _without_empty(values: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in values.items()
            if value is not None and value != ""
        }


CodexConfigurationTranslator = CodexContentTranslator

__all__ = [
    "CodexAgentSettings",
    "CodexConfigurationTranslator",
    "CodexContentTranslator",
    "CodexForkSettings",
    "CodexSettingsValidator",
    "CodexSubagentSettings",
    "CodexVidbyteTranslator",
]
