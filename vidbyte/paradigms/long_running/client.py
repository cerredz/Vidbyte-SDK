"""Context Protocol Header

Path: vidbyte/paradigms/long_running/client.py
Purpose: Provide namespace-client construction for LongRunningParadigm.
Architecture: LongRunningClient is a thin callable factory used by ParadigmClient.
Exports: LongRunningClient.
Invariants: Both call surfaces construct the real paradigm with unchanged kwargs.
Do not: Start runs, cache harness state, or silently alter settings.
Related: vidbyte/paradigms/client.py and long_running/paradigm.py.
Tests: Existing namespace-client import verification; no new tests by approval.
"""

from __future__ import annotations

from typing import Any

from vidbyte.paradigms.long_running.paradigm import LongRunningParadigm


class LongRunningClient:
    """Factory namespace for durable long-running paradigm harnesses."""

    def __call__(self, **kwargs: Any) -> LongRunningParadigm:
        # Match other SDK namespace clients with a concise callable surface.
        return self.create(**kwargs)

    def create(self, **kwargs: Any) -> LongRunningParadigm:
        # Construct a real independent harness without retaining live run state.
        return LongRunningParadigm(**kwargs)


__all__ = ["LongRunningClient"]
