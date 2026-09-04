"""Typed configuration and config translation for Codex-backed agents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from vidbyte.context.manager import ContextManager
from vidbyte.lib.errors import ConfigurationError

_APPROVAL_MODES = frozenset({"auto_review", "deny_all"})
_PERSONALITIES = frozenset({"none", "friendly", "pragmatic"})
_REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})
_REASONING_SUMMARIES = frozenset({"none", "auto", "concise", "detailed"})
_SANDBOXES = frozenset({"read-only", "workspace-write", "full-access"})


class CodexSettingsValidator:
    """Validates provider settings before a Codex process is started."""

    @staticmethod
    def optional_text(field_name: str, value: str | None) -> None:
        # Rejects blank values while allowing the provider default through None.
        if value is not None and not value.strip():
            raise ConfigurationError(
                f"Codex {field_name} cannot be empty when provided."
            )

    @staticmethod
    def choice(field_name: str, value: str | None, choices: frozenset[str]) -> None:
        # Rejects values outside the stable SDK enum surface.
        CodexSettingsValidator.optional_text(field_name, value)
        if value is not None and value not in choices:
            allowed = ", ".join(sorted(choices))
            raise ConfigurationError(f"Codex {field_name} must be one of: {allowed}.")


@dataclass(frozen=True, slots=True)
class CodexSubagentSettings:
    """Configuration for Codex-owned subagent orchestration."""

    enabled: bool = True
    max_concurrent_threads: int | None = None
    default_model: str | None = None
    default_reasoning_effort: str | None = None
    interrupt_message: bool = True

    def __post_init__(self) -> None:
        # Ensures every subagent setting can be translated without coercion.
        if self.max_concurrent_threads is not None and self.max_concurrent_threads <= 0:
            raise ConfigurationError(
                "Codex subagent max_concurrent_threads must be greater than zero."
            )
        CodexSettingsValidator.optional_text(
            "subagent default_model", self.default_model
        )
        CodexSettingsValidator.choice(
            "subagent default_reasoning_effort",
            self.default_reasoning_effort,
            _REASONING_EFFORTS,
        )


@dataclass(frozen=True, slots=True)
class CodexAgentSettings:
    """Stable Codex thread and turn settings exposed by the Vidbyte agent."""

    model: str | None = None
    cwd: str | None = None
    sandbox: str | None = None
    approval_mode: str | None = None
    reasoning_effort: str | None = None
    personality: str | None = None
    summary: str | None = None
    service_tier: str | None = None
    ephemeral: bool = False
    subagents: CodexSubagentSettings = field(default_factory=CodexSubagentSettings)

    def __post_init__(self) -> None:
        # Validates text fields and values represented by Codex SDK enums.
        for field_name in ("model", "cwd", "service_tier"):
            CodexSettingsValidator.optional_text(field_name, getattr(self, field_name))
        CodexSettingsValidator.choice("sandbox", self.sandbox, _SANDBOXES)
        CodexSettingsValidator.choice(
            "approval_mode", self.approval_mode, _APPROVAL_MODES
        )
        CodexSettingsValidator.choice(
            "reasoning_effort", self.reasoning_effort, _REASONING_EFFORTS
        )
        CodexSettingsValidator.choice("personality", self.personality, _PERSONALITIES)
        CodexSettingsValidator.choice("summary", self.summary, _REASONING_SUMMARIES)


@dataclass(frozen=True, slots=True)
class CodexForkSettings:
    """Overrides applied to one provider-native Codex thread fork."""

    name: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    additional_context: str | None = None
    context_manager: ContextManager | None = None
    output_schema: type | Mapping[str, Any] | None = None
    ephemeral: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Rejects blank fork overrides before contacting the provider.
        for field_name in ("name", "system_prompt", "model", "additional_context"):
            CodexSettingsValidator.optional_text(
                f"fork {field_name}", getattr(self, field_name)
            )


class CodexConfigurationTranslator:
    """Builds wire-neutral SDK arguments from validated Codex settings."""

    @classmethod
    def thread_start_kwargs(cls, system_prompt: str, settings: CodexAgentSettings) -> dict[str, Any]:
        # Builds arguments accepted when starting a new Codex thread.
        kwargs = cls._thread_common_kwargs(system_prompt, settings)
        kwargs["ephemeral"] = settings.ephemeral
        if settings.personality is not None:
            kwargs["personality"] = settings.personality
        return kwargs

    @classmethod
    def thread_resume_kwargs(cls, system_prompt: str, settings: CodexAgentSettings) -> dict[str, Any]:
        # Builds arguments accepted when resuming an existing Codex thread.
        kwargs = cls._thread_common_kwargs(system_prompt, settings)
        if settings.personality is not None:
            kwargs["personality"] = settings.personality
        return kwargs

    @classmethod
    def thread_fork_kwargs(cls, system_prompt: str, settings: CodexAgentSettings, ephemeral: bool | None) -> dict[str, Any]:
        # Builds arguments accepted by the provider-native thread fork operation.
        kwargs = cls._thread_common_kwargs(system_prompt, settings)
        kwargs["ephemeral"] = settings.ephemeral if ephemeral is None else ephemeral
        return kwargs

    @classmethod
    def turn_kwargs(cls, settings: CodexAgentSettings, output_schema: Mapping[str, Any] | None) -> dict[str, Any]:
        # Builds per-turn overrides while omitting values delegated to Codex defaults.
        values: dict[str, Any] = {
            "effort": settings.reasoning_effort,
            "model": settings.model,
            "output_schema": dict(output_schema) if output_schema is not None else None,
            "personality": settings.personality,
            "sandbox": settings.sandbox,
            "service_tier": settings.service_tier,
            "summary": settings.summary,
        }
        return cls._without_none(values)

    @classmethod
    def with_fork_model(cls, settings: CodexAgentSettings, model: str | None, ephemeral: bool | None) -> CodexAgentSettings:
        # Produces immutable child settings from the parent and fork overrides.
        return replace(
            settings,
            model=settings.model if model is None else model,
            ephemeral=settings.ephemeral if ephemeral is None else ephemeral,
        )

    @classmethod
    def _thread_common_kwargs(cls, system_prompt: str, settings: CodexAgentSettings) -> dict[str, Any]:
        # Builds fields shared by start, resume, and fork calls.
        values: dict[str, Any] = {
            "approval_mode": settings.approval_mode,
            "config": {"agents": cls._subagent_config(settings.subagents)},
            "cwd": settings.cwd,
            "developer_instructions": system_prompt,
            "model": settings.model,
            "sandbox": settings.sandbox,
            "service_tier": settings.service_tier,
        }
        return cls._without_none(values)

    @staticmethod
    def _subagent_config(settings: CodexSubagentSettings) -> dict[str, Any]:
        # Maps Vidbyte settings to Codex's documented agents configuration keys.
        values: dict[str, Any] = {
            "enabled": settings.enabled,
            "max_concurrent_threads_per_session": settings.max_concurrent_threads,
            "default_subagent_model": settings.default_model,
            "default_subagent_reasoning_effort": settings.default_reasoning_effort,
            "interrupt_message": settings.interrupt_message,
        }
        return CodexConfigurationTranslator._without_none(values)

    @staticmethod
    def _without_none(values: Mapping[str, Any]) -> dict[str, Any]:
        # Preserves explicit false values while removing provider-default nulls.
        return {key: value for key, value in values.items() if value is not None}


__all__ = [
    "CodexAgentSettings",
    "CodexConfigurationTranslator",
    "CodexForkSettings",
    "CodexSubagentSettings",
]
