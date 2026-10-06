"""Semantic tracing schema for Vidbyte trace profiles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.lib.tracing import SpanContext


class TraceDetail(str, Enum):
    """Trace detail thresholds used by profile presets."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    VERBOSE = "verbose"
    DIAGNOSTIC = "diagnostic"


class SpanKind(str, Enum):
    """Provider-neutral span kinds that map to tracing provider categories."""

    CHAIN = "chain"
    LLM = "llm"
    TOOL = "tool"
    RETRIEVER = "retriever"
    EMBEDDING = "embedding"
    PROMPT = "prompt"
    PARSER = "parser"


class ParentPolicy(str, Enum):
    """Semantic parent-resolution policies for component span specs."""

    EXPLICIT = "explicit"
    CURRENT = "current"
    AGENT = "agent"
    RUNTIME_ITERATION = "runtime_iteration"
    AGGREGATE = "aggregate"
    SESSION = "session"
    ROOT = "root"


@dataclass(frozen=True, slots=True)
class SpanSpec:
    """Provider-neutral description of one Vidbyte semantic span."""

    name: str
    kind: SpanKind = SpanKind.CHAIN
    component: str = "core"
    detail: TraceDetail = TraceDetail.MINIMAL
    parent_policy: ParentPolicy = ParentPolicy.CURRENT
    attributes: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def with_attributes(self, **attributes: Any) -> SpanSpec:
        # Returns a copy with merged semantic attributes.
        return SpanSpec(
            name=self.name,
            kind=self.kind,
            component=self.component,
            detail=self.detail,
            parent_policy=self.parent_policy,
            attributes={**dict(self.attributes), **attributes},
            metadata=dict(self.metadata),
        )


@dataclass(slots=True)
class SemanticSpanContext(SpanContext):
    """SpanContext wrapper that keeps semantic and provider state together."""

    provider_context: SpanContext | None = None
    spec: SpanSpec | None = None
    suppressed: bool = False


__all__ = [
    "ParentPolicy",
    "SemanticSpanContext",
    "SpanKind",
    "SpanSpec",
    "TraceDetail",
]
