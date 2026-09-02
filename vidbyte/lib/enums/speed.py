"""FILE: vidbyte/lib/enums/speed.py

PURPOSE:
    Defines AgentSpeedRecordingIntegrity, the speed-tracking analog of
    UsageRecordingIntegrity. Lets AgentSpeedRollup distinguish "no calls
    happened" from "calls happened but a metering bug lost data."

ROLE IN CODEBASE:
    Imported by vidbyte/lib/dataclasses/speed.py (AgentSpeedRollup's
    recording_integrity field) and vidbyte/agents/speed/tracker.py
    (AgentSpeedTracker.rollup builds this enum's value). Re-exported from
    vidbyte/lib/enums/__init__.py.

ARCHITECTURE NOTE:
    A two-value lifecycle flag with no behavior, mirroring
    vidbyte/agents/pricing/records.py's UsageRecordingIntegrity exactly so
    both trackers report failure the same way.

FUNCTION INVENTORY:
    AgentSpeedRecordingIntegrity: str Enum with INTACT and CORRUPTED members.
    No functions; the enum has no test file of its own and is covered through
    AgentSpeedTracker's tests.

COMMON MODIFICATION PATTERNS:
    Do not add members here without updating AgentSpeedTracker.rollup's
    corrupted-flag logic and AgentSpeedRollup's docstring in the same change.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add behavior or methods; this is a pure lifecycle flag.
    2. Do not duplicate UsageRecordingIntegrity; the two trackers are
       intentionally separate enums even though their values are identical.

KNOWN EDGE CASES:
    None; a two-member enum has no ambiguous states.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-speed-tracking.md

TESTS:
    tests/test_agent_speed.py (AgentSpeedTrackerRollupTests exercises both
    INTACT and CORRUPTED via AgentSpeedTracker.rollup()).
"""

from __future__ import annotations

from enum import Enum


class AgentSpeedRecordingIntegrity(str, Enum):
    """Whether every attempted speed-tracking record actually reached the run's ledgers."""

    INTACT = "intact"
    CORRUPTED = "corrupted"


__all__ = ["AgentSpeedRecordingIntegrity"]
