"""FILE: lint/core/baseline.py

PURPOSE: Implements the per-rule debt ratchet used by the SDK lint suite.
ROLE IN CODEBASE: Lets blocking rules ship without permitting any new debt.
ARCHITECTURE NOTE: Missing/stale keys are invalid outside explicit baseline updates.
FUNCTION INVENTORY: BaselineStore load/write/validate; verdict_for compares counts.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py and source CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from lint.core.discovery import repo_root

Verdict = Literal["CLEAN", "RATCHETED", "IMPROVED", "REGRESSED", "ERRORED"]


class BaselineContractError(RuntimeError):
    """Baseline file is malformed or disagrees with the registered catalogue."""


class BaselineStore:
    """Reads, validates, and deterministically writes rule allowances."""

    def __init__(self, path: Path | None = None) -> None:
        # Binds the store to lint/baseline.json unless explicitly overridden.
        self.path = path or repo_root() / "lint" / "baseline.json"

    def load(self) -> dict[str, int]:
        # Parses non-negative integer allowances with actionable file context.
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BaselineContractError(f"Could not read valid JSON baseline {self.path}: {exc}. Restore a sorted rule-to-count object.") from exc
        if not isinstance(payload, dict) or any(not isinstance(key, str) or not isinstance(value, int) or value < 0 for key, value in payload.items()):
            raise BaselineContractError(f"Baseline {self.path} must map every rule ID to a non-negative integer.")
        return dict(payload)

    def validate(self, registered: set[str]) -> None:
        # Rejects both missing and stale IDs so a rule cannot silently escape the ratchet.
        actual = set(self.load())
        if actual != registered:
            raise BaselineContractError(f"Baseline catalogue mismatch at {self.path}: missing={sorted(registered - actual)}, stale={sorted(actual - registered)}. Run --update-baseline only after reviewing every new rule finding.")

    def write(self, counts: dict[str, int]) -> None:
        # Rewrites the complete sorted catalogue using UTF-8 and a trailing newline.
        ordered = {key: counts[key] for key in sorted(counts)}
        self.path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def verdict_for(found: int, allowance: int) -> Verdict:
    # Classifies a full finding count against its immutable debt ceiling.
    if found > allowance:
        return "REGRESSED"
    if found == allowance == 0:
        return "CLEAN"
    if found == allowance:
        return "RATCHETED"
    return "IMPROVED"
