"""FILE: vidbyte/agents/codex/session.py

PURPOSE: Converts Codex provider state to and from a durable checkpoint mapping.
ROLE IN CODEBASE: agent.py's export_state/restore call this; Session owns the store,
    the checkpoint DAG, and the trace. This module owns only the state translation.
ARCHITECTURE NOTE: A checkpoint carries the native thread id, not a transcript. Codex
    owns the thread, so replaying text into a new thread would produce a different
    conversation while looking, to the caller, like a resume.
FUNCTION INVENTORY: to_provider_state(request) emits the JSON-safe mapping;
    to_settings(state) rebuilds CodexAgentSettings; to_placements(state) rebuilds the
    context anchors; require_resumable(state) refuses a checkpoint that cannot resume.
COMMON MODIFICATION PATTERNS: A new provider setting must be added to both directions
    here deliberately; the mapping is field-by-field so nothing is included silently.
WHAT NOT TO DO IN THIS FILE: Do not serialize client.env (it routinely holds
    credentials and a session store is not a secret store), do not serialize the
    ContextManager, output_schema, or middleware, and do not claim to restore files.
KNOWN EDGE CASES: An ephemeral thread dies with its process and can never resume; a
    checkpoint with no thread id would silently start a fresh thread.
RELATED DOCS: docs/design/codex-durable-sessions.md
TESTS: tests/test_codex_durable_sessions.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.constants.codex import (
    CODEX_PROVIDER_STATE_KIND,
    CODEX_ROOT_FORK_DEPTH,
    CODEX_STATE_KIND_KEY,
    CODEX_STATE_SETTINGS_KEY,
    CODEX_STATE_THREAD_ID_KEY,
)
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexClientSettings,
    CodexContextPlacement,
    CodexSessionExportRequest,
    CodexSubagentSettings,
    CodexThreadSettings,
    CodexTurnSettings,
)
from vidbyte.lib.enums.codex import (
    CodexApprovalMode,
    CodexContextAnchor,
    CodexPersonality,
    CodexReasoningEffort,
    CodexReasoningSummary,
    CodexSandbox,
    CodexThreadSource,
    CodexThreadStartSource,
)
from vidbyte.sessions.errors import SessionError


class CodexSessionTranslator:
    """Converts Codex provider state to and from a checkpoint mapping."""

    @classmethod
    def to_provider_state(cls, request: CodexSessionExportRequest) -> dict[str, Any]:
        # @intent persist-the-thread-not-the-transcript
        # The native thread id is the only handle to a Codex conversation, so it is
        # what a checkpoint must carry; a copied transcript would resume nothing.
        settings = request.settings
        lineage = dict(settings.metadata)
        return {
            CODEX_STATE_KIND_KEY: CODEX_PROVIDER_STATE_KIND,
            CODEX_STATE_THREAD_ID_KEY: request.thread_id,
            "additional_context": settings.additional_context,
            "forked_from_thread_id": str(lineage.get("forked_from_thread_id", "")),
            "fork_depth": int(
                lineage.get("fork_depth", CODEX_ROOT_FORK_DEPTH) or CODEX_ROOT_FORK_DEPTH
            ),
            "context_placements": [
                {"primitive_id": placement.primitive_id, "anchor": placement.anchor.value}
                for placement in settings.context_placements
            ],
            CODEX_STATE_SETTINGS_KEY: cls._settings_state(settings.codex),
        }

    @classmethod
    def to_settings(cls, provider_state: Mapping[str, Any]) -> CodexAgentSettings:
        # @intent classify-a-corrupt-checkpoint-at-its-own-boundary
        # An unknown stored enum value must surface as a SessionError, not a bare
        # ValueError from an enum constructor several frames down.
        stored = provider_state.get(CODEX_STATE_SETTINGS_KEY) or {}
        if not isinstance(stored, Mapping):
            raise SessionError(
                "Codex checkpoint provider state is missing its settings mapping.",
                details={"key": CODEX_STATE_SETTINGS_KEY},
            )
        try:
            return CodexAgentSettings(
                client=cls._client_settings(stored.get("client") or {}),
                thread=cls._thread_settings(stored.get("thread") or {}),
                turn=cls._turn_settings(stored.get("turn") or {}),
                subagents=cls._subagent_settings(stored.get("subagents") or {}),
            )
        except SessionError:
            raise
        except Exception as exc:
            raise SessionError(
                "Codex checkpoint provider state could not be rebuilt.",
                details={"error_type": type(exc).__name__},
            ) from exc

    @staticmethod
    def require_resumable(provider_state: Mapping[str, Any]) -> str:
        # @intent refuse-a-checkpoint-that-cannot-resume
        # Without this, restore builds an agent with no thread id, whose next turn
        # silently starts a fresh conversation that looks like the restored one.
        thread_id = str(provider_state.get(CODEX_STATE_THREAD_ID_KEY, "")).strip()
        if not thread_id:
            raise SessionError(
                "Codex checkpoint has no native thread id and cannot be resumed.",
                details={"provider_state_kind": CODEX_PROVIDER_STATE_KIND},
            )
        stored = provider_state.get(CODEX_STATE_SETTINGS_KEY) or {}
        thread = stored.get("thread") or {} if isinstance(stored, Mapping) else {}
        if bool(thread.get("ephemeral", False)):
            raise SessionError(
                "Codex ephemeral threads live only in their owning process and "
                "cannot be resumed from a checkpoint.",
                details={"thread_id": thread_id},
            )
        return thread_id

    @staticmethod
    def to_placements(
        provider_state: Mapping[str, Any],
    ) -> tuple[CodexContextPlacement, ...]:
        """Rebuild the agent-level context placements a checkpoint recorded."""
        # Anchors are stored by value; a dropped placement would silently move a
        # primitive back to the default zone on the restored agent's next turn.
        stored = provider_state.get("context_placements") or ()
        return tuple(
            CodexContextPlacement(
                primitive_id=str(entry.get("primitive_id", "")),
                anchor=CodexContextAnchor(entry.get("anchor", "")),
            )
            for entry in stored
        )

    @classmethod
    def _settings_state(cls, settings: CodexAgentSettings) -> dict[str, Any]:
        # @intent explicit-fields-so-nothing-persists-by-accident
        # Field-by-field on purpose: a new provider setting must be a deliberate
        # addition here rather than something reflection picks up unreviewed, and
        # client.env is omitted because a session store is not a secret store.
        client = settings.client
        thread = settings.thread
        turn = settings.turn
        subagents = settings.subagents
        return {
            "client": {
                "codex_bin": client.codex_bin,
                "launch_args_override": list(client.launch_args_override),
                "config_overrides": list(client.config_overrides),
                "cwd": client.cwd,
                "client_name": client.client_name,
                "client_title": client.client_title,
                "client_version": client.client_version,
                "experimental_api": client.experimental_api,
            },
            "thread": {
                "approval_mode": thread.approval_mode.value,
                "base_instructions": thread.base_instructions,
                "cwd": thread.cwd,
                "model": thread.model,
                "model_provider": thread.model_provider,
                "personality": thread.personality.value,
                "sandbox": thread.sandbox.value,
                "service_name": thread.service_name,
                "service_tier": thread.service_tier,
                "session_start_source": thread.session_start_source.value,
                "thread_source": thread.thread_source.value,
                "ephemeral": thread.ephemeral,
                "config": dict(thread.config),
            },
            "turn": {
                "approval_mode": turn.approval_mode.value,
                "cwd": turn.cwd,
                "effort": turn.effort.value,
                "model": turn.model,
                "personality": turn.personality.value,
                "sandbox": turn.sandbox.value,
                "service_tier": turn.service_tier,
                "summary": turn.summary.value,
            },
            "subagents": {
                "enabled": subagents.enabled,
                "max_concurrent_threads": subagents.max_concurrent_threads,
                "default_model": subagents.default_model,
                "default_reasoning_effort": subagents.default_reasoning_effort.value,
                "interrupt_message": subagents.interrupt_message,
                "roles": {
                    name: dict(role) for name, role in subagents.roles.items()
                },
            },
        }

    @staticmethod
    def _client_settings(stored: Mapping[str, Any]) -> CodexClientSettings:
        # client.env is deliberately absent from every checkpoint, so a restored
        # agent starts with an empty environment and the caller re-supplies it.
        defaults = CodexClientSettings()
        return CodexClientSettings(
            codex_bin=str(stored.get("codex_bin", "")),
            launch_args_override=tuple(stored.get("launch_args_override", ()) or ()),
            config_overrides=tuple(stored.get("config_overrides", ()) or ()),
            cwd=str(stored.get("cwd", "")),
            client_name=str(stored.get("client_name", defaults.client_name)),
            client_title=str(stored.get("client_title", defaults.client_title)),
            client_version=str(stored.get("client_version", defaults.client_version)),
            experimental_api=bool(
                stored.get("experimental_api", defaults.experimental_api)
            ),
        )

    @staticmethod
    def _thread_settings(stored: Mapping[str, Any]) -> CodexThreadSettings:
        # Each enum is rebuilt from its stored .value, never from a repr.
        return CodexThreadSettings(
            approval_mode=CodexApprovalMode(stored.get("approval_mode", "")),
            base_instructions=str(stored.get("base_instructions", "")),
            cwd=str(stored.get("cwd", "")),
            model=str(stored.get("model", "")),
            model_provider=str(stored.get("model_provider", "")),
            personality=CodexPersonality(stored.get("personality", "")),
            sandbox=CodexSandbox(stored.get("sandbox", "")),
            service_name=str(stored.get("service_name", "")),
            service_tier=str(stored.get("service_tier", "")),
            session_start_source=CodexThreadStartSource(
                stored.get("session_start_source", "")
            ),
            thread_source=CodexThreadSource(stored.get("thread_source", "")),
            ephemeral=bool(stored.get("ephemeral", False)),
            config=dict(stored.get("config", {}) or {}),
        )

    @staticmethod
    def _turn_settings(stored: Mapping[str, Any]) -> CodexTurnSettings:
        # Turn overrides outrank thread defaults, so losing one changes the next turn.
        return CodexTurnSettings(
            approval_mode=CodexApprovalMode(stored.get("approval_mode", "")),
            cwd=str(stored.get("cwd", "")),
            effort=CodexReasoningEffort(stored.get("effort", "")),
            model=str(stored.get("model", "")),
            personality=CodexPersonality(stored.get("personality", "")),
            sandbox=CodexSandbox(stored.get("sandbox", "")),
            service_tier=str(stored.get("service_tier", "")),
            summary=CodexReasoningSummary(stored.get("summary", "")),
        )

    @staticmethod
    def _subagent_settings(stored: Mapping[str, Any]) -> CodexSubagentSettings:
        # Role tables are plain string maps, so they round-trip without coercion.
        defaults = CodexSubagentSettings()
        return CodexSubagentSettings(
            enabled=bool(stored.get("enabled", defaults.enabled)),
            max_concurrent_threads=int(stored.get("max_concurrent_threads", 0) or 0),
            default_model=str(stored.get("default_model", "")),
            default_reasoning_effort=CodexReasoningEffort(
                stored.get("default_reasoning_effort", "")
            ),
            interrupt_message=bool(
                stored.get("interrupt_message", defaults.interrupt_message)
            ),
            roles={
                str(name): {str(key): str(value) for key, value in dict(role).items()}
                for name, role in dict(stored.get("roles", {}) or {}).items()
            },
        )


__all__ = ["CodexSessionTranslator"]
