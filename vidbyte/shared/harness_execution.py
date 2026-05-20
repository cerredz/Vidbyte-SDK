from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class HarnessRole(str, Enum):
    """Known roles that can write to a harness ledger."""

    BLUE = "blue"
    RED = "red"
    JUDGE = "judge"
    PURIFIER = "purifier"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One model-visible or system-visible harness event."""

    role: HarnessRole
    kind: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FilteredContextView:
    """Role-specific context assembled from the master ledger."""

    role: HarnessRole
    entries: list[LedgerEntry] = field(default_factory=list)
    redaction_rules: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArtifactRevision:
    """Immutable revision of the artifact under construction or attack."""

    revision: int
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ModelFunction(Protocol):
    """Async model callable accepted by harness pipelines."""

    def __call__(
        self,
        prompt: str,
        *,
        context: Sequence[LedgerEntry],
        tools: Sequence[object],
    ) -> Awaitable[str]: ...


__all__ = [
    "ArtifactRevision",
    "FilteredContextView",
    "HarnessRole",
    "LedgerEntry",
    "ModelFunction",
]
