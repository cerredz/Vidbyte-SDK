"""FILE: vidbyte/agents/jev/scope_coverage/handoff.py

PURPOSE: Owns the scope section of JevRunHandoff: a per-unit account of the run for every checked scope dimension.
ROLE IN CODEBASE: JevRunHandoffBuilderAgent fills this section at each finish attempt; ScopeCoverageDoneCheck reads it.
ARCHITECTURE NOTE: The handoff reports cited observations only. It carries no verdict, and code recomputes each unit's source.
COMMON MODIFICATION PATTERNS: Change a field together with output_schema, the handoff_builder_scope_coverage.md asset, and tests.
KNOWN EDGE CASES: A found_by_run unit whose name is absent from every enumeration excerpt is demoted to mentioned_by_agent.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vidbyte.agents.jev.evidence import (
    FINAL_ANSWER_SOURCE_ID,
    ITERATION_SOURCE_PREFIX,
    TOOL_CALL_SOURCE_PREFIX,
    JevEvidenceReference,
)
from vidbyte.agents.jev.scope_coverage.enums import JevScopeUnitSource
from vidbyte.agents.jev.scope_coverage.state import (
    JevScopeDimension,
    JevScopeSection,
    normalize_scope_text,
    scope_texts_match,
)

ENUMERATION_SOURCES: tuple[str, ...] = (TOOL_CALL_SOURCE_PREFIX,)
WORK_SOURCES: tuple[str, ...] = (ITERATION_SOURCE_PREFIX, TOOL_CALL_SOURCE_PREFIX)
NARROWING_SOURCES: tuple[str, ...] = (ITERATION_SOURCE_PREFIX, FINAL_ANSWER_SOURCE_ID)
CLAIM_SOURCES: tuple[str, ...] = (FINAL_ANSWER_SOURCE_ID,)


@dataclass(frozen=True, slots=True)
class JevScopeUnitRecord:
    """One member of a scope group and the cited actions the run took on it."""

    unit: str
    source: JevScopeUnitSource
    work: tuple[JevEvidenceReference, ...]

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-compatible record."""
        return {"unit": self.unit, "source": self.source.value, "work": [item.to_payload() for item in self.work]}


@dataclass(frozen=True, slots=True)
class JevScopeDimensionHandoff:
    """The run's cited account of one checked scope dimension."""

    dimension_id: str
    enumeration: tuple[JevEvidenceReference, ...]
    units: tuple[JevScopeUnitRecord, ...]
    narrowing: tuple[JevEvidenceReference, ...]
    coverage_claims: tuple[JevEvidenceReference, ...]

    def required_units(self, dimension: JevScopeDimension) -> tuple[JevScopeUnitRecord, ...]:
        """Return the units the change must reach: named or listed by the run, minus exclusions."""
        # @intent required-set-from-verified-sources
        # Only named or listing-verified units are required, minus explicit exclusions; mentioned_by_agent units must never widen the scope beyond the request.
        required = (JevScopeUnitSource.NAMED_IN_REQUEST, JevScopeUnitSource.FOUND_BY_RUN)
        return tuple(item for item in self.units if item.source in required and not dimension.is_excluded(item.unit))

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-compatible dimension account."""
        return {
            "dimension_id": self.dimension_id,
            "enumeration": [item.to_payload() for item in self.enumeration],
            "units": [item.to_payload() for item in self.units],
            "narrowing": [item.to_payload() for item in self.narrowing],
            "coverage_claims": [item.to_payload() for item in self.coverage_claims],
        }


@dataclass(frozen=True, slots=True)
class JevScopeHandoff:
    """Scope accounts for exactly the checked dimensions of one generated JevScopeSection."""

    dimensions: tuple[JevScopeDimensionHandoff, ...]

    def by_id(self) -> Mapping[str, JevScopeDimensionHandoff]:
        """Return dimension accounts keyed by their state dimension IDs."""
        return {item.dimension_id: item for item in self.dimensions}

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-compatible section."""
        return {"dimensions": [item.to_payload() for item in self.dimensions]}

    @classmethod
    def from_payload(cls, payload: object, section: JevScopeSection, sources: Mapping[str, str]) -> JevScopeHandoff:
        """Validate coverage of checked dimensions, citations, and named units before any Jev request."""
        # @intent scope-handoff-covers-every-named-unit
        # A handoff that drops a named member would hide exactly the narrowing this check exists to catch.
        if not isinstance(payload, Mapping):
            raise ValueError("handoff.scope must be an object")
        raw = payload.get("dimensions")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValueError("handoff.scope.dimensions must be an array")
        checked = {item.id: item for item in section.checked_dimensions()}
        accounts = []
        for value in raw:
            if not isinstance(value, Mapping):
                raise ValueError("each handoff.scope dimension must be an object")
            identifier = value.get("dimension_id")
            dimension = checked.get(identifier) if isinstance(identifier, str) else None
            if dimension is None:
                raise ValueError(f"handoff.scope names unknown or unchecked dimension {identifier!r}")
            accounts.append(cls._dimension(value, dimension, sources))
        actual = [item.dimension_id for item in accounts]
        if len(set(actual)) != len(actual) or set(actual) != set(checked):
            raise ValueError(f"handoff.scope IDs must exactly match checked dimensions; expected {sorted(checked)}, got {sorted(actual)}")
        by_id = {item.dimension_id: item for item in accounts}
        return cls(tuple(by_id[item.id] for item in section.checked_dimensions()))

    @staticmethod
    def output_schema(section: JevScopeSection) -> dict[str, Any]:
        """Return the strict schema requiring one account per checked dimension."""
        text = {"type": "string", "minLength": 1}
        refs = {"type": "array", "items": JevEvidenceReference.schema()}
        unit = {
            "type": "object",
            "properties": {"unit": text, "source": {"type": "string", "enum": JevScopeUnitSource.values()}, "work": refs},
            "required": ["unit", "source", "work"],
            "additionalProperties": False,
        }
        dimension = {
            "type": "object",
            "properties": {"dimension_id": text, "enumeration": refs, "units": {"type": "array", "items": unit}, "narrowing": refs, "coverage_claims": refs},
            "required": ["dimension_id", "enumeration", "units", "narrowing", "coverage_claims"],
            "additionalProperties": False,
        }
        count = len(section.checked_dimensions())
        return {
            "type": "object",
            "properties": {"dimensions": {"type": "array", "items": dimension, "minItems": count, "maxItems": count}},
            "required": ["dimensions"],
            "additionalProperties": False,
        }

    @classmethod
    def _dimension(cls, value: Mapping[str, Any], dimension: JevScopeDimension, sources: Mapping[str, str]) -> JevScopeDimensionHandoff:
        # Parses one account, recomputes unit sources in code, and requires every named unit.
        enumeration = cls._refs(value.get("enumeration"), sources, "handoff.scope.enumeration", ENUMERATION_SOURCES)
        listed = " ".join(normalize_scope_text(item.excerpt) for item in enumeration)
        raw_units = value.get("units")
        if not isinstance(raw_units, Sequence) or isinstance(raw_units, (str, bytes)):
            raise ValueError("handoff.scope.units must be an array")
        units = tuple(cls._unit(item, dimension, listed, sources) for item in raw_units)
        names = [normalize_scope_text(item.unit) for item in units]
        if len(set(names)) != len(names):
            raise ValueError(f"handoff.scope.units repeats a unit in dimension {dimension.id!r}")
        missing = [name for name in dimension.required_named_units() if not any(scope_texts_match(name, item.unit) for item in units)]
        if missing:
            raise ValueError(f"handoff.scope dimension {dimension.id!r} omits named units {missing}")
        return JevScopeDimensionHandoff(
            dimension_id=dimension.id,
            enumeration=enumeration,
            units=units,
            narrowing=cls._refs(value.get("narrowing"), sources, "handoff.scope.narrowing", NARROWING_SOURCES),
            coverage_claims=cls._refs(value.get("coverage_claims"), sources, "handoff.scope.coverage_claims", CLAIM_SOURCES),
        )

    @classmethod
    def _unit(cls, value: object, dimension: JevScopeDimension, listed: str, sources: Mapping[str, str]) -> JevScopeUnitRecord:
        # Parses one unit and replaces the generated source label with the one code can verify.
        # @intent code-owns-unit-source
        # The generated source label is replaced by what code can verify; trusting it would let the handoff shrink or inflate the required set.
        if not isinstance(value, Mapping):
            raise ValueError("each handoff.scope unit must be an object")
        name = value.get("unit")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("handoff.scope.units.unit must be a non-blank string")
        name = name.strip()
        try:
            claimed = JevScopeUnitSource(value.get("source"))
        except ValueError as exc:
            raise ValueError("handoff.scope.units.source is not an allowed value") from exc
        if any(scope_texts_match(name, named) for named in dimension.named_units):
            source = JevScopeUnitSource.NAMED_IN_REQUEST
        elif claimed is JevScopeUnitSource.FOUND_BY_RUN and normalize_scope_text(name) in listed:
            source = JevScopeUnitSource.FOUND_BY_RUN
        else:
            source = JevScopeUnitSource.MENTIONED_BY_AGENT
        work = cls._refs(value.get("work"), sources, "handoff.scope.units.work", WORK_SOURCES)
        return JevScopeUnitRecord(name, source, work)

    @staticmethod
    def _refs(value: object, sources: Mapping[str, str], field_name: str, allowed: tuple[str, ...]) -> tuple[JevEvidenceReference, ...]:
        # Parses an array of exact citations restricted to the source kinds this field may cite.
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError(f"{field_name} must be an array")
        return tuple(JevEvidenceReference.parse(item, sources, field_name=field_name, allowed=allowed) for item in value)


__all__ = ["JevScopeDimensionHandoff", "JevScopeHandoff", "JevScopeUnitRecord"]
