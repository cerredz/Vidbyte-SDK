"""FILE: vidbyte/agents/speed/__init__.py

PURPOSE:
    Public surface for agent speed tracking. Allows package-level imports of
    AgentSpeedTracker and its dataclasses, mirroring
    vidbyte/agents/pricing/__init__.py's export of UsageTracker alongside
    UsageRecord/UsageRollup.

ROLE IN CODEBASE:
    Imported by vidbyte/agents/base.py, vidbyte/agents/runtime.py,
    vidbyte/agents/__init__.py, and the package root vidbyte/__init__.py.
    Re-exports AgentSpeedTracker from vidbyte/agents/speed/tracker.py and
    every speed dataclass from vidbyte/lib/dataclasses/speed.py.

ARCHITECTURE NOTE:
    A thin package export with no logic of its own, structurally identical to
    vidbyte/agents/pricing/__init__.py.

FUNCTION INVENTORY:
    No functions; re-exports AgentSpeedTracker and the speed dataclasses. See
    vidbyte/agents/speed/tracker.py and vidbyte/lib/dataclasses/speed.py for
    their own inventories.

COMMON MODIFICATION PATTERNS:
    When a new dataclass is added to vidbyte/lib/dataclasses/speed.py, add it
    to both the import and __all__ here in the same change, mirroring
    vidbyte/lib/dataclasses/__init__.py's own export of the same symbol.

WHAT NOT TO DO IN THIS FILE:
    1. Do not define AgentSpeedTracker or any dataclass here directly; they
       belong in tracker.py and vidbyte/lib/dataclasses/speed.py respectively.
    2. Do not add import-time side effects.

KNOWN EDGE CASES:
    None.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-speed-tracking.md

TESTS:
    tests/test_agent_speed.py imports every symbol re-exported here.
"""

from __future__ import annotations

from vidbyte.agents.speed.tracker import AgentSpeedTracker
from vidbyte.lib.dataclasses.speed import (
    AgentSpeedRollup,
    CallSpeedRecord,
    CallSpeedStats,
    RecordModelCallInput,
    RecordStepInput,
    RecordToolCallInput,
    RunSpeedStats,
    StepSpeedRecord,
    StepSpeedStats,
    ToolCallSpeedRecord,
    ToolCallSpeedStats,
)

__all__ = [
    "AgentSpeedRollup",
    "AgentSpeedTracker",
    "CallSpeedRecord",
    "CallSpeedStats",
    "RecordModelCallInput",
    "RecordStepInput",
    "RecordToolCallInput",
    "RunSpeedStats",
    "StepSpeedRecord",
    "StepSpeedStats",
    "ToolCallSpeedRecord",
    "ToolCallSpeedStats",
]
