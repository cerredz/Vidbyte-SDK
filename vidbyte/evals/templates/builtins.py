"""Prebuilt multi-grader eval templates for common evaluation intents."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.graders import (
    AllOfGrader,
    ChoiceMatchGrader,
    ContainsAllGrader,
    ContainsGrader,
    ForbiddenContentGrader,
    JSONSchemaGrader,
    JSONSubsetGrader,
    LengthGrader,
    NumericMatchGrader,
)
from vidbyte.evals.templates.base import EvalTemplate

DEFAULT_SUPPORT_FORBIDDEN = ("internal", "confidential", "POLICY_INTERNAL_", "staff-only")


class ShortAnswerFactTemplate(EvalTemplate):
    """Template for short factual answers that should mention the expected answer."""

    name = "short_answer_fact"
    description = "Requires the expected answer to appear and keeps output concise."

    def __init__(self, *, max_chars: int = 240) -> None:
        # Stores the maximum character length for short factual answers.
        self.max_chars = self._validate_non_negative(max_chars, "max_chars")

    def build_grader(self) -> BaseGrader:
        # Builds a contains-plus-length grader bundle.
        return AllOfGrader([ContainsGrader(), LengthGrader(max_chars=self.max_chars)])

    def _validate_non_negative(self, value: int, name: str) -> int:
        # Validates a non-negative integer option.
        if value < 0:
            raise ValueError(f"{name} must be non-negative.")
        return value


class MultipleChoiceTemplate(EvalTemplate):
    """Template for single-label multiple-choice answers."""

    name = "multiple_choice"
    description = "Requires one expected choice from the allowed choice set."

    def __init__(self, *, choices: Sequence[str] = ("A", "B", "C", "D"), max_chars: int = 32) -> None:
        # Stores allowed choices and concise answer length bounds.
        if not choices:
            raise ValueError("choices must contain at least one value.")
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        self.choices = tuple(str(choice) for choice in choices)
        self.max_chars = max_chars

    def build_grader(self) -> BaseGrader:
        # Builds a choice parser plus length grader bundle.
        return AllOfGrader([ChoiceMatchGrader(self.choices), LengthGrader(max_chars=self.max_chars)])


class StructuredJsonTemplate(EvalTemplate):
    """Template for raw JSON outputs that must satisfy schema and/or subset checks."""

    name = "structured_json"
    description = "Validates JSON shape, expected subset values, and optional markdown-fence leakage."

    def __init__(self, *, schema: Mapping[str, Any] | None = None, require_subset: bool = True, forbid_markdown_fences: bool = True) -> None:
        # Stores structured JSON validation options.
        if schema is None and not require_subset:
            raise ValueError("structured_json requires schema or require_subset=True.")
        self.schema = dict(schema) if schema is not None else None
        self.require_subset = require_subset
        self.forbid_markdown_fences = forbid_markdown_fences

    def build_grader(self) -> BaseGrader:
        # Builds the configured JSON validation bundle.
        graders: list[BaseGrader] = []
        if self.schema is not None:
            graders.append(JSONSchemaGrader(self.schema))
        if self.require_subset:
            graders.append(JSONSubsetGrader())
        if self.forbid_markdown_fences:
            graders.append(ForbiddenContentGrader(["```"]))
        return AllOfGrader(graders)


class ClassificationTemplate(EvalTemplate):
    """Template for single-label classification outputs."""

    name = "classification"
    description = "Requires exactly one allowed label matching the expected value."

    def __init__(self, *, labels: Sequence[str], max_chars: int = 120) -> None:
        # Stores allowed labels and concise answer length bounds.
        if not labels:
            raise ValueError("labels must contain at least one value.")
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        self.labels = tuple(str(label) for label in labels)
        self.max_chars = max_chars

    def build_grader(self) -> BaseGrader:
        # Builds a label parser plus length grader bundle.
        return AllOfGrader([ChoiceMatchGrader(self.labels), LengthGrader(max_chars=self.max_chars)])


class NumericAnswerTemplate(EvalTemplate):
    """Template for numeric answers with configurable tolerance."""

    name = "numeric_answer"
    description = "Requires a numeric value matching expected within tolerance."

    def __init__(self, *, tolerance: float = 0.0, max_chars: int = 120) -> None:
        # Stores tolerance and concise answer length bounds.
        if tolerance < 0:
            raise ValueError("tolerance must be non-negative.")
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        self.tolerance = tolerance
        self.max_chars = max_chars

    def build_grader(self) -> BaseGrader:
        # Builds a numeric parser plus length grader bundle.
        return AllOfGrader([NumericMatchGrader(tolerance=self.tolerance), LengthGrader(max_chars=self.max_chars)])


class ConciseGroundedAnswerTemplate(EvalTemplate):
    """Template for concise answers that must include required facts and avoid forbidden facts."""

    name = "concise_grounded_answer"
    description = "Requires required terms, blocks forbidden terms, and enforces max length."

    def __init__(self, *, required_terms: Sequence[str] = (), forbidden_terms: Sequence[str] = (), max_chars: int = 800) -> None:
        # Stores grounded-answer checklist and length options.
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        self.required_terms = tuple(required_terms)
        self.forbidden_terms = tuple(forbidden_terms)
        self.max_chars = max_chars

    def build_grader(self) -> BaseGrader:
        # Builds a checklist, forbidden-content, and length grader bundle.
        graders: list[BaseGrader] = [ContainsAllGrader(self.required_terms), ForbiddenContentGrader(self.forbidden_terms), LengthGrader(max_chars=self.max_chars)]
        return AllOfGrader(graders)


class SafeCustomerSupportTemplate(EvalTemplate):
    """Template for customer support answers that should answer and avoid internal leakage."""

    name = "safe_customer_support"
    description = "Requires expected answer content, blocks leakage terms, and keeps replies bounded."

    def __init__(self, *, forbidden_terms: Sequence[str] = DEFAULT_SUPPORT_FORBIDDEN, max_chars: int = 1000) -> None:
        # Stores forbidden support terms and response length options.
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        self.forbidden_terms = tuple(forbidden_terms)
        self.max_chars = max_chars

    def build_grader(self) -> BaseGrader:
        # Builds an answer-content, leakage, and length grader bundle.
        return AllOfGrader([ContainsGrader(), ForbiddenContentGrader(self.forbidden_terms), LengthGrader(max_chars=self.max_chars)])


def short_answer_fact(*, max_chars: int = 240) -> EvalTemplate:
    # Creates the short factual answer template.
    return ShortAnswerFactTemplate(max_chars=max_chars)


def multiple_choice(*, choices: Sequence[str] = ("A", "B", "C", "D"), max_chars: int = 32) -> EvalTemplate:
    # Creates the multiple-choice answer template.
    return MultipleChoiceTemplate(choices=choices, max_chars=max_chars)


def structured_json(*, schema: Mapping[str, Any] | None = None, require_subset: bool = True, forbid_markdown_fences: bool = True) -> EvalTemplate:
    # Creates the structured JSON response template.
    return StructuredJsonTemplate(schema=schema, require_subset=require_subset, forbid_markdown_fences=forbid_markdown_fences)


def classification(*, labels: Sequence[str], max_chars: int = 120) -> EvalTemplate:
    # Creates the single-label classification template.
    return ClassificationTemplate(labels=labels, max_chars=max_chars)


def numeric_answer(*, tolerance: float = 0.0, max_chars: int = 120) -> EvalTemplate:
    # Creates the numeric answer template.
    return NumericAnswerTemplate(tolerance=tolerance, max_chars=max_chars)


def concise_grounded_answer(*, required_terms: Sequence[str] = (), forbidden_terms: Sequence[str] = (), max_chars: int = 800) -> EvalTemplate:
    # Creates the concise grounded answer template.
    return ConciseGroundedAnswerTemplate(required_terms=required_terms, forbidden_terms=forbidden_terms, max_chars=max_chars)


def safe_customer_support(*, forbidden_terms: Sequence[str] = DEFAULT_SUPPORT_FORBIDDEN, max_chars: int = 1000) -> EvalTemplate:
    # Creates the safe customer support answer template.
    return SafeCustomerSupportTemplate(forbidden_terms=forbidden_terms, max_chars=max_chars)


def register_builtin_templates(registry: Any) -> None:
    # Registers all prebuilt template factories on a registry.
    registry.register(ShortAnswerFactTemplate.name, ShortAnswerFactTemplate)
    registry.register(MultipleChoiceTemplate.name, MultipleChoiceTemplate)
    registry.register(StructuredJsonTemplate.name, StructuredJsonTemplate)
    registry.register(ClassificationTemplate.name, ClassificationTemplate)
    registry.register(NumericAnswerTemplate.name, NumericAnswerTemplate)
    registry.register(ConciseGroundedAnswerTemplate.name, ConciseGroundedAnswerTemplate)
    registry.register(SafeCustomerSupportTemplate.name, SafeCustomerSupportTemplate)

