"""FILE: vidbyte/agents/jev/evidence.py

PURPOSE: Owns the exact-excerpt evidence reference shared by every Jev done-check handoff section.
ROLE IN CODEBASE: run_state.py (multipart) and scope_coverage/handoff.py parse handoff citations through JevEvidenceReference.parse.
ARCHITECTURE NOTE: Kept apart from run_state.py so section modules can import it without a circular import through JevRunHandoff.
COMMON MODIFICATION PATTERNS: Add a new source kind by extending JevRunSnapshot.evidence_sources and the prefix constants together.
KNOWN EDGE CASES: Excerpts must match their source exactly; a paraphrase or an unknown source ID fails the whole handoff.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md and docs/design/jev-scope-coverage-done-criteria.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ITERATION_SOURCE_PREFIX: str = "iteration_"
TOOL_CALL_SOURCE_PREFIX: str = "tool_call_"
FINAL_ANSWER_SOURCE_ID: str = "final_answer"


@dataclass(frozen=True, slots=True)
class JevEvidenceReference:
    """One exact excerpt tied to a known iteration, tool call, or final-answer source."""

    source_id: str
    excerpt: str

    @classmethod
    def parse(cls, value: object, sources: Mapping[str, str], *, field_name: str, allowed: tuple[str, ...] = ()) -> JevEvidenceReference:
        """Validate one generated citation against the snapshot's exact source text."""
        # @intent reject-invented-evidence
        # A fluent fabricated sentence or a citation of the wrong source kind must never reach a Jev state.
        if not isinstance(value, Mapping):
            raise TypeError(f"each {field_name} reference must be an object")
        source_id = value.get("source_id")
        excerpt = value.get("excerpt")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError(f"{field_name}.source_id must be a non-blank string")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ValueError(f"{field_name}.excerpt must be a non-blank string")
        source_id = source_id.strip()
        excerpt = excerpt.strip()
        source = sources.get(source_id)
        if source is None:
            raise ValueError(f"unknown evidence source ID {source_id!r} in {field_name}")
        if excerpt not in source:
            raise ValueError(f"{field_name} excerpt is not present in source {source_id!r}")
        if allowed and not any(source_id == kind or source_id.startswith(kind) for kind in allowed):
            raise ValueError(f"{field_name} must cite one of {list(allowed)}, got {source_id!r}")
        return cls(source_id, excerpt)

    @staticmethod
    def schema() -> dict[str, Any]:
        """Return the strict structured-output schema of one citation."""
        text = {"type": "string", "minLength": 1}
        return {"type": "object", "properties": {"source_id": text, "excerpt": text}, "required": ["source_id", "excerpt"], "additionalProperties": False}

    def to_payload(self) -> dict[str, str]:
        """Return the JSON-compatible citation."""
        return {"source_id": self.source_id, "excerpt": self.excerpt}


__all__ = ["FINAL_ANSWER_SOURCE_ID", "ITERATION_SOURCE_PREFIX", "TOOL_CALL_SOURCE_PREFIX", "JevEvidenceReference"]
