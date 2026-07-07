"""Context Protocol Header

Description:
    Defines the declarative registry that maps context primitive keys to create tools.
Purpose:
    Gives the SDK one source of truth for per-primitive tool names, schemas,
    flat parameters, and primitive builder logic.
Architecture:
    - PrimitiveToolDefinition: immutable registry row for one create tool.
    - PrimitiveToolRegistryBuilder: constructs ordered rows for supported primitives.
Relations:
    Used by CreateContextPrimitiveTool and context_window_tools. Depends on
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
from vidbyte.tools.types import ToolParameter

_PLACEMENT_ENUM = (
    "top_of_context",
    "end_of_context",
    "top_of_conversation",
    "end_of_conversation",
)


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
        definitions = (
            self._text_definition(),
            self._document_definition(),
            self._memory_definition(),
            self._plan_definition(),
            self._task_definition(),
            self._progress_definition(),
            self._artifact_definition(),
            self._environment_definition(),
            self._git_diff_definition(),
        )
        return {definition.key: definition for definition in definitions}

    def _text_definition(self) -> PrimitiveToolDefinition:
        """Build the text primitive create-tool definition."""
        fields = {
            "content": self._string_property("Text content to store in the primitive."),
            "source": self._string_property("Optional source attribution for the text."),
        }
        return self._definition("text", TextContextItem, "Create or overwrite a text context window primitive.", fields, ("content",), self._build_text)

    def _document_definition(self) -> PrimitiveToolDefinition:
        """Build the document primitive create-tool definition."""
        fields = {
            "source": self._string_property("Document source, path, URL, or label."),
            "content": self._string_property("Document content to store in the primitive."),
            "document_id": self._string_property("Optional external document identifier."),
        }
        return self._definition("document", DocumentContextItem, "Create or overwrite a document context window primitive.", fields, ("source", "content"), self._build_document)

    def _memory_definition(self) -> PrimitiveToolDefinition:
        """Build the memory primitive create-tool definition."""
        fields = {
            "content": self._string_property("Memory summary content to store in the primitive."),
            "source": self._string_property("Optional source attribution for the memory."),
        }
        return self._definition("memory", MemoryContextItem, "Create or overwrite a memory context window primitive.", fields, ("content",), self._build_memory)

    def _plan_definition(self) -> PrimitiveToolDefinition:
        """Build the plan primitive create-tool definition."""
        fields = {
            "steps": self._string_array_property("Ordered plan steps."),
            "current_step": self._integer_property("Zero-based index of the current step."),
            "status": self._string_property("Plan status label."),
        }
        return self._definition("plan", PlanContextItem, "Create or overwrite a plan context window primitive.", fields, ("steps",), self._build_plan)

    def _task_definition(self) -> PrimitiveToolDefinition:
        """Build the task primitive create-tool definition."""
        fields = {
            "goal": self._string_property("Task goal the agent is trying to complete."),
            "status": self._string_property("Task status label."),
            "progress": self._string_property("Optional progress summary."),
            "completed": self._string_array_property("Completed task entries."),
            "next_steps": self._string_array_property("Remaining next steps."),
            "deterministic_checks": self._string_array_property("Deterministic verification checks."),
        }
        return self._definition("task", TaskContextItem, "Create or overwrite a task context window primitive.", fields, ("goal",), self._build_task)

    def _progress_definition(self) -> PrimitiveToolDefinition:
        """Build the progress primitive create-tool definition."""
        fields = {
            "completed_tasks": self._string_array_property("Completed task entries."),
            "touched_files": self._string_array_property("Files touched while making progress."),
            "decisions": self._string_array_property("Decisions made so far."),
            "errors": self._string_array_property("Errors or blockers encountered."),
            "next_steps": self._string_array_property("Remaining next steps."),
        }
        return self._definition("progress", ProgressContextItem, "Create or overwrite a progress context window primitive.", fields, (), self._build_progress)

    def _artifact_definition(self) -> PrimitiveToolDefinition:
        """Build the artifact primitive create-tool definition."""
        fields = {
            "name": self._string_property("Artifact name."),
            "content": self._string_property("Artifact content."),
            "artifact_type": self._string_property("Artifact type label, such as text, markdown, or json."),
        }
        return self._definition("artifact", ArtifactContextItem, "Create or overwrite an artifact context window primitive.", fields, ("name", "content"), self._build_artifact)

    def _environment_definition(self) -> PrimitiveToolDefinition:
        """Build the environment primitive create-tool definition."""
        fields = {
            "os_name": self._string_property("Operating system name."),
            "cwd": self._string_property("Current working directory."),
            "shell": self._string_property("Active shell name."),
        }
        return self._definition("environment", EnvironmentContextItem, "Create or overwrite an environment context window primitive.", fields, (), self._build_environment)

    def _git_diff_definition(self) -> PrimitiveToolDefinition:
        """Build the git-diff primitive create-tool definition."""
        fields = {
            "diff": self._string_property("Raw git diff content."),
            "files": self._string_array_property("Files changed by the diff."),
            "repo_root": self._string_property("Repository root path or label."),
            "branch": self._string_property("Current branch name."),
            "base_ref": self._string_property("Base ref for the diff."),
            "head_ref": self._string_property("Head ref for the diff."),
        }
        return self._definition("git_diff", GitDiffContextItem, "Create or overwrite a git diff context window primitive.", fields, ("diff",), self._build_git_diff)

    def _definition(self, key: str, primitive_cls: type, summary: str, fields: Mapping[str, Mapping[str, Any]], required_fields: tuple[str, ...], builder: Callable[[Mapping[str, Any]], ContextItem]) -> PrimitiveToolDefinition:
        """Assemble one registry row from common fields and primitive-specific fields."""
        tool_name = f"context_create_{key}"
        properties = {**self._common_properties(), **dict(fields)}
        required = ("primitive_id", *required_fields)
        return PrimitiveToolDefinition(
            key=key,
            primitive_cls=primitive_cls,
            tool_name=tool_name,
            description=f"{summary} Reusing primitive_id intentionally overwrites the existing primitive unless it is frozen.",
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
        """Return shared create-tool JSON Schema properties."""
        return {
            "primitive_id": self._string_property("Stable id for the primitive, such as 'plan:current'."),
            "title": self._string_property("Optional display title shown in the context window."),
            "placement": {
                "type": "string",
                "enum": list(_PLACEMENT_ENUM),
                "default": "end_of_context",
                "description": "Where the primitive should render in the agent context window.",
            },
        }

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

    def _string_property(self, description: str) -> dict[str, Any]:
        """Return a JSON Schema property for a string argument."""
        return {"type": "string", "description": description}

    def _integer_property(self, description: str) -> dict[str, Any]:
        """Return a JSON Schema property for an integer argument."""
        return {"type": "integer", "description": description}

    def _string_array_property(self, description: str) -> dict[str, Any]:
        """Return a JSON Schema property for an array of strings."""
        return {"type": "array", "items": {"type": "string"}, "description": description}

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

    def _build_text(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a TextContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Text")
        return TextContextItem(primitive_id=primitive_id, title=title, content=self._required_string(args, "content"), source=self._optional_string(args, "source"))

    def _build_document(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a DocumentContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Document")
        return DocumentContextItem(primitive_id=primitive_id, title=title, source=self._required_string(args, "source"), content=self._required_string(args, "content"), document_id=self._optional_string(args, "document_id"))

    def _build_memory(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a MemoryContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Memory")
        return MemoryContextItem(primitive_id=primitive_id, title=title, content=self._required_string(args, "content"), source=self._optional_string(args, "source"))

    def _build_plan(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a PlanContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Plan")
        return PlanContextItem(primitive_id=primitive_id, title=title, steps=self._string_tuple(args, "steps"), current_step=self._integer(args, "current_step", 0), status=str(args.get("status") or "planning"))

    def _build_task(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a TaskContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Task")
        return TaskContextItem(primitive_id=primitive_id, title=title, goal=self._required_string(args, "goal"), status=str(args.get("status") or "pending"), progress=self._optional_string(args, "progress"), completed=self._string_tuple(args, "completed"), next_steps=self._string_tuple(args, "next_steps"), deterministic_checks=self._string_tuple(args, "deterministic_checks"))

    def _build_progress(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a ProgressContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Progress")
        return ProgressContextItem(primitive_id=primitive_id, title=title, completed_tasks=self._string_tuple(args, "completed_tasks"), touched_files=self._string_tuple(args, "touched_files"), decisions=self._string_tuple(args, "decisions"), errors=self._string_tuple(args, "errors"), next_steps=self._string_tuple(args, "next_steps"))

    def _build_artifact(self, args: Mapping[str, Any]) -> ContextItem:
        """Build an ArtifactContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Artifact")
        return ArtifactContextItem(primitive_id=primitive_id, title=title, name=self._required_string(args, "name"), content=self._required_string(args, "content"), artifact_type=str(args.get("artifact_type") or "text"))

    def _build_environment(self, args: Mapping[str, Any]) -> ContextItem:
        """Build an EnvironmentContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Environment")
        return EnvironmentContextItem(primitive_id=primitive_id, title=title, os_name=self._optional_string(args, "os_name"), cwd=self._optional_string(args, "cwd"), shell=self._optional_string(args, "shell"))

    def _build_git_diff(self, args: Mapping[str, Any]) -> ContextItem:
        """Build a GitDiffContextItem from validated create-tool arguments."""
        primitive_id, title = self._common_args(args, "Git Diff")
        return GitDiffContextItem(primitive_id=primitive_id, title=title, diff=self._required_string(args, "diff"), files=self._string_tuple(args, "files"), repo_root=self._optional_string(args, "repo_root"), branch=self._optional_string(args, "branch"), base_ref=self._optional_string(args, "base_ref"), head_ref=self._optional_string(args, "head_ref"))


CREATE_TOOL_REGISTRY = PrimitiveToolRegistryBuilder().build()

__all__ = ["CREATE_TOOL_REGISTRY", "PrimitiveToolDefinition", "PrimitiveToolRegistryBuilder"]
