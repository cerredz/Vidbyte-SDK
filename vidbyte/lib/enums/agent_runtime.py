"""FILE: vidbyte/lib/enums/agent_runtime.py

PURPOSE:
    Defines the stable enum contracts for selecting agent runtime families and
    naming reserved per-run runtime state keys. This module contains enum values
    only; execution remains in ``vidbyte/agents/runtime.py``.

ROLE IN CODEBASE:
    Re-exported by ``vidbyte/lib/enums/__init__.py`` and consumed by agent
    configuration and the direct runtime. ``AgentRuntimeStateKey`` is the
    canonical source for runtime-owned dictionary handoff keys.

ARCHITECTURE NOTE:
    String-backed enums preserve compatibility with serialized configuration and
    dictionary boundaries while giving callers named SDK constants.

FUNCTION INVENTORY:
    ``AgentRuntimeStateKey`` -> reserved runtime-state key enum.
    ``AgentRuntimeType`` -> configured runtime-family enum.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add runtime behavior or mutable execution state; keep it in the
       owning runtime module.
    2. Do not rename existing enum values without a compatibility migration.

TEST FILES:
    Runtime and configuration tests cover enum use through their public paths.
"""

from __future__ import annotations

from enum import Enum


class AgentRuntimeStateKey(str, Enum):
    """Reserved keys for data published through one agent runtime run state."""

    ITERATION_OUTPUTS = "__iteration_outputs__"
    RESULT_METADATA = "__result_metadata__"


class AgentRuntimeType(str, Enum):
    """String-backed enum class representing the swappable agent loops."""

    LINEAR = "linear"
    MCTS_SEARCH = "mcts_search"
    ACTOR_MODEL = "actor_model"
    ACTOR_MODEL_P2P = "actor_model_p2p"
    ACTOR_MODEL_BROADCAST = "actor_model_broadcast"


__all__ = ["AgentRuntimeStateKey", "AgentRuntimeType"]
