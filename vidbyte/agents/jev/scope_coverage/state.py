"""FILE: vidbyte/agents/jev/scope_coverage/state.py

PURPOSE: Owns the scope section of JevRunState: one JevScopeDimension per group the request asks a change to cover.
ROLE IN CODEBASE: JevRunStateBuilderAgent fills this section once per run; the handoff builder, questions, and check read it.
ARCHITECTURE NOTE: Every quoted field is validated against the original request in code, so a hallucinated scope fails closed.
COMMON MODIFICATION PATTERNS: Change a field together with output_schema, the state_builder_scope_coverage.md asset, and tests.
KNOWN EDGE CASES: Empty strings mean "none" for partial_allowed_quote and deliverable_id because strict schemas avoid nullable fields.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from vidbyte.agents.jev.scope_coverage.enums import JevScopeBreadth, JevScopeUniverse

SCOPE_DIMENSION_ID_PATTERN: str = r"[a-z][a-z0-9_]{0,63}"
MIN_NAMED_LIST_UNITS: int = 2


def normalize_scope_text(value: str) -> str:
    """Collapse whitespace and case so verbatim-quote checks tolerate formatting only."""
    return " ".join(value.split()).casefold()


def scope_texts_match(left: str, right: str) -> bool:
    """Return whether two unit names are the same after whitespace and case normalization."""
    # @intent exact-unit-identity
    # Containment would let "web" match "webhook" and silently shrink the required set, so only normalized equality counts.
    normalized = normalize_scope_text(left)
    return bool(normalized) and normalized == normalize_scope_text(right)


@dataclass(frozen=True, slots=True)
class JevScopeDimension:
    """One group the request asks a change to reach, with its members and how to recognize them."""

    id: str
    request_quote: str
    requested_change: str
    unit_noun: str
    membership_rule: str
    breadth: JevScopeBreadth
    universe: JevScopeUniverse
    named_units: tuple[str, ...]
    excluded_units: tuple[str, ...]
    partial_allowed_quote: str
    deliverable_id: str
    breadth_upgraded: bool = False

    def is_checked(self) -> bool:
        """Return whether the finish check must verify coverage of this dimension."""
        return self.breadth.is_checked() and not self.partial_allowed_quote

    def is_excluded(self, unit: str) -> bool:
        """Return whether the request explicitly excluded this unit."""
        return any(scope_texts_match(unit, excluded) for excluded in self.excluded_units)

    def required_named_units(self) -> tuple[str, ...]:
        """Return the named units that the request did not also exclude."""
        return tuple(unit for unit in self.named_units if not self.is_excluded(unit))

    def upgraded(self, breadth: JevScopeBreadth) -> JevScopeDimension:
        """Return a copy widened by the Jev breadth review, keeping the universe consistent."""
        # @intent widened-dimension-stays-valid
        # A widened dimension must still satisfy the named_list and universe rules enforced at parse time, or the handoff schema and required set disagree.
        universe = self.universe
        if breadth is JevScopeBreadth.NAMED_LIST and (universe is not JevScopeUniverse.NAMED_IN_REQUEST or len(self.named_units) < MIN_NAMED_LIST_UNITS):
            breadth = JevScopeBreadth.EVERY_MEMBER
        if universe is JevScopeUniverse.NAMED_IN_REQUEST and not self.named_units:
            universe = JevScopeUniverse.FOUND_IN_WORKSPACE
        return replace(self, breadth=breadth, universe=universe, breadth_upgraded=True)

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-compatible dimension shared with the handoff builder."""
        # @intent payload-mirrors-validated-fields
        # Builders see exactly the validated request-grounded fields; breadth_upgraded stays internal so the handoff cannot argue with the review.
        return {
            "id": self.id,
            "request_quote": self.request_quote,
            "requested_change": self.requested_change,
            "unit_noun": self.unit_noun,
            "membership_rule": self.membership_rule,
            "breadth": self.breadth.value,
            "universe": self.universe.value,
            "named_units": list(self.named_units),
            "excluded_units": list(self.excluded_units),
            "partial_allowed_quote": self.partial_allowed_quote,
            "deliverable_id": self.deliverable_id,
        }


@dataclass(frozen=True, slots=True)
class JevScopeSection:
    """Every coverage dimension the original request states."""

    dimensions: tuple[JevScopeDimension, ...]

    def checked_dimensions(self) -> tuple[JevScopeDimension, ...]:
        """Return the dimensions the finish check verifies."""
        return tuple(item for item in self.dimensions if item.is_checked())

    def with_dimensions(self, dimensions: Sequence[JevScopeDimension]) -> JevScopeSection:
        """Return a copy holding replacement dimensions in the same order."""
        return JevScopeSection(tuple(dimensions))

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-compatible section."""
        return {"dimensions": [item.to_payload() for item in self.dimensions]}

    @classmethod
    def from_payload(cls, payload: object, *, original_request: str, deliverable_ids: Sequence[str]) -> JevScopeSection:
        """Validate generated dimensions against the verbatim request and known deliverable IDs."""
        # @intent ground-scope-in-request
        # Quotes, unit names, and permissions must be copied from the request so the check never enforces an invented scope.
        if not isinstance(payload, Mapping):
            raise ValueError("scope must be an object")
        raw = payload.get("dimensions")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValueError("scope.dimensions must be an array")
        request = normalize_scope_text(original_request)
        dimensions = tuple(cls._dimension(item, request, tuple(deliverable_ids)) for item in raw)
        identifiers = [item.id for item in dimensions]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("scope.dimensions IDs must be unique")
        return cls(dimensions)

    @staticmethod
    def output_schema() -> dict[str, Any]:
        """Return the strict structured-output schema for the scope section."""
        text = {"type": "string", "minLength": 1}
        optional_text = {"type": "string"}
        texts = {"type": "array", "items": text}
        dimension = {
            "type": "object",
            "properties": {
                "id": text,
                "request_quote": text,
                "requested_change": text,
                "unit_noun": text,
                "membership_rule": text,
                "breadth": {"type": "string", "enum": JevScopeBreadth.values()},
                "universe": {"type": "string", "enum": JevScopeUniverse.values()},
                "named_units": texts,
                "excluded_units": texts,
                "partial_allowed_quote": optional_text,
                "deliverable_id": optional_text,
            },
            "required": ["id", "request_quote", "requested_change", "unit_noun", "membership_rule", "breadth", "universe", "named_units", "excluded_units", "partial_allowed_quote", "deliverable_id"],
            "additionalProperties": False,
        }
        return {"type": "object", "properties": {"dimensions": {"type": "array", "items": dimension}}, "required": ["dimensions"], "additionalProperties": False}

    @classmethod
    def _dimension(cls, value: object, request: str, deliverable_ids: tuple[str, ...]) -> JevScopeDimension:
        # Converts one generated dimension and enforces the request-grounding and breadth/universe rules.
        # @intent breadth-universe-consistency
        # Every quoted field is checked against the request and breadth/universe pairs are enforced, so a mislabeled scope fails closed before the run.
        if not isinstance(value, Mapping):
            raise ValueError("each scope dimension must be an object")
        identifier = cls._text(value.get("id"), "scope.id")
        if re.fullmatch(SCOPE_DIMENSION_ID_PATTERN, identifier) is None:
            raise ValueError("scope dimension IDs must start with a lowercase letter and contain only lowercase letters, digits, or underscores")
        quote = cls._quoted(value.get("request_quote"), "scope.request_quote", request)
        named = tuple(cls._quoted(item, "scope.named_units", request) for item in cls._list(value.get("named_units"), "scope.named_units"))
        excluded = tuple(cls._quoted(item, "scope.excluded_units", request) for item in cls._list(value.get("excluded_units"), "scope.excluded_units"))
        partial = cls._optional(value.get("partial_allowed_quote"), "scope.partial_allowed_quote")
        if partial:
            cls._quoted(partial, "scope.partial_allowed_quote", request)
        deliverable_id = cls._optional(value.get("deliverable_id"), "scope.deliverable_id")
        if deliverable_id and deliverable_id not in deliverable_ids:
            raise ValueError(f"scope.deliverable_id {deliverable_id!r} does not name a multipart deliverable")
        try:
            breadth = JevScopeBreadth(value.get("breadth"))
            universe = JevScopeUniverse(value.get("universe"))
        except ValueError as exc:
            raise ValueError("scope.breadth or scope.universe is not an allowed value") from exc
        if breadth is JevScopeBreadth.NAMED_LIST and (universe is not JevScopeUniverse.NAMED_IN_REQUEST or len(named) < MIN_NAMED_LIST_UNITS):
            raise ValueError(f"a named_list scope must use universe named_in_request and name at least {MIN_NAMED_LIST_UNITS} units")
        if universe is JevScopeUniverse.NAMED_IN_REQUEST and not named:
            raise ValueError("a named_in_request scope must name at least one unit")
        return JevScopeDimension(
            id=identifier,
            request_quote=quote,
            requested_change=cls._text(value.get("requested_change"), "scope.requested_change"),
            unit_noun=cls._text(value.get("unit_noun"), "scope.unit_noun"),
            membership_rule=cls._text(value.get("membership_rule"), "scope.membership_rule"),
            breadth=breadth,
            universe=universe,
            named_units=named,
            excluded_units=excluded,
            partial_allowed_quote=partial,
            deliverable_id=deliverable_id,
        )

    @staticmethod
    def _text(value: object, field_name: str) -> str:
        # Requires a non-blank string and returns it stripped.
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-blank string")
        return value.strip()

    @staticmethod
    def _optional(value: object, field_name: str) -> str:
        # Accepts an empty string as "none" and strips any other text.
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string (use an empty string for none)")
        return value.strip()

    @staticmethod
    def _list(value: object, field_name: str) -> tuple[object, ...]:
        # Requires a JSON array without accepting a bare string as a sequence of characters.
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError(f"{field_name} must be an array of strings")
        return tuple(value)

    @classmethod
    def _quoted(cls, value: object, field_name: str, request: str) -> str:
        # Requires text that appears in the original request after whitespace and case normalization.
        # @intent verbatim-within-normalization
        # Only whitespace and case differences are forgiven; any word difference is a fabricated quote and must fail the run closed.
        text = cls._text(value, field_name)
        if normalize_scope_text(text) not in request:
            raise ValueError(f"{field_name} value {text!r} is not quoted from the original request")
        return text


__all__ = ["JevScopeDimension", "JevScopeSection", "normalize_scope_text", "scope_texts_match"]
