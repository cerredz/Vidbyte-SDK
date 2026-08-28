"""Context Protocol Header

Description:
    Implements the central ContextManager abstraction for structured context items.
Purpose:
    Provides a single developer-facing object for collecting standardized context
    items and converting them into existing SDK context dataclasses. Supports a
    dict-backed registry for addressable, window-resident managed primitives.
Architecture:
    - ContextManager: Ordered context item collection with registry for managed primitives.
    - Registry methods: upsert, get_by_id, remove_by_id, recite, upsert_preserving_placement,
      render_primitives_zone, render_conversation_messages.
    - Compatibility conversion from context items to BaseContext fields.
Relations:
    Used by BaseAgent/AgentRuntime and re-exported through vidbyte.context.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives import (
    ArtifactContextItem,
    ContextItem,
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    ToolCallContextItem,
)
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.dataclasses.context import (
    BaseContext,
    ContextArtifact,
    ContextResponse,
    ContextToolCall,
)


@dataclass(slots=True)
class ContextManager:
    """Ordered collection and compatibility bridge for context items, with a managed primitive registry."""

    context_items: Sequence[ContextItem] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    _registry: dict[str, ContextItem] = field(init=False, repr=False, default_factory=dict)
    _placements: dict[str, ContextWindowPlacement] = field(init=False, repr=False, default_factory=dict)
    _id_counters: dict[str, int] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        # Converts sequences to tuples and ensures metadata is a plain dict.
        self.context_items = tuple(self.context_items)
        self.metadata = dict(self.metadata)

    def upsert(self, item: ContextItem, *, placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT) -> "ContextManager":
        """Add or replace a managed primitive in the registry by its primitive_id."""
        # Stores an addressable primitive and its render placement.
        primitive_id = getattr(item, "primitive_id", None)
        if not primitive_id:
            raise ValueError(
                "upsert() requires a primitive with a non-empty primitive_id. "
                "Use add() for unmanaged context items."
            )
        existing = self._registry.get(primitive_id)
        if existing is not None and getattr(existing, "primitive_frozen", False):
            raise ValueError(
                f"Primitive '{primitive_id}' is frozen and cannot be overwritten. "
                "Set primitive_frozen=False to allow updates."
            )
        normalized_placement = ContextWindowPlacement(placement)
        self._registry[primitive_id] = item
        self._placements[primitive_id] = normalized_placement
        return self

    def place_after_system_prompt(self, item: ContextItem) -> str:
        """Place a primitive at the top of the context zone, just after the system prompt."""
        # Renders before default end-of-context primitives via TOP_OF_CONTEXT placement.
        return self._place(item, ContextWindowPlacement.TOP_OF_CONTEXT)

    def place_after_tools(self, item: ContextItem) -> str:
        """Place a primitive at the end of the context zone, after tool-bound primitives."""
        # Renders at the end of the primitives zone via END_OF_CONTEXT placement.
        return self._place(item, ContextWindowPlacement.END_OF_CONTEXT)

    def _place(self, item: ContextItem, placement: ContextWindowPlacement) -> str:
        """Upsert a primitive at a placement, generating a stable id when missing."""
        # Lets callers add a fresh primitive without minting their own ids.
        primitive_id = str(getattr(item, "primitive_id", "") or "").strip()
        if not primitive_id:
            primitive_id = self._generate_primitive_id(item)
            item = self._with_primitive_id(item, primitive_id)
        self.upsert(item, placement=placement)
        return primitive_id

    def _generate_primitive_id(self, item: ContextItem) -> str:
        """Build a deterministic id scoped to this manager and item kind."""
        kind = str(getattr(item, "kind", "context"))
        next_value = self._id_counters.get(kind, 0) + 1
        self._id_counters[kind] = next_value
        return f"{kind}:{next_value}"

    @staticmethod
    def _with_primitive_id(item: ContextItem, primitive_id: str) -> ContextItem:
        """Return a copy of a dataclass primitive with a primitive id attached."""
        if not dataclasses.is_dataclass(item):
            raise ValueError("place_*() requires a dataclass context item when primitive_id is missing.")
        return dataclasses.replace(item, primitive_id=primitive_id)

    def get_by_id(self, primitive_id: str) -> ContextItem | None:
        """Return the managed primitive with the given id, or None if not found."""
        return self._registry.get(primitive_id)

    def registry_items(self) -> tuple[tuple[str, ContextItem], ...]:
        """Return an ordered, read-only view of managed primitive registry entries."""
        return tuple(self._registry.items())

    def set_placement(self, primitive_id: str, placement: ContextWindowPlacement) -> "ContextManager":
        """Update the render placement for an existing managed primitive."""
        if primitive_id not in self._registry:
            raise ValueError(f"Primitive '{primitive_id}' does not exist in the context window registry.")
        self._placements[primitive_id] = ContextWindowPlacement(placement)
        return self

    def set_frozen(self, primitive_id: str, frozen: bool) -> "ContextManager":
        """Update the frozen flag for an existing managed primitive."""
        item = self._registry.get(primitive_id)
        if item is None:
            raise ValueError(f"Primitive '{primitive_id}' does not exist in the context window registry.")
        if not dataclasses.is_dataclass(item):
            raise ValueError(f"Primitive '{primitive_id}' is not a dataclass and cannot be frozen.")
        self._registry[primitive_id] = dataclasses.replace(item, primitive_frozen=bool(frozen))
        return self

    def remove_by_id(self, primitive_id: str) -> "ContextManager":
        """Remove the managed primitive with the given id; silently ignores missing ids."""
        self._registry.pop(primitive_id, None)
        self._placements.pop(primitive_id, None)
        return self

    def clear_registry(self) -> "ContextManager":
        """Remove all managed primitives from the registry."""
        self._registry.clear()
        self._placements.clear()
        self._id_counters.clear()
        return self

    def placement_for(self, primitive_id: str) -> ContextWindowPlacement | None:
        """Return the render placement for a managed primitive id."""
        # Exposes placement metadata without exposing the mutable placement registry.
        return self._placements.get(primitive_id)

    def upsert_preserving_placement(self, item: ContextItem) -> "ContextManager":
        """Re-upsert a managed primitive using its prior placement when known."""
        # Defaults to END_OF_CONTEXT when the id has no stored placement yet.
        primitive_id = getattr(item, "primitive_id", None)
        if not primitive_id:
            raise ValueError(
                "upsert_preserving_placement() requires a primitive with a non-empty primitive_id."
            )
        placement = self.placement_for(str(primitive_id)) or ContextWindowPlacement.END_OF_CONTEXT
        return self.upsert(item, placement=placement)

    def recite(self, primitive_id: str, *, slot_id: str | None = None) -> str:
        """Copy a managed primitive to END_OF_CONVERSATION under a recitation id."""
        # Leaves the source id/placement unchanged; returns the recitation slot id used.
        source = self.get_by_id(primitive_id)
        if source is None:
            raise ValueError(f"Unknown primitive '{primitive_id}'.")
        if not dataclasses.is_dataclass(source):
            raise ValueError(f"Primitive '{primitive_id}' is not a dataclass and cannot be recited.")
        target_id = (slot_id or "").strip() or f"recite:{primitive_id}"
        replace_kwargs: dict[str, Any] = {"primitive_id": target_id, "primitive_frozen": False}
        field_names = {f.name for f in dataclasses.fields(source)}
        if "title" in field_names:
            title = str(getattr(source, "title", "") or "")
            replace_kwargs["title"] = title if title.startswith("Recite: ") else f"Recite: {title}"
        copy = dataclasses.replace(source, **replace_kwargs)
        self.upsert(copy, placement=ContextWindowPlacement.END_OF_CONVERSATION)
        return target_id

    def render_primitives_zone(self) -> str:
        """Return a formatted block of all registry primitives in insertion order."""
        visible = self._items_for_context_zone()
        if not visible:
            return ""
        sections: list[str] = ["## Context Window Primitives"]
        for primitive_id, item in visible:
            header = f"### [{primitive_id}] {item.title}"
            sections.append(f"{header}\n{item.to_context_text()}")
        return "\n\n".join(sections)

    def render_conversation_messages(self, placement: ContextWindowPlacement) -> tuple[dict[str, str], ...]:
        """Return managed primitives for a conversation placement as provider messages."""
        # Converts conversation-placed primitives into assistant messages for the next call.
        normalized_placement = ContextWindowPlacement(placement)
        messages: list[dict[str, str]] = []
        for primitive_id, item in self._registry.items():
            if self._placements.get(primitive_id, ContextWindowPlacement.END_OF_CONTEXT) is normalized_placement:
                messages.append({"role": "assistant", "content": item.to_context_text()})
        return tuple(messages)

    def _items_for_context_zone(self) -> list[tuple[str, ContextItem]]:
        """Return primitives that should render in the system context zone."""
        # Keeps top-of-context entries before default end-of-context entries.
        top: list[tuple[str, ContextItem]] = []
        end: list[tuple[str, ContextItem]] = []
        for primitive_id, item in self._registry.items():
            placement = self._placements.get(primitive_id, ContextWindowPlacement.END_OF_CONTEXT)
            if placement is ContextWindowPlacement.TOP_OF_CONTEXT:
                top.append((primitive_id, item))
            elif placement is ContextWindowPlacement.END_OF_CONTEXT:
                end.append((primitive_id, item))
        return [*top, *end]

    def add(self, item: ContextItem) -> "ContextManager":
        """Append one unmanaged context item and return this manager."""
        self.context_items = (*tuple(self.context_items), item)
        return self

    def extend(self, items: Iterable[ContextItem]) -> "ContextManager":
        """Append many unmanaged context items and return this manager."""
        self.context_items = (*tuple(self.context_items), *tuple(items))
        return self

    def remove(self, item: ContextItem) -> "ContextManager":
        """Remove one matching unmanaged context item and return this manager."""
        items = list(self.context_items)
        items.remove(item)
        self.context_items = tuple(items)
        return self

    def clear(self) -> "ContextManager":
        """Remove all unmanaged context items; does not touch the registry."""
        self.context_items = ()
        return self

    def items(self) -> tuple[ContextItem, ...]:
        """Return only the unmanaged context items in insertion order."""
        return tuple(self.context_items)

    def by_kind(self, kind: str) -> tuple[ContextItem, ...]:
        """Return all unmanaged context items matching a kind."""
        return tuple(item for item in self.context_items if item.kind == kind)

    def to_context(self, base_context: BaseContext | None = None, **overrides: Any) -> BaseContext:
        """Convert unmanaged items into a BaseContext-compatible shape."""
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
            if isinstance(item, FileContextItem):
                file_paths.append(item.absolute_path)
                if item.content is not None or item.excerpt is not None:
                    artifacts.append(
                        ContextArtifact(
                            name=item.path,
                            content=item.content if item.content is not None else str(item.excerpt),
                            artifact_type="file",
                            metadata={**dict(item.metadata), "absolute_path": item.absolute_path},
                        )
                    )
            elif isinstance(item, GitDiffContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "git_diff", item.metadata))
            elif isinstance(item, TaskContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "task", item.metadata))
            elif isinstance(item, DocumentContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "document", item.metadata))
            elif isinstance(item, EnvironmentContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "environment", item.metadata))
            elif isinstance(item, MemoryContextItem):
                memory_parts.append(item.to_context_text())
            elif isinstance(item, ProgressContextItem):
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), "progress", item.metadata))
            elif isinstance(item, ArtifactContextItem):
                artifacts.append(ContextArtifact(item.name, item.content, item.artifact_type, item.metadata))
            elif isinstance(item, ResponseContextItem):
                responses.append(ContextResponse(item.content, item.sender, item.metadata))
            elif isinstance(item, ToolCallContextItem):
                tool_calls.append(ContextToolCall(item.name, item.arguments, item.output, item.metadata))
            else:
                artifacts.append(ContextArtifact(item.title, item.to_context_text(), item.kind, item.metadata))

        fields["file_paths"] = tuple(file_paths)
        fields["artifacts"] = tuple(artifacts)
        fields["responses"] = tuple(responses)
        fields["tool_calls"] = tuple(tool_calls)
        fields["memory"] = "\n\n".join(memory_parts) if memory_parts else None
        fields["context_items"] = tuple(items)
        fields["metadata"] = metadata
        return BaseContext(**fields)


def _context_fields(context: BaseContext | None) -> dict[str, Any]:
    if context is None:
        return {
            "system_prompt": None,
            "agent_name": None,
            "role": None,
            "history": (),
            "file_paths": (),
            "tools": (),
            "run_metadata": {},
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
        "run_metadata": dict(context.run_metadata),
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
