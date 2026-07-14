"""Context Protocol Header

Path: vidbyte/tools/builtins/verified_context/contracts.py
Purpose: Define stable handles and a source protocol for expanding verified dependencies.
Architecture: VerifiedContextRef is capsule-visible metadata; VerifiedContextSource is
the trusted ledger/artifact resolver that rechecks task status and content hash.
Exports: VerifiedContextRef and VerifiedContextSource.
Invariants: Handles include kind/run/task/item/hash; summary is display-only and never
used as the source of expanded content.
Do not: Read files, infer task verification, or trust arbitrary handle text here.
Related: verified_context/load.py and paradigms/long_running/ledger.py.
Tests: Existing import verification plus inline smoke checks; no new tests by approval.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VerifiedContextRef:
    """Stable advertised handle for one verified task result or artifact."""

    kind: str
    run_id: str
    task_id: str
    item_id: str
    content_hash: str
    summary: str

    def handle(self) -> str:
        # Encode the exact identity fields without making the display summary authoritative.
        raw = json.dumps(
            {"kind": self.kind, "run_id": self.run_id, "task_id": self.task_id, "item_id": self.item_id, "content_hash": self.content_hash},
            ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
        return "vc_" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @classmethod
    def from_handle(cls, handle: str, *, summary: str = "") -> "VerifiedContextRef":
        # Decode one capsule handle and reject missing identity fields before source access.
        if not handle.startswith("vc_"):
            raise ValueError("Verified context handle must start with 'vc_'.")
        encoded = handle[3:]
        encoded += "=" * (-len(encoded) % 4)
        try:
            raw = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Verified context handle is malformed.") from exc
        required = ("kind", "run_id", "task_id", "item_id", "content_hash")
        if not isinstance(raw, dict) or any(not str(raw.get(key, "")).strip() for key in required):
            raise ValueError("Verified context handle is missing identity fields.")
        return cls(*(str(raw[key]).strip() for key in required), summary=summary)


class VerifiedContextSource(Protocol):
    """Trusted resolver for currently verified, hash-matched dependency content."""

    def load_verified(self, ref: VerifiedContextRef, *, allowed_task_ids: tuple[str, ...]) -> str:
        # Return content only after revalidating run, task, item, status, and hash.
        ...


__all__ = ["VerifiedContextRef", "VerifiedContextSource"]
