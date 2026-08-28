"""Context Protocol Header

Description:
    Defines the schema version, default store cap, and validation bounds
    AgentKeys is built with.
Purpose:
    Keeps AgentKeys' tunable constants alongside every other SDK constant
    instead of as private module attributes local to one dataclass file.
Architecture:
    - AGENT_KEYS_SCHEMA_VERSION: envelope schema version stamped on every
      AgentKeys entry, bumped only on an incompatible envelope shape change.
    - DEFAULT_MAX_STORE_ENTRIES: default FIFO eviction cap for one AgentKeys
      instance's in-memory store.
    - AGENT_KEYS_MAX_* and AGENT_KEYS_*_TEMPERATURE: shared bounds for the
      strictly validated identity and settings dataclasses.
Relations:
    Consumed by vidbyte.agents.settings.keys.AgentKeys and
    vidbyte.lib.dataclasses.agent_keys.
"""

from __future__ import annotations

AGENT_KEYS_SCHEMA_VERSION = 1
DEFAULT_MAX_STORE_ENTRIES = 2000
AGENT_KEYS_MAX_AGENT_NAME_CHARS = 1024
AGENT_KEYS_MAX_MODEL_NAME_CHARS = 1024
AGENT_KEYS_MAX_RUN_ID_CHARS = 1024
AGENT_KEYS_MAX_SYSTEM_PROMPT_CHARS = 1_000_000
AGENT_KEYS_MAX_DESCRIPTION_CHARS = 10_000
AGENT_KEYS_MAX_ALGORITHM_CHARS = 512
AGENT_KEYS_MAX_CAPABILITY_CHARS = 512
AGENT_KEYS_MAX_CAPABILITIES = 128
AGENT_KEYS_MAX_CONTRACT_NAME_CHARS = 512
AGENT_KEYS_MAX_PERMISSION_CHARS = 512
AGENT_KEYS_MIN_TEMPERATURE = 0.0
AGENT_KEYS_MAX_TEMPERATURE = 2.0

__all__ = [
    "AGENT_KEYS_MAX_AGENT_NAME_CHARS",
    "AGENT_KEYS_MAX_ALGORITHM_CHARS",
    "AGENT_KEYS_MAX_CAPABILITIES",
    "AGENT_KEYS_MAX_CAPABILITY_CHARS",
    "AGENT_KEYS_MAX_CONTRACT_NAME_CHARS",
    "AGENT_KEYS_MAX_DESCRIPTION_CHARS",
    "AGENT_KEYS_MAX_MODEL_NAME_CHARS",
    "AGENT_KEYS_MAX_PERMISSION_CHARS",
    "AGENT_KEYS_MAX_RUN_ID_CHARS",
    "AGENT_KEYS_MAX_SYSTEM_PROMPT_CHARS",
    "AGENT_KEYS_MAX_TEMPERATURE",
    "AGENT_KEYS_MIN_TEMPERATURE",
    "AGENT_KEYS_SCHEMA_VERSION",
    "DEFAULT_MAX_STORE_ENTRIES",
]
