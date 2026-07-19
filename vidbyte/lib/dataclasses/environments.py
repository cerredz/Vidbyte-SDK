"""Context Protocol Header

Description:
    Reusable immutable dataclasses for the environments package that belong in
    the central Vidbyte lib namespace rather than a feature module.
Purpose:
    Keeps environment result contracts alongside the SDK's other shared
    dataclasses so they can be imported without depending on the environments
    runtime, matching the lib.dataclasses convention.
Architecture:
    - AuditReport: Frozen outcome of an EnvironmentAudit (baseline scores,
      determinism verdict, and notes).
Relations:
    Re-exported (compatibility shim) by vidbyte.environments.audit, which owns
    the EnvironmentAudit runner that produces it.
Similar Files:
    - vidbyte/lib/dataclasses/runner.py: Equivalent shared result dataclasses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuditReport:
    """Outcome of an environment audit: baseline scores, determinism, and notes."""

    env_name: str
    env_version: str
    ok: bool
    baseline_scores: Mapping[str, float]
    deterministic: bool
    notes: tuple[str, ...] = field(default_factory=tuple)


__all__ = [
    "AuditReport",
]
