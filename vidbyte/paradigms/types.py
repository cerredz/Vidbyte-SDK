"""Context Protocol Header

Path: vidbyte/paradigms/types.py
Purpose: Own settings shared by concrete paradigm families.
Architecture: AgentRoleSettings is the immutable construction envelope consumed by
paradigm-local role factories; concrete orchestration remains in each family.
Exports: AgentRoleSettings.
Invariants: Live tools and middleware are normalized to tuples, caller mappings are
copied, and overrides never mutate the original settings object.
Do not: Put task-graph, persistence, or family-specific policy in this module.
Related: docs/design/long-running-paradigm.md and vidbyte/paradigms/README.md.
Tests: Covered by the existing paradigm import/settings suite; no new tests are added
under the approved design-doc-no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentRoleSettings:
    """Per-role construction settings shared by paradigm harnesses."""

    name: str = ""
    system_prompt: str | None = None
    runner: object | None = None
    provider: str | None = None
    model_name: str | Sequence[str] | None = None
    api_key: str | None = None
    temperature: float | None = None
    tools: tuple[object, ...] = ()
    middleware: tuple[object, ...] = ()
    agent_options: Mapping[str, Any] = field(default_factory=dict)
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        # Freeze collection-shaped settings so one role run cannot pollute another.
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "tools", self._object_tuple(self.tools))
        object.__setattr__(self, "middleware", self._object_tuple(self.middleware))
        object.__setattr__(self, "agent_options", dict(self.agent_options))

    def with_overrides(self, **overrides: Any) -> "AgentRoleSettings":
        # Return a replacement while treating None as "keep the existing value."
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)

    @staticmethod
    def _object_tuple(value: object) -> tuple[object, ...]:
        # Normalize one object or a non-text sequence into the role's immutable list.
        if value is None:
            return ()
        all_items = getattr(value, "all", None)
        if callable(all_items):
            return tuple(all_items())
        if isinstance(value, tuple):
            return value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(value)
        return (value,)


__all__ = ["AgentRoleSettings"]
