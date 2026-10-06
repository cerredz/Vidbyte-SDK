"""Context Protocol Header

Description:
    Defines enum contracts for artifact sources.
Purpose:
    Keeps source policy enums in the central SDK enum namespace.
Architecture:
    - PinPolicy: Determines whether a source load reuses a pinned snapshot or fetches live.
Relations:
    Imported by vidbyte.sources.base and public source package exports.
"""

from __future__ import annotations

from enum import Enum


class PinPolicy(str, Enum):
    """Determines whether a load reuses a pinned snapshot or always re-fetches."""

    PINNED = "pinned"
    LIVE = "live"


__all__ = [
    "PinPolicy",
]
