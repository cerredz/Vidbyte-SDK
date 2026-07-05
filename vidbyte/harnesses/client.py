from __future__ import annotations

from vidbyte.sessions.client import SessionClient


class HarnessClient:
    """Namespace client for custom harness integrations."""

    def __init__(self) -> None:
        # Expose the durable-sessions namespace under sdk.harnesses.sessions.
        self.sessions = SessionClient()
