"""Context-window semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class ContextTrace:
    """Factory for context-window and context primitive spans."""

    @staticmethod
    def window_build(**attributes: Any) -> SpanSpec:
        # Describes context-window construction for an iteration.
        return SpanSpec("context.window.build", SpanKind.PROMPT, "context", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def primitive_render(**attributes: Any) -> SpanSpec:
        # Describes context primitive rendering.
        return SpanSpec("context.primitive.render", SpanKind.PROMPT, "context", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def compaction(**attributes: Any) -> SpanSpec:
        # Describes context compaction or truncation.
        return SpanSpec("context.compaction", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def update(**attributes: Any) -> SpanSpec:
        # Describes a context object update.
        return SpanSpec("context.update", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def manager_upsert(**attributes: Any) -> SpanSpec:
        # Describes a ContextManager upsert operation.
        return SpanSpec("context.manager.upsert", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def manager_extend(**attributes: Any) -> SpanSpec:
        # Describes a ContextManager extend operation.
        return SpanSpec("context.manager.extend", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def primitive_add(**attributes: Any) -> SpanSpec:
        # Describes a context primitive being added.
        return SpanSpec("context.primitive.add", SpanKind.CHAIN, "context", TraceDetail.DIAGNOSTIC, ParentPolicy.AGENT, attributes)

    @staticmethod
    def primitive_remove(**attributes: Any) -> SpanSpec:
        # Describes a context primitive being removed.
        return SpanSpec("context.primitive.remove", SpanKind.CHAIN, "context", TraceDetail.DIAGNOSTIC, ParentPolicy.AGENT, attributes)

    @staticmethod
    def compaction_trigger(**attributes: Any) -> SpanSpec:
        # Describes context compaction being triggered by a token threshold.
        return SpanSpec("context.compaction.trigger", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def compaction_strategy(**attributes: Any) -> SpanSpec:
        # Describes which compaction strategy was selected.
        return SpanSpec("context.compaction.strategy", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def template_record(**attributes: Any) -> SpanSpec:
        # Describes a context template recorder capturing a template.
        return SpanSpec("context.template.record", SpanKind.CHAIN, "context", TraceDetail.DIAGNOSTIC, ParentPolicy.AGENT, attributes)

    @staticmethod
    def handoff_sync(**attributes: Any) -> SpanSpec:
        # Describes a handoff being synced to the context registry.
        return SpanSpec("context.handoff.sync", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)


__all__ = ["ContextTrace"]
