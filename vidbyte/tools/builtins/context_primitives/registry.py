"""Context Protocol Header

Description:
    Defines the declarative registry that maps context primitive keys to create tools.
Purpose:
    Gives the SDK one source of truth for per-primitive tool builders while reading
    model-facing tool strings from each primitive's TOOL_CREATE_META dictionary.
Architecture:
    - PrimitiveToolDefinition: immutable registry row for one create tool.
    - PrimitiveToolRegistryBuilder: assembles schemas from primitive metadata + builders.
Relations:
    Used by CreateContextPrimitiveTool and ContextWindowFactory. Depends on
    vidbyte.context.primitives and vidbyte.tools.types.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from vidbyte.context.primitives import (
    ArtifactContextItem,
    ContextItem,
    DocumentContextItem,
    EnvironmentContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    TaskContextItem,
    TextContextItem,
)
from vidbyte.context.primitives.base import CREATE_TOOL_COMMON_FIELDS
from vidbyte.tools.types import ToolParameter


@dataclass(frozen=True, slots=True)
class PrimitiveToolDefinition:
    """Immutable declaration for one generated context primitive create tool."""

    key: str
    primitive_cls: type
    tool_name: str
    description: str
    parameters: tuple[ToolParameter, ...]
    input_schema: Mapping[str, Any]
    builder: Callable[[Mapping[str, Any]], ContextItem]


class PrimitiveToolRegistryBuilder:
    """Builds registry definitions for model-callable primitive creation tools."""

    def build(self) -> dict[str, PrimitiveToolDefinition]:
        """Return the ordered create-tool registry keyed by primitive key."""
        rows: tuple[tuple[type, Callable[[Mapping[str, Any]], ContextItem]], ...] = (
            (TextContextItem, self._build_text),
            (DocumentContextItem, self._build_document),
            (MemoryContextItem, self._build_memory),
            (PlanContextItem, self._build_plan),
            (TaskContextItem, self._build_task),
            (ProgressContextItem, self._build_progress),
            (ArtifactContextItem, self._build_artifact),
            (EnvironmentContextItem, self._build_environment),
            (GitDiffContextItem, self._build_git_diff),
        )
        return {definition.key: definition for definition in (self._definition_from_primitive(cls, builder) for cls, builder in rows)}

    def _definition_from_primitive(self, primitive_cls: type, builder: Callable[[Mapping[str, Any]], ContextItem]) -> PrimitiveToolDefinition:
        """Assemble one registry row from a primitive's TOOL_CREATE_META plus a builder."""
        meta = getattr(primitive_cls, "TOOL_CREATE_META", None)
        if not isinstance(meta, Mapping):
            raise ValueError(f"{primitive_cls.__name__} is missing TOOL_CREATE_META for create-tool registration.")
        key = str(meta["key"])
        tool_name = str(meta.get("tool_name") or f"context_create_{key}")
        description = str(meta["description"])
        field_meta = dict(meta.get("fields") or {})
        properties = {**self._common_properties(), **{name: self._field_to_schema(spec) for name, spec in field_meta.items()}}
        required = ("primitive_id", *tuple(name for name, spec in field_meta.items() if bool(spec.get("required"))))
        return PrimitiveToolDefinition(
            key=key,
            primitive_cls=primitive_cls,
            tool_name=tool_name,
            description=description,
            parameters=self._parameters(properties, required),
            input_schema={
                "type": "object",
                "required": list(required),
                "additionalProperties": False,
                "properties": properties,
            },
            builder=builder,
        )

    def _common_properties(self) -> dict[str, Mapping[str, Any]]:
        """Return shared create-tool JSON Schema properties from CREATE_TOOL_COMMON_FIELDS."""
        return {name: self._field_to_schema(spec) for name, spec in CREATE_TOOL_COMMON_FIELDS.items()}

    def _field_to_schema(self, field_spec: Mapping[str, Any]) -> dict[str, Any]:
        """Convert a TOOL_CREATE_META / common field dict into a JSON Schema property."""
        schema: dict[str, Any] = {
            "type": str(field_spec.get("type", "string")),
            "description": str(field_spec.get("description", "")),
        }
        if "items" in field_spec:
            schema["items"] = dict(field_spec["items"])
        if "enum" in field_spec:
            schema["enum"] = list(field_spec["enum"])
        if "default" in field_spec:
            schema["default"] = field_spec["default"]
        return schema

    def _parameters(self, properties: Mapping[str, Mapping[str, Any]], required: tuple[str, ...]) -> tuple[ToolParameter, ...]:
        """Return flat ToolParameter entries mirroring the authoritative schema."""
        required_set = set(required)
        return tuple(
            ToolParameter(
                name=name,
                type=str(schema.get("type", "string")),
                description=str(schema.get("description", "")),
                required=name in required_set,
                default=schema.get("default"),
            )
            for name, schema in properties.items()
        )

    def _common_args(self, args: Mapping[str, Any], default_title: str) -> tuple[str, str]:
        """Extract and validate primitive_id plus title from create-tool arguments."""
        primitive_id = str(args.get("primitive_id", "")).strip()
        if not primitive_id:
            raise ValueError("primitive_id must be a non-empty string.")
        title = str(args.get("title") or default_title).strip() or default_title
        return primitive_id, title

    def _optional_string(self, args: Mapping[str, Any], name: str) -> str | None:
        """Return an optional string argument, preserving None when absent or blank."""
        value = args.get(name)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _required_string(self, args: Mapping[str, Any], name: str) -> str:
        """Return a required non-empty string argument or raise ValueError."""
        text = str(args.get(name, "")).strip()
        if not text:
            raise ValueError(f"{name} must be a non-empty string.")
        return text

    def _string_tuple(self, args: Mapping[str, Any], name: str) -> tuple[str, ...]:
        """Coerce a JSON array argument into a tuple of strings."""
        value = args.get(name, ())
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{name} must be an array of strings.")
        return tuple(str(item) for item in value)

    def _integer(self, args: Mapping[str, Any], name: str, default: int) -> int:
        """Coerce an optional integer argument into an int."""
        value = args.get(name, default)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer.") from exc

    def _default_title(self, primitive_cls: type, fallback: str) -> str:
        """Return the default title declared on TOOL_CREATE_META, if any."""
        meta = getattr(primitive_cls, "TOOL_CREATE_META", {})
        if isinstance(meta, Mapping) and meta.get("default_title"):
            return str(meta["default_title"])
        return fallback

    def _build_text(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a TextContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(TextContextItem, "Text"))
        return TextContextItem(primitive_id=primitive_id, title=title, content=self._required_string(args, "content"), source=self._optional_string(args, "source"))

    def _build_document(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a DocumentContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(DocumentContextItem, "Document"))
        return DocumentContextItem(primitive_id=primitive_id, title=title, source=self._required_string(args, "source"), content=self._required_string(args, "content"), document_id=self._optional_string(args, "document_id"))

    def _build_memory(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a MemoryContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(MemoryContextItem, "Memory"))
        return MemoryContextItem(primitive_id=primitive_id, title=title, content=self._required_string(args, "content"), source=self._optional_string(args, "source"))

    def _build_plan(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a PlanContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(PlanContextItem, "Plan"))
        return PlanContextItem(primitive_id=primitive_id, title=title, steps=self._string_tuple(args, "steps"), current_step=self._integer(args, "current_step", 0), status=str(args.get("status") or "planning"))

    def _build_task(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a TaskContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(TaskContextItem, "Task"))
        return TaskContextItem(primitive_id=primitive_id, title=title, goal=self._required_string(args, "goal"), status=str(args.get("status") or "pending"), progress=self._optional_string(args, "progress"), completed=self._string_tuple(args, "completed"), next_steps=self._string_tuple(args, "next_steps"), deterministic_checks=self._string_tuple(args, "deterministic_checks"))

    def _build_progress(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a ProgressContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(ProgressContextItem, "Progress"))
        return ProgressContextItem(primitive_id=primitive_id, title=title, completed_tasks=self._string_tuple(args, "completed_tasks"), touched_files=self._string_tuple(args, "touched_files"), decisions=self._string_tuple(args, "decisions"), errors=self._string_tuple(args, "errors"), next_steps=self._string_tuple(args, "next_steps"))

    def _build_artifact(self, args: Mapping[str, Any]) -> ContextItem:
        """Build an ArtifactContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(ArtifactContextItem, "Artifact"))
        return ArtifactContextItem(primitive_id=primitive_id, title=title, name=self._required_string(args, "name"), content=self._required_string(args, "content"), artifact_type=str(args.get("artifact_type") or "text"))

    def _build_environment(self, args: Mapping[str, Any]) -> ContextItem:
        """Build an EnvironmentContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(EnvironmentContextItem, "Environment"))
        return EnvironmentContextItem(primitive_id=primitive_id, title=title, os_name=self._optional_string(args, "os_name"), cwd=self._optional_string(args, "cwd"), shell=self._optional_string(args, "shell"))

    def _build_git_diff(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a GitDiffContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, self._default_title(GitDiffContextItem, "Git Diff"))
        return GitDiffContextItem(primitive_id=primitive_id, title=title, diff=self._required_string(args, "diff"), files=self._string_tuple(args, "files"), repo_root=self._optional_string(args, "repo_root"), branch=self._optional_string(args, "branch"), base_ref=self._optional_string(args, "base_ref"), head_ref=self._optional_string(args, "head_ref"))


CREATE_TOOL_REGISTRY = PrimitiveToolRegistryBuilder().build()

__all__ = ["CREATE_TOOL_REGISTRY", "PrimitiveToolDefinition", "PrimitiveToolRegistryBuilder"]
