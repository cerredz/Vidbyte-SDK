"""FILE: vidbyte/lib/enums/reasoning_strategies.py

PURPOSE: Defines the closed-vocabulary categorical values validated by the 25 batch-2 reasoning-strategy builtin tools. This module owns their canonical spelling only; it does not validate tool arguments or render context.
ROLE IN CODEBASE: Each module under vidbyte/tools/builtins/reasoning/ imports the enum classes it needs from here and passes ClassName.values() to ReasoningToolInput.enum_error().
ARCHITECTURE NOTE: These enums live in vidbyte.lib because the vocabulary is an SDK contract shared by model-facing schemas, matching the existing vidbyte/lib/enums/cot_events.py precedent and the centralize-categorical-vocabularies convention in field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
COMMON MODIFICATION PATTERNS: Add a new category here first, then update the owning tool's ToolParameter description and design-doc requirement so the model-facing schema and the enum stay synchronized.
WHAT NOT TO DO: Do not parse tool arguments here; parsing belongs to ReasoningToolInput.enum_error() in the owning tool module. Do not add runtime policy or context-manager behavior.
KNOWN EDGE CASES: Enum members are also strings, but callers should use .values() rather than relying on enum display formatting.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from enum import Enum


class ReasoningStrategyEnum(str, Enum):
    """Base enum that exposes canonical serialized values."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the serialized values in declaration order."""
        return tuple(member.value for member in cls)


class AbsenceEvidenceSignificance(ReasoningStrategyEnum):
    """What an evidentiary absence implies for the hypothesis under test."""

    EVIDENCE_AGAINST = "evidence_against"
    NEUTRAL = "neutral"
    EVIDENCE_FOR = "evidence_for"


class BurdenOfProofVerdict(ReasoningStrategyEnum):
    """Resolution of who carried the burden of proof."""

    ESTABLISHED = "established"
    NOT_ESTABLISHED = "not_established"
    CONTESTED = "contested"


class CircularityVerdict(ReasoningStrategyEnum):
    """Whether an argument's dependency chain returns to its own conclusion."""

    CIRCULAR = "circular"
    NOT_CIRCULAR = "not_circular"
    PARTIALLY = "partially"


class CompositionDivisionValidity(ReasoningStrategyEnum):
    """Whether a part-whole property transfer is valid or a named fallacy."""

    VALID = "valid"
    FALLACY_OF_COMPOSITION = "fallacy_of_composition"
    FALLACY_OF_DIVISION = "fallacy_of_division"
    UNKNOWN = "unknown"


class ConsistencyStatus(ReasoningStrategyEnum):
    """Whether a claim set holds together without contradiction."""

    CONSISTENT = "consistent"
    CONTRADICTORY = "contradictory"
    UNRESOLVED = "unresolved"


class DefeasibleRuleApplies(ReasoningStrategyEnum):
    """Whether a default rule applies to the case once defeaters are checked."""

    YES = "yes"
    NO = "no"
    BORDERLINE = "borderline"


class EquivocationFallacy(ReasoningStrategyEnum):
    """Whether an argument's validity depends on a term shifting sense."""

    YES = "yes"
    NO = "no"
    UNCERTAIN = "uncertain"


class IdentityVerdict(ReasoningStrategyEnum):
    """Whether two entities are judged the same, different, or indeterminate."""

    SAME = "same"
    DIFFERENT = "different"
    INDETERMINATE = "indeterminate"


class ModalStatus(ReasoningStrategyEnum):
    """Modal category assigned to a claim: necessary, possible, contingent, or impossible."""

    NECESSARY = "necessary"
    POSSIBLE = "possible"
    CONTINGENT = "contingent"
    IMPOSSIBLE = "impossible"


class NecessarySufficientVerdict(ReasoningStrategyEnum):
    """Which combination of necessity and sufficiency a condition satisfies."""

    NECESSARY_ONLY = "necessary_only"
    SUFFICIENT_ONLY = "sufficient_only"
    BOTH = "both"
    NEITHER = "neither"


class PartitionVerdict(ReasoningStrategyEnum):
    """Whether a classification exhaustively and disjointly covers its items."""

    EXHAUSTIVE_DISJOINT = "exhaustive_disjoint"
    GAPS = "gaps"
    OVERLAPS = "overlaps"


class PredictMatch(ReasoningStrategyEnum):
    """Whether an observed outcome matched a theory-derived prediction."""

    YES = "yes"
    NO = "no"
    PARTIAL = "partial"


class QuantifierKind(ReasoningStrategyEnum):
    """Scope of a quantified claim: all, some, none, or most."""

    ALL = "all"
    SOME = "some"
    NONE = "none"
    MOST = "most"


class QuantifierVerdict(ReasoningStrategyEnum):
    """Whether a quantified claim holds, fails, or could not be verified."""

    HOLDS = "holds"
    FAILS = "fails"
    UNVERIFIABLE = "unverifiable"


class RegressStyle(ReasoningStrategyEnum):
    """How a justification chain terminates: foundational, circular, or infinite."""

    FOUNDATIONAL = "foundational"
    CIRCULAR = "circular"
    INFINITE = "infinite"


class StrawmanCriticism(ReasoningStrategyEnum):
    """Whether a restated argument's criticism still applies to the fair version."""

    YES = "yes"
    NO = "no"
    PARTIALLY = "partially"


class TestimonyTrust(ReasoningStrategyEnum):
    """Trust level assigned to a testimony source."""

    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    WITHHELD = "withheld"


class TransitivityConsistency(ReasoningStrategyEnum):
    """Whether a chained relation stays consistent, cycles, or breaks transitivity."""

    CONSISTENT = "consistent"
    CYCLIC = "cyclic"
    INTRANSITIVE = "intransitive"


__all__ = [
    "AbsenceEvidenceSignificance",
    "BurdenOfProofVerdict",
    "CircularityVerdict",
    "CompositionDivisionValidity",
    "ConsistencyStatus",
    "DefeasibleRuleApplies",
    "EquivocationFallacy",
    "IdentityVerdict",
    "ModalStatus",
    "NecessarySufficientVerdict",
    "PartitionVerdict",
    "PredictMatch",
    "QuantifierKind",
    "QuantifierVerdict",
    "ReasoningStrategyEnum",
    "RegressStyle",
    "StrawmanCriticism",
    "TestimonyTrust",
    "TransitivityConsistency",
]
