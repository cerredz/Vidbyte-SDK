"""Context Protocol Header

Description:
    Defines the schema version and default store cap AgentKeys is built with.
Purpose:
    Keeps AgentKeys' tunable constants alongside every other SDK constant
    instead of as private module attributes local to one file.
Architecture:
    - AGENT_KEYS_SCHEMA_VERSION: envelope schema version stamped on every
      AgentKeys entry, bumped only on an incompatible envelope shape change.
    - DEFAULT_MAX_STORE_ENTRIES: default FIFO eviction cap for one AgentKeys
      instance's in-memory store.
Relations:
    Consumed by vidbyte.agents.settings.keys.AgentKeys.
"""

from __future__ import annotations

AGENT_KEYS_SCHEMA_VERSION = 1
DEFAULT_MAX_STORE_ENTRIES = 2000

__all__ = [
    "AGENT_KEYS_SCHEMA_VERSION",
    "DEFAULT_MAX_STORE_ENTRIES",
]
