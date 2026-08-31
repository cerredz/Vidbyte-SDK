"""Context Protocol Header

Description:
    Defines the recording-integrity enum for agent speed tracking.
Purpose:
    Lets AgentSpeedRollup distinguish "no calls happened" from "calls happened
    but a metering bug lost data," mirroring UsageRecordingIntegrity.
Architecture:
    - AgentSpeedRecordingIntegrity: two-value lifecycle flag on AgentSpeedRollup.
Relations:
    Consumed by vidbyte.lib.dataclasses.speed and vidbyte.agents.speed.tracker.
Similar Files:
    - vidbyte/agents/pricing/records.py (UsageRecordingIntegrity)
"""

from __future__ import annotations

from enum import Enum


class AgentSpeedRecordingIntegrity(str, Enum):
    """Whether every attempted speed-tracking record actually reached the run's ledgers."""

    INTACT = "intact"
    CORRUPTED = "corrupted"


__all__ = ["AgentSpeedRecordingIntegrity"]
