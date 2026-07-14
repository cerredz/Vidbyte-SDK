"""Context Protocol Header

Description:
    Defines the Vidbyte paradigms namespace client.
Purpose:
    Owns public factories for concrete paradigm harness families while keeping the
    direct paradigm classes as the primary documented entry point.
Architecture:
    - ParadigmClient: Exposes context-minimal fanout and future paradigm families.
Relations:
    Instantiated by vidbyte.client.VidbyteSDK and exported through
    vidbyte.paradigms.
"""

from __future__ import annotations

from vidbyte.paradigms.context_minimal_fanout import ContextMinimalFanoutClient
from vidbyte.paradigms.long_running import LongRunningClient


class ParadigmClient:
    """Namespace client for paradigm harness factories."""

    def __init__(self) -> None:
        # Attaches concrete paradigm family clients to the root paradigm namespace.
        self.context_minimal_fanout = ContextMinimalFanoutClient()
        self.long_running = LongRunningClient()


__all__ = ["ParadigmClient"]
