"""Context Protocol Header

Description:
    Implements the central ContextManager abstraction for structured context items.
Purpose:
    Provides a single developer-facing object for collecting standardized context
    items and converting them into existing SDK context dataclasses.
Architecture:
    - ContextManager: Ordered context item collection with simple utilities.
    - Compatibility conversion from context items to StrategyContext fields.
Relations:
    Used by BaseAgent/AgentRuntime and re-exported through vidbyte.context.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.dataclasses.context import (
    BaseContext,
    ContextArtifact,
    ContextResponse,
    ContextToolCall,
    StrategyContext,
)
from vidbyte.context.primitives import (
    ArtifactContextItem,
    ContextItem,
    ContextPrimitiveVisibility,
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    IdentityContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    ToolCallContextItem,
    context_primitive_id,
    context_primitive_visibility,
    sort_context_primitives,
)
from vidbyte.context.updates import ContextPrimitiveUpdate, ContextPrimitiveUpdateAction


@dataclass(slots=True)
class ContextManager:
    """Ordered collection and compatibility bridge for context items."""

    context_items: Sequence[ContextItem] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.context_items = tuple(self.context_items)
        self.metadata = dict(self.metadata)

    def add(self, item: ContextItem) -> "ContextManager":
        """Append one context item and return this manager."""
        self.context_items = (*tuple(self.context_items), item)
        return self

    def extend(self, items: Iterable[ContextItem]) -> "ContextManager":
        """Append many context items and return this manager."""
        self.context_items = (*tuple(self.context_items), *tuple(items))
        return self

    def remove(self, item: ContextItem) -> "ContextManager":
        """Remove one matching context item and return this manager."""
        items = list(self.context_items)
        items.remove(item)
        self.context_items = tuple(items)
        return self

    def upsert(self, item: ContextItem) -> "ContextManager":
        """Insert or replace one context primitive by stable ID."""
        item_id = context_primitive_id(item)
        replaced = False
        items: list[ContextItem] = []
        for existing in self.context_items:
            if context_primitive_id(existing) == item_id:
                if not replaced:
                    items.append(item)
                    replaced = True
                continue
            items.append(existing)
        if not replaced:
            items.append(item)
        self.context_items = tuple(items)
        return self

    def remove_by_id(self, item_id: str) -> "ContextManager":
        """Remove any context primitive matching a stable ID."""
        self.context_items = tuple(
            item for item in self.context_items if context_primitive_id(item) != item_id
        )
        return self

    def apply_update(self, update: ContextPrimitiveUpdate) -> "ContextManager":
        """Apply one primitive update and return this manager."""
        action = ContextPrimitiveUpdateAction(update.action)
        if action is ContextPrimitiveUpdateAction.UPSERT:
            if update.item is None:
                raise ValueError("UPSERT context primitive update requires an item")
            return self.upsert(update.item)
        if not update.item_id:
            raise ValueError("REMOVE context primitive update requires an item_id")
        return self.remove_by_id(update.item_id)

    def apply_updates(self, updates: Iterable[ContextPrimitiveUpdate]) -> "ContextManager":
        """Apply primitive updates in order and return this manager."""
        for update in updates:
            self.apply_update(update)
        return self

    def clear(self) -> "ContextManager":
        """Remove all context items and return this manager."""
        self.context_items = ()
        return self

    def items(self) -> tuple[ContextItem, ...]:
        """Return the current context items in insertion order."""
        return tuple(self.context_items)

    def by_kind(self, kind: str) -> tuple[ContextItem, ...]:
        """Return all context items matching a kind."""
        return tuple(item for item in self.context_items if item.kind == kind)

    def visible_items(self, algorithm: Any | None = None) -> tuple[ContextItem, ...]:
        """Return model-visible primitives using an optional algorithm admission policy."""
        if algorithm is not None and hasattr(algorithm, "model_visible_context_primitives"):
            return tuple(algorithm.model_visible_context_primitives(self.items()))
        return sort_context_primitives(
            tuple(
                item
                for item in self.context_items
                if context_primitive_visibility(item) is ContextPrimitiveVisibility.MODEL
            )
        )

    def to_context(self, base_context: BaseContext | None = None, **overrides: Any) -> StrategyContext:
        """Convert managed items into an existing StrategyContext-compatible shape."""
        fields = _context_fields(base_context)
        fields.update(overrides)
        items = (*tuple(fields.get("context_items", ())), *self.items())
        metadata = {
            **dict(fields.get("metadata", {})),
            **dict(self.metadata),
            **dict(overrides.get("metadata", {})),
        }

        file_paths = list(fields.get("file_paths", ()))
        artifacts = list(fields.get("artifacts", ()))
        responses = list(fields.get("responses", ()))
        tool_calls = list(fields.get("tool_calls", ()))
        memory_parts: list[str] = []
        if fields.get("memory"):
            memory_parts.append(str(fields["memory"]))

        for item in self.items():
            if context_primitive_visibility(item) is not ContextPrimitiveVisibility.MODEL:
                continue
            primitive_metadata = {
                **dict(item.metadata),
                "context_primitive_id": context_primitive_id(item),
            }
            if isinstance(item, FileContextItem):
                file_paths.append(item.absolute_path)
                if item.content is not None or item.excerpt is not None:
                    artifacts.append(
                        ContextArtifact(
                            name=item.path,
                            content=item.content if item.content is not None else str(item.excerpt),
                            artifact_type="file",
                            metadata={**primitive_metadata, "absolute_path": item.absolute_path},
                        )
                    )
            elif isinstance(item, GitDiffContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "git_diff", primitive_metadata))
            elif isinstance(item, (IdentityContextItem, PlanContextItem, TaskContextItem)):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), item.kind, primitive_metadata))
            elif isinstance(item, DocumentContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "document", primitive_metadata))
            elif isinstance(item, EnvironmentContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "environment", primitive_metadata))
            elif isinstance(item, MemoryContextItem):
                memory_parts.append(item.to_context_text())
            elif isinstance(item, ProgressContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "progress", primitive_metadata))
            elif isinstance(item, ArtifactContextItem):
                artifacts.append(ContextArtifact(item.name, item.content, item.artifact_type, primitive_metadata))
            elif isinstance(item, ResponseContextItem):
                responses.append(ContextResponse(item.content, item.sender, primitive_metadata))
            elif isinstance(item, ToolCallContextItem):
                tool_calls.append(ContextToolCall(item.name, item.arguments, item.output, primitive_metadata))
            else:
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), item.kind, primitive_metadata))

        fields["file_paths"] = tuple(file_paths)
        fields["artifacts"] = tuple(artifacts)
        fields["responses"] = tuple(responses)
        fields["tool_calls"] = tuple(tool_calls)
        fields["memory"] = "\n\n".join(memory_parts) if memory_parts else None
        fields["context_items"] = tuple(items)
        fields["metadata"] = metadata
        return StrategyContext(**fields)


def _context_fields(context: BaseContext | None) -> dict[str, Any]:
    if context is None:
        return {
            "system_prompt": None,
            "agent_name": None,
            "role": None,
            "history": (),
            "file_paths": (),
            "tools": (),
            "strategy_metadata": {},
            "tool_calls": (),
            "responses": (),
            "budget": None,
            "artifacts": (),
            "memory": None,
            "permissions": None,
            "metadata": {},
            "context_items": (),
        }
    return {
        "system_prompt": context.system_prompt,
        "agent_name": context.agent_name,
        "role": context.role,
        "history": tuple(context.history),
        "file_paths": tuple(context.file_paths),
        "tools": tuple(context.tools),
        "strategy_metadata": dict(context.strategy_metadata),
        "tool_calls": tuple(context.tool_calls),
        "responses": tuple(context.responses),
        "budget": context.budget,
        "artifacts": tuple(context.artifacts),
        "memory": context.memory,
        "permissions": context.permissions,
        "metadata": dict(context.metadata),
        "context_items": tuple(context.context_items),
    }


__all__ = ["ContextManager"]
