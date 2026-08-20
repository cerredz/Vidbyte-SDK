"""Context Protocol Header

Description:
    Defines the shared canonicalize-and-hash primitives used everywhere in the
    agents/middleware layers that need a stable, deterministic string key.
Purpose:
    Replaces four independent hand-rolled implementations of "canonicalize to
    JSON, sha256, sometimes truncate" with one pure, stateless module.
Architecture:
    - canonical_json: deterministic JSON serialization.
    - hex_digest: sha256 hex digest, optionally truncated.
    - stable_key: the common "prefix:16-hex-digest" shape most callers want.
Relations:
    Used by ToolSettings.fingerprint, AgentKeys, LoopDetectionMiddleware,
    MultiAgentOrchestratorLedger, and ProsecutorDefenderJudgeAlgorithm. Has no
    dependency on BaseAgent or any agent-bound object, so it is safe to import
    from objects (like ToolSettings) that are constructed before any agent exists.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    # Deterministic JSON: sorted keys, non-native values stringified via default=str.
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except Exception:
        return str(value)


def hex_digest(text: str, *, length: int | None = None) -> str:
    # Lowercase sha256 hex digest of text, truncated to length hex characters if given.
    digest = hashlib.sha256(text.encode()).hexdigest()
    return digest if length is None else digest[:length]


def stable_key(prefix: str, payload: Any, *, length: int = 16) -> str:
    # Builds the "prefix:short-digest" shape used by in-memory dedup/loop-detection callers.
    return f"{prefix}:{hex_digest(canonical_json(payload), length=length)}"


__all__ = ["canonical_json", "hex_digest", "stable_key"]
