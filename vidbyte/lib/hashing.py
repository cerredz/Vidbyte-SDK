"""Context Protocol Header

Description:
    Defines Hashing, the canonical source of every canonicalize-and-hash
    primitive used across the SDK.
Purpose:
    Replaces four independent hand-rolled implementations of "canonicalize to
    JSON, sha256, sometimes truncate" (vidbyte/agents/settings/tool.py,
    vidbyte/middleware/builtins/loop_detection.py,
    vidbyte/agents/settings/keys.py, and
    vidbyte/agents/algorithms/prosecutor_defender_judge.py) with one static
    helper class, so no other module hand-rolls hashing again.
Architecture:
    - CanonicalJsonInput/Output, HexDigestInput/Output, StableKeyInput/Output:
      one request/response dataclass pair per Hashing static method.
    - Hashing: static-method-only class exposing canonical_json, hex_digest,
      and stable_key.
Relations:
    Used by vidbyte.agents.settings.keys.AgentKeys,
    vidbyte.agents.settings.tool.ToolSettings.fingerprint,
    vidbyte.middleware.builtins.loop_detection.LoopDetectionMiddleware, and
    vidbyte.agents.algorithms.prosecutor_defender_judge. Has no dependency on
    BaseAgent or any agent-bound object, so it is safe to import from objects
    (like ToolSettings) constructed before any agent exists.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CanonicalJsonInput:
    """Input for Hashing.canonical_json."""

    value: Any


@dataclass(frozen=True, slots=True)
class CanonicalJsonOutput:
    """Output of Hashing.canonical_json."""

    text: str


@dataclass(frozen=True, slots=True)
class HexDigestInput:
    """Input for Hashing.hex_digest."""

    text: str
    length: int | None = None


@dataclass(frozen=True, slots=True)
class HexDigestOutput:
    """Output of Hashing.hex_digest."""

    digest: str


@dataclass(frozen=True, slots=True)
class StableKeyInput:
    """Input for Hashing.stable_key."""

    prefix: str
    payload: Any
    length: int = 16


@dataclass(frozen=True, slots=True)
class StableKeyOutput:
    """Output of Hashing.stable_key."""

    key: str


class Hashing:
    """Canonical static-method source of every canonicalize-and-hash primitive in the SDK."""

    @staticmethod
    def canonical_json(request: CanonicalJsonInput) -> CanonicalJsonOutput:
        """Serialize a value into deterministic JSON: sorted keys, non-native values stringified via default=str."""
        try:
            text = json.dumps(request.value, sort_keys=True, default=str)
        except Exception:
            text = str(request.value)
        return CanonicalJsonOutput(text=text)

    @staticmethod
    def hex_digest(request: HexDigestInput) -> HexDigestOutput:
        """Return the lowercase sha256 hex digest of text, truncated to length hex characters if given."""
        digest = hashlib.sha256(request.text.encode()).hexdigest()
        return HexDigestOutput(digest=digest if request.length is None else digest[: request.length])

    @staticmethod
    def stable_key(request: StableKeyInput) -> StableKeyOutput:
        """Build the "prefix:short-digest" shape used by in-memory dedup/loop-detection callers."""
        serialized = Hashing.canonical_json(CanonicalJsonInput(value=request.payload)).text
        digest = Hashing.hex_digest(HexDigestInput(text=serialized, length=request.length)).digest
        return StableKeyOutput(key=f"{request.prefix}:{digest}")


__all__ = [
    "CanonicalJsonInput",
    "CanonicalJsonOutput",
    "HexDigestInput",
    "HexDigestOutput",
    "Hashing",
    "StableKeyInput",
    "StableKeyOutput",
]
