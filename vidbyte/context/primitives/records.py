"""Context Protocol Header

Description:
    Defines record-style context primitives compatible with existing SDK records.
Purpose:
    Gives developers immutable artifact, response, and tool-call context units
    that map onto existing BaseContext record dataclasses.
Architecture:
    - Artifact/Response/ToolCall context primitives.
    - TOOL_CREATE_META ClassVar on create-enabled primitives holds model-facing
      tool strings (description + field schemas) for the create-tool registry.
Relations:
    Re-exported through vidbyte.context.primitives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True, slots=True)
class ArtifactContextItem:
    """Structured artifact context compatible with ContextArtifact."""

    name: str
    content: str
    artifact_type: str = "text"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "artifact"
    title: str = "Artifact"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "artifact",
        "tool_name": "context_create_artifact",
        "default_title": "Artifact",
        "description": (
            "context_create_artifact is the typed create tool for ArtifactContextItem deliverable "
            "payloads in the managed context window registry. context_create_artifact does insert or "
            "overwrite an artifact primitive by primitive_id with a name, typed body, and content so "
            "the agent can keep produced outputs (drafts, reports, structured data) available as first-"
            "class context for later steps or handoff."
        ),
        "fields": {
            "name": {
                "type": "string",
                "required": True,
                "description": (
                    "name is the short identifier for the artifact (file-like label or deliverable "
                    "title). name does distinguish this artifact from others when multiple outputs "
                    "are parked in the context window."
                ),
            },
            "content": {
                "type": "string",
                "required": True,
                "description": (
                    "content is the full artifact payload body. content does store the actual "
                    "deliverable text (markdown, code, JSON, prose) that later steps should consume."
                ),
            },
            "artifact_type": {
                "type": "string",
                "required": False,
                "description": (
                    "artifact_type is an optional type label such as text, markdown, json, or code. "
                    "artifact_type does help the model interpret how to read or present the body; "
                    "defaults to 'text' when omitted."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders artifact name, type, and content.
        return f"{self.name} ({self.artifact_type}):\n{self.content}"


@dataclass(frozen=True, slots=True)
class ResponseContextItem:
    """Structured model or agent response context."""

    content: str
    sender: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "response"
    title: str = "Response"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders response with optional sender attribution.
        prefix = f"Response from {self.sender}:" if self.sender else "Response:"
        return f"{prefix}\n{self.content}"


@dataclass(frozen=True, slots=True)
class ToolCallContextItem:
    """Structured tool-call context compatible with ContextToolCall."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    output: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "tool_call"
    title: str = "Tool Call"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders tool name, arguments, and output.
        return f"Tool call: {self.name}\nArguments: {dict(self.arguments)}\nOutput: {self.output}"


__all__ = [
    "ArtifactContextItem",
    "ResponseContextItem",
    "ToolCallContextItem",
]
