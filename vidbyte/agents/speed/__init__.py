"""Context Protocol Header

Description:
    Public surface for agent speed tracking.
Purpose:
    Allows package-level imports of AgentSpeedTracker, mirroring
    vidbyte.agents.pricing's export of UsageTracker.
Architecture:
    - AgentSpeedTracker accumulates timed records into an AgentSpeedRollup.
    - Record/stats dataclasses live in vidbyte.lib.dataclasses.speed and are
      re-exported here so a caller of vidbyte.agents.speed gets everything in
      one import, mirroring vidbyte.agents.pricing's export of UsageTracker
      alongside UsageRecord/UsageRollup.
Relations:
    Imported by vidbyte.agents.base, vidbyte.agents.runtime, and the root package.
Similar Files:
    - vidbyte/agents/pricing/__init__.py
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
