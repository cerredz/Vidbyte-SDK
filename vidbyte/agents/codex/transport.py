"""Official Codex Python SDK transport for CodexHarnessAgent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from vidbyte.agents.codex.config import CodexAgentSettings, CodexConfigurationTranslator
from vidbyte.agents.codex.result import CodexRunResult
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError


class _ModelValidator(Protocol):
    """Structural type for generated SDK models with Pydantic validation."""

    @classmethod
    def model_validate(cls, value: object) -> Any:
        # Declares only the generated-model operation consumed by this transport.
        ...


class _CodexThread(Protocol):
    """Structural type for a Codex thread returned by the SDK client."""

    id: str

    async def run(self, prompt: str, **kwargs: object) -> object:
        # Declares the complete-turn operation consumed by the transport.
        ...


class _CodexClient(Protocol):
    """Structural type for the stable Codex thread lifecycle operations."""

    async def thread_start(self, **kwargs: object) -> _CodexThread:
        # Starts a provider thread with translated configuration.
        ...

    async def thread_resume(self, thread_id: str, **kwargs: object) -> _CodexThread:
        # Resumes a provider thread by its durable identifier.
        ...

    async def thread_fork(self, thread_id: str, **kwargs: object) -> _CodexThread:
        # Forks a provider thread by its durable identifier.
        ...


@dataclass(frozen=True, slots=True)
class _CodexSdk:
    """Lazily imported Codex SDK classes needed by the transport."""

    async_codex: type
    codex_config: type
    approval_mode: type
    sandbox: type
    personality: type
    reasoning_effort: type
    reasoning_summary: type[_ModelValidator]


class CodexTransport:
    """Owns Codex app-server process, thread, and turn operations."""

    async def run(self, *, thread_id: str | None, system_prompt: str, prompt: str, settings: CodexAgentSettings, output_schema: dict[str, Any] | None) -> CodexRunResult:
        # Starts or resumes one thread, runs one complete turn, and closes the client.
        sdk = self._load_sdk()
        try:
            config = sdk.codex_config(cwd=settings.cwd)
            async with sdk.async_codex(config) as client:
                thread = await self._open_thread(
                    client, sdk, thread_id, system_prompt, settings
                )
                turn_kwargs = self._typed_kwargs(
                    CodexConfigurationTranslator.turn_kwargs(settings, output_schema),
                    sdk,
                )
                result = await thread.run(prompt, **turn_kwargs)
                return CodexRunResult.from_sdk(thread.id, result)
        except asyncio.CancelledError:
            raise
        except (ConfigurationError, AgentExecutionError):
            raise
        except Exception as exc:
            operation = "resume_and_run" if thread_id is not None else "start_and_run"
            raise AgentExecutionError(
                "Codex failed to execute the requested turn.",
                details={"operation": operation, "error_type": type(exc).__name__},
            ) from exc

    async def fork(self, *, thread_id: str, system_prompt: str, settings: CodexAgentSettings, ephemeral: bool | None) -> str:
        # Forks an established provider thread and closes the temporary client.
        sdk = self._load_sdk()
        try:
            config = sdk.codex_config(cwd=settings.cwd)
            async with sdk.async_codex(config) as client:
                kwargs = CodexConfigurationTranslator.thread_fork_kwargs(
                    system_prompt, settings, ephemeral
                )
                thread = await client.thread_fork(
                    thread_id, **self._typed_kwargs(kwargs, sdk)
                )
                return str(thread.id)
        except asyncio.CancelledError:
            raise
        except (ConfigurationError, AgentExecutionError):
            raise
        except Exception as exc:
            raise AgentExecutionError(
                "Codex failed to fork the requested thread.",
                details={"operation": "thread_fork", "error_type": type(exc).__name__},
            ) from exc

    async def _open_thread(self, client: _CodexClient, sdk: _CodexSdk, thread_id: str | None, system_prompt: str, settings: CodexAgentSettings) -> _CodexThread:
        # Selects the stable start or resume operation for the known thread state.
        if thread_id is None:
            kwargs = CodexConfigurationTranslator.thread_start_kwargs(
                system_prompt, settings
            )
            return await client.thread_start(**self._typed_kwargs(kwargs, sdk))
        kwargs = CodexConfigurationTranslator.thread_resume_kwargs(
            system_prompt, settings
        )
        return await client.thread_resume(thread_id, **self._typed_kwargs(kwargs, sdk))

    @staticmethod
    def _typed_kwargs(kwargs: dict[str, Any], sdk: _CodexSdk) -> dict[str, Any]:
        # Converts validated public strings into the enum types required by the SDK.
        typed = dict(kwargs)
        enum_fields = {
            "approval_mode": sdk.approval_mode,
            "effort": sdk.reasoning_effort,
            "personality": sdk.personality,
            "sandbox": sdk.sandbox,
        }
        for field_name, enum_type in enum_fields.items():
            if field_name in typed:
                typed[field_name] = enum_type(typed[field_name])
        if "summary" in typed:
            typed["summary"] = sdk.reasoning_summary.model_validate(typed["summary"])
        return typed

    @staticmethod
    def _load_sdk() -> _CodexSdk:
        # Imports the optional dependency only when a Codex operation is requested.
        try:
            from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox
            from openai_codex.generated.v2_all import (
                Personality,
                ReasoningEffort,
                ReasoningSummary,
            )
        except ImportError as exc:
            raise ConfigurationError(
                "CodexHarnessAgent requires the optional Codex integration; install 'vidbyte-sdk[codex]'."
            ) from exc
        return _CodexSdk(
            async_codex=AsyncCodex,
            codex_config=CodexConfig,
            approval_mode=ApprovalMode,
            sandbox=Sandbox,
            personality=Personality,
            reasoning_effort=ReasoningEffort,
            reasoning_summary=ReasoningSummary,
        )


__all__ = ["CodexTransport"]
