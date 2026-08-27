"""Context Protocol Header

Description:
    Compatibility vocabulary for verifier runtime pillars and legacy imports.
Purpose:
    Keeps the small execution enums local while forwarding shared contracts to
    their lower-layer dataclass owner without creating an import cycle.
Role in codebase:
    Preserves the public ``verifier.types`` import path used by existing
    verifier pillars and downstream callers.
Architecture note:
    Shared enums and dataclasses are resolved lazily from
    ``vidbyte.lib.dataclasses.verifier``; the concrete dependency stays
    downward in the runtime graph.
Common modification patterns:
    Add shared contracts to the lib dataclass module and list their names in
    ``__all__``; retain local execution enums only when behavior owns them.
Known edge cases:
    Module-level ``__getattr__`` intentionally returns a dynamic compatibility
    value for re-exported names, which is safe because imports are immutable.
Related docs:
    docs/design/verifier-runtime.md; docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by the verifier runtime and package import smoke tests.
"""

from __future__ import annotations

from enum import Enum
from importlib import import_module
from typing import Any


_DATACLASSES_MODULE = "vidbyte.lib.dataclasses.verifier"


class VerifierExecutionMode(str, Enum):
    """How VerifierCollection dispatches verifiers within one tier."""

    SEQUENTIAL = "sequential"
    PARALLEL_WITHIN_TIER = "parallel_within_tier"
    COST_ORDERED = "cost_ordered"


class GateTrigger(str, Enum):
    """When VerifierRuntimeGate.should_fire considers this loop moment a checkpoint."""

    ON_FINALIZATION_ONLY = "on_finalization_only"
    ON_EVERY_ITERATION = "on_every_iteration"
    ON_EXPLICIT_SIGNAL = "on_explicit_signal"
    ON_TIER_BOUNDARY = "on_tier_boundary"


def __getattr__(name: str) -> Any:
    """Resolve shared contracts lazily so this compatibility module stays acyclic."""

    return getattr(import_module(_DATACLASSES_MODULE), name)


__all__ = [
    "GateTrigger",
    "VerifierExecutionMode",
]
