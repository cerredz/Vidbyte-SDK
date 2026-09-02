"""Context Protocol Header

Description:
    Defines the structured ActorMessage class for message passing between concurrent actors.
Purpose:
    Enables reliable context, state, and conversation propagation across concurrent actors
    in both Point-to-Point and Broadcast topologies.
Architecture:
    - ActorMessage: Frozen dataclass mapping message ID, sender, recipient, content, parent task, and local state.
Relations:
    Located in vidbyte/agents/runtimes/actor/message.py. Replaces primitive string loops.
Similar Files:
    - vidbyte/agents/types.py: Core agent execution types.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ActorMessage:
    """Represents a structured, serializable message passed between concurrent actors."""

    message_id: str
    sender: str
    recipient: str  # Specific actor_id, "all", or "system"
    content: str
    parent_task_id: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
