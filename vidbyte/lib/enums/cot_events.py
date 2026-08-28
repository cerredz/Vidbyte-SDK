"""Context Protocol Header

FILE: vidbyte/lib/enums/cot_events.py

PURPOSE: Defines the stable categorical vocabulary for the five deep chain-of-
thought event tools. The enum values are serialized into tool arguments,
context primitives, and observability metadata, so this module owns their
canonical spelling and does not own parsing or tool execution.

ROLE IN CODEBASE: `vidbyte/tools/builtins/cot_events.py` validates model input
against these enums, while `vidbyte/lib/constants/cot_events.py` derives the
shared defaults and bounds that accompany them. Context primitives render the
enum values as plain strings for compatibility with existing context windows.

ARCHITECTURE NOTE: These enums live in `vidbyte.lib` because the vocabulary is
an SDK contract shared by model-facing schemas and runtime records. Keeping
the values here prevents a tool module from becoming the source of truth for
public categorical data.

FUNCTION INVENTORY: `CotEventEnum.values()` returns the tuple of serialized
values for one enum class. The concrete enum classes expose only their stable
string members and do not raise errors during normal access.

COMMON MODIFICATION PATTERNS: Add a new category here first, then update the
tool description, parser call, primitive rendering, and design document that
consume it. Preserve the serialized value once released because metadata and
stored context may contain it.

WHAT NOT TO DO IN THIS FILE:
1. Do not parse tool arguments; parsing belongs to `cot_events.py` in the
   builtins package.
2. Do not add runtime policy or context-manager behavior; those belong to the
   tool and primitive layers.
3. Do not rename a serialized value without a compatibility decision for
   existing observability records.

KNOWN EDGE CASES: Enum members are also strings, but callers should serialize
`.value` or use `values()` rather than relying on enum display formatting.

RELATED DOCS: `https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/deep-cot-tools.md`
describes the event vocabulary and lifecycle.

AUTO-GENERATED FLAG: No; maintained source data.

TEST FILES: No dedicated test file exists in the source PR; import and value
smoke checks are part of resolver verification.

CONCURRENCY MODEL: Immutable enum definitions; no shared mutable state.
"""

from __future__ import annotations

from enum import Enum


class CotEventEnum(str, Enum):
    """Base enum that exposes canonical serialized values."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the serialized values in declaration order."""
        return tuple(member.value for member in cls)


class HypothesisStatus(CotEventEnum):
    """Lifecycle status for a recorded hypothesis."""

    PROPOSED = "proposed"
    SUPPORTED = "supported"
    WEAKENED = "weakened"
    FALSIFIED = "falsified"


class BasisType(CotEventEnum):
    """Kind of support behind a hypothesis."""

    EVIDENCE = "evidence"
    INFERENCE = "inference"
    PRIOR = "prior"


class Reversibility(CotEventEnum):
    """Cost category for reversing a decision."""

    YES = "yes"
    NO = "no"
    COSTLY = "costly"


class AssumptionAction(CotEventEnum):
    """Lifecycle action recorded for an assumption."""

    DECLARED = "declared"
    VERIFIED = "verified"
    FALSIFIED = "falsified"


class ImpactLevel(CotEventEnum):
    """Blast-radius category when an assumption is wrong."""

    FATAL = "fatal"
    MAJOR = "major"
    MINOR = "minor"


class ProgressState(CotEventEnum):
    """Directional progress state for an uncertainty snapshot."""

    PROGRESSING = "progressing"
    STALLED = "stalled"
    REGRESSING = "regressing"


class ReturnableOption(CotEventEnum):
    """Whether an abandoned path can be revisited."""

    YES = "yes"
    NO = "no"


__all__ = [
    "AssumptionAction",
    "BasisType",
    "CotEventEnum",
    "HypothesisStatus",
    "ImpactLevel",
    "ProgressState",
    "ReturnableOption",
    "Reversibility",
]
