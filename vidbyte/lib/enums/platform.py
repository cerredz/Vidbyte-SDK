from __future__ import annotations

from enum import Enum


class Platform(str, Enum):
    """Execution platform for SDK filesystem tools."""

    LOCAL = "local"
    DOCKER = "docker"
    E2B = "e2b"
    WASM = "wasm"
    MODAL = "modal"
    DAYTONA = "daytona"
    FLY = "fly"


__all__ = [
    "Platform",
]
