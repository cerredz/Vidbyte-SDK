"""Context Protocol Header

Path: vidbyte/tools/builtins/verified_context/load.py
Purpose: Expand one advertised verified dependency result/artifact into fresh role context.
Architecture: VerifiedContextLoadTool binds advertised handles, allowed task ids, a
trusted source, one ContextManager, and cumulative expansion budgets.
Exports: VerifiedContextLoadTool.
Invariants: Permission is READ; unadvertised, unrelated, duplicate, oversized, stale,
or hash-mismatched content is rejected before context mutation.
Do not: Read arbitrary paths, accept raw content from the model, or expose full content
again in ToolResult.
Related: verified_context/contracts.py and paradigms/long_running/context.py.
Tests: Existing tool verification and inline smoke checks only under no-tests approval.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.context import ContextManager
from vidbyte.context.primitives import MemoryContextItem
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.verified_context.contracts import VerifiedContextRef, VerifiedContextSource
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class VerifiedContextLoadTool(BaseTool):
    """Load one allowlisted currently verified dependency into role context."""

    def __init__(self, source: VerifiedContextSource, context_manager: ContextManager, *, allowed_task_ids: Sequence[str], available_refs: Sequence[VerifiedContextRef] = (), max_loaded_items: int = 3, max_total_loaded_chars: int = 30000, max_item_chars: int = 16000) -> None:
        # Bind the capsule allowlist and cumulative budget to one fresh role instance.
        if min(max_loaded_items, max_total_loaded_chars, max_item_chars) < 1:
            raise ValueError("VerifiedContextLoadTool limits must be positive.")
        self.source = source
        self.context_manager = context_manager
        self.allowed_task_ids = tuple(dict.fromkeys(str(item) for item in allowed_task_ids))
        self.available_refs = {ref.handle(): ref for ref in available_refs}
        self.max_loaded_items = max_loaded_items
        self.max_total_loaded_chars = max_total_loaded_chars
        self.max_item_chars = max_item_chars
        self._loaded: set[str] = set()
        self._loaded_chars = 0

    @property
    def loaded_refs(self) -> tuple[VerifiedContextRef, ...]:
        # Expose authoritative successful expansions for audit records.
        return tuple(self.available_refs[handle] for handle in self.available_refs if handle in self._loaded)

    def spec(self) -> ToolSpec:
        # Declare one read-only expansion by a handle already visible in the capsule.
        return ToolSpec(
            name="verified_context_load",
            description="Load one advertised verified dependency result or artifact into context. Unadvertised handles are rejected.",
            permission=ToolPermission.READ,
            parameters=(ToolParameter("handle", "string", "Stable vc_ handle from the current context capsule."),),
            binds_to_primitive="memory",
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Recheck the advertised handle through the source before one bounded context write.
        try:
            handle = str(call.arguments["handle"]).strip()
            ref = self.available_refs.get(handle)
            if ref is None:
                raise ValueError("Verified context handle was not advertised in this role capsule.")
            if handle in self._loaded:
                return ToolResult.success(self.name, f"Verified context item {ref.item_id} is already loaded.", metadata={"already_loaded": True, "handle": handle})
            if ref.task_id not in self.allowed_task_ids:
                raise ValueError("Verified context handle belongs to a task outside this role's dependency scope.")
            content = self.source.load_verified(ref, allowed_task_ids=self.allowed_task_ids)
            self._assert_budget(len(content))
            primitive_id = f"verified-context:{ref.content_hash}"
            self.context_manager.upsert(
                MemoryContextItem(
                    title=f"Verified {ref.kind}: {ref.item_id}",
                    content="\n".join(("<untrusted_verified_context>", content, "</untrusted_verified_context>")),
                    source=f"verified-context:{ref.run_id}/{ref.task_id}/{ref.item_id}",
                    metadata={"content_hash": ref.content_hash, "kind": ref.kind, "untrusted_reference": True},
                    primitive_id=primitive_id, primitive_frozen=True,
                )
            )
            self._loaded.add(handle)
            self._loaded_chars += len(content)
            return ToolResult.success(self.name, f"Loaded verified context item {ref.item_id} as {primitive_id}.", metadata={"primitive_id": primitive_id, "handle": handle, "loaded_chars": len(content)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error_type": exc.__class__.__name__})

    def _assert_budget(self, content_chars: int) -> None:
        # Reject the expansion before mutation when item/count/cumulative limits fail.
        if content_chars > self.max_item_chars:
            raise ValueError(f"Verified context item has {content_chars} characters; maximum is {self.max_item_chars}.")
        if len(self._loaded) >= self.max_loaded_items:
            raise ValueError(f"Verified context load count would exceed maximum {self.max_loaded_items}.")
        if self._loaded_chars + content_chars > self.max_total_loaded_chars:
            raise ValueError(f"Verified context would exceed cumulative maximum {self.max_total_loaded_chars} characters.")


__all__ = ["VerifiedContextLoadTool"]
