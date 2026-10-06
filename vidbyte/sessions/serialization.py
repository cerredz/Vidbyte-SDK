"""Context Protocol Header

Description:
    Converts durable-session contracts to and from JSON-safe dicts.
Purpose:
    Centralizes serialization, secret scrubbing, and AgentMessage projection so
    every store persists an identical, safe payload shape.
Architecture:
    - SessionSerializer: class-first codec for Checkpoint, SessionMeta, and AgentMessage.
Relations:
    Used by every SessionStore implementation, the Session facade, and
    vidbyte.agents.base export_state()/restore().
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.types import AgentMessage
from vidbyte.sessions.contracts import (
    SESSION_SCHEMA_VERSION,
    Checkpoint,
    RunState,
    SessionMeta,
    SessionStatus,
)
from vidbyte.sessions.errors import SessionSerializationError, SessionVersionError

_SECRET_TOKENS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
_TRACE_WHITELIST = ("trace", "trace_metadata")
_USAGE_WHITELIST = ("tokens_used", "tool_call_count")


class SessionSerializer:
    """JSON-safe codec for session checkpoints, metadata, and messages."""

    def checkpoint_to_dict(self, checkpoint: Checkpoint) -> dict[str, Any]:
        # Render a full checkpoint (with schema version envelope) to a JSON-safe dict.
        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "checkpoint": {
                "id": checkpoint.id,
                "session_id": checkpoint.session_id,
                "parent_id": checkpoint.parent_id,
                "seq": checkpoint.seq,
                "created_at": checkpoint.created_at,
                "label": checkpoint.label,
                "status": checkpoint.status.value,
                "run_state": self._run_state_to_dict(checkpoint.run_state),
                "trace_artifact": self._safe(checkpoint.trace_artifact),
                "trace_summary": self._safe(checkpoint.trace_summary),
                "trace_events": self._safe(list(checkpoint.trace_events)) if checkpoint.trace_events is not None else None,
            },
        }

    def checkpoint_from_dict(self, data: Mapping[str, Any]) -> Checkpoint:
        # Parse a checkpoint payload, rejecting unknown schema versions.
        self._require_version(data)
        body = self._require_field(data, "checkpoint")
        events = body.get("trace_events")
        return Checkpoint(
            id=self._require_field(body, "id"),
            session_id=self._require_field(body, "session_id"),
            parent_id=body.get("parent_id"),
            seq=int(self._require_field(body, "seq")),
            created_at=self._require_field(body, "created_at"),
            run_state=self._run_state_from_dict(self._require_field(body, "run_state")),
            label=body.get("label", ""),
            status=SessionStatus(body.get("status", SessionStatus.ACTIVE.value)),
            trace_artifact=body.get("trace_artifact"),
            trace_summary=body.get("trace_summary"),
            trace_events=tuple(events) if isinstance(events, list) else None,
        )

    def meta_to_dict(self, meta: SessionMeta) -> dict[str, Any]:
        # Render session metadata to a JSON-safe dict with a schema envelope.
        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": meta.session_id,
            "head_id": meta.head_id,
            "parent_session_id": meta.parent_session_id,
            "agent_name": meta.agent_name,
            "status": meta.status.value,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
            "tags": list(meta.tags),
        }

    def meta_from_dict(self, data: Mapping[str, Any]) -> SessionMeta:
        # Parse session metadata, rejecting unknown schema versions.
        self._require_version(data)
        return SessionMeta(
            session_id=self._require_field(data, "session_id"),
            head_id=data.get("head_id"),
            parent_session_id=data.get("parent_session_id"),
            agent_name=data.get("agent_name", ""),
            status=SessionStatus(data.get("status", SessionStatus.ACTIVE.value)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tags=tuple(data.get("tags", ()) or ()),
        )

    def message_to_dict(self, message: AgentMessage) -> dict[str, Any]:
        # Project an AgentMessage to a JSON-safe dict with scrubbed metadata.
        return {
            "sender": message.sender,
            "recipient": message.recipient,
            "content": message.content,
            "message_type": message.message_type,
            "metadata": self._scrub_metadata(message.metadata),
            "structured": self._safe(message.structured),
        }

    def message_from_dict(self, data: Mapping[str, Any]) -> AgentMessage:
        # Rebuild an AgentMessage from a persisted dict; structured returns as plain data, not a model.
        return AgentMessage(
            sender=data.get("sender", ""),
            recipient=data.get("recipient", ""),
            content=data.get("content", ""),
            message_type=data.get("message_type", "response"),
            metadata=dict(data.get("metadata", {}) or {}),
            structured=data.get("structured"),
        )

    def _run_state_to_dict(self, state: RunState) -> dict[str, Any]:
        # Render a RunState to a JSON-safe dict, scrubbing runner options.
        return {
            "schema_version": state.schema_version,
            "agent_name": state.agent_name,
            "system_prompt": state.system_prompt,
            "description": state.description,
            "capabilities": list(state.capabilities),
            "provider": state.provider,
            "model_name": state.model_name,
            "temperature": state.temperature,
            "runtime_type": state.runtime_type,
            "runtime_config": self._safe(state.runtime_config),
            "algorithm": state.algorithm,
            "metadata": self._scrub_metadata(state.metadata),
            "agent_metadata": dict(state.agent_metadata),
            "tool_names": list(state.tool_names),
            "history": [dict(item) for item in state.history],
            "run_id": state.run_id,
            "loop_settings": self._safe(state.loop_settings),
            "aggregate_plan": self._safe(state.aggregate_plan),
            "context_summary": self._safe(state.context_summary),
            "trace_option": self._safe(state.trace_option),
            "output_schema": self._safe(state.output_schema),
        }

    def _run_state_from_dict(self, data: Mapping[str, Any]) -> RunState:
        # Rebuild a RunState from a persisted dict.
        return RunState(
            schema_version=int(data.get("schema_version", SESSION_SCHEMA_VERSION)),
            agent_name=data.get("agent_name", ""),
            system_prompt=data.get("system_prompt", ""),
            description=data.get("description", ""),
            capabilities=tuple(data.get("capabilities", ()) or ()),
            provider=data.get("provider"),
            model_name=data.get("model_name"),
            temperature=data.get("temperature"),
            runtime_type=data.get("runtime_type", "linear"),
            runtime_config=dict(data.get("runtime_config", {}) or {}),
            algorithm=data.get("algorithm", "default"),
            metadata=dict(data.get("metadata", {}) or {}),
            agent_metadata=dict(data.get("agent_metadata", {}) or {}),
            tool_names=tuple(data.get("tool_names", ()) or ()),
            history=tuple(dict(item) for item in data.get("history", ()) or ()),
            run_id=data.get("run_id"),
            loop_settings=dict(data.get("loop_settings", {}) or {}),
            aggregate_plan=dict(data.get("aggregate_plan", {}) or {}),
            context_summary=dict(data.get("context_summary", {}) or {}),
            trace_option=dict(data.get("trace_option", {}) or {}),
            output_schema=data.get("output_schema"),
        )

    def _scrub_metadata(self, metadata: Mapping[str, Any] | None) -> dict[str, Any]:
        # Drop credential-like keys, keep the trace whitelist, and JSON-safe the rest.
        scrubbed: dict[str, Any] = {}
        for key, value in dict(metadata or {}).items():
            key_text = str(key)
            if self._is_secret_key(key_text):
                continue
            scrubbed[key_text] = self._safe(value)
        return scrubbed

    def _safe(self, value: Any) -> Any:
        # Recursively coerce a value into JSON-safe form, marking non-serializable leaves.
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return {str(k): self._safe(v) for k, v in value.items() if not self._is_secret_key(str(k))}
        if isinstance(value, (list, tuple)):
            return [self._safe(item) for item in value]
        dumped = self._dumped_model(value)
        if dumped is not None:
            return dumped
        return {"__dropped__": type(value).__name__}

    def _dumped_model(self, value: Any) -> dict[str, Any] | None:
        # Renders a validated structured-output instance as plain JSON data, or None if it is not one.
        try:
            from pydantic import BaseModel
        except ImportError:
            return None
        if not isinstance(value, BaseModel):
            return None
        return {str(k): self._safe(v) for k, v in value.model_dump(mode="json").items()}

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        # Decide whether a metadata key looks like a credential to strip.
        upper = key.upper()
        if upper in (token.upper() for token in (*_TRACE_WHITELIST, *_USAGE_WHITELIST)):
            return False
        return any(token in upper for token in _SECRET_TOKENS)

    @staticmethod
    def _require_version(data: Mapping[str, Any]) -> None:
        # Raise SessionVersionError when the payload version is unsupported.
        version = data.get("schema_version")
        if version is None:
            raise SessionSerializationError("Session payload missing schema_version.", details={"payload": "schema_version"})
        if int(version) != SESSION_SCHEMA_VERSION:
            raise SessionVersionError(
                f"Unsupported session schema version: {version}.",
                details={"found": version, "expected": SESSION_SCHEMA_VERSION},
            )

    @staticmethod
    def _require_field(data: Mapping[str, Any], field: str) -> Any:
        # Return a required field or raise SessionSerializationError naming it.
        if field not in data:
            raise SessionSerializationError(f"Session payload missing required field: {field}.", details={"field": field})
        return data[field]


__all__ = ["SessionSerializer"]
